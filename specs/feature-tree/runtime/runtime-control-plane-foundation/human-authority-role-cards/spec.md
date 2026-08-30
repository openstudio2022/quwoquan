# L3 Story：Human Authority 角色卡 (`human-authority-role-cards`)

> 所属能力：[`runtime-control-plane-foundation`](../spec.md)
>
> Journey / Scenario：不直接参与终端用户 Journey；为 Ops Portal 中具名 Human Authority 提供可理解、可访问且可恢复的决定入口
>
> 设计归属：[L2 DEC-002](../design.md#dec-002)

## 1. 用户价值

作为承担 Human Authority 职责的运营、产品、体验、工程、质量、风险、发布与渠道角色，我希望在 Ops Portal 中以符合自身责任的角色卡查看事实、独立提交输入并恢复异常，从而无需理解仓库内部术语，也不会因界面偏置、错误身份或网络中断作出越权或不可追溯的决定。

## 2. 范围与非目标

### In Scope

- Ops Portal 作为四类角色卡的主交互与展示 surface，以及 Round 1 / Round 2 角色 submission 入口。
- OIDC 登录、MFA 与当前角色提示的用户体验；服务器端对 principal、role、scope、SoD、evidence freshness 与重复提交的强制校验。
- 补证据、转交正确角色、暂停或停止、超时、离线恢复与 authority readback 的可见终态。
- 键盘、读屏和窄屏可用性，以及对非技术角色隐藏内部术语的分层审计详情。

### Out of Scope

- 定义或改写 Human Authority、DecisionUnit、卡片字段、错误码、决定状态与恢复语义；这些属于 canonical Human-Agent 交付 Story 与机器契约。
- 由 Portal 判断 Human 决定、派生授权、执行 effect，或把前端状态、菜单 metadata、缓存与测试替身当作 authority。
- 修改 Portal 源码、`portal_menu` authoring metadata、generated projection，或以机器测试代替真实人类可用性验收。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 Portal 投影四类角色卡但不拥有决定语义

- Portal 必须依据 canonical role interaction / card projection 展示选择卡、授权卡、异常卡与事后检查卡，并作为角色 submission 的主入口；不得在页面内复制 Human Authority 角色、合法动作、决定或恢复语义。
- Portal 只能严格消费 provider-owned、authenticated `RoleTask/CardProjection` generated projection；projection 必须绑定 actor principal、DecisionUnit/candidate/scope 与恰好一个 pending role/task capability。unknown/legacy schema、raw aggregate、`intake` shadow card 或缺失字段必须 fail-closed，不得由前端推导 current role/status/actions 或 fallback。
- 选择卡必须支持 Round 1 原始事实、约束与未知项的独立输入，以及 Round 2 基于同一冻结事实包的独立影响输入；提交在汇总前互相隔离，合法选项使用中性标识、对称字段与无预选、无视觉强调、无推荐偏置的展示顺序。
- 每类卡必须提供补证据、转交正确角色、暂停或停止；异常卡必须展示安全默认与超时终态，事后检查卡必须展示 authority readback 和当前角色可接受的范围，不得把提交成功冒充决定已记录或 effect 已执行。
- 补证据、转交、暂停/停止与事后结果接受必须分别调用 provider capability 并独立 readback；事后检查不得再次 finalize。role submission 与 round seal 不得由 Portal 合并为一个 partial-success 请求。

<a id="req-002"></a>
### REQ-002 身份与权限在服务器端 fail-closed

- Portal 必须提供 OIDC Authorization Code + PKCE、MFA 状态、会话失效与重新认证的可理解 UX；浏览器显示或隐藏卡片仅用于体验，不构成授权。
- OIDC 登录必须一次性校验 `state/nonce`；provider 返回认证 freshness 不足时 Portal 必须发起 re-auth。未认证为 401，已认证但 scope denied 或 wrong role 为可区分 403。
- 服务器端必须以已验证 principal 与 canonical role/scope 强制校验每次读取和 submission；错误角色、身份未知、scope 无效、证据过期和 SoD 不成立必须返回可区分的 fail-closed 结果，并引导转交、重新认证、补证据或暂停。
- `role-record-only` 可由同一 authenticated actor 以不同角色分别提交；`independent-principal-required` 必须由不同 authenticated actor 完成，Portal 不得通过角色切换或同一账号重复提交绕过。
- role submission 成功必须投影 accepted/pending/next-role；server 可在最后一份有效 submission 的同一事务自动 seal，或由独立 `seal-orchestrate` capability 恢复，generic write scope、普通 role 与 Portal 均不能 seal。

<a id="req-003"></a>
### REQ-003 重复、离线与超时恢复不产生隐式批准

- 同一 submission 的重复发送必须得到同一已记录结果或明确冲突，不生成第二份角色输入；决定或 evidence 版本漂移时必须刷新并重新确认，不得静默覆盖。
- 相同 operation/idempotency key 与 request digest 的重试必须得到 provider committed byte-identical response；同 key 不同 digest 明确冲突。Portal 不得依赖本地 mutex、随机新 key 或复合 submit+seal 猜测结果。
- 网络离线、请求结果未知或页面重载时，Portal 必须先 readback 当前 authority 状态，再允许安全重试；在 readback 未确认前保持未决定，不展示成功，不触发 effect。
- 角色缺席、会话超时或决定超时时只允许 canonical pause、hold、escalate 或 abort 终态；恢复后必须显示哪些输入已被接受、哪些仍未提交以及下一责任角色。

<a id="req-004"></a>
### REQ-004 角色卡对键盘、读屏与窄屏可理解

- 四类卡的标题、当前角色、问题、已知与未知事实、硬约束、选项、后果、状态和恢复动作必须具有稳定语义层级；键盘可完成浏览、选择、提交、补证据、转交和暂停，焦点顺序与错误定位可预测。
- 读屏必须可辨认当前轮次、卡片类型、选项标签、是否选中、校验错误、异步状态和 readback 结果；颜色、位置或图标不得成为唯一信息载体。
- 窄屏不得隐藏方案对称字段、硬约束或安全动作，不得因重排改变选项含义、默认选择或提交后果。
- 自动化验收必须以 component/browser 行为验证真实 DOM 的名称/角色/状态、焦点、键盘操作、live-region readback 与窄屏字段完整；源码 regex 只能辅助。真实 screen-reader 与 MFA principals 的外部 UAT 继续保持 OPEN。

<a id="req-005"></a>
### REQ-005 人类主视图隐藏内部术语且保留受限审计详情

- 面向角色的主视图必须使用人类可理解的事实、影响、未知项和后果，不得暴露 digest、CAS、typed blocker、fingerprint、owner manifest、receipt、exact-byte readback、内部绝对路径、命令或工具名。
- 需要调查时，受权限保护的审计详情可以展示 canonical audit projection；技术详情必须与角色决定区隔，不得成为业务角色理解或提交的前置条件。
- raw audit/evidence 必须经独立 least-privilege audit query/scope，角色卡 query 只得到 redacted role projection。recommendation 只在 provider 确认 required rounds sealed 后可见，并同时展示 assumptions/counterexamples/alternatives。Portal 不得手写 seal gate。
- Portal 的导航入口只能来自 `quwoquan_service/contracts/metadata/_control_plane/portal_menu.yaml` authoring metadata 的 generated projection；generated 文件禁止手改，菜单存在也不代表服务器端读取或 submission 已授权。

## 4. 契约引用

- Human Authority 角色、两轮 submission、四类卡、合法动作与恢复：`quwoquan_ops/policies/human_agent_delivery_contract.yaml`
- Human Authority 产品语义：[`human-agent-delivery-interaction`](../../development-workflow-governance/human-agent-delivery-interaction/spec.md)
- hosted authority provider：[`hosted-human-authority`](../../../platform-ops-governance/config-and-reliability-governance/hosted-human-authority/spec.md)；负责 authenticated principal/role、durable submission、exact-byte readback 与 consume/revoke，不拥有 Portal 页面
- Portal menu authoring metadata：`quwoquan_service/contracts/metadata/_control_plane/portal_menu.yaml`
- Portal 工程根：`quwoquan_ops/portal`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 两轮四类卡保持对称并由正确角色提交

- GIVEN 一个 DecisionUnit 已声明当前 Human Authority 角色、Round 1 / Round 2、四类卡投影、SoD policy 与仍有效 evidence，且 Portal 会话来自已完成 MFA 的 OIDC principal。
- WHEN 角色通过 Portal 查看卡片、独立输入并提交。
- THEN 选择卡、授权卡、异常卡与事后检查卡均只展示当前角色责任内问题，以相同冻结事实和对称字段呈现合法选项，且不存在预选、视觉推荐偏置或他人未封存输入泄漏。
- AND Round 1 / Round 2 分别提交并在汇总前隔离；错误角色、scope 无效或 independent-principal-required 使用同一 actor 时服务器端拒绝，Portal 提供转交、重新认证或暂停。
- AND 每类卡均可补证据、转交正确角色、暂停或停止；超时只产生安全终态，authority readback 未确认前不显示决定成功且不执行 effect。

<a id="gwt-002"></a>
### GWT-002 重复和离线恢复保持单一可追溯结果

- GIVEN 角色已提交或正在提交一份绑定当前决定与 evidence 版本的输入。
- WHEN 浏览器重复发送、提交结果未知、离线后恢复或页面重载。
- THEN Portal 先 readback authority，重复 submission 返回同一记录或明确冲突，未确认结果保持未决定且不产生隐式批准。
- AND 版本漂移、证据过期、身份会话失效或决定超时均要求刷新、补证据、重新认证、转交或暂停，不静默覆盖已有记录。
- AND 恢复视图明确区分已接受输入、待提交输入、当前安全终态与下一责任角色，审计详情可追溯但不把内部术语泄漏到角色主视图。

<a id="gwt-003"></a>
### GWT-003 真实双 MFA 角色在无障碍界面完成职责分离

- GIVEN 两个不同的真实 MFA principal 被正式 identity / authority provider 映射到 `independent-principal-required` 所需角色，并使用键盘、读屏和窄屏代表环境。
- WHEN 两位角色分别完成卡片理解、输入、提交、补证据或转交，并查看最终 readback。
- THEN 两位角色只能读取和提交各自被授权范围，错误角色与伪造身份均被服务器端拒绝，Portal 菜单或客户端状态不能绕过权限。
- AND 键盘焦点、读屏名称与状态播报、窄屏信息完整性支持完成全部代表任务，选项顺序或布局变化不改变选择语义和后果。
- AND Portal 的本地测试与生产构建只证明实现与构建完整性；真实双 MFA 账号 UAT 独立证明身份、SoD、人类可理解性和可恢复性，任一层失败均不得由另一层替代。

## 6. 依赖

- 前置要求：[`human-agent-delivery-interaction`](../../development-workflow-governance/human-agent-delivery-interaction/spec.md) 的 `REQ-001`、`REQ-003`、`REQ-004`、`REQ-005` 与 canonical Human Authority contract。
- 上游事实：hosted authority provider 的 authenticated principal/role、DecisionUnit、card projection、submission result 与 readback，以及 `portal_menu` authoring metadata 的 generated projection。
- 下游结果：人类可理解且可访问的卡片展示、限权 submission 与可恢复终态；不输出 Human Decision authority 或 effect 成功事实。
- 父级设计：`DEC-002`

## 7. 开放事项

<a id="open-002"></a>
### OPEN-002 Generated role-task capabilities 与行为级 Portal seams 待单轨落地

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺实现：Portal 仍未完成 generated role-task capabilities 严格解析、raw aggregate/`intake`/本地 role-status-action-recommendation fallback 删除、submit+seal 拆分、post-check 独立 command 与 typed 401/403/recovery terminals；在 provider/Human contract 与 Portal 路径的并行写入结束前，本 OPEN 只拥有设计决定而不占用这些实现字节。尚缺验收证据：component/browser 行为级 accessibility 与 provider api_integration 尚未证明上述单轨边界，source-regex 只能作为辅助。
- 完成判定：`GWT-001.t1`、`GWT-001.t2`、`GWT-001.t3`、`GWT-002.t1`、`GWT-002.t2`、`GWT-002.t3`、`GWT-003.t1`、`GWT-003.t2` 由 generated decoder/capability contract、component/browser 行为测试及 provider api_integration 直接绑定，且 source-regex a11y 只作辅助。
- 依赖：[`hosted-human-authority/OPEN-001`](../../../platform-ops-governance/config-and-reliability-governance/hosted-human-authority/spec.md#open-001)、Portal 与 provider 当前 writer 释放目标文件；落地时不得手改 generated projection。

<a id="open-001"></a>
### OPEN-001 正式 hosted identity 与双 MFA 账号 UAT 尚未闭合

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：Portal 角色卡、generated 菜单投影、职责匹配的本地测试与生产构建已闭合，但若无正式 OIDC/MFA identity、authenticated hosted authority、两个不同真实 principal、durable hosted submission/readback 与真实人类参与者，机器证据仍不能证明身份、职责分离、决定真实性或 human usability。
- 完成判定：`GWT-003.t1`、`GWT-003.t2`、`GWT-003.t4` 均由正式 provider 上两个不同 MFA principal 的真实 user_acceptance 证据直接绑定；已闭合的 Portal local_contract、组件测试与生产构建不得替代人类可用性观察。
- 依赖：[`hosted-human-authority/OPEN-002`](../../../platform-ops-governance/config-and-reliability-governance/hosted-human-authority/spec.md#open-002)、正式企业 IdP/OIDC client、MFA principal/role mapping、durable hosted authority submission/readback 与经同意的真实角色 UAT。
