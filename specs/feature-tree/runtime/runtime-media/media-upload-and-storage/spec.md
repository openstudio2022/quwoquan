# L3 Story：媒体上传与存储（Media Upload and Storage） (`media-upload-and-storage`)

> 所属能力：[`runtime-media`](../spec.md)

> Journey / Scenario：[`JNY-004 / SCN-003`](../../../spec.md#scn-003)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为上传头像、图片或视频的用户，
我希望完成上传会话后获得可追踪的 `assetId`，重放完成请求仍返回同一资产结果，
从而在网络重试后继续发布而不产生重复或丢失媒体。

## 2. 范围与非目标

### In Scope

- “媒体上传与存储（Media Upload and Storage）”的输入、可观察主路径、失败语义以及与父能力的交接。
- InitUpload → upload ticket → CompleteUpload/Abort 的类型化会话。
- storageOrigin、uploadIngress 与 avatar/image/video deliveryBase 的职责隔离。
- App 仅消费 assetId/publicSliceKey，经 MediaDeliveryResolver 生成交付 URI。
- alpha/beta/gamma/prod 的 HTTPS、CA、Range/MIME 和真实设备证据边界。
- 禁止 App 重写已签名 URL host、保存对象 key 或保留旧上传 wire 的兼容路径。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 媒体上传与存储（Media Upload and Storage）

- `MediaUploadSession completed` 必须持久化所创建的 `assetId`，使重复 complete 返回同一资产并允许客户端继续发布。

<a id="req-002"></a>
### REQ-002 上传完成幂等返回同一资产

- `MediaUploadSession completed` 必须持久化所创建的 `assetId`；重复 complete 必须返回同一 `MediaAsset`，客户端据此继续发布且不得创建重复资产。
- Session 与 MediaAsset 创建必须在同一 transaction 内完成；资产追加失败时
  Session、receipt 与 outbox 均不得泄漏 completed 状态。
- 内容发布禁止 `uploadBytes/uploadLocalPath`、UI 裸 HTTP 和整文件读入 Dart heap。
- 错误使用 metadata 生成的 `RuntimeFailure`；策略拒绝、取消、暂时不可用和不可恢复失败。

<a id="req-003"></a>
### REQ-003 上传与公开媒体交付 authority 单轨

- App、媒体服务与对象存储必须对同一 `assetId/publicSliceKey` 收敛，Android/iOS 不得生成端侧替代身份。
- path-versioned public slice 只允许 query-free 公开交付；原图或处理中私有 object 只允许短期 signed URL，私有 key 不得进入 public-slice builder，public slice 不得追加签名或版本 query。
- 图片、视频、短文本配图、文章封面与正文图均先完成上传，再只以
  `mediaAssetIds` 进入 Post 发布；文章 manifest 只允许资产身份与展示元数据，
  服务端绑定后补充 canonical `publicSliceKey`。

<a id="req-004"></a>
### REQ-004 upload ticket 默认有效期 15 分钟，可配；其公开 authority 必须等于当前设备 target

- upload ticket 默认有效期 15 分钟，可配；其公开 authority 必须等于当前设备 target。
- 本地设备 target 收到 canonical `upload.<env>.quwoquan.com` 已签名 ticket 时，
  URL authority、Host、TLS SNI 与签名输入必须保持不变；Android 只允许通过
  `adb reverse` 转发 target 端口，禁止 host 改写或私有 CA 绕过。

## 4. 契约引用

- upload session：`quwoquan_service/services/content-service/contracts/media/media_upload_session/operations.yaml`
- media asset：`quwoquan_service/services/content-service/contracts/media/media_asset/operations.yaml`
- post publication：`quwoquan_service/services/content-service/contracts/content/post/operations.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 媒体上传与存储（Media Upload and Storage）

- GIVEN 开发、测试或运维角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“媒体上传与存储（Media Upload and Storage）”对应的公开行为。
- THEN `MediaUploadSession completed` 持久化所创建的 `assetId`；重复 complete 返回同一 `MediaAsset`，客户端可继续发布且不产生重复资产。
- AND grant 过期、complete 响应丢失或 App 重启时，客户端通过同一 session 与
  idempotency key 恢复；无法继续的 pending session 先权威 abort 再开启新会话。
- AND MediaAsset 创建失败时 transaction 整体回滚，不留下 completed Session、
  complete receipt 或 completed outbox。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 上传与公开媒体交付 authority 单轨

- GIVEN App、媒体服务与对象存储处理同一上传资产。
- WHEN 客户端完成上传并解析公开交付 URI。
- THEN 各方以同一 assetId 或 publicSliceKey 收敛，且交付 authority 与当前设备 target 一致。
- AND 发布请求与文章 manifest 不含 localPath、objectKey、presignUrl 或 cdnUrl；
  这些字段不得作为端云发布 authority。
- AND 本地 Simulator 对 canonical 已签名上传 URL 保留原始 authority 与 SNI，
  通过公共 CA 校验证书并完成真实 PUT。

## 6. 依赖

- 前置要求：[`runtime-media`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 上传与存储结果子句尚未逐条绑定

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：缺 `GWT-001` 四条结果子句的逐条证据，14 条测试整体绑定锚点，未区分各子句分别由哪条断言证明。
- 完成判定：`GWT-001.t1` 至 `GWT-001.t4` 各自被真实测试 `spec_ref` 绑定。

<a id="open-002"></a>
### OPEN-002 上传与公开媒体交付 authority 单轨

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：local_contract、真实 storage api_integration 与 Android/iOS user_acceptance 对同一 assetId/publicSliceKey 均可复验。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效。
