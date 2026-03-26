# L3 Scenario: xiaoqu-entry-handoff

## 节点定位

- `L1_capability`: `global-search-experience`
- `L2_journey`: `cross-domain-search-journey`
- `L3_scenario`: `xiaoqu-entry-handoff`

## 背景与动机

该 Scenario 虽然沿用历史节点名 `xiaoqu-entry-handoff`，但最新两段式搜索 UX 已经明确把它冻结为“独立网络结果页最左侧的小趣搜 tab”。阶段 B 也已确认这里必须返回真实 assistant 搜索结果，而不是只做 handoff 占位。

## 目标用户

- 在同一个搜索 query 下需要查看 assistant 摘要、引用并继续追问的用户。

## 功能范围

- 独立网络结果页中的 `小趣搜` tab。
- 基于当前搜索 query 拉取 assistant 摘要、引用与结果强度。
- 从 `小趣搜` 结果继续打开引用对象或延续 assistant 对话的承接语义。

## Out of Scope

- 助手 runtime、skill、tool、prompt 改造本身。
- assistant 结果混入联想页四段。
- 单独再维护一套 AI 搜索 query 历史模型。

## 约束

- `小趣搜` 只存在于独立网络结果页左侧 tab，不进入联想页混排。
- `小趣搜` 必须通过 assistant 的 typed contract / metadata 路径返回真实结果，不能在 runtime 做字符串语义分流。
- `小趣搜` 复用当前全局搜索 query，不额外新增一套 AI query 历史模型。

## 对标输入与吸收结论

- 借鉴微信搜索中的独立 AI / 网络结果入口心智，但统一收口为网络结果页中的 `小趣搜` tab。

## 角色分工

- `global-search-experience`: 提供网络结果页 tab 入口、query 同步与引用跳转承接。
- `assistant`: 返回摘要、引用、结果强度，并承接后续 assistant continuation。

## 既有 Story 覆盖矩阵

| 既有能力 | 处理 |
|---|---|
| assistant 内部搜索/联网能力 | 继续由 assistant 域承接 |
| 搜索页内 AI 搜索构想 | 不保留旧入口形态，收口为网络结果页中的 `小趣搜` tab |

## 数据生命周期合同

- `小趣搜` 不单独写一条 AI query 历史；它复用当前全局搜索 query。
- 若用户从 `小趣搜` 继续进入 assistant 对话，则后续上下文保存在 assistant 对话链路中。

## 小趣 / 权限 / 分享边界

- 本 Scenario 定义的是搜索到 assistant 结果 tab 的展示与 continuation，不扩展助手能力边界。
- 当前账号或登录子账号的 assistant 上下文延续既有能力，不在本 Scenario 内重定义。

## 非功能目标

- 从网络结果页切到 `小趣搜` tab 应快速稳定，不让用户产生“重新进另一个系统”的割裂感。

## 迁移、灰度与回滚要求

- 不保留“AI 搜索结果混排”的并行方案。
- 若 `小趣搜` 结果链路不稳定，可整体回退到旧搜索实现，但不回退为 AI 搜索混排。

## 验收重点

1. `小趣搜` 是独立网络结果页中的 assistant 结果 tab，而不是占位入口。
2. assistant 结果包含摘要与可跳转引用，不依赖纯 handoff 占位。
3. assistant 结果链路不依赖 runtime 字符串硬编码。
