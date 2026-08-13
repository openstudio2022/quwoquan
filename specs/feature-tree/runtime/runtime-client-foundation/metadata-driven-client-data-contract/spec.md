# L3 Story：元数据驱动的客户端数据契约（metadata-driven-client-data-contract） (`metadata-driven-client-data-contract`)

> 所属能力：[`runtime-client-foundation`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，
我希望同一 **Repository 抽象接口** 的 `Mock*` 与 `Remote*` 实现：对同一业务操作返回 **同一 codegen 类型**（或经同一 `fromMap`/工厂解析到该类型），**禁止** Mock 返回「另一套 Map 键名」而 Remote 另一套，
从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- “元数据驱动的客户端数据契约（metadata-driven-client-data-contract）”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 元数据驱动的客户端数据契约（metadata-driven-client-data-contract）

- 同一 **Repository 抽象接口** 的 `Mock*` 与 `Remote*` 实现：对同一业务操作返回 **同一 codegen 类型**（或经同一 `fromMap`/工厂解析到该类型），**禁止** Mock 返回「另一套 Map 键名」而 Remote 另一套。

<a id="req-002"></a>
### REQ-002 同一 Repository 抽象接口 的 Mock* 与 Remote* 实现：对同一业务操作返回 同一 codegen 类型（或经同一 fromMap/工厂解析到该类型），禁止 Mock 返回「另一套 Map 键名」而 Remote 另一套

- 同一 **Repository 抽象接口** 的 `Mock*` 与 `Remote*` 实现：对同一业务操作返回 **同一 codegen 类型**（或经同一 `fromMap`/工厂解析到该类型），**禁止** Mock 返回「另一套 Map 键名」而 Remote 另一套。
- `lib/service/<service>/<context>/<object>/presentation/**` 中，领域实体行数据应以 codegen DTO 或基于 metadata 的 ViewModel 进入 `build`，禁止以裸 `Map` 作为列表模型类型；存量由门禁直接扫描。
- 若某域迁移失败，恢复代码但不得删除已经成立的 metadata 字段，也不得通过登记清单豁免回归。
- 新增云接口或新页面数据模型：**须** 先改 metadata 再 codegen，**禁止** 仅端侧手写 DTO 作为长期方案。
- alpha/beta/gamma/prod 统一使用 `lib/main.dart` 的 production Remote composition，代码图中不得保留 `AppDataSourceMode`、`appDataSourceModeProvider`、alpha runner、mock package 或同义运行时切换器；环境名和 runtime define 只能选择 endpoint/config，不得改变数据源。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 元数据驱动的客户端数据契约（metadata-driven-client-data-contract）

- GIVEN 开发、测试或运维角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“元数据驱动的客户端数据契约（metadata-driven-client-data-contract）”对应的公开行为。
- THEN 同一 typed port 的生产 Remote 实现与测试树对象级 typed double：对同一业务操作返回 **同一 codegen 类型**（或经同一 `fromMap`/工厂解析到该类型），**禁止** typed double 返回「另一套 Map 键名」而 Remote 另一套。
- AND 四环境 artifact、kernel/AOT 可达图与 UAT support 始终解析为同一 Remote composition，Mock/fixture/Noop 数量为零；对象级 typed double 只存在测试树。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 Feed 信封准入由契约生成并 fail-closed

- GIVEN feed slice 契约声明列表上限、canonical SHA256 字形和 nullable 字段共现约束。
- WHEN App generated decoder 收到越过分页或卡片数量上限、非法 digest，或只携带 `cursor`/`paginationExpiresAt` 其中之一的信封。
- THEN decoder 在进入 presentation 前拒绝该信封，并返回 canonical failure。
- AND 生成器对未知格式、类型不匹配、悬空或非 nullable 的共现声明在生成期拒绝。

## 6. 依赖

- 前置要求：[`runtime-client-foundation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 页面与资料读模型仍含手写 Map 边界

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：`homepage_introduction_page.dart`、`profile_stats_page.dart` 与若干 profile read model 仍直接解析匿名 Map，metadata 字段变化可能绕过 codegen 校验。
- 完成判定：`GWT-001` 的“同一 codegen 类型、禁止另一套 Map 键名”对应行为在这些读模型上满足——上述页面与 profile read model 改为具名 projection/ViewModel；`page_object_contract` 的 typed presentation 与代码扫描均无匿名业务 Map。
- 依赖：user profile 与 entity homepage projection metadata。

<a id="open-002"></a>
### OPEN-002 内容阅读与创作仍保留 raw wire 过渡边界

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：内容详情、沉浸阅读、圈子作品和创作 payload 仍存在 raw Map 过渡，容易形成 DTO 与手写键双轨。
- 完成判定：`GWT-001` 的 typed 单轨对应行为覆盖内容阅读与创作路径——UI 只消费 `PostReadPresentation`/generated DTO；raw Map 仅存在于 HTTP decoder 单点且由 wire key/codegen 门禁证明。
- 依赖：content projection metadata 与创作 draft composite。

<a id="open-003"></a>
### OPEN-003 四环境 Remote composition 与 release-bound UAT

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：仍缺四环境 artifact 的 transitive dependency attestation，以及绑定同一 canonical release 的精确 API/UI 读回 CaseResult。仓内 Alpha runner、aggregate mock package 与 Patrol 业务 Provider 注入已退役，并由 `verify-production-data-source-single-path` fail-closed。
- 完成判定：`GWT-001` 由四环境 Remote artifact、Mock/fixture 可达数为零、release-bound API/UI CaseResult 与 required non-skipped CI 直接证明。
- 依赖：环境 topology、canonical release activation 与 App core readback。

<a id="open-004"></a>
### OPEN-004 信封准入约束待在 feed slice 契约声明并重建

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：仍缺 feed slice 契约上的取值声明与重建后的落盘 decoder，表达位与生成能力已就位。响应字段现在可声明三类信封准入位：`max_items`（列表长度上界）、`format: canonical_sha256`（字符串 canonical 字形）、`co_present_with`（必须同时出现或同时缺失的 nullable 字段组）；前两者的 schema 位在 `contracts/metadata/_schemas/fields.schema.json`，`co_present_with` 为本次新增。`tools/codegen_app_metadata` 的 `renderDomainResponseModel` / `renderDomainDecoderHelpers` 会分别生成 `_requiredBoundedList`、`_requiredCanonicalSha256Digest`（复用 `quwoquan_cloud_contracts` 的 `isCanonicalSha256Digest`，不复制字形正则）与 `_requireCoPresentFields`，并对未知 `format`、非 string 上的 `format`、非 list 上的 `max_items`、悬空或非 nullable 的 `co_present_with` 生成期 fail-closed，由 `TestDomainResponseDecoderEnforcesEnvelopeAdmission` 与 `TestDomainResponseDecoderRejectsInvalidAdmissionDeclarations` 覆盖。`content/content/post/projections/content_discovery_feed_page_slice.yaml` 尚未声明这些取值，磁盘上的 generated decoder 也未重建，因此分页上限、`objectCards` 数量有界、`cursor` 与 `paginationExpiresAt` 成对出现、`policyDigest` 的 `sha256:<64 hex>` 字形在端侧仍未 fail-closed。
- 完成判定：`GWT-002` 通过；feed slice 契约声明上述四条取值，重跑 codegen 后 generated decoder 带上对应准入调用，并由 App `local_contract` 断言四条越界信封各自被拒绝。
- 依赖：`projections/*.yaml` 目前没有 JSON Schema（`validate.MetadataSchemas` 只覆盖 `fields.yaml` 等对象包文件），投影侧声明位仍靠 compiler 与生成器语义校验。
- 当前边界：`codegen-app` 落盘链路本身已验证可用（直接调用 `tools/codegen_app_metadata` 消费现存 `generated/contract_graph.json`，与 App lock 哈希一致且产物幂等），因此剩余阻断只在契约取值声明与端侧越界证据，不在重建窗口。
