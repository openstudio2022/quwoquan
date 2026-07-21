# L3 Story：image-delivery-variants

## Spec Entry

- AppRoot Journey / Scenario：`content-creation-to-publication` /
  `photo-post-create-publish-return`。
- L1 / L2 / L3：`discovery-content` /
  `media-processing-helper-read` / `image-delivery-variants`。
- 验收意图：图片从编辑确认后的上传、受信处理、展示派生、原图授权到发布回流的
  `GWT + SIT + UAT` 闭环。
- 证据：`local_contract` 验证状态机、策略与授权；`api_integration` 验证真实
  Mongo、对象存储与 CDN URL；`user_acceptance` 验证 Remote App 与四环境设备矩阵。

## 用户目标

创作者确认编辑结果后，图片必须只上传一次、只产生一个 `MediaAsset`，并在可解释的
处理进度后安全进入发布和消费。读者在 Feed、详情、搜索和沉浸浏览中获得与屏幕和网络
相匹配的图像；原图只能在已发布内容可见性与资产策略同时允许时，经短时授权访问。
处理失败、策略升级和访问被拒绝都必须有真实、可恢复的终态，不能回退到私有原始字节或
客户端拼接的假成功 URL。

## 对象边界

| 对象 | 类型与归属 | 职责 | 明确非职责 |
| --- | --- | --- | --- |
| `MediaAsset` | `content.media` aggregate root | 持有原始摘要、处理状态、图片交付 descriptor、`processingVersion` 与 `derivativePolicyVersion` | 不为 thumbnail/display/cover/full 建独立聚合或独立生命周期 |
| `ImageDeliveryDescriptor` | `MediaAsset` owned value | 受信归一化基线、尺寸、MIME、公共 slice、dominant color、LQIP、内容画像与策略版本 | 不保存访问者或 Post 可见性 |
| `ImageVariantPolicy` | metadata policy，不是运行时业务对象 | 唯一声明 `thumbnail/display/cover/full` 的尺寸、格式、质量、场景、URL 参数与 policy version | 不保存用户图片、不由 App/Data 手写复制 |
| `MediaOriginalAccessFact` | append-only fact | 记录一次可审计、幂等、限流后的原图授权结果 | 不取代 `MediaAsset` 的访问策略，不授予 Post 不可见图片 |
| `Post` | 相邻 aggregate | 持有 `mediaId` 与可见性；其可见性是原图授权的必要条件 | 不持有 variant 配置、object key 或原图 URL |

`thumbnail/display/cover/full` 是同一已归一化图片的 CDN delivery profile，不是
`MediaAssetVariant`、`ImageVariant` 或第二份媒体业务对象。这样避免“一个图片多对象”
的写入竞争、状态漂移和发布引用不一致。

## 交付策略与不变量

1. `ImageVariantPolicy` 从
   `quwoquan_service/contracts/metadata/content/media_asset/image_variant_policy.yaml`
   唯一生成 Service、Dart 和 Data 的 profile 映射；现有
   `content/post/media_variant_profiles.yaml`、App 默认 `400/750` 与 Python 常量必须删除，
   不保留兼容双读。
2. 同一 policy version 的 image profiles 固定为 `thumbnail=320 webp q80`、
   `display=960 webp q82`、`cover=1280 webp q85`、`full=2048 webp q90`。CDN URL
   必须由 generated resolver 从 `MediaAsset` descriptor 与 profile 生成；业务页面不得裸拼
   `cw/ch/dpr` 或把 `original` 当作默认展示资源。
3. `ready` 只在真实解码、EXIF 方向归一、像素/尺寸守卫、正常化对象写入、公共 slice
   可读、`ImageDeliveryDescriptor` 校验以及 `derivativePolicyVersion` 绑定全部成功后产生。
   `processing` 内部阶段可以重试，但 aggregate 外部状态仍只有
   `processing -> ready | rejected -> deleted`，不新增无法恢复的中间公开状态。
4. `dominantColor`、`lqip`、`contentProfile` 和 `derivativePolicyVersion` 必须由受信
   processor 产出，进入 `MediaAsset` public slice；`lqip` 只允许受尺寸上限约束的低清
   占位数据，不能含原始 EXIF、用户 ID 或对象 key。
5. 每个 ready descriptor 固定 `processingVersion + derivativePolicyVersion`。策略升级不
   覆盖旧 slice：先在新 processing version 生成并验证，再原子切换 descriptor；失败保持
   旧 ready 交付。历史资产 backfill 按 cursor 生成新版本，支持暂停、重试、审计和回滚，
   禁止把历史资产直接改写为 ready。
