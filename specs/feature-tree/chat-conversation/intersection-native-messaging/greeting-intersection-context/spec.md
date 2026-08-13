# L3 Story：破冰交集依据 (`greeting-intersection-context`)

> 所属能力：[`intersection-native-messaging`](../spec.md)

> Journey / Scenario：[`JNY-011 / SCN-026`](../../../spec.md#scn-026)

> 设计归属：[L2 DEC-002](../design.md#dec-002)

## 1. 用户价值

作为收到陌生人打招呼的用户，
我希望一眼看到对方为什么找我，
从而能判断这次搭讪是有理由的还是骚扰。

## 2. 范围与非目标

### In Scope

- 打招呼请求携带交集引用。
- 服务端按当前发起方与接收方重解析该引用后写入依据。
- 请求箱与升级后 1v1 会话中依据的一致展示。

### Out of Scope

- 交集事实的识别与排序，由 `object-homepage-network` 负责。
- 打招呼请求箱本身的治理与升级规则，由 `contact-and-session-governance` 负责。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 交集引用只作为意图上传

- 打招呼请求可携带交集引用；该引用只表达发起方的意图，不得被直接作为依据落库。

<a id="req-002"></a>
### REQ-002 依据必须经服务端重解析后才成立

- 服务端必须按当前发起方与接收方重新解析该交集是否成立，成立才写入依据。
- 重解析不成立时不得写入依据，打招呼仍可作为普通问候继续。

<a id="req-003"></a>
### REQ-003 依据在破冰与升级后保持同一口径

- 请求箱与升级后的 1v1 会话展示的依据必须是同一条云侧内容，不得在两处出现不同表述。

<a id="req-004"></a>
### REQ-004 服务本地契约引用边界

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

## 4. 契约引用

- canonical：`quwoquan_service/services/user-service/contracts/relationship/greeting_request/fields.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/relationship/greeting_request/operations.yaml`
- 父能力公开契约：[`L2 spec`](../spec.md)

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 成立的交集成为可见破冰依据

- GIVEN 发起方与接收方之间存在成立的交集。
- WHEN 发起方从交集卡发起打招呼，接收方在请求箱查看。
- THEN 接收方看到由云侧给出的破冰依据，回复升级后该依据在 1v1 会话中保持一致。
- AND 依据内容整体来自云侧，端侧不参与拼接。

<a id="gwt-002"></a>
### GWT-002 不成立的引用被拒绝且不伪造依据

- GIVEN 发起方提交了一条当前不成立的交集引用。
- WHEN 服务端重解析该引用。
- THEN 不写入任何依据，请求箱不展示破冰依据。
- AND 打招呼本身仍可作为普通问候完成，不返回失败终态。

## 6. 依赖

- 前置要求：[`intersection-native-messaging`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-002](../design.md#dec-002)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 破冰依据剩四环境真实身份 UAT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺四环境真实身份下「交集卡发起 → 请求箱看到依据 → 升级会话保留」的 user_acceptance 留证。
  契约与实现已闭合：`GreetingRequest` 携带 `intersectionRef`（意图）与
  `intersectionSnapshot`（服务端重解析后的不可变依据），Send 按当前双方重解析、
  失效引用与解析失败均降级普通问候不伪造依据，测试
  `greeting_intersection_resolver__local_contract_test.go` 与
  `greeting_intersection_fail_open__local_contract_test.go` 绑定 `GWT-001`/`GWT-002`；
  请求箱展示云侧依据原文且无依据请求不显示
  （`greeting_inbox_journey__local_contract_test.dart`）；升级后 1v1 会话头
  保留同一依据由 `conversation-intersection-header` 的 `GWT-002` 承载。
- 完成判定：`GWT-001` 与 `GWT-002` 的结果子句（`gwt-001.t1..t2`、`gwt-002.t1..t2`）各自被真实测试 `spec_ref` 绑定，且四环境真实身份下「交集卡发起 → 请求箱看到依据 → 升级会话保留」的 user_acceptance readback 留证。
