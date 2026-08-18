# L3 Story：主页、文章、图片和视频复用同一 execution、来源权利与发布闭 (`geo-content-trinity`)

> 所属能力：[`runtime-data-engineering`](../spec.md)
>
> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，我希望主页、文章、图片和视频复用同一 execution、来源权利与发布闭包，从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- 四类内容的单 execution 五阶段结构。
- source unit、图片权利、creator/tag/entity 引用与 review 闭包。
- 失败对象隔离和成功对象独立发布。

### Out of Scope

- 按站点建立第二套 runner 或发布目录。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 多内容类型复用同一来源与权利合同

- 图片来源、下载字节、授权与发布引用均可回放。
- creator/avatar、实体主页、文章、图片作品、真实视频与 poster 共享同一 execution/release 引用闭包，公开消费者只接收按 kind 物化的 public slice。

<a id="req-002"></a>
### REQ-002 失败对象隔离与成功对象独立发布

- release-first ship 与 operator journey 契约通过；同一 release digest 依次在 alpha/beta/gamma/prod 形成 import/API/media/rollback receipt。
- homepage、article、image、video 共享冻结 entity catalog，但各自使用 immutable execution、quota 与失败终态；post 不依赖 homepage execution 或 publish 结果。
- 四类 active workloads 彼此独立调度，可串行或重叠运行；固定四路并发、四个同时 workspace、capacity soak 或 resource sample 均不是 dispatch/promotion 前置。每个实际启动的 task 逐项形成 typed 终态，共享 canonical publish 继续由对象事务单写。

## 4. 契约引用

- canonical：`quwoquan_data/verticals/<vertical>/providers.yaml`
- canonical：`quwoquan_data/verticals/travel/rights/license_policy.yaml`
- canonical：`quwoquan_data/scripts/content/release/canonical/gate.py`
- canonical：`quwoquan_data/scripts/content/review/publish_filter.py`
- release media authority：`quwoquan_data/schema/release/media_manifest.schema.json`
- MediaAsset authority：`quwoquan_service/services/content-service/contracts/media/media_asset/fields.yaml`
- public slice authority：`quwoquan_service/runtime/media/asset_ref.go`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 多内容类型复用同一来源与权利合同

- GIVEN recipe 明确 contentType，来源与权利规则来自静态 registry。
- WHEN execution 执行 download、quality、compose、draft、review。
- THEN creator/avatar、entity、article/image/video 与 poster 均经同一 immutable release MediaAsset authority 绑定 source unit、Agent 审计与逐图权利闭包；公开消费者只接收按 kind 物化的 public slice，owner/rights 身份漂移必须 fail-closed。
- THEN 中间文件只进入 execution，approved 对象才进入 publish/release。

<a id="gwt-002"></a>
### GWT-002 失败对象隔离与成功对象独立发布

- GIVEN 四个 carrier execution 共享同一 commit、source digest 与 entity catalog digest，且部分对象在来源、质量、权利或 review 门失败。
- WHEN 四个 execution 按可用容量独立调度，可串行或重叠执行，并分别产生实际 task 终态后进入 canonical publish 与 immutable release。
- THEN 每个 carrier 按自身 quota 隔离失败对象，post 不等待 homepage；release 只包含 approved 对象，失败对象保留在所属 execution evidence。
- THEN soak、workspace smoke、effective concurrency 与 resource samples 只记录诊断事实，不改变 task dispatch、对象发布或结构性 promotion；canonical publish 保持单写者，最终 release 对全部被选对象与引用做 exact closure。
- THEN 下游不得看到悬挂 entity、creator、tag 或 media 引用。

## 6. 依赖

- 前置要求：[`runtime-data-engineering`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-002"></a>
### OPEN-002 四环境 activation 与 rollback 晋级证据

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺同一 immutable release digest 的 tag/creator/content/homepage 四环境 activation、API/media consumer readback 与 rollback/replay receipt。仓库内 importer/MediaAsset authority、local/hosted topology 的 `userPostgresPortRole`/`userPostgresDsnEnv` 契约与 local_contract 已另轨关闭，禁止用这些静态工程门替代 Alpha → Beta → Gamma → Prod 的真实晋级证据。Alpha 对 `20260731--travel-zhejiang-six--scale-017`（`payloadSha256=sha256:93af46e1a2399c22ae6df81c95a6a546a5f652ad025ad477f49b6885c9bc4eae`）已有 import + consumer ship verify + `stackctl verify --profile integration` 证据，但**不得**据此关闭本 OPEN；Beta/Gamma/Prod activation、readback 与 rollback/replay 仍缺。
- 完成判定：`GWT-002` 的 3 条 THEN 组全部具备子句级 `spec_ref`（`gwt-002.t1..t3`）绑定的真实晋级证据——同一 immutable release digest 依次取得 Beta、Gamma、Prod 的 activation、consumer readback 与 rollback/replay receipt，静态工程门不计。
