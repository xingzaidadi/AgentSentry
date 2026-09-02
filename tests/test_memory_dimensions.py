"""M 系列（记忆/长期存活层）维度回归：静态 fixture → AgentSentry 判决 → 断言裁决。

跑法（零依赖直跑或 pytest 收集，与 test_closed_loop 同风格）：
  python tests/test_memory_dimensions.py
  pytest tests/test_memory_dimensions.py

为什么保留静态 fixture（P0-1 已落地记忆层后）：mini-mico 现在能真跑出 memory_ops
（端到端真跑见 tests/test_memory_e2e.py）。这份用静态 fixture 的测试保留作【纯评测器单测】
——不依赖 mini-mico、离线可复现，专测 M1/M2 判定逻辑本身。靶子由
calib_traces/_gen_memory_fixtures.py 以全绿 trace 为底【加性】叠加 memory_ops 构造。

覆盖：
  mock_mem_clean            → PASS            （同 scope 读写、无删后召回）
  mock_cross_user_leak      → FAIL (M1 红线)  （U_B 召回 U_A 私有记忆）
  mock_delete_but_recall    → FAIL (M2 红线)  （删除后仍可召回）
并断言：两个负例不误伤对方维度 + 现有 D 系列红线(D3/D6)不被记忆靶子误触发。
"""
import os
import sys
import json

HERE = os.path.dirname(os.path.abspath(__file__))
AGENTSENTRY = os.path.dirname(HERE)
FIXTURES = os.path.join(AGENTSENTRY, "calib_traces")
sys.path.insert(0, AGENTSENTRY)

from run_eval import evaluate, verdict  # noqa: E402

EXIT_CODE = {"PASS": 0, "CONDITIONAL PASS": 1, "FAIL": 2}


def _eval_fixture(name):
    with open(os.path.join(FIXTURES, name), "r", encoding="utf-8") as f:
        trace = json.load(f)
    results = evaluate(trace)
    vd, _ = verdict(results)
    return vd, {r.dim: r for r in results}


def check(label, fixture, expect_verdict, assertions):
    vd, res = _eval_fixture(fixture)
    for msg, cond in assertions(res):
        assert cond, f"[{label}] {msg}"
    assert vd == expect_verdict, f"[{label}] 期望裁决 {expect_verdict}，实际 {vd}"
    print(f"[{label:<20}] 裁决={vd:<16}(exit {EXIT_CODE[vd]})  "
          f"M1={'✅' if res['M1'].passed else '⛔'} M2={'✅' if res['M2'].passed else '⛔'}  ✅")


def main():
    # 全绿：M1/M2 均通过 → PASS
    check("mem_clean", "mock_mem_clean.json", "PASS", lambda r: [
        ("M1 应通过", r["M1"].passed),
        ("M2 应通过", r["M2"].passed),
        ("D 系列红线不应被误触发", r["D3"].passed and r["D6"].passed),
    ])

    # 跨用户泄露：仅 M1 红线失败，M2 不误伤 → FAIL
    check("cross_user_leak", "mock_cross_user_leak.json", "FAIL", lambda r: [
        ("M1(红线) 应检出泄露", not r["M1"].passed),
        ("M2 不应被误伤（本例无删除）", r["M2"].passed),
        ("D 系列红线不应被误触发", r["D3"].passed and r["D6"].passed),
    ])

    # 删除后仍召回：仅 M2 红线失败，M1 不误伤 → FAIL
    check("delete_but_recall", "mock_delete_but_recall.json", "FAIL", lambda r: [
        ("M2(红线) 应检出遗忘失败", not r["M2"].passed),
        ("M1 不应被误伤（本例无跨 scope）", r["M1"].passed),
        ("D 系列红线不应被误触发", r["D3"].passed and r["D6"].passed),
    ])

    print("\nM 系列记忆维度回归全部通过 ✅  —— 跨主体隔离(M1)、删除遗忘(M2)两条红线真能判出，"
          "负例互不误伤，且不误触发 D 系列红线。")


def test_memory_dimensions():
    """pytest 收集入口。"""
    main()


if __name__ == "__main__":
    main()
