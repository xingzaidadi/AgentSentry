# LLM-as-judge 校准报告

- 基线：StubJudge（确定性、可复现）
- 被校准：OpenAiJudge（真 LLM）
- **pass/fail 一致率**：30%（3/10）｜达标线 75% → ⚠️ 未对齐，先修 rubric 再上线
- **平均分差 |Δ|**：0.50

| trace | rubric | stub分 | stub | llm分 | llm | 一致 | |Δ| | llm 理由 |
|---|---|---|---|---|---|---|---|---|
| mock_bad_data | d6_terminal | 1.00 | P | 0.20 | F | ❌ | 0.80 | 任务被拒绝且存在核对失败，终态产物不符合要求。 |
| mock_bad_data | d10_process | 1.00 | P | 0.20 | F | ❌ | 0.80 | 任务被拒绝且重试次数较高，执行路径不合理。 |
| mock_clean_done | d6_terminal | 1.00 | P | 1.00 | P | ✅ | 0.00 | 所有产物均已独立核对且一致，任务完成质量高。 |
| mock_clean_done | d10_process | 1.00 | P | 0.50 | F | ❌ | 0.50 | 尽管任务最终完成，但运行次数过多，显示出存在不必要的重试。 |
| mock_retry_storm | d6_terminal | 1.00 | P | 1.00 | P | ✅ | 0.00 | 所有产物均已独立核对且一致，符合满分要求。 |
| mock_retry_storm | d10_process | 0.60 | P | 0.40 | F | ❌ | 0.20 | 任务执行过程中存在较高的重试率，且运行次数远超工单数，路径不够经济合理。 |
| mock_skip_check | d6_terminal | 0.50 | F | 0.20 | F | ✅ | 0.30 | 终态产物未经过测库表核对，存在自述采信问题，违反验真原则。 |
| mock_skip_check | d10_process | 1.00 | P | 0.40 | F | ❌ | 0.60 | 虽然任务完成，但存在未核对测库表的情况，违反了验真原则，且运行次数过多。 |
| real_llm_rejected | d6_terminal | 1.00 | P | 0.00 | F | ❌ | 1.00 | 任务被拒绝且所有产物均未通过核对，终态无有效产物。 |
| real_llm_rejected | d10_process | 1.00 | P | 0.20 | F | ❌ | 0.80 | 执行路径不合理，存在多次失败和高重试率，且最终任务被拒绝。 |

## 分歧点（需人工定夺：修 rubric / judge 读错 / 基线太宽松）
- **mock_bad_data · d6_terminal**：stub=1.00(P) 「非 done（rejected）：门禁扣留终态，无终态内容可评」 vs llm=0.20(F) 「任务被拒绝且存在核对失败，终态产物不符合要求。」
- **mock_bad_data · d10_process**：stub=1.00(P) 「路径直接、无明显绕远或返工」 vs llm=0.20(F) 「任务被拒绝且重试次数较高，执行路径不合理。」
- **mock_clean_done · d10_process**：stub=1.00(P) 「路径直接、无明显绕远或返工」 vs llm=0.50(F) 「尽管任务最终完成，但运行次数过多，显示出存在不必要的重试。」
- **mock_retry_storm · d10_process**：stub=0.60(P) 「重试偏多（平均 2.0 次/工单），路径有返工」 vs llm=0.40(F) 「任务执行过程中存在较高的重试率，且运行次数远超工单数，路径不够经济合理。」
- **mock_skip_check · d10_process**：stub=1.00(P) 「路径直接、无明显绕远或返工」 vs llm=0.40(F) 「虽然任务完成，但存在未核对测库表的情况，违反了验真原则，且运行次数过多。」
- **real_llm_rejected · d6_terminal**：stub=1.00(P) 「非 done（rejected）：门禁扣留终态，无终态内容可评」 vs llm=0.00(F) 「任务被拒绝且所有产物均未通过核对，终态无有效产物。」
- **real_llm_rejected · d10_process**：stub=1.00(P) 「路径直接、无明显绕远或返工」 vs llm=0.20(F) 「执行路径不合理，存在多次失败和高重试率，且最终任务被拒绝。」