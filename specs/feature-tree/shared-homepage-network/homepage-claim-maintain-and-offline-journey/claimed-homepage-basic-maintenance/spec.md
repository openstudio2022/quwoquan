# L3 Scenario: claimed-homepage-basic-maintenance

## 节点定位

- `L1_capability`: `shared-homepage-network`
- `L2_journey`: `homepage-claim-maintain-and-offline-journey`
- `L3_scenario`: `claimed-homepage-basic-maintenance`

## 背景与动机

认领通过后，如果没有明确的维护边界，认领方会要么无事可做，要么越权改动用户内容。  
因此必须冻结“已认领主页可以维护什么，不能维护什么”。

## 目标用户

- 已通过认领审核的经营主体或维护者。

## 功能范围

- 基础信息维护。
- 封面与图库维护。
- 营业/开放状态与官方说明维护。

## Out of Scope

- 用户口碑管理。
- 历史内容删改。
- 复杂运营后台。

## 约束

- 认领方不能直接删改真实用户口碑和历史用户内容。
- 维护操作必须有清晰可审计边界。

## 角色分工

- `shared-homepage-network`：已认领主页可维护字段

## 数据生命周期合同

- 维护的是主页主档字段，不是内容事实。

## 非功能目标

- 维护提交可审计、可回看

## 验收重点

1. 已认领主页可维护基础信息。
2. 维护边界不越权到用户口碑与历史内容。
3. 状态与官方说明可更新。
