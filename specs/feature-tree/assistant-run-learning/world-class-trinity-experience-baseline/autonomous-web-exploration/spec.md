# L3 Story：自主公开网探索 (`autonomous-web-exploration`)

> 所属能力：[小趣统一体验](../spec.md)
>
> Journey / Scenario：[`JNY-009 / SCN-018`](../../../spec.md#scn-018)
>
> 设计归属：[L2 DEC-002](../design.md#dec-002)

## 1. 用户价值

作为向小趣提供网页或要求其研究公开信息的用户，我希望小趣可以从我给出的 URL 或自行发现的链接继续探索，从而获得有来源、可核验且不会越过私有网络边界的回答。

## 2. 范围与非目标

### In Scope

- 公开 HTTPS 内容的只读搜索、打开、文内查找、继续链接与来源引用。
- 用户、搜索结果和已读文档链接三类起点的同一安全边界与证据账本。

### Out of Scope

- 登录态网页、企业私有数据、内网地址、网页提交、购买、发帖或任意浏览器写操作。

## 3. 行为要求

### REQ-001 公开 URL 可直接成为探索起点

- 用户或模型给出的公开 HTTPS URL 无需预先成为搜索结果即可读取。
- 搜索来源和已读文档链接必须保留父级来源血缘，模型不得伪造来源身份。

### REQ-002 所有读取均受统一公开网边界约束

- 读取必须在解析、重定向和最终连接阶段阻止非公开地址、危险端口、凭证继承、无界响应与无界抓取。
- 网页内容必须作为不可信证据处理，不得改变系统目标、工具权限、Connector 授权或完成条件。

### REQ-003 回答保留可核验来源

- 被采用的网页事实必须可追踪到规范化目标、抓取摘要、来源血缘和用户可打开的引用。
- 安全拒绝、预算耗尽与不支持内容必须进入可区分、可恢复终态，不得伪造已读取。

### REQ-004 研究预算只依赖工具语义能力

- 可参与证据探索的 Tool 必须在 canonical metadata 声明 `discover / navigate / inspect` 语义及其输入绑定；AgentLoop 不按工具名或垂类分支判断搜索广度、来源上限和导航深度。
- 新增符合相同 metadata 合同的站内 Reader、公开网 Reader 或 Connector Reader 时，只增加 Tool metadata 与 adapter；不得修改 AgentLoop 才能获得既有研究预算、恢复和审计能力。
- 公共网页搜索、天气事实与行情事实必须是独立 typed capability Tool；具体 Skill 只通过 active CapabilityProfile 组合工具，运行时不得按 `skillId`、中文关键词或入参形状猜测 Provider。
- Tool Registry 必须在注册、读取和每次 Run 开始时生成隔离快照；模型声明、Hook 或 Adapter 对 schema map 的修改不得污染其他 Run。
- Provider 失败必须由该 Tool metadata 绑定到真实存在的 AssistantRun error；AgentLoop 不得按 Provider capability、toolName 或垂类分支映射错误码。
- 所有研究 Tool 的输出 schema 必须强制包含封闭且完整的 `evidenceAssessment`，至少表达充分性、是否重规划、原因及 target/document/artifact/source 引用集合；不得把缺失评估当作成功。
- 需要把检索中浮现的兴趣反馈给用户体验或推荐系统的 Tool，必须在自身封闭输出 schema 中声明并返回标准 `emergedTagRefs`；Tool adapter 负责从所属领域的 canonical payload 生成路径制 tagRef，AgentLoop 只合并标准字段，不猜测 `results`、`payload` 或垂类字段。

### REQ-005 站内检索与公开网检索共享研究语义但保持独立 Provider

- `app_search` 与 `web_search` 必须共享 `query`、分维度 `searchQueries`、证据评估和是否重规划语义；站内检索始终调用 canonical `SearchIndexView.Search`，公开网检索始终调用公开网 Provider。
- 任一 Tool 失败时不得自动切换另一 Tool，也不得以另一来源的结果冒充本次检索成功；下一步 Tool 只能由模型基于冻结 metadata、证据缺口和剩余预算显式选择。
- AgentLoop 不得按 Tool 名称、Skill、Provider 或自然语言关键词实现搜索业务分支。

## 4. 契约引用

- object / projection：`AssistantWebTarget`、`AssistantWebDocument`、`AssistantSourceLedgerEntry`
- tool：`web_search`、`web_open`、`web_find`、`weather_lookup`、`finance_quote`
- error / recovery：`ASSISTANT.USER.web_target_rejected`、`ASSISTANT.MIDDLEWARE.web_fetch_unavailable`、`ASSISTANT.MIDDLEWARE.web_budget_exhausted`、`ASSISTANT.SYSTEM.web_budget_unavailable`、`ASSISTANT.SYSTEM.web_evidence_unavailable`
- event / metric：`assistant_web_fetch`、`assistant_web_security_rejection`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 用户直接提供公开 URL

- GIVEN 用户提供一个未经过站内搜索的公开 HTTPS URL。
- WHEN 小趣读取并使用其中事实回答问题。
- THEN 回答带有可打开引用和完整来源血缘。
- AND 请求不携带用户或服务凭证。

<a id="gwt-002"></a>
### GWT-002 自主继续探索并阻断边界逃逸

- GIVEN 已读网页包含公开链接、内网链接与重定向链接。
- WHEN 小趣依据证据缺口继续探索。
- THEN 公开目标在预算内可继续读取，非公开目标在每个解析边界均被拒绝。
- AND 被拒绝内容不会被表述为已验证事实。

<a id="gwt-003"></a>
### GWT-003 新研究工具按 metadata 接入统一预算

- GIVEN 一个新只读 Tool 声明 `discover`、`navigate` 或 `inspect` 语义及合法输入绑定。
- WHEN Skill 在冻结的 Tool allowlist 中使用该 Tool 探索证据。
- THEN AgentLoop 复用同一来源、广度、深度、循环与恢复预算，不新增该 Tool 名称分支。
- AND 非法绑定、写工具冒充研究工具、target kind 超出其输入 schema 或缺少完整 `evidenceAssessment` 时，contract/codegen 在发布前失败。
- AND 声明 `emergedTagRefs` 的 Tool 可以直接进入统一兴趣回流，新增 Tool 不需要修改 AgentLoop 的结果解析分支。

<a id="gwt-004"></a>
### GWT-004 垂类事实能力不由 Skill 名称猜测

- GIVEN 天气、行情和公共网页分别由独立 Tool metadata、Provider port 与 active CapabilityProfile 声明。
- WHEN 天气问题文本被提交给 `web_search`，或任意 Skill 显式调用 `weather_lookup / finance_quote`。
- THEN `web_search` 始终只调用 public search；两个垂类 Tool 只调用各自 typed Provider，不跨能力降级或回退。
- AND 新 Skill 采用这些能力只修改 Skill package profile，不增加 Go 中的 Skill 分支。
- AND 任意新垂类 Tool 可用 metadata 绑定自己的 canonical Provider failure error，Coordinator 无需认识其 capability 名称。

<a id="gwt-005"></a>
### GWT-005 站内与公开网检索不自动互相降级

- GIVEN 同一研究问题可使用站内 canonical Search 或公开网搜索且其中一个 Tool 失败或证据不足
- WHEN 编排评估该 Tool 的 `evidenceAssessment`
- THEN 运行时不自动调用另一搜索 Tool，只有新的冻结检索计划和显式 Tool 选择才能继续检索

## 6. 依赖

- 前置要求：Tool Fabric、canonical runtime failure 与来源跳转契约可用。
- 上游事实：用户问题、Skill capability policy 与 Run budget。
- 下游结果：证据 Artifact、来源账本与引用绑定。
- 父级设计：`DEC-002`

## 7. 开放事项

### OPEN-001 受管 Provider 与真机公开网验收尚未闭环

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前仍缺 `assistant.public.search` 等受管 Provider material/readiness 证据，以及真实 Provider 与 Android/iPhone 真机执行收据。`web_search/web_open/web_find` 已由 canonical Tool Catalog 注册并接入 AgentLoop；authoritative Mongo Artifact/Document/Source Ledger、Run budget CAS、来源血缘、HTTPS/凭证/端口/IP/DNS rebinding/重定向/响应预算防线、prompt-injection/failure replay 及持久化 API integration 已有 direct 证据，公开 URL→引用答案 Patrol UAT 也已定义。Alpha/Gamma Remote 环境因此无法启动。
- 完成判定：在受管非生产 Provider 与同一候选 baseline 上执行真实公开 HTTPS、重定向、引用回查、预算耗尽和攻击 corpus API integration，并在 Android/iPhone 真机完成公开 URL→引用答案 UAT；引用必须 100% 回查 authoritative ledger。
