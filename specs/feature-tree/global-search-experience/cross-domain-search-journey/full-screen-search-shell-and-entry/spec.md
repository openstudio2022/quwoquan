# L3 Scenario: full-screen-search-shell-and-entry

## 节点定位

- `L1_capability`: `global-search-experience`
- `L2_journey`: `cross-domain-search-journey`
- `L3_scenario`: `full-screen-search-shell-and-entry`

## 背景与动机

全局搜索首先是一个壳层问题，而不是一个接口问题。当前 App 内没有统一的全屏搜索首页，入口上下文和视觉结构也不一致，因此用户无法形成稳定心智。

## 目标用户

- 从首页、聊天、圈子、助手页进入搜索的普通用户。
- 需要快速切换搜索类型而不是直接盲搜的高频用户。

## 功能范围

- 统一全屏搜索首页。
- 统一首页、聊天、圈子、助手页的搜索入口行为。
- 搜索框、问小趣入口、语音按钮、指定搜索内容、最近搜索区块的壳层布局。
- 默认 scope、默认 placeholder、返回路径与上下文保留。

## Out of Scope

- 综合结果的数据编排。
- 最近搜索的同步实现细节。
- 语音 ASR 识别实现细节。

## 约束

- 全局搜索必须是唯一全屏全局浮层。
- 页面视觉必须遵循 iOS 原生 UX 规则与 design token。
- 搜索入口不得在各页自行维护第二套 path、surface、route 行为。

## 对标输入与吸收结论

- 以微信搜索首页四段式结构作为直接对标。
- 吸收顶部搜索框、第二行快捷入口、指定搜索内容、最近搜索四段结构。

## 角色分工

- `global-search-experience`: 负责壳层、入口、上下文。
- `_shared` metadata: 负责 route、surface、page context 真相源。

## 既有 Story 覆盖矩阵

| 既有实现 | 处理 |
|---|---|
| `GlobalSearchSheet` 原型 | 被新壳层吸收并替换 |
| 各页面局部搜索图标行为 | 收口到统一入口策略 |

## 数据生命周期合同

- 本 Scenario 只关心展示“最近搜索”区块，不定义其持久化细节。
- 入口页上下文只在本次打开搜索期间保留，具体持久化不由本 Scenario 冻结。

## 小趣 / 权限 / 分享边界

- 问小趣只作为快捷入口按钮出现，不作为混排结果分组。
- 本 Scenario 不新增分享能力。

## 非功能目标

- 搜索首页打开即时可见。
- 首屏布局在深色/浅色、不同断点下保持同一信息架构。

## 迁移、灰度与回滚要求

- 本 Scenario 不保留旧壳层并行路径。
- 若新壳层出现严重问题，整体回退到旧搜索实现。

## 验收重点

1. 统一入口和统一全屏壳层成立。
2. 搜索首页四段式结构清晰稳定。
3. route / surface / page context 不再散落在各页面手写。
