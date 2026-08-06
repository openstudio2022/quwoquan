# L3 Story：筛选目录发布 (`filter-catalog-release`)

> 所属能力：[`publish-comment-reaction`](../spec.md)
>
> Journey / Scenario：[`JNY-003 / SCN-008`](../../../spec.md#scn-008)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容创作者或浏览者，我希望滤镜目录以不可变 FilterCatalogRelease 单轨发布，App 经 typed query、verified cache 和同源 bootstrap replica 消费，从而完成可恢复的内容创作、发现或互动。

## 2. 范围与非目标

### In Scope

- FilterCatalogRelease、FilterCategoryDefinition、FilterPresetDefinition、FilterAdjustmentValues 的 metadata 与状态机。
- Stage、Activate、Rollback、GetActiveFilterCatalog typed operations。
- content-service Store/Reader/Facade/HTTP 装配和单 active 原子切换。
- App RemoteFilterCatalogQuery、VerifiedFilterCatalogStore、coordinator 与图片编辑器注入。
- canonical catalog artifact、四环境 seed、bootstrap replica 和 digest 同源门禁。
- `qwq-data filter-catalog publish` 与 `stackctl filter-catalog` 的受信环境发布、只读回查和 prod gray 防误触边界。

### Out of Scope

- EditRecipe、FilterUsageFact、FilterUsageStatsView 与圈子交集。
- 图片像素算法和 MediaAsset variants。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 不可变目录可幂等 Stage 并单 active 激活

- Mongo 真实引擎 contract 覆盖 digest 幂等、状态机和单 active CAS

<a id="req-002"></a>
### REQ-002 active catalog 可公开读取且可原子回滚

- 服务公开 HTTP 必须与 FilterCatalogRelease command/query 契约使用同一状态和错误语义。

<a id="req-003"></a>
### REQ-003 App 只消费 typed release 并具备可证明离线能力

- Remote 映射、cache 校验与 bootstrap 必须同源；缓存损坏或远端失败时 UI 展示明确错误与重试态。

<a id="req-004"></a>
### REQ-004 四环境发布、观测和回滚证据闭环

- canonical binding、环境 import payload、发布 HTTP path 与 `Idempotency-Key` 必须同源，回执不得暴露敏感字段。
- beta/gamma 的 stackctl Stage→Activate→GET 与 App 在线/离线证据均 recorded。
- prod gray Stage/Activate、public GET 与 Rollback 证据均 recorded，且 activation 未绕过显式人工批准。
- stackctl verify 与 CONTENT_MEDIA_GAMMA_UAT 证据均 recorded。

<a id="req-005"></a>
### REQ-005 一个 release 最多包含 32 个分类、256 个预设

- 一个 release 最多包含 32 个分类、256 个预设；每个预设必须引用同 release 内已启用分类。
- `releaseId`、`canonicalDigest`、分类、预设和推荐列表在 Stage 成功后不可变。
- 分类 ID、分类排序、预设 ID、同分类预设排序必须唯一；`original` 必须存在且调整参数全为 0。
- public Reader 只返回完整校验通过的 active release；禁止返回 staged 或半写入目录。
- bootstrap replica 必须带真实 `releaseId/canonicalDigest`，并由门禁与环境 seed 校验同源；禁止手写第二套 `filter_presets.json`。
- Stage/Activate/Rollback 仅允许 service principal 与 `content.filter_catalog.manage` scope。
- 维度：`outcome`、`source=remote|cache|bootstrap`、`release_id_hash`、`digest_match`、`cache_age_bucket`；禁止记录用户 ID 或图片内容。
- beta/gamma 必须完成 Stage→Activate→GET→App 映射→离线 cache 重启验证。
- 发布证据必须记录 releaseId、digest、presetCount、激活时间和回滚目标，不记录目录内容全文。

## 4. 契约引用

- canonical：`quwoquan_service/services/content-service/contracts/media/filter_catalog_release/object.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/media/filter_catalog_release/operations.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/media/filter_catalog_release/errors.yaml`
- canonical：`quwoquan_app/packages/quwoquan_cloud_contracts/lib/src/content/filter_catalog_facets.dart`
- canonical：`quwoquan_app/lib/service/content_service/media/filter_catalog_release/application`
- canonical：`quwoquan_app/lib/service/content_service/media/filter_catalog_release/adapters`
- canonical：`specs/feature-tree/discovery-content/publish-comment-reaction/filter-catalog-release/spec.md`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 不可变目录可幂等 Stage 并单 active 激活

- GIVEN data publish plane 持有通过 schema 与目录不变量校验的 canonical catalog artifact
- WHEN Stage 相同 digest 两次并 Activate 新 release
- THEN 相同 digest 重放返回首次 release，不产生第二份目录。
- THEN 同 Idempotency-Key 不同 payload 返回 CONTENT.USER.filter_catalog_idempotency_conflict。
- THEN 新 release 原子变为 active，旧 active 变为 retired，同一环境只有一个 active。
- THEN 分类、预设、推荐列表和调整参数在 Stage 后不可修改。

<a id="gwt-002"></a>
### GWT-002 active catalog 可公开读取且可原子回滚

- GIVEN 环境已有 active release 和至少一个 retired release
- WHEN public Reader 获取 active catalog，随后 publish plane Rollback 到 retired release
- THEN GET 只返回完整 active release，不暴露 sourceOwner、receipt 或内部操作字段。
- THEN Rollback 后 public GET 立即返回目标 release，原 active 变 retired。
- THEN 重复回滚到已 active release 为 no-op receipt，不递增 version。

<a id="gwt-003"></a>
### GWT-003 App 只消费 typed release 并具备可证明离线能力

- GIVEN App production composition 已注入 RemoteFilterCatalogQuery 和 VerifiedFilterCatalogStore
- WHEN 首次在线加载、重启离线加载、远端发布新 release、cache 损坏
- THEN 在线成功校验后按 releaseId + canonicalDigest 原子替换 cache。
- THEN 离线重启读取最后一次 verified cache；无 cache 时只读取同源 bootstrap replica。
- THEN cache 或 bootstrap digest 不匹配时拒绝使用并输出 RuntimeFailure，不返回手写空目录。
- THEN ImageEditorPage 不实例化 Remote、Mock、文件 Store 或动态 Map 配置。

<a id="gwt-004"></a>
### GWT-004 四环境发布、观测和回滚证据闭环

- GIVEN alpha/beta/gamma/prod manifest 均声明 FilterCatalogRelease seed 或发布输入
- WHEN 运行 environment import、gamma UAT 和 prod gray activation
- THEN 每个环境可证明 releaseId、digest、presetCount 与 active 状态。
- THEN gamma 完成在线获取、编辑器展示、离线重启与回滚后再获取。
- THEN 读取、Stage、Activate、Rollback 指标与告警可查询，日志不含图片和用户身份。

## 6. 依赖

- 前置要求：[`publish-comment-reaction`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-004"></a>
### OPEN-004 四环境发布、观测和回滚证据闭环

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：仍缺 gamma 编辑器在线/离线重启与回滚后的 Remote 证据，以及受保护 prod gray activation/rollback 的批准与执行证据。beta 已可经受信 publish plane 完成 Stage→Activate→GET。
- 完成判定：`GWT-004` 的 gamma 与 prod gray 行为均实际执行，真实
  `spec_ref` 与环境 report 可复验。
