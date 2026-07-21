# L3 特性：filter-catalog-release

## 用户目标

创作者打开图片编辑器时，应获得可用、稳定、可回滚且跨环境一致的滤镜目录；运营可以发布或回滚目录，而无需重新发版 App。断网时只能使用已验证的同一发布副本，禁止用手写空列表、动态 Map 或另一套资产配置伪造成功。

## 对象边界

| 对象 | 类型 | 职责 | 非职责 |
|---|---|---|---|
| `FilterCatalogRelease` | aggregate root | 承载一次不可变目录发布、摘要、状态和有界成员 | 不记录用户使用事实，不保存编辑会话 |
| `FilterCategoryDefinition` | owned entity | 分类显示、排序和启停 | 不独立写入、查询或维护生命周期 |
| `FilterPresetDefinition` | owned entity | 预设显示、排序、默认强度和强类型调整参数 | 不保存图片、不直接执行像素处理 |
| `FilterAdjustmentValues` | owned value | 15 项调整参数，范围统一为 `[-100, 100]` | 不允许任意键 Map |
| `VerifiedFilterCatalogCache` | App local infrastructure replica | 按 `releaseId + canonicalDigest` 保存最近一次校验通过的发布 | 不是业务真相源，不允许修改目录 |

`FilterCatalogRelease` 属于 `content.media` bounded context。目录只描述可用滤镜；像素执行仍由 `ImageEditorExportEngine` 负责，编辑器本地会话仍归 `image-editing`。

## 关系与不变量

- 一个 release 最多包含 32 个分类、256 个预设；每个预设必须引用同 release 内已启用分类。
- `releaseId`、`canonicalDigest`、分类、预设和推荐列表在 Stage 成功后不可变。
- 分类 ID、分类排序、预设 ID、同分类预设排序必须唯一；`original` 必须存在且调整参数全为 0。
- `defaultStrength` 范围为 `[0, 100]`；15 项调整参数范围为 `[-100, 100]`。
- 同一环境同一时刻只能有一个 `active` release。
- public Reader 只返回完整校验通过的 active release；禁止返回 staged 或半写入目录。
- `Stage` 以 digest 和 Idempotency-Key 幂等；同 key 不同 payload 返回冲突。
- `Activate` 只允许 `staged -> active`，旧 active 原子进入 `retired`。
- `Rollback` 只允许目标 `retired -> active`，当前 active 原子进入 `retired`；重复目标已 active 为 no-op receipt。

## 生命周期

```text
canonical catalog artifact
  -> StageFilterCatalogRelease
  -> staged
  -> ActivateFilterCatalogRelease
  -> active
  -> retired
  -> RollbackFilterCatalogRelease
  -> active

invalid artifact -> stable validation failure (no persisted release)
```

Stage、Activate、Rollback 均由受信 data publish plane 调用；App 只有公开只读能力 `GetActiveFilterCatalog`。

- 唯一发布入口为 `qwq-data filter-catalog publish`：它先验证 canonical binding，再从
  metadata 解析 operation path，以稳定 Idempotency-Key 执行 Stage/Activate/Rollback，
  并以 public GET 回读 `releaseId`、digest 和成员计数。发布回执不得记录 bearer、
  目录全文、用户身份或图片内容。
- beta/gamma 仅可经 `stackctl filter-catalog --target <beta-local|gamma-local>` 调用；
  stackctl 在进程内签发最小权限的本地 `service` principal
  (`content.filter_catalog.manage`)，只经子进程环境变量传递 bearer。prod 不签发本地
  token，必须由受控 secret 提供 service principal；`activate` 还必须显式声明
  `--prod-gray-activation`，防止 Stage 被误当作已放量。

## 端云读取与离线策略

```text
content-service ActiveFilterCatalogReader
  -> generated operation client
  -> RemoteFilterCatalogQuery
  -> FilterCatalogCoordinator
       -> VerifiedFilterCatalogStore
       -> ImageEditorFilterCatalog
  -> ImageEditorPage
```

- Remote adapter 只做 generated DTO 到 typed application model 的映射，不读资产、不吞异常。
- coordinator 成功校验远端 release 后原子替换本地 verified cache。
- 无网时只允许读取 digest 已校验的 cache；首次安装无 cache 时读取由同一 canonical release artifact 生成的 bootstrap replica。
- bootstrap replica 必须带真实 `releaseId/canonicalDigest`，并由门禁与环境 seed 校验同源；禁止手写第二套 `filter_presets.json`。
- cache/bootstrap 都无效时返回结构化 `RuntimeFailure`，滤镜面板展示可重试错误态，编辑器其他工具保持可用。

## 安全、性能与可观测

- public GET 不需要登录，不返回 source owner、内部 receipt 或操作审计字段。
- Stage/Activate/Rollback 仅允许 service principal 与 `content.filter_catalog.manage` scope。
- `GetActiveFilterCatalog` P95 ≤ 300ms、可用性 ≥ 99.9%；App warm cache 加载 P95 ≤ 100ms。
- 指标：`content_filter_catalog_get/stage/activate/rollback`、`filter_catalog_load`。
- 维度：`outcome`、`source=remote|cache|bootstrap`、`release_id_hash`、`digest_match`、`cache_age_bucket`；禁止记录用户 ID 或图片内容。
- 告警：连续 5 分钟 active catalog 读取成功率低于 99.9%，或任一环境 active release 缺失。

## 四环境与发布回滚

- alpha/beta/gamma/prod 均由各自 seed manifest 导入同一结构的 release；环境可使用不同 `releaseId`，但字段和不变量一致。
- beta/gamma 必须完成 Stage→Activate→GET→App 映射→离线 cache 重启验证。
- prod 发布先 Stage 校验，再灰度 Activate；回滚只执行 `RollbackFilterCatalogRelease`，不回滚 App 二进制。
- 发布证据必须记录 releaseId、digest、presetCount、激活时间和回滚目标，不记录目录内容全文。
- `stackctl verify` 的 integration/release profile 对 beta、gamma、prod-hosted 自动追加
  public active-release readback；它只读，不会隐式 Stage 或 Activate。实际 mutation
  仍需显式 `stackctl filter-catalog`，避免环境巡检改变业务状态。

## Out of Scope

- 用户配方、滤镜使用事实和圈子热度交集，归 `EditRecipe/FilterUsageFact/FilterUsageStatsView` Story。
- 像素算法、预览缩略图生成和编辑会话，归 `image-editing`。
- 图片压缩、variants 与 CDN 交付，归媒体处理 Story。

