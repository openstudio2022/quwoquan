# L3 Story：Active Skill Package 目录与运行单轨 (`active-skill-package-catalog`)

> 所属能力：[用户 Skill 产品与集成平台](../spec.md)
>
> Journey / Scenario：[`JNY-009 / SCN-034`](../../../spec.md#scn-034)
>
> 设计归属：[`L2 DEC-001`](../design.md#dec-001)

## 1. 用户价值

作为 Skill 用户和平台发布者，我希望目录、运行、展示和回放都对应同一份已激活能力，从而看到的说明、授权要求与实际结果一致，并能可靠回滚。

## 2. 范围与非目标

### In Scope

- 官方 package publisher、签名/digest、stage/activate/rollback、active resolver、Catalog/Profile 解析、Run digest 冻结与旧 Run 恢复。

### Out of Scope

- 第三方 Skill、任意代码执行、生产请求路径直接读取源码 Manifest/Profile。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 所有 Skill 消费方必须解析同一 active release

- Manifest 必须引用 Catalog/Activation/Input/Context/Capability/Orchestration/Trigger/Memory/Presentation/Evaluation/Prompt/Replay 不可变资产。
- builder 必须拒绝未被任何 Manifest 引用的 Profile 资产；新增或退出垂类时必须在同一 source change 中完成 Manifest 引用或物理删除，禁止以休眠 Profile 形成隐藏目录和第二路由真相源。
- activate 前必须校验 publisher、签名、所有 asset digest、schema、capability/node compatibility 与 replay gate；失败不改变 active pointer。
- Catalog、Router、Context、Prompt、Tool Policy、Presentation、Evaluation 不得维护自己的 built-in 项或文件扫描 fallback。
- Catalog 每个目录项必须携带 active `packageId/releaseDigest`、输入 schema digest、setup template、激活模式和适用 surface；用户设置只能绑定该已验证发布的 schema，不得伪造 digest。
- 只有价值说明、目标用户、数据使用、适用场景和成果示例均完整且引用同一 resolved package 的 Skill 才能进入用户目录；内部路由或质量未达标 Skill 不得以半成品目录项暴露。
- 目标用户、场景、授权说明和成果示例必须由 active package 提供可直接展示的安全语义，App 不得按 Skill、垂类、scope 或 surface 另建文案映射；示例中的展示模板必须解析到同一 package 的 digest-qualified template。
- Catalog 封面或示例媒体只有在 package 同时携带 canonical MediaAssetRef、尺寸、alt、来源与授权证明时才可发布；当前无该证明的字符串引用必须在构建阶段拒绝，不得形成悬空媒体。
- Catalog 只是 `SkillPackageRelease` 的投影；账号 Consent、Setting 与 Subscription 必须通过各自对象读取，不得拼接到目录描述或发布元数据。

## 4. 契约引用

- object / projection：`assistant.SkillPackageRelease`、`assistant.SkillCatalog`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 激活与回滚保持新旧 Run 可重放

- GIVEN release A 已 active，Run A 冻结其 digest，release B 完整通过发布门。
- WHEN 激活 B、启动 Run B，再回滚 active pointer 到 A 并恢复 Run A/Run B。
- THEN 新 Run 分别使用当时 active digest，恢复 Run A/Run B 继续解析各自冻结资产，回滚后的后续 Run 使用 A。
- AND 删除源码扫描入口或改变本地 Manifest 不影响生产 resolver，缺 artifact 时诚实阻断而非 fallback。

## 6. 依赖

- 前置要求：Artifact store、签名信任根、schema/codegen 与 App capability matrix。
- 上游事实：官方源码资产和 publisher identity。
- 下游结果：Catalog/Router/Run/Presentation/Evaluation frozen release。
- 父级设计：`DEC-001`

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 Active Skill Package 尚缺 Gamma 同 digest 与 rollback 收据

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：仍缺同一 digest 在 Gamma 的 activation/readback 与 rollback 环境收据，不能仅凭 Alpha 激活宣称可发布。Alpha canonical 已取得官方 SkillPackage 空环境自举激活收据（`activatedBy: service:local-managed-bootstrap:alpha-local`，`activeReleaseDigest: sha256:ec6fc1eb1eff0db87a1aed15a50dc13de67db8ec32689a5db8013f40b37f0a06`，health 29/29 run `20260813T160518410673Z-d38bed3e0945497980753e19bcb051e5-health-alpha-local`）。生产 `Catalog`、Prompt、Input Schema 与 Presentation 已统一读取 active/frozen `SkillPackageRelease`，源码扫描器只存在于 package builder 和测试 fixture。
- 尚缺实现：无新增实现。空环境自举、验签、digest 与评测 receipt 门禁已接入 `PrepareMigration`。
- 尚缺验收证据：同一 package digest 的 Gamma activation/readback 与 rollback 环境收据尚未取得。最近一次 `stackctl up --env gamma` GATE_BLOCK（run `20260813T165117596635Z-05f1f7ae24b149f187e67df4127e90fd-up-gamma`）因并行 `beta-local` 操作锁。`gamma-local` 与在场 `alpha-local` 共享 `workstation-commercial-runtime`，不能并行启动。
- 完成判定：`GWT-001` 的 local_contract、Mongo api_integration 和 replay 全部通过，并取得同一 package digest 的 Alpha/Gamma 受管环境 activation/readback/rollback receipt；生产 API binary 不出现源码 asset scanner 或 built-in catalog fallback。
- 依赖：受保护 publisher identity、SkillPackage artifact store 与 Assistant Provider 环境闭环。
