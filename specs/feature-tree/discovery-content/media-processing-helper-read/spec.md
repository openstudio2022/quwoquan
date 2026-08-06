# L2 Business Capability：媒体处理与辅助阅读 (`media-processing-helper-read`)

> 所属领域：[`discovery-content`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

图片/视频从上传完成事实到 ready/rejected 终态、归一化公开切片与可预览读取的商用闭环。

## 2. 范围与非目标

### In Scope

- MediaAsset 状态机、outbox worker、checkpoint、FFmpeg/FFprobe、对象存储派生物、健康与指标。
- 真实 MinIO + MongoDB + FFmpeg 的数据一致性证据。

### Out of Scope

- 文章摘要生成由 helper-read-summary 独立 Story 验收。
- HLS/DASH ABR 在 feature flag 关闭时不属于首发交付。

## 3. Journey / Scenario 贡献

- [`JNY-004 / SCN-002`](../../spec.md#scn-002)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：图片/视频从上传完成事实到 ready/rejected 终态、归一化公开切片与可预览读取的商用闭环，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。
- [`JNY-004 / SCN-003`](../../spec.md#scn-003)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：图片/视频从上传完成事实到 ready/rejected 终态、归一化公开切片与可预览读取的商用闭环，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。

## 4. Story



- [`helper-read-summary`](./helper-read-summary/spec.md)：定义“辅助读取摘要”的可观察主路径、失败语义及父能力交接。
- [`image-delivery-variants`](./image-delivery-variants/spec.md)：损坏、超限、descriptor 缺字段或 CDN baseline 不可读全部进入 rejected 或保持 processing 重试，不能发布。
- [`media-failure-recovery`](./media-failure-recovery/spec.md)：checkpoint 保存失败后重放同一事实只产生一个有效 ready 结果。
- [`media-status-pipeline`](./media-status-pipeline/spec.md)：带音轨与无音轨输入均产生 H.264/AAC progressive fast-start MP4。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 图片/视频媒体处理、恢复与读取能力 SIT

- completed 上传产生耐久事实，worker 以 checkpoint 至少一次消费并把资产推进到 ready 或 rejected。
- 图片只有在真实解码、像素/尺寸守卫和归一化成功后才 ready，公开 slice 从 normalized object 物化，不复制原始上传字节。
- 图片 ready descriptor 必须绑定 processingVersion 与 derivativePolicyVersion；thumbnail/display/cover/full 由同一 ImageVariantPolicy 的 CDN profile 派生，不创建第二个 MediaAsset 或手写 App/Data profile。
- 原图授权同时验证 Post 可见性和 asset policy；非可见访问为 403、超限为 429，且不泄露 原图 URL 或图片内容。
- 带音轨视频完成 H.264/AAC 归一，无音轨视频注入 AAC 静音轨；二者均满足 fast-start 与关键帧约束。
- 非媒体字节稳定进入 rejected，不生成可发布 slice。
- checkpoint 保存失败可重放，重复事实不重复处理已终态资产。
- ready descriptor 的 processingVersion 与可变 aggregate version 分离；视频封面或访问策略 后续变更后，原有 versioned public slice 仍可恢复、读取和校验。

<a id="req-002"></a>
### REQ-002 处理结果回写必须幂等；重放不得重复改变终态

- 处理结果回写必须幂等；重放不得重复改变终态。
- FFmpeg、对象存储或 checkpoint 不可用时 fail-fast/重试，禁止伪造成功或回退原视频。

## 6. 契约与依赖

- 上游能力：[`discovery-content`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 图片/视频媒体处理、恢复与读取能力 SIT

- GIVEN 执行“图片/视频媒体处理、恢复与读取能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“图片/视频媒体处理、恢复与读取能力”对应动作。
- THEN completed 上传产生耐久事实，worker 以 checkpoint 至少一次消费并把资产推进到 ready 或 rejected。
- THEN 图片只有在真实解码、像素/尺寸守卫和归一化成功后才 ready，公开 slice 从 normalized object 物化，不复制原始上传字节。
- THEN 图片 ready descriptor 必须绑定 processingVersion 与 derivativePolicyVersion；thumbnail/display/cover/full 由同一 ImageVariantPolicy 的 CDN profile 派生，不创建第二个 MediaAsset 或手写 App/Data profile。
- THEN 原图授权同时验证 Post 可见性和 asset policy；非可见访问为 403、超限为 429，且不泄露 原图 URL 或图片内容。
- THEN 带音轨视频完成 H.264/AAC 归一，无音轨视频注入 AAC 静音轨；二者均满足 fast-start 与关键帧约束。
- THEN 非媒体字节稳定进入 rejected，不生成可发布 slice。
- THEN checkpoint 保存失败可重放，重复事实不重复处理已终态资产。
- THEN ready descriptor 的 processingVersion 与可变 aggregate version 分离；视频封面或访问策略 后续变更后，原有 versioned public slice 仍可恢复、读取和校验。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 图片/视频媒体处理、恢复与读取能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：completed 上传产生耐久事实，worker 以 checkpoint 至少一次消费并把资产推进到 ready 或 rejected。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 媒体用途上下文与类型命名族缺 typed 边界

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：当前 `quwoquan_service/services/content-service/contracts/media/media_upload_session/fields.yaml` 没有 typed 用途上下文字段，上传会话无法声明该媒体将用于头像、封面、正文还是随拍。
- 缺用途上下文时，尺寸守卫、派生 profile 与访问策略只能由调用方口头约定，服务端无法按用途失败关闭。
- `quwoquan_service/services/content-service/contracts/content/post/fields.yaml` 的 `contentType` 表示内容载体类型，与媒体侧 `mediaType` 和 `mimeType` 构成同名族语义冲突，跨对象阅读时容易把两层类型混用。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效
- 依赖：媒体用途上下文值域裁决与内容、媒体类型命名族边界裁决。
