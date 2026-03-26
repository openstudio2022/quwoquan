# L3 Scenario: homepage-claim-request-and-review

## 节点定位

- `L1_capability`: `shared-homepage-network`
- `L2_journey`: `homepage-claim-maintain-and-offline-journey`
- `L3_scenario`: `homepage-claim-request-and-review`

## 背景与动机

认领是共享主页可信治理的关键入口。  
如果认领材料和审核规则不明确，主页会在“没人敢认领”和“谁都能认领”之间摇摆。

## 目标用户

- 经营主体、品牌方、门店授权方、主理人。
- 平台审核人员。

## 功能范围

- 认领申请入口。
- 分层材料提交。
- 审核状态与结果。

## Out of Scope

- 认领后的详细维护界面。
- 多门店批量认领。
- 合作签约与交易后台。

## 约束

- 认领采用分层验证。
- 审核通过前不得显示官方认领标识。

## 角色分工

- `shared-homepage-network`：认领申请与审核状态
- `product-ops`：材料规则与审核

## 数据生命周期合同

- 认领状态至少区分 `unclaimed / pending_claim / claimed`

## 非功能目标

- 审核 SLA `<= 3 个工作日`

## 验收重点

1. 认领申请与材料分层清晰。
2. 审核状态可追踪。
3. 审核通过后主页进入可维护状态。
