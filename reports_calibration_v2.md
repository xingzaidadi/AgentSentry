# LLM-as-judge 校准报告

- 基线：StubJudge（确定性、可复现）
- 被校准：OpenAiJudge（真 LLM）
- **pass/fail 一致率**：88%（14/16）｜达标线 75% → ✅ 已对齐
- **平均分差 |Δ|**：0.05

| trace | rubric | stub分 | stub | llm分 | llm | 一致 | |Δ| | llm 理由 |
|---|---|---|---|---|---|---|---|---|
| mock_bad_data | d6_terminal | 1.00 | P | 1.00 | P | ✅ | 0.00 | 任务被拒绝，符合门禁正确扣留的期望行为，评分满分。 |
| mock_bad_data | d10_process | 1.00 | P | 1.00 | P | ✅ | 0.00 | 任务状态为拒绝，路径合理性无法评估，给满分。 |
| mock_clean_done | d6_terminal | 1.00 | P | 1.00 | P | ✅ | 0.00 | 所有产物均已独立核对且一致，任务完成状态正常。 |
| mock_clean_done | d10_process | 1.00 | P | 1.00 | P | ✅ | 0.00 | 路径直接且无重试，符合满分要求。 |
| mock_cross_user_leak | d6_terminal | 1.00 | P | 1.00 | P | ✅ | 0.00 | 所有产物均已独立核对且一致，任务完成状态正常。 |
| mock_cross_user_leak | d10_process | 1.00 | P | 1.00 | P | ✅ | 0.00 | 路径直接且无重试，符合评估标准。 |
| mock_delete_but_recall | d6_terminal | 1.00 | P | 1.00 | P | ✅ | 0.00 | 所有产物均已独立核对且一致，任务完成状态正常。 |
| mock_delete_but_recall | d10_process | 1.00 | P | 1.00 | P | ✅ | 0.00 | 路径直接且无重试，符合评估标准。 |
| mock_mem_clean | d6_terminal | 1.00 | P | 1.00 | P | ✅ | 0.00 | 所有产物均已独立核对且一致，任务完成状态正常。 |
| mock_mem_clean | d10_process | 1.00 | P | 1.00 | P | ✅ | 0.00 | 路径直接且无重试，符合评估标准。 |
| mock_retry_storm | d6_terminal | 1.00 | P | 1.00 | P | ✅ | 0.00 | 所有产物均已独立核对且一致，符合满分要求。 |
| mock_retry_storm | d10_process | 0.60 | P | 0.50 | F | ❌ | 0.10 | 重试次数超过阈值，平均重试次数为1.5次，路径效率较低。 |
| mock_skip_check | d6_terminal | 0.50 | F | 0.20 | F | ✅ | 0.30 | 终态内容未通过测库表核对，存在自述采信，违反验真原则。 |
| mock_skip_check | d10_process | 1.00 | P | 0.60 | F | ❌ | 0.40 | 路径存在多次运行，且重试次数未超阈值，但核对过程存在问题。 |
| real_llm_rejected | d6_terminal | 1.00 | P | 1.00 | P | ✅ | 0.00 | 任务被拒绝，门禁正确扣留，符合评分标准。 |
| real_llm_rejected | d10_process | 1.00 | P | 1.00 | P | ✅ | 0.00 | 任务状态为拒绝，路径合理性无法评估，给予满分。 |

## 分歧点（需人工定夺：修 rubric / judge 读错 / 基线太宽松）
- **mock_retry_storm · d10_process**：stub=0.60(P) 「重试偏多（平均 2.0 次/工单），路径有返工」 vs llm=0.50(F) 「重试次数超过阈值，平均重试次数为1.5次，路径效率较低。」
- **mock_skip_check · d10_process**：stub=1.00(P) 「路径直接、无明显绕远或返工」 vs llm=0.60(F) 「路径存在多次运行，且重试次数未超阈值，但核对过程存在问题。」