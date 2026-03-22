# L3 Scenario: xiaoqu-entry-handoff

## 节点定位

- `L1_capability`: `global-search-experience`
- `L2_journey`: `cross-domain-search-journey`
- `L3_scenario`: `xiaoqu-entry-handoff`

## 背景与动机

搜索首页需要保留“问小趣”入口，但产品已经明确去掉独立 AI 搜索 query。PRD 必须冻结这一点：问小趣是快捷 handoff，不是综合搜索结果的一部分。

## 目标用户

- 在站内搜索之外需要继续提问、联网或进入助手对话的用户。

## 功能范围

- 搜索首页中的“问小趣”入口。
- 从搜索首页向 assistant 会话的 query handoff。
- handoff 后的上下文继承与 assistant 对话承接语义。

## Out of Scope

- 助手 runtime、skill、tool、prompt 改造本身。
- AI 结果混排。
- 问小趣 query 的最近搜索持久化。

## 约束

- 问小趣只作为快捷入口，不进入综合结果混排。
- 问小趣 query 不进入最近搜索。
- handoff 必须通过 assistant 的 typed contract / metadata 路径承接，不能在 runtime 做字符串语义分流。

## 对标输入与吸收结论

- 借鉴微信搜索中的“问一问/问消息”类快捷入口心智，但统一收口为“问小趣”。

## 角色分工

- `global-search-experience`: 提供入口与 handoff 触发。
- `assistant`: 承接 query、保存会话与后续回答。

## 既有 Story 覆盖矩阵

| 既有能力 | 处理 |
|---|---|
| assistant 内部搜索/联网能力 | 继续由 assistant 域承接 |
| 搜索页内 AI 搜索构想 | 不保留，收口为问小趣入口 |

## 数据生命周期合同

- 问小趣 query 不写入最近搜索。
- 问小趣 query 与上下文保存在 assistant 对话链路中。

## 小趣 / 权限 / 分享边界

- 本 Scenario 只定义搜索到助手的 handoff，不扩展助手能力边界。
- 当前账号或登录子账号的 assistant 上下文延续既有能力，不在本 Scenario 内重定义。

## 非功能目标

- 从搜索页进入问小趣的 handoff 应快速稳定，不让用户产生“重新进另一个系统”的割裂感。

## 迁移、灰度与回滚要求

- 不保留“AI 搜索结果混排”的并行方案。
- 若问小趣 handoff 不稳定，可整体回退到旧搜索实现，但不回退为 AI 搜索混排。

## 验收重点

1. 问小趣是入口，不是结果域。
2. query 生命周期进入 assistant 对话，不进入搜索历史。
3. assistant handoff 不依赖 runtime 字符串硬编码。
