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

## 4. 契约引用

- object / projection：`AssistantWebTarget`、`AssistantWebDocument`、`AssistantSourceLedgerEntry`
- tool：`web_search`、`web_open`、`web_find`
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
