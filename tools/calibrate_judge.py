"""LLM-as-judge 校准：把【确定性 StubJudge】当基线，量化【真 LLM judge】与它的偏离。

为什么要校准（第一性原理）：
  judge 层判的是规则测不了的主观质量，但"主观"不等于"可以乱打分"。
  上线一个 LLM judge 前，必须先证明它和可复现基线【大体一致】、并【定位分歧】——
  分歧点要么暴露 rubric 写得不够清楚，要么暴露 judge 读错了 trace，要么说明基线太宽松。
  这就是 Anthropic「先对齐 judge、再信任 judge」的做法，也是测评岗的核心手艺。

做法：
  对 calib_traces/ 下每条 trace、每个 rubric，分别用 StubJudge 和真 LLM judge 打分，
  报告：pass 是否一致、分差 |Δ|、逐条分歧明细，以及总体一致率 / 平均分差。

用法：
  # 基线 vs OpenAI 兼容 judge（本机 mify/ppio）
  export OPENAI_BASE_URL=... OPENAI_API_KEY=... AGENTSENTRY_JUDGE_LLM=1
  python tools/calibrate_judge.py
  # 指定目录 / 落盘报告
  python tools/calibrate_judge.py --traces calib_traces --out reports_calibration.md
"""
import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dimensions.judge import StubJudge, RUBRICS, get_judge  # noqa: E402

PASS_AGREE_TARGET = 0.75   # pass/fail 一致率达标线（低于此说明 judge 未对齐、别上线）


def _load_traces(folder):
    out = []
    for path in sorted(glob.glob(os.path.join(folder, "*.json"))):
        with open(path, "r", encoding="utf-8") as f:
            out.append((os.path.splitext(os.path.basename(path))[0], json.load(f)))
    return out


def calibrate(folder):
    traces = _load_traces(folder)
    if not traces:
        raise SystemExit(f"没有找到 trace：{folder}/*.json")

    stub = StubJudge()
    llm = get_judge()
    if getattr(llm, "source", None) != "llm":
        raise SystemExit(
            "未启用真 LLM judge（get_judge() 回退成了 Stub）。\n"
            "请设 AGENTSENTRY_JUDGE_LLM=1 且提供 OPENAI_BASE_URL+OPENAI_API_KEY "
            "（或 ANTHROPIC_API_KEY）后重试。")
    llm_name = type(llm).__name__

    rows, agree, total, deltas, divergences = [], 0, 0, [], []
    for name, tr in traces:
        for rk in RUBRICS:
            s = stub(rk, tr, None)
            l = llm(rk, tr, None)
            same = (s.passed == l.passed)
            d = abs(s.score - l.score)
            agree += 1 if same else 0
            total += 1
            deltas.append(d)
            rows.append((name, rk, s.score, s.passed, l.score, l.passed, same, d, l.rationale))
            if not same:
                divergences.append((name, rk, s, l))
    return {
        "llm_name": llm_name, "rows": rows,
        "agree": agree, "total": total,
        "pass_agree": agree / total if total else 0.0,
        "mean_delta": sum(deltas) / len(deltas) if deltas else 0.0,
        "divergences": divergences,
    }


def render(res):
    L = []
    L.append("# LLM-as-judge 校准报告\n")
    L.append(f"- 基线：StubJudge（确定性、可复现）")
    L.append(f"- 被校准：{res['llm_name']}（真 LLM）")
    L.append(f"- **pass/fail 一致率**：{res['pass_agree']:.0%}（{res['agree']}/{res['total']}）"
             f"｜达标线 {PASS_AGREE_TARGET:.0%} → "
             f"{'✅ 已对齐' if res['pass_agree'] >= PASS_AGREE_TARGET else '⚠️ 未对齐，先修 rubric 再上线'}")
    L.append(f"- **平均分差 |Δ|**：{res['mean_delta']:.2f}\n")
    L.append("| trace | rubric | stub分 | stub | llm分 | llm | 一致 | |Δ| | llm 理由 |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for (name, rk, ss, sp, ls, lp, same, d, rat) in res["rows"]:
        L.append(f"| {name} | {rk} | {ss:.2f} | {'P' if sp else 'F'} | "
                 f"{ls:.2f} | {'P' if lp else 'F'} | {'✅' if same else '❌'} | {d:.2f} | {rat} |")
    L.append("")
    if res["divergences"]:
        L.append("## 分歧点（需人工定夺：修 rubric / judge 读错 / 基线太宽松）")
        for (name, rk, s, l) in res["divergences"]:
            L.append(f"- **{name} · {rk}**：stub={s.score:.2f}({'P' if s.passed else 'F'}) "
                     f"「{s.rationale}」 vs llm={l.score:.2f}({'P' if l.passed else 'F'}) 「{l.rationale}」")
    else:
        L.append("## 分歧点\n无——真 judge 与确定性基线在 pass/fail 上完全一致。")
    return "\n".join(L)


def main():
    p = argparse.ArgumentParser(prog="calibrate_judge")
    p.add_argument("--traces", default="calib_traces")
    p.add_argument("--out", default=None)
    args = p.parse_args()
    res = calibrate(args.traces)
    report = render(res)
    print(report)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\n[报告已写入 {args.out}]")


if __name__ == "__main__":
    main()
