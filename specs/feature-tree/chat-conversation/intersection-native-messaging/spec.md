# L2 Business Capability：交集原生消息 (`intersection-native-messaging`)

> 所属领域：[`chat-conversation`](../spec.md)
>
> 设计归属：`本层 design.md`

## 1. 能力目标

让会话成为交集转化为行动的承接主干：用户知道「为什么是这个人」，能在会话里就近完成下一步行动，并能就会话里被引用的对象向小趣提问。消息域因此区别于通讯录式的消息应用，而实现这一点不需要消息域知道任何垂类。

## 2. 范围与非目标

### In Scope

- 打招呼携带交集引用，以及升级为正式 1v1 后破冰依据的可追溯性。
- 联系首页与 1v1 会话头部的真实交集展示。
- 对象分享进会话后的可行动 card 与其行动分流。
- 会话内 @小趣 的触发、上下文注入与引用边界。

### Out of Scope

- 交集的识别、排序与句子生成，由 `object-homepage-network` 的交集统一体验负责；本能力只消费其云侧结果。
- 消息时间线的可靠性与性能，由 [`message-reliability-foundation`](../message-reliability-foundation/spec.md) 负责。
- Gathering 的生命周期与名单治理，由 `circle-community` 的 `gathering-coordination` 负责。
- 消息首页的交集展示：消息首页心智是未读会话，本能力明确不在其上叠加交集。

## 3. Journey / Scenario 贡献

- [`JNY-011 / SCN-026`](../../spec.md#scn-026)
  - 本能力接收：来自对象页交集卡的破冰意图与交集引用。
  - 本能力处理：把交集引用带入打招呼请求，并在升级后的会话中保留破冰依据。
  - 本能力输出：一条带有可追溯依据的正式 1v1 会话。
  - 失败时终态：引用失效时不展示依据也不伪造依据，破冰仍可作为普通打招呼继续。
- [`JNY-007 / SCN-015`](../../spec.md#scn-015)
  - 本能力接收：群会话中的 @小趣 提及与会话内被引用对象。
  - 本能力处理：把最近消息窗口与被引用对象的事实作为上下文交给助手域。
  - 本能力输出：回群的助手回复及其可打开的引用边界。
  - 失败时终态：助手不可用时给出结构化不可用，不产生无依据的回复。
- [`JNY-011 / SCN-029`](../../spec.md#scn-029)
  - 本能力接收：分享进会话的对象引用及其云侧行动提示。
  - 本能力处理：按行动键、路由类别与目标可达性渲染可行动 card。
  - 本能力输出：可直接执行的行动，或明确不可执行的规划口径。
  - 失败时终态：目标不可达时展示为不可执行，不进入无承接页的死路。

## 4. Story

- [`greeting-intersection-context`](./greeting-intersection-context/spec.md)：打招呼带着「为什么是你」而不是空白问候。
- [`contact-home-intersection-facts`](./contact-home-intersection-facts/spec.md)：联系首页展示真实交集而不是资料拼接。
- [`conversation-intersection-header`](./conversation-intersection-header/spec.md)：1v1 会话头部保留可追溯的交集摘要。
- [`actionable-object-card`](./actionable-object-card/spec.md)：分享进会话的对象是可行动的而不是一段链接文本。
- [`assistant-mention-in-conversation`](./assistant-mention-in-conversation/spec.md)：会话内 @小趣 基于会话上下文作答。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 交集句只来自云侧，端不拼句

- 消息域展示的交集句必须整体来自云侧登记的展示文本与片段；端侧不得拼接、翻译或改写交集句。
- 片段拼接结果必须与整句一致，二者不一致时不得展示。

<a id="req-002"></a>
### REQ-002 端侧垂类无关

- 行动分流必须只依据云侧登记的行动键、路由类别与目标可达性；端侧不得出现按垂类或按具体交集类型的分支。
- 新增垂类不得要求改动本能力的任何端侧代码路径。

<a id="req-003"></a>
### REQ-003 交集只出现在主体明确的位置

- 交集只在联系首页与 1v1 会话头部展示；群会话头部不展示交集，消息首页不叠加交集行。
- 展示必须给出具体交集点，最多两个；不得以聚合计数表述代替具体内容。

<a id="req-004"></a>
### REQ-004 依据必须由服务端按当前发起方重解析

- 端侧传入的交集引用只作为意图；服务端必须按当前发起方与接收方重新解析该引用成立后才写入依据。
- 重解析不成立时不得写入依据，也不得以端侧传入内容直接落库。

<a id="req-005"></a>
### REQ-005 不可承接的行动必须诚实

- 目标不可达的行动必须展示为不可执行的规划口径；不得渲染为可点击入口，也不得点击后进入空白页。

<a id="req-006"></a>
### REQ-006 服务本地契约引用边界

- 跨边界字段、operation、事件与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

## 6. 契约与依赖

- 上游能力：`object-homepage-network` 的交集统一体验提供交集事实与行动提示；`assistant-run-learning` 提供助手回复。
- 下游能力：本目录直接 Story 及其公开结果。
- 读取事实：交集理由与行动提示投影、被引用对象的标签与可达性。
- 写入事实：打招呼请求上的交集依据、会话内的助手提及事件。
- operation / event / surface：`quwoquan_service/services/recommendation-service/contracts/recommendation/recommendation_feature_profile_view/projections/intersection_action_hint.yaml`、`quwoquan_service/services/user-service/contracts/relationship/greeting_request/operations.yaml`、`quwoquan_service/services/chat-service/contracts/chat/conversation/operations.yaml`
- 一致性要求：依据以服务端重解析结果为准；端侧展示不得领先于服务端事实。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 破冰依据端到端可追溯

- GIVEN 两个账号之间存在成立的交集，且发起方从交集卡发起打招呼。
- WHEN 接收方在请求箱查看该打招呼并回复。
- THEN 请求箱与升级后的 1v1 会话头部都展示同一条云侧依据。
- AND 依据在服务端重解析不成立时两处均不展示，且打招呼仍可作为普通问候继续。

<a id="sit-002"></a>
### SIT-002 可行动对象按可达性分流

- GIVEN 一个对象被分享进会话，其云侧行动提示同时包含可承接与不可承接的行动。
- WHEN 用户在会话中查看该 card。
- THEN 可承接行动可直接执行，不可承接行动展示为不可执行的规划口径。
- AND 不出现点击后无承接页的行动入口。

<a id="sit-003"></a>
### SIT-003 更换垂类不触发端侧改动

- GIVEN 交集事实从一个 vertical 切换到另一个 vertical。
- WHEN 重新执行本能力的全部验收行为。
- THEN 展示与行动分流结果随事实变化而变化，端侧代码路径不发生任何改动。
- AND 不出现按垂类命名的展示分支或行动分支。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 消息域尚无任何交集接口

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：当前联系首页的交集摘要由资料字段拼接伪装且圈子与群组行展示裸标识，会话页没有任何交集与助手落地，打招呼不携带交集引用。消息域因此无法承接交集行动，差异化在消息层面不成立。
- 完成判定：`SIT-001` 与 `SIT-002` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 垂类无关性尚无可执行证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：缺少能证明「更换垂类不需要改端侧代码」的可重复验收；没有该证据时垂类扩展契约在消息域只是约定而非约束。
- 完成判定：`SIT-003` 对应行为满足且真实测试 `spec_ref` 有效
