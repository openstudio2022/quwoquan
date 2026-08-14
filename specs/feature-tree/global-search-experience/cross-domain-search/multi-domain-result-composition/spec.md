# L3 Story：搜索结果不只是“查出来” (`multi-domain-result-composition`)

> 所属能力：[`cross-domain-search`](../spec.md)
>
> Journey / Scenario：[`JNY-005 / SCN-011`](../../../spec.md#scn-011)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为执行搜索的用户，我希望联想页提供快速直达、独立网络结果页编排 assistant 与内容分类结果，并在局部失败时保留可用结果，从而看懂结果、准确进入目标且不会陷入持续等待。

## 2. 范围与非目标

### In Scope

- 本地分段与云实体并行、部分失败和终态映射。
- 正式结果页 canonical `SearchPage` persisted GraphQL 单请求。
- 3 秒慢提示、6 秒取消、supersede/dispose 与旧内容保留。

### Out of Scope

- 搜索索引和生产部署。
- 新的 request profile 或第二套 outcome 状态体系。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 多域结果并行结算且等待必有出口

- 输入“钱”可预览并打开发布态“东钱湖”实体主页。
- 全页同一 request scope 同时只有一个主 indicator，任何路径均停止等待。

<a id="req-002"></a>
### REQ-002 点击联系人/聊天记录直达会话、点击网络结果进入独立结果页、点击结果卡片进入内容或引用对象的统一跳转语义

- 点击联系人/聊天记录直达会话、点击网络结果进入独立结果页、点击结果卡片进入内容或引用对象的统一跳转语义。
- 联系人和聊天记录的“更多”只能做当前页内联展开，不能跳到新的中间列表页。
- 跨 Circle 对象的聚合分区显示“讨论”，消息 group 显示“群聊”，Circle 对象显示“圈子”。
- 结果模型必须可类型化，不允许长期停留在松散 `Map` 拼装层。
- 任何 query/tab generation 被替换、超时或页面销毁时都必须让旧结果失效，并通过真实 cancellation signal 终止可见网络请求；`Future.timeout` 不作为 transport cancellation。
- `page_lifecycle_state` 复用 `waitMode`、`durationMs` 与 `phase=slow/timeout/cancelled/partial`，禁止记录原始搜索词。

<a id="req-003"></a>
### REQ-003 网络结果与一方地点落地必须以 canonical Remote 结果恢复

- 正式结果页每个 generation 只经 canonical result 请求取得 typed hit，并区分 online、empty、partial、timeout 与 failure；已确认分区不得因另一个分区失败而被清空。
- `entity.homepage` 命中进入该主页；尚未绑定主页的 `location.place` 进入地点落地页，冷启动、深链或进程恢复缺少页面内存参数时必须以 canonical place identity 精确重读。
- 地点已提升为主页时只跳转 canonical Homepage；地点不存在、过期或 Remote 不可用时显示可重试或可返回终态，不得用 route extra、裸 Map、旧标题或假地址伪造可用地点。

## 4. 契约引用

- canonical：`quwoquan_service/services/search-service/contracts/search/search_request_fact/operations.yaml`
- canonical：`quwoquan_service/services/entity-service/contracts/entity_homepage/homepage/operations.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 多域结果并行结算且等待必有出口

- GIVEN 用户输入 query，本地域与云域响应时延或失败情况不同。
- WHEN 联想页或正式结果页执行搜索，随后发生完成、部分失败、超时、query 替换或 dispose。
- THEN 本地结果先展示，云实体只在“搜索网络结果”段局部等待。
- THEN 正式结果每个 generation 只调用一次 canonical `SearchPage` persisted query。
- THEN 3 秒只在空白阻塞时显示一次提示；6 秒真实取消 transport 并进入可重试终态。
- THEN empty、partial、timeout、failure 分开映射；旧 completion 不得回写。

<a id="gwt-002"></a>
### GWT-002 网络结果与 location.place production Remote 落地

- GIVEN 用户提交非空 query 进入网络结果页，结果可能包含 `entity.homepage`、`location.place`、内容和其他可导航 typed hit，App 使用 production Remote composition。
- WHEN canonical result 请求完成，用户打开地点命中，或地点页在冷启动、深链、进程恢复后缺少页面内存参数而重新读取。
- THEN 每个 generation 只产生一次 canonical result 请求；partial 保留已确认 hit，empty、timeout 与 failure 分别进入明确终态并允许重试或返回。
- THEN `entity.homepage` 只进入 canonical 主页；`location.place` 只进入地点落地页并按自身 identity 精确重读，若已提升则转入该主页。
- THEN 不存在、已过期或不可用的地点与内容不得以 route extra、旧页面缓存或裸 Map 伪装成功；页面保留 query 与仍有效结果，并提供重试、返回或移除失效项的恢复动作。

## 6. 依赖

- 前置要求：[`cross-domain-search`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 网络结果与地点恢复 production Remote 双真机验收

- 类型：`external_blocker`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：规格已区分主页与一方地点单源以及冷启动恢复，但尚无同一 candidate 的真实设备 CaseResult 证明 typed hit、partial/timeout 恢复和地点精确重读均成立。
- 完成判定：`GWT-002` 的结果页、地点落地、已提升主页跳转与失败恢复在物理 Android 与物理 iPhone 上通过，且 ReadinessResultBundle 绑定同一 commit、ContractGraph、candidate、environment 与非内存 Provider。
- 依赖：production Remote 搜索索引与地点读模型、可控的有效/失效/已提升地点样本及真实 `user_acceptance` runner；不得用 route extra fixture 或动态 skip 代替。
