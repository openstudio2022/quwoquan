# L3 Story：图片投递变体 (`image-delivery-variants`)

> 所属能力：[`media-processing-helper-read`](../spec.md)
>
> Journey / Scenario：[`JNY-004 / SCN-002`](../../../spec.md#scn-002)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容创作者或浏览者，我希望单一 MediaAsset 图片交付 descriptor、唯一 CDN variant policy、原图授权和可回滚 reprocess 闭环，从而完成可恢复的内容创作、发现或互动。

## 2. 范围与非目标

### In Scope

- MediaAsset 的 ImageDeliveryDescriptor、derivativePolicyVersion、CDN profile 与历史资产 reprocess。
- ImageVariantPolicy metadata/codegen、Data materializer、Dart resolver 和 Image 读侧。
- Post 可见性驱动的原图授权、403/429 限流和对应审计事实。
- alpha/beta/gamma/prod 非 dry-run 图片端到端证据。

### Out of Scope

- 编辑算法、滤镜目录、用户配方、滤镜使用事实、视频 ABR。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 图片只有在完整交付 descriptor 可验证后才能 ready

- 损坏、超限、descriptor 缺字段或 CDN baseline 不可读全部进入 rejected 或保持 processing 重试，不能发布。
- thumbnail/display/cover/full 不创建独立 MediaAsset、独立 Store 或独立生命周期。
- 真实 PNG/JPEG 经 FFmpegMediaProcessor、Mongo、对象存储和 public reader 的 descriptor 一致。

<a id="req-002"></a>
### REQ-002 所有消费者只使用 metadata 生成的图片 profile

- 读取页只经 generated ImageUrlResolver/AppImage 消费 display profile，沉浸页只消费 full profile。
- policy 变更先生成新 processingVersion 并完成可读验证，失败时保持旧 descriptor。

<a id="req-003"></a>
### REQ-003 原图访问按 Post 可见性授权并可靠限流

- 授权服务经 Post named visibility reader，不以 ViewerID 伪装 owner 查询。
- grant/rejection/ratelimit 仅追加 MediaOriginalAccessFact 与安全指标，不泄露原图 URL 或图片字节。

<a id="req-004"></a>
### REQ-004 策略升级与历史资产重处理可停止、恢复和回滚

- cursor、idempotency、旧新 descriptor、清理候选和 rollback target 都可审计。
- 不直接覆写 ready descriptor、不删除仍被 Post 引用的旧 slice、不以 aggregate version 重解释 processingVersion。

<a id="req-005"></a>
### REQ-005 图片四环境设备矩阵以真实 Remote 主线闭环

- alpha 只作为同构工程证据；beta Android 与 iOS、gamma 与 prod gray-initial/carry-on/full 任一缺失均保持 GATE_BLOCK。
- 报告符合 image-end-to-end-commercial-matrix 的统一 schema，禁止用 mock、fixture、路径存在性或 dry-run 代替。

<a id="req-006"></a>
### REQ-006 处理与交付故障必须 fail-closed

- `processing` 超过 SLO、checkpoint 失败、CDN baseline 不可读或 descriptor 校验失败时，只允许保留旧 descriptor 或保持可重试终态；不得生成新的 ready 结果。
- 授权判定必须读取 Post 的 named visibility reader，禁止从 `MediaAsset` aggregate 直接导入可见性事实。

## 4. 契约引用

- canonical：`quwoquan_service/services/content-service/contracts/media/media_asset/object.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/media/media_asset/fields.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/media/media_asset/operations.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/media/media_asset/image_variant_policy.yaml`
- canonical：`quwoquan_data/scripts/core/media_asset_url.py`
- canonical：`quwoquan_app/lib/service/content_service/media/media_asset/adapters/cdn_image_url_builder.dart`
- canonical：`quwoquan_service/services/content-service/contracts/media/media_original_access_fact/operations.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/media/media_original_access_fact/fields.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/media/media_original_access_fact/original_access_policy.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 图片只有在完整交付 descriptor 可验证后才能 ready

- GIVEN 已完成的图片 MediaUploadSession 产生 processing MediaAsset 和耐久 outbox 事实。
- WHEN processor 真实解码、方向归一、执行像素/尺寸守卫、写入 normalized baseline 并绑定 ImageDeliveryDescriptor。
- THEN ready 资产拥有 processingVersion、derivativePolicyVersion、公共 slice、尺寸、MIME、dominantColor、lqip 与 contentProfile。

<a id="gwt-002"></a>
### GWT-002 所有消费者只使用 metadata 生成的图片 profile

- GIVEN active ImageVariantPolicy 声明 thumbnail/display/cover/full 的 policy version。
- WHEN App、Data 与 Service 解析同一 MediaAsset image descriptor。
- THEN 三侧得到相同 profile 尺寸、格式、质量和 URL 参数；业务代码不存在默认 400/750、Python profile 常量或 Post 目录副本。

<a id="gwt-003"></a>
### GWT-003 原图访问按 Post 可见性授权并可靠限流

- GIVEN ready 图片被 public、followers 或 private Post 引用，且访问者身份各不相同。
- WHEN 访问者请求 view 或 save 原图授权。
- THEN 同时满足内容可见性和 accessPolicy 的请求获得短时 grant
- AND 非可见者稳定得到 403
- AND 超过窗口稳定得到 429。

<a id="gwt-004"></a>
### GWT-004 策略升级与历史资产重处理可停止、恢复和回滚

- GIVEN 已存在不同 processingVersion 的 ready 图片以及待升级的 ImageVariantPolicy。
- WHEN reprocess worker 分批处理历史资产，或在验证失败时停止 activation。
- THEN 每个资产仅在新 descriptor 完整、可读且与 policy 匹配时原子切换；失败、暂停和回滚继续提供旧 slice。

<a id="gwt-005"></a>
### GWT-005 图片四环境设备矩阵以真实 Remote 主线闭环

- GIVEN 同 release/config hash 的 beta Android/iOS、gamma remote 和 prod gray 环境可用。
- WHEN 用户选图、编辑、上传、等待 ready、发布、在第二账号查看并请求原图。
- THEN 每个必选环境都有非 dry-run serviceEvidence 与 uiEvidence，包含 mediaId/postId、descriptor、profile load、授权结局和回滚结论。

## 6. 依赖

- 前置要求：[`media-processing-helper-read`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-005"></a>
### OPEN-005 图片四环境设备矩阵以真实 Remote 主线闭环

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：alpha 只作为同构工程证据；beta Android 与 iOS、gamma 与 prod gray-initial/carry-on/full 任一缺失均保持 GATE_BLOCK。
- 完成判定：`GWT-005` 对应行为满足且真实测试 `spec_ref` 有效
