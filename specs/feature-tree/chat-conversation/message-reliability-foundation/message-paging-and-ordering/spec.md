# L3 Story：消息分页与排序 (`message-paging-and-ordering`)

> 所属能力：[`message-reliability-foundation`](../spec.md)

> Journey / Scenario：[`JNY-007 / SCN-012`](../../../spec.md#scn-012)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为在长会话里向上翻阅的用户，
我希望历史消息按稳定游标连续加载并保持确定顺序，翻页与刷新不会造成重复、遗漏或位置回退，
从而能一路读回到很久以前而不迷失当前位置。

## 2. 范围与非目标

### In Scope

- 向上翻阅历史的游标分页触发与连续加载。
- 分页结果、实时推送与补洞结果合并后的顺序稳定性与去重。
- 到达最早一条时的终止判定。

### Out of Scope

- 首次打开的本地水合，由 [`message-timeline-local-persistence`](../message-timeline-local-persistence/spec.md) 负责。
- 断连缺口补齐，由 [`realtime-push-and-offline-sync`](../realtime-push-and-offline-sync/spec.md) 负责。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 历史加载必须由滚动位置触发并使用 keyset 游标

- 向上滚动接近已加载区间顶端时必须触发历史加载，加载必须以已持有的最早 seq 为 keyset 游标，不得使用偏移量分页。
- 加载中必须可观察，重复触发不得产生并发重复请求。

<a id="req-002"></a>
### REQ-002 翻页与刷新不得重复、遗漏或回退

- 分页结果与已有内容合并后必须按 seq 严格有序且无重复条目。
- 加载历史不得改变当前可视位置；下拉刷新不得丢弃已加载的更早历史。

<a id="req-003"></a>
### REQ-003 终止判定必须明确

- 到达会话最早一条时必须给出明确终止态；不得以空结果反复触发加载。

<a id="req-004"></a>
### REQ-004 服务本地契约引用边界

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

## 4. 契约引用

- canonical：`quwoquan_service/services/chat-service/contracts/chat/message/operations.yaml`
- canonical：`quwoquan_service/services/chat-service/contracts/chat/message/fields.yaml`
- 父能力公开契约：[`L2 spec`](../spec.md)

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 连续向上翻阅不重复不遗漏

- GIVEN 一个消息数量超过单页容量的会话。
- WHEN 用户连续向上滚动直至加载到最早一条。
- THEN 每次加载以最早 seq 为游标续接，合并结果按 seq 严格有序且无重复。
- AND 到达最早一条后给出终止态且不再触发加载。

<a id="gwt-002"></a>
### GWT-002 加载历史不改变当前可视位置

- GIVEN 用户已向上翻阅若干页并停在某条消息。
- WHEN 新的一页历史加载完成并插入到列表顶部。
- THEN 当前可视位置保持在原消息上。
- AND 失败时返回 canonical failure 且保留已加载内容。

<a id="gwt-003"></a>
### GWT-003 乱序写入下分页与增量同步仍有序无重无缺

- GIVEN 同一会话的消息文档以与 seq 无关的顺序写入持久层。
- WHEN 客户端经 keyset 分页跨页读取历史,或以某 seq 为起点做增量同步。
- THEN 跨页合并结果按 seq 有序、无重复、无缺号。
- AND 增量同步结果同样按 seq 有序、无重复、无缺号。
- AND 增量补齐从缺口最早处按 seq 递增取满限额；限额小于缺口时不得跳过最早的缺口消息。

## 6. 依赖

- 前置要求：[`message-reliability-foundation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

