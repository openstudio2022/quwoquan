# 阶段证据：mustIncludeFact 契约修复经门 A 全绿

- 提交：`3f5eae86a 修复不可满足的 mustIncludeFact 契约`
- 门禁：`bash quwoquan_data/scripts/verify/verify_quwoquan_data.sh`
- 结果：`[verify-quwoquan-data] PASSED`，`91 passed in 11.24s`，`EXIT=0`
- 日志：`/tmp/verify_data_gate_A2.log`

## 根因（P5 八篇文章 produce_review 全挂）

`_auto_content_plan`（`quwoquan_data/scripts/task/run.py`）给每篇 article brief 硬塞了两条
**写作策略串**进 `mustIncludeFacts`：

1. `"<目标> 文字底稿来自单一来源单元 <source_id>；标题取自底稿，正文按整篇底稿轻改、禁跨底稿拼接"`
2. `"若使用配图，必须来自同一底稿的已授权源图（一源一作品）"`

而 review 的 `evidenceQuality / factTraceability` 门要求每条 `mustIncludeFact` 出现在正文且
可被来源追溯。agent 不可能把"我必须用同源图"写进游记正文 → 形成**不可满足契约** → 八篇全败。

## 修复

- `mustIncludeFacts` 改为空清单（单一底稿 article 的"事实"就是底稿本身，由 `baseDraftFidelity`
  门保真，无独立事实清单）。
- 两条策略本属生产约束而非可叙述事实，已由结构门强制：
  - `baseSourceRef` 单源 + `verify single-contract-source`
  - `route_assets` 同源选图 + `source_quality` RC4 红线
  - `baseDraftFidelity` 门
  - prompt "底稿编辑硬合同" 段向 agent 明确传达
- 新增 `local_contract` 契约测试 `test_auto_content_plan_article_brief_has_no_policy_as_mustincludefact`，
  断言 article brief 的 `mustIncludeFacts` 不含策略标记串；已接入 `verify_quwoquan_data.sh`（L108）。

## 注意（与 fidelity 质量缺口区分）

本修复仅解除**契约不可满足**导致的硬挂。P5 此前观测到 6/8 文章 `baseDraftFidelity`
18-49%（阈值 55%）属**模型改写过度的质量缺口**，与本契约 bug 独立，将在 P5 重跑后据实评估。
