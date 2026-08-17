"""judge 自检工具：诚实报告当前 judge 走桩还是走真 LLM，并在有 key 时做一次真调用。

用途：面试/演示时一句话说清「judge 层不是画饼」——
  - 默认（无 key / 未开启）：走 StubJudge，确定性、CI 可复现，闭环不依赖外部服务。
  - 显式 AGENTSENTRY_JUDGE_LLM=1 且有 ANTHROPIC_API_KEY：走 LLMJudge，本工具真发一次请求验证接口通。

诚实边界：本机没有 key 时，无法真正跑通 LLM 分支——本工具会明说「未验证真实调用」，
不会伪造一个看起来成功的结果。这正是 judge.py 的设计：绝不静默造分。

跑法：
  # 只看当前模式（默认桩）
  python tools/check_judge.py
  # 真跑 LLM（需自备 key）
  AGENTSENTRY_JUDGE_LLM=1 ANTHROPIC_API_KEY=sk-... python tools/check_judge.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
AGENTSENTRY = os.path.dirname(HERE)
sys.path.insert(0, AGENTSENTRY)

from dimensions.judge import get_judge, StubJudge, LLMJudge, RUBRICS  # noqa: E402

# 最小合法 trace（done + 一条经测库表核对的验真）——给 judge 一个能打分的对象
SAMPLE_TRACE = {
    "task": {"id": "chk", "readable_id": "CHK-1", "title": "judge 自检样例",
             "spec": "decompose:造单A", "status": "done", "mode": "squad"},
    "agents": [{"id": 1, "name": "exec-1", "role": "executor",
                "visibility": "public", "engine": "mock", "run_count": 1}],
    "issues": [{"id": 1, "seq": 1, "subspec": "造单A", "status": "accepted",
                "attempts": 1, "batch_group": None, "batch_index": None, "batch_total": None}],
    "runs": [{"id": 1, "agent_role": "checker", "engine": "mock", "issue_id": 1,
              "agent_id": 1, "parent_run_id": None, "status": "done", "result": "",
              "events": [{"type": "verify", "payload": {
                  "matched": True, "verified_against": "test_records"}}],
              "tokens": {"input": 10, "output": 10, "tool_calls": 1}}],
    "test_records": [{"issue_id": 1, "record_key": "K1",
                      "record": {"entity_id": "E1", "status": "OK"}, "written_by": "executor"}],
    "final_state": {"merged": "accepted:K1"},
}


class _RuleStub:
    """_combine 用不到 judge 自检；给个占位 rule_result 即可。"""
    dim, name, passed, score, reason, evidence = "D6", "验收门禁+终态", True, 1.0, "", []


def main():
    want_llm = os.environ.get("AGENTSENTRY_JUDGE_LLM") == "1"
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    judge = get_judge()
    mode = judge.source

    print("=== AgentSentry · judge 自检 ===")
    print(f"AGENTSENTRY_JUDGE_LLM = {os.environ.get('AGENTSENTRY_JUDGE_LLM') or '(未设)'}")
    print(f"ANTHROPIC_API_KEY     = {'已设置' if has_key else '(未设)'}")
    print(f"get_judge() 实际返回   = {type(judge).__name__} (source={mode})")
    print(f"可用 rubric           = {sorted(RUBRICS.keys())}")
    print("-" * 48)

    if mode == "stub":
        # 桩一定能跑，且确定性——真实验证一次打分
        r = judge("d6_terminal", SAMPLE_TRACE, _RuleStub())
        print("走 StubJudge（确定性桩，默认）：")
        print(f"  d6_terminal → score={r.score} pass={r.passed}  {r.rationale}")
        r2 = judge("d10_process", SAMPLE_TRACE, _RuleStub())
        print(f"  d10_process → score={r2.score} pass={r2.passed}  {r2.rationale}")
        if want_llm and not has_key:
            print("\n⚠️ 你显式要求了 LLM judge，但未提供 ANTHROPIC_API_KEY → 已安全回落到桩。")
        print("\n结论：judge 层就绪、可复现；LLM 分支代码已实现但本次未真实调用"
              "（需自备 key，见下）。诚实起见——本机无 key，不代跑不伪造。")
        # 静态确认 LLM 分支可实例化（不发请求）
        try:
            LLMJudge(model="claude-sonnet-5")
            print("       LLMJudge 可正常实例化（接口存在），真调用留给带 key 的环境。")
        except Exception as e:  # noqa
            print(f"       LLMJudge 实例化异常：{e}")
        sys.exit(0)

    # mode == "llm"：真发一次请求
    print("走 LLMJudge（真实调用）：")
    try:
        r = judge("d6_terminal", SAMPLE_TRACE, _RuleStub())
        print(f"  d6_terminal → score={r.score} pass={r.passed}  {r.rationale}")
        print("\n✅ 真实 LLM judge 调用成功，接口打通。")
        sys.exit(0)
    except Exception as e:  # noqa
        print(f"\n❌ LLM judge 调用失败：{type(e).__name__}: {e}")
        print("（未伪造结果。检查 key / 网络 / anthropic SDK 安装。）")
        sys.exit(3)


if __name__ == "__main__":
    main()
