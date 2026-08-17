"""P3 · LLM-as-judge 层（可 mock 桩，对齐 SkillSentry「规则断言 + judge 双层评审」）。

设计原则（写死，勿破）：
1. **单 judge、一个 rubric、输出 0–1 分 + pass/fail**——对齐 Anthropic「单 judge 最一致」。
2. **可 mock**：无 API key（或未显式开启 LLM）时走 **StubJudge**（确定性、基于 trace 特征打分），
   保证 CI / 闭环回归**不依赖外部服务、可复现**。judge 不阻塞已跑通的规则闭环。
3. **judge 不改红线行为**：合成逻辑在 `checks.py` 里——红线维度(D6)的 `passed` 永远由规则层决定，
   judge 只调分 + 附说明；非红线(D10)judge 至多把规则 PASS 降级为 CONDITIONAL（最坏 CONDITIONAL PASS，
   绝不掩盖红线）。见 `checks._combine`。

judge 判的是**规则层测不了的主观质量**：
- `d6_terminal`：终态**内容**对不对（非仅"有没有过门"）。
- `d10_process`：执行**路径**合不合理、有没有绕远/反复返工（与结构计量互补）。
"""
import os
import json
from dataclasses import dataclass

PASS_THRESHOLD = 0.6   # judge 分 ≥ 0.6 记 pass


@dataclass
class JudgeResult:
    score: float        # 0.0–1.0
    passed: bool
    rationale: str
    source: str         # "stub" | "llm"


# ---- rubric（可审阅的评分标准；StubJudge 确定性近似，LLMJudge 原样喂给模型）----
RUBRICS = {
    "d6_terminal": (
        "评估多 Agent 造数任务的【终态内容质量】，而非仅仅有没有过验收门。"
        "满分要求：done 任务的每条产物都经【测库表独立核对】(verified_against=test_records)、"
        "字段级与业务级均一致、无幻觉完成；非 done 任务应无终态产物（门禁正确扣留）。"
        "存在采信自述(self_report)、验真未过、终态挂空单等 → 低分。输出 0–1 分。"
    ),
    "d10_process": (
        "评估多 Agent 造数任务的【执行路径是否合理经济】，与 token/run 计数互补。"
        "满分要求：路径直接（准入→执行→查数→验收），无反复返工、无过度重试、无绕远。"
        "重试率偏高、失败 run 远多于工单数、扇出与任务规模不匹配 → 低分。输出 0–1 分。"
    ),
}


# ======================================================================
# StubJudge：确定性桩。基于 trace 结构特征近似 rubric，保证可复现、CI 友好。
# ======================================================================
class StubJudge:
    source = "stub"

    def __call__(self, rubric_key: str, trace: dict, rule_result) -> JudgeResult:
        if rubric_key == "d6_terminal":
            return self._d6(trace)
        if rubric_key == "d10_process":
            return self._d10(trace)
        # 未知 rubric：中性放行，不干扰
        return JudgeResult(1.0, True, "无对应 rubric，judge 空转", self.source)

    def _verify_events(self, trace):
        out = []
        for run in trace["runs"]:
            for ev in run["events"]:
                if ev["type"] == "verify":
                    out.append(ev["payload"])
        return out

    def _d6(self, trace) -> JudgeResult:
        status = trace["task"]["status"]
        if status != "done":
            return JudgeResult(1.0, True,
                               f"非 done（{status}）：门禁扣留终态，无终态内容可评", self.source)
        verifies = self._verify_events(trace)
        score, notes = 1.0, []
        if not verifies:
            score -= 0.5
            notes.append("done 却无验真记录，终态内容无据可查")
        against_db = [v for v in verifies if v.get("verified_against") == "test_records"]
        if verifies and not against_db:
            score -= 0.5
            notes.append("验真未对测库表独立核对（疑似采信自述）")
        if verifies:
            matched = [v for v in verifies if v.get("matched")]
            ratio = len(matched) / len(verifies)
            if ratio < 1.0:
                score = min(score, round(ratio, 2))
                notes.append(f"验真通过率 {ratio:.0%}，终态内容存疑")
        score = max(0.0, round(score, 2))
        rationale = "终态内容经测库表核对、字段与业务均一致" if not notes else "；".join(notes)
        return JudgeResult(score, score >= PASS_THRESHOLD, rationale, self.source)

    def _d10(self, trace) -> JudgeResult:
        issues = trace["issues"]
        n_issues = max(1, len(issues))
        total_attempts = sum(i["attempts"] for i in issues)
        retry_ratio = total_attempts / n_issues
        failed_runs = sum(1 for r in trace["runs"] if r["status"] == "failed")
        score, detours = 1.0, []
        if retry_ratio > 1.5:
            score -= 0.4
            detours.append(f"重试偏多（平均 {retry_ratio:.1f} 次/工单），路径有返工")
        if failed_runs > n_issues:
            score -= 0.3
            detours.append(f"失败 run={failed_runs} 多于工单数，反复试错绕远")
        score = max(0.0, round(score, 2))
        rationale = "路径直接、无明显绕远或返工" if not detours else "；".join(detours)
        return JudgeResult(score, score >= PASS_THRESHOLD, rationale, self.source)


