# L3 Scenario: homepage-overview-and-module-shell

## 节点定位

- `L1_capability`: `shared-homepage-network`
- `L2_journey`: `homepage-review-and-content-journey`
- `L3_scenario`: `homepage-overview-and-module-shell`

## 背景与动机

主页首屏必须先回答“这是什么、值不值得继续看、我接下来能做什么”。  
如果主页只是把模块堆在一起，用户无法快速建立主页心智。

## 目标用户

- 初次进入主页的浏览用户。
- 需要快速判断是否继续深入的决策型用户。

## 功能范围

- 主页首屏总览。
- 模块化骨架与独立降级。
- 关键操作：关注、发布、写口碑、提问、认领入口等。

## Out of Scope

- 具体的评分明细读取。
- 内容/问答聚合细节。
- 认领审核。

## 约束

- 首屏必须优先显示名称、类型、关键摘要和主操作。
- 单模块失败不得导致整页不可用。

## 角色分工

- `shared-homepage-network`：总览与模块骨架

## 数据生命周期合同

- 首屏只消费已发布主页及其摘要字段。

## 非功能目标

- 首屏骨架 `p95 < 300ms`
- 关键摘要可见时间 `p95 < 1.2s`

## 验收重点

1. 主页首屏可理解。
2. 模块独立降级成立。
3. 主操作位置清晰稳定。
