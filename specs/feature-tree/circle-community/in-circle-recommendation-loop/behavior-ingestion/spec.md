# L3 Story：行为摄入 (`behavior-ingestion`)

> 所属能力：[`in-circle-recommendation-loop`](../spec.md)

> Journey / Scenario：[`JNY-004 / SCN-001`](../../../spec.md#scn-001)

> 设计归属：[L1 DEC-002](../../design.md#dec-002)

## 1. 用户价值

作为参与圈子内容的用户，
我希望让真实曝光、停留、加入和离开行为只记录一次并影响后续圈内推荐，
从而获得与自己近期行为相关且可解释的圈内内容。

## 2. 范围与非目标

### In Scope

- “行为摄入”的输入、可观察主路径、失败语义以及与父能力的交接。
- App 端圈子主页 impression/dwell 与 join/leave 行为事实追加（游客态守卫、幂等重放不重复追加）
- circle-service CircleBehaviorFact append-only 存储、weeklyActive 投影与 events.circle.behavior_facts stream。
- circle-service 以 Circle 权威状态形成发现候选，并由行为投影更新 `weeklyActiveCount` 与失效发现缓存。
- 圈子发现排序策略（`recommendation-ranking` 承载）。
- 通用 content 行为事件通道（content 域 behaviors.yaml 承载）

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。
- recommendation-service 的模型训练、发布与评分；它不复制 Circle 候选资格。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 可信且幂等的行为摄入

- 认证用户的 `impression/dwell/joinCircle/leaveCircle` 必须以可信 actor 和稳定幂等键追加为 `CircleBehaviorFact`；同键同载荷重放不得重复写入，同键不同载荷必须冲突失败。
- 游客态不得解析 Remote writer 或产生 401 噪音；行为写入失败不得破坏页面主交互，并必须进入全局异常遥测。

<a id="req-002"></a>
### REQ-002 Circle 权威候选与行为排序投影

- active/public Circle 必须进入 `CircleDiscoveryFeed` 候选，归档或不可见 Circle 必须退出候选。
- `CircleBehaviorFact` 必须投影为去重主体的七日活跃数；投影成功后必须同时失效圈子详情与发现切片缓存。

<a id="req-003"></a>
### REQ-003 服务本地契约引用边界

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

<a id="req-004"></a>
### REQ-004 行为事实可供下游模型评估消费

- `CircleBehaviorFactAppended` 必须发布到 canonical `events.circle.behavior_facts` stream，供模型评估等下游以自己的 consumer group 消费；下游不得反向修改 Circle 候选资格。

## 4. 契约引用

- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/circle_behavior_fact/operations.yaml`
- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/circle_behavior_fact/events.yaml`
- canonical：`quwoquan_service/services/circle-service/contracts/circle_management/circle/events.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 行为摄入、排序刷新与归档下线

- GIVEN 两个 active/public 圈子已进入同一用户的推荐候选，且该发现切片已缓存。
- WHEN 认证用户对其中一个圈子产生行为事实，行为投影完成后 owner 将该圈子归档。
- THEN 行为活跃度会刷新候选排序且不返回旧缓存，归档后该圈子不再被召回。
- AND 游客不写行为事实；重放、伪造 actor 或冲突幂等键不产生重复或伪成功事实。

## 6. 依赖

- 前置要求：[`in-circle-recommendation-loop`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-002](../../design.md#dec-002)