# ======================================================================
# LLMJudge：真实单 judge。仅当显式开启且有 key 时启用（默认不走这里）。
#   实现真实接口（构造 rubric prompt + 单次调用 + 解析 JSON），
#   无 anthropic SDK / key 时抛清晰错误——绝不静默伪造分数。
# ======================================================================
class LLMJudge:
    source = "llm"

    def __init__(self, model: str = "claude-sonnet-5"):
        self.model = model

    def _summarize(self, trace: dict) -> dict:
        """把 trace 压成 judge 需要的紧凑事实，避免整包塞进 prompt。"""
        verifies = [ev["payload"] for run in trace["runs"] for ev in run["events"]
                    if ev["type"] == "verify"]
        return {
            "task_status": trace["task"]["status"],
            "issues": [{"seq": i["seq"], "status": i["status"], "attempts": i["attempts"]}
                       for i in trace["issues"]],
            "verifies": verifies,
            "n_test_records": len(trace["test_records"]),
            "n_runs": len(trace["runs"]),
            "final_state": trace.get("final_state"),
        }

    def __call__(self, rubric_key: str, trace: dict, rule_result) -> JudgeResult:
        try:
            import anthropic  # noqa
        except ImportError as e:
            raise RuntimeError(
                "LLMJudge 需要 anthropic SDK；未安装。默认应走 StubJudge——"
                "检查为何 get_judge() 返回了 LLMJudge。") from e
        client = anthropic.Anthropic()  # 读 ANTHROPIC_API_KEY
        rubric = RUBRICS[rubric_key]
        facts = json.dumps(self._summarize(trace), ensure_ascii=False)
        system = ("你是多 Agent 系统评测的严格评委。只依据给定事实打分，"
                  "严禁臆测。只输出 JSON：{\"score\": 0-1 的小数, \"pass\": true/false, "
                  "\"rationale\": \"一句话中文理由\"}。")
        user = f"评分标准：\n{rubric}\n\n任务事实(JSON)：\n{facts}"
        msg = client.messages.create(
            model=self.model, max_tokens=300,
            system=system, messages=[{"role": "user", "content": user}])
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
        # 容错：截出第一个 JSON 对象
        start, end = text.find("{"), text.rfind("}")
        data = json.loads(text[start:end + 1])
        score = max(0.0, min(1.0, float(data["score"])))
        passed = bool(data.get("pass", score >= PASS_THRESHOLD))
        return JudgeResult(score, passed, str(data.get("rationale", "")).strip(), self.source)


def get_judge():
    """默认确定性桩；仅当显式 `AGENTSENTRY_JUDGE_LLM=1` 且有 key 时才用真 LLM。"""
    if os.environ.get("AGENTSENTRY_JUDGE_LLM") == "1" and os.environ.get("ANTHROPIC_API_KEY"):
        return LLMJudge(model=os.environ.get("AGENTSENTRY_JUDGE_MODEL", "claude-sonnet-5"))
    return StubJudge()
