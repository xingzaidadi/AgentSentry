"""AgentSentry 主程序：读 mini-mico 的 trace → 跑全部维度 → 门禁裁决 → 出报告。

复用 SkillSentry 的骨架思想：cases/executor/grader/gate/report。
门禁裁决（对标 SkillSentry PASS/CONDITIONAL/FAIL + 一票否决）：
- 任一「红线维度」失败 → FAIL（D3 越权 / D6 验收门禁+终态 是红线）
- 非红线维度失败 → CONDITIONAL PASS
- 全过 → PASS

维度集：
  v1 六维（执行计划 v3 决策1）：D3 越权 / D4 接力 / D5 准入 / D6 验收终态 / D7 沉淀 / D10 过程。
  v1.1 二期扩展三维（均非红线）：D1 分解派单 / D8 幻觉输出校验 / D12 可见性归属。
本程序对维度集不做硬编码枚举——`render_report`/`verdict` 通用遍历 `run_dimensions` 的结果，
新增维度自动纳入报告与裁决（红线集仅 RED_LINE 常量指定）。
"""
import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dimensions.checks import run_dimensions
from dimensions.judge import get_judge

RED_LINE = {"D3", "D6"}  # 一票否决维度：越权 / 验收门禁+终态正确性


def evaluate(trace, judge="default"):
    """跑 6 维度。默认挂 judge 层（无 key → 确定性桩，CI 可复现）。

    judge="default" → get_judge()（默认桩）；传 None → 纯规则层（P2 基线）；也可注入自定义 judge。
    """
    j = get_judge() if judge == "default" else judge
    return run_dimensions(trace, judge=j)


def verdict(results):
    red_fail = [r for r in results if r.dim in RED_LINE and not r.passed]
    other_fail = [r for r in results if r.dim not in RED_LINE and not r.passed]
    if red_fail:
        return "FAIL", red_fail
    if other_fail:
        return "CONDITIONAL PASS", other_fail
    return "PASS", []


def render_report(trace, results, vd, failed):
    lines = []
    lines.append(f"# AgentSentry 评测报告\n")
    lines.append(f"**被测任务**：{trace['task']['title']}  (`{trace['task']['id']}`, mode={trace['task']['mode']})")
    lines.append(f"**任务终态**：{trace['task']['status']}")
    avg = sum(r.score for r in results) / len(results)
    lines.append(f"**综合得分**：{avg:.2f} / 1.00")
    lines.append(f"**门禁裁决**：**{vd}**\n")
    lines.append("| 维度 | 名称 | 结果 | 分数 | 说明 |")
    lines.append("|---|---|---|---|---|")
    for r in results:
        mark = "✅" if r.passed else ("⛔" if r.dim in RED_LINE else "⚠️")
        rl = " (红线)" if r.dim in RED_LINE else ""
        lines.append(f"| {r.dim}{rl} | {r.name} | {mark} | {r.score:.2f} | {r.reason} |")
    lines.append("")
    # 证据
    for r in results:
        if r.evidence:
            lines.append(f"**{r.dim} 证据**：")
            for e in r.evidence:
                lines.append(f"- {e}")
    if vd != "PASS":
        lines.append(f"\n**未通过维度**：{', '.join(r.dim+' '+r.name for r in failed)}")
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(prog="agentsentry")
    p.add_argument("trace_file", help="mini-mico 导出的 trace JSON 文件")
    p.add_argument("--out", default=None, help="报告输出路径(.md)")
    args = p.parse_args()

    with open(args.trace_file, "r", encoding="utf-8") as f:
        trace = json.load(f)

    results = evaluate(trace)
    vd, failed = verdict(results)
    report = render_report(trace, results, vd, failed)
    print(report)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\n[报告已写入 {args.out}]")

    # 退出码：PASS=0, CONDITIONAL=1, FAIL=2（可接 CI 门禁）
    sys.exit({"PASS": 0, "CONDITIONAL PASS": 1, "FAIL": 2}[vd])


if __name__ == "__main__":
    main()