6. 原图授权同时要求：资产 ready、`accessPolicy` 允许、引用该资产的已发布 Post 对该
   persona 可见、请求 purpose 在闭集 `view|save`，以及 rate limit 未触发。所有其他情况
   返回同源的 `403` 或 `429`，不通过 `ViewerID == OwnerID` 的 owner-only 查询偷换
   Post 可见性。

## 生命周期与恢复

```text
Image editor result
  -> MediaUploadSession completed
  -> MediaAsset(processing)
  -> decode / normalize / descriptor + policy bind
  -> MediaAsset(ready, processingVersion, derivativePolicyVersion)
  -> Post(mediaId) published
  -> generated delivery profile URL

corrupt/oversize/policy-invariant failure -> rejected
storage/CDN/checkpoint failure           -> processing + retry/replay
policy upgrade                            -> versioned reprocess -> validate -> atomic descriptor switch
```

- `rejected` 返回稳定 failure reason 和重新选择/编辑/上传动作，不生成公开 slice。
- `processing` 超过 SLO、checkpoint 失败、CDN baseline 不可读或 descriptor 校验失败只允许
  重试；不得让 Post 引用它。
- 用户删除或治理删除进入 `deleted`，撤销新的 delivery/original grant；已签发短 URL 按最短
  TTL 自然失效并留审计。

## 原图访问与隐私

- `RequestOriginalImageAccess` 继续以 `MediaOriginalAccessFact` append sink 记录结果；
  grant 只含短时签名 URL、格式、大小、到期时间与审计 ID。
- 授权判定读取 Post 的 named visibility reader，禁止从 `MediaAsset` aggregate 直接 import
  Post persistence，也禁止把 Post access snapshot 缓存在 App。
- 限流键为 `viewerPersonaId + mediaId + purpose`；只记录结果、reason 和 hash 化资源标识，
  不记录原图 URL、图片字节、Post 正文或用户原始 IP。
- Feed/详情展示只消费 delivery profile；没有 grant 时不展示“查看原图”入口，失败使用
  `RuntimeFailure + RuntimeRecoveryPolicy`，不显示原始 exception。

## 性能、观测与回滚

| 指标 | 商用目标 | 告警/动作 |
| --- | --- | --- |
| complete → ready（图片 ≤ 20 MiB） | P95 ≤ 45s，P99 ≤ 120s | 5 分钟 P95 超标 warning；连续 10 分钟失败率 > 1% critical |
| descriptor / CDN profile 可读 | 成功率 ≥ 99.9% | 5 分钟低于目标 critical，停止策略放量 |
| `GetMediaAsset` | P95 ≤ 400ms | 超标 warning，检查 descriptor/cache |
| original grant | P95 ≤ 800ms，403/429 分开计数 | 403 异常增幅与 429 连续命中分别告警 |
| backfill | cursor lag、reprocess outcome、旧版本占比 | lag 超过发布窗口阻断 policy activation |

服务指标使用 `outcome`、`media_type=image`、`derivative_policy_version`、profile、
failure category 和 hash 化 release/asset 维度；端侧只记录 profile、网络档位、缓存命中、
图片加载结局与 hash 化 `mediaId`。禁止采集图片内容、原始 URL、EXIF 或用户身份。

回滚为停止新 policy activation，恢复上一个已验证 policy version，并保持旧
`processingVersion` descriptor 可读；不回滚 App 二进制、不删除私有原始 CAS、不强制把
资产改为 ready。

## 实施顺序

1. metadata 定义 `ImageDeliveryDescriptor` 和唯一 `ImageVariantPolicy`，再 codegen；
2. Service descriptor、worker、backfill/reprocess、visibility reader 和 rate limiter；
3. Data importer/materializer 与 generated Dart resolver，删除所有手写 profile；
4. local_contract、真实 API integration、Remote App UAT 与四环境 device matrix；
5. 只有 Q1–Q4 报告均为 non-dry-run passed，才允许解除
   `image-end-to-end-commercial-matrix.md` 的 `GATE_BLOCK`。

## Out of Scope

- 滤镜算法、编辑 session 与滤镜目录发布归 `image-editing`、`filter-catalog-release`。
- 用户编辑配方、使用事实、圈子热度和交集推荐归 `edit-recipe-filter-intersection`。
- HLS/DASH、视频 ABR 与视频 cover 继续归视频处理 Story。
