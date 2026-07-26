# L3 Story：上下文有依据问答 (`context-grounded-answering`)

> 所属能力：[`runtime-assistant`](../spec.md)
>
> Journey / Scenario：[`JNY-009 / SCN-017`](../../../spec.md#scn-017)
>
> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，我希望小趣基于当前页面结构化 context snapshot（`capturedAt`、`pageType`、`pageObjects`、`userActions`、`consentMatrix`）做 grounding 回答；引用只指向真实站内对象或声明的外部来源，从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- ReportPageContext 上报与 Redis TTL 缓存
- grounding 注入 run prompt 与引用回溯

### Out of Scope

- 搜索 handoff（归 assistant-search-handoff-and-grounding）

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 页面上下文注入回答

- App 只上报强类型 `AssistantContextSnapshot`；页面展示文本、标题、摘要、URL 与标签不得进入页面上下文。
- assistant-service 必须校验时效、当前页读取同意、metadata 已登记对象类型和结构化动作，并按 persona 写入 300 秒 Redis TTL。
- 下一次 Run 只读取服务端缓存的有效页面上下文并注入 prompt；上下文缺失或过期时不得注入页面事实。
- 非法、过期、缺少同意或未知对象的 snapshot 必须 fail-closed；Redis 未配置或写入失败必须返回 metadata 定义的结构化失败。
- 上下文过期/缺失时降级为通用回答且不伪造事实。

<a id="req-002"></a>
### REQ-002 交集证据授权回查与引用落点

- 内部 citation 以 canonical destination 打开正确对象，外部 citation 仅允许已校验 HTTPS URL。
- 未知对象、缺失 destination 或权限失败不回退打开 post。

<a id="req-003"></a>
### REQ-003 交集入口只提交 `AssistantIntersectionEvidenceRef`（intersectionId、evidenceId、sourceRef、canonical object type/id）

- 交集入口只提交 `AssistantIntersectionEvidenceRef`（intersectionId、evidenceId、sourceRef、canonical object type/id）；assistant-service 必须按当前 actor 通过 content 的公开 Reader 回查当前事实后，才可将其注入 prompt、evidence ledger 与 citation。
- 页面只上报结构化 snapshot（`ReportPageContext`），小趣不得维护第二套对象真相源。
- 携带交集证据引用的 Run 在对象不存在、actor 无权访问、证据快照已过期或 sourceRef/目标不匹配时必须 fail-closed，返回 metadata 定义的结构化失败；禁止静默忽略或信任客户端标题、结论、URL、tag 与样本。
- 引用（citation）必须携带唯一 `CitationDestination`：站内为 canonical object type/id 与 metadata 生成的 deep link，站外仅为已校验 HTTPS URL；未知目标、无链接或无权访问不得回退打开 post。

## 4. 契约引用

- canonical：`quwoquan_service/services/assistant-service/contracts/assistant/assistant_run/operations.yaml`
- canonical：`quwoquan_service/services/assistant-service/contracts/assistant/assistant_run/fields.yaml`
- canonical：`quwoquan_service/services/assistant-service/contracts/assistant/assistant_run/errors.yaml`
- canonical：`quwoquan_service/contracts/metadata/_shared/search_objects.yaml`
- canonical：`quwoquan_service/contracts/metadata/_shared/link_templates.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 页面上下文注入回答

- GIVEN 用户在内容详情页上报了结构化 page context。
- WHEN 用户在小趣发起提问。
- THEN HTTP 边界将强类型 snapshot 写入带 300 秒 TTL 的 Redis，并由下一次 Run 读取。
- THEN 回答 prompt 只注入结构化 page context；引用可回溯到 metadata 已登记的源对象。
- THEN 上下文缺失、过期、无同意或对象类型未知时不向 prompt 注入页面事实。

<a id="gwt-002"></a>
### GWT-002 交集证据授权回查与引用落点

- GIVEN 用户从对象页交集卡打开小趣，App 提交强类型 AssistantIntersectionEvidenceRef。
- WHEN 用户启动 AssistantRun。
- THEN assistant-service 以当前 persona 通过 content 公开 Reader 回查 intersectionId、evidenceId、sourceRef 与目标对象。
- THEN 仅回查到的当前事实可进入 prompt、evidence ledger 与 citation。
- THEN 伪造、过期、撤销或无权访问的引用返回结构化失败，不降级为客户端声明的事实。

## 6. 依赖

- 前置要求：[`runtime-assistant`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

- 无。
