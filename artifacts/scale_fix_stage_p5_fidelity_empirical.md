# Phase C 实证：P5 fidelity 修复经真实 composer-2.5 端到端验证（7/8 PASS）

## 执行

清理陈旧 brief（mustIncludeFacts=[] + 重 compose base-aware wordCount）后，
`task run --resume --managed --agent-provider cursor_sdk --model composer-2.5 --until produce_review`
（bound 840s，实际 ~440s 完成，未超时）重 author→annotate→review。

- produce_author：agent 重写待创作 5 篇（generator=agent）
- produce_annotate：7 link 标注
- produce_review：media_check 5/5 PASS；review approved=4 failed=1（都江堰_base_2 有界重试耗尽弃稿，allowPartialContent）；materialize 4 包

## baseDraftFidelity 硬证据（base_draft_similarity 直算，trigram 重叠）

| 文章 | fidelity | draftlen | baselen |
|---|---|---|---|
| 彭水.成都.**都江堰**.乐山.赤水.遵义（多目的地路书） | **90.8%** | 7088 | 6331 |
| 此生必驾318～套马汉子（川藏自驾） | 96.7% | 3902 | 6320 |
| 自驾去乐山，深度游峨眉山全攻略 | 96.4% | 4118 | 6321 |
| 拿捏峨眉山，通宵夜爬15小时 | 75.6% | 1651 | 2181 |
| 非常特种兵四地5日游 | 70.7% | 3982 | 6038 |
| 跋山涉水去见你，心之所向九寨沟 | 68.6% | 3241 | 6188 |
| 天上瑶池 人间九寨 | 60.2% | 1981 | 4676 |

**全部 ≥55%**（gate 下限）。都江堰多目的地路书 **18.6% → 90.8%**，证明三组根因修复
（base-aware wordCount + 去 baseDraftText 截断 + 清 prompt 单实体裁剪诱导 + 清策略串 mustIncludeFact）
经真实 composer-2.5 端到端生效，无一 fidelity 失败、无一 mustIncludeFact 失败。

## review 结论：7 PASS / 1 FAIL（firstPassRate = 0.875）

唯一 FAIL：`此生必驾318～套马汉子`（`entityCoverage: entity '都江堰' not mentioned in article`）。
该篇 fidelity 96.7%（高度忠实底稿），但其底稿是 318/川藏自驾游记、正文不含「都江堰」，
却被 content_plan 分配到 都江堰 实体——**entity-coverage 硬门正确拦截了「源-实体错配」**，
属 content_plan 源到实体分配质量问题，**非 fidelity/mustIncludeFact 修复的回归**。

## 结论

- fidelity + mustIncludeFact 根因修复：**真实 agent 端到端 PASS（7/8，全篇 ≥55%）**。
- firstPassRate 0.875 < 0.9 目标：差距来自 1 篇 entityCoverage 源-实体错配（content_plan 分配问题），
  非本轮修复缺陷；修复方向为 content_plan 不把不覆盖目标实体的底稿分配给该实体（后续项）。
