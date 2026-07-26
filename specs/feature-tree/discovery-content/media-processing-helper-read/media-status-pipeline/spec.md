# L3 Story：媒体处理状态流水线 (`media-status-pipeline`)

> 所属能力：[`media-processing-helper-read`](../spec.md)
>
> Journey / Scenario：[`JNY-004 / SCN-002`](../../../spec.md#scn-002)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容创作者或浏览者，我希望completed 上传事实到 MediaAsset ready/rejected 与可发布派生物的单轨状态流水线，从而完成可恢复的内容创作、发现或互动。

## 2. 范围与非目标

### In Scope

- durable outbox、worker、FFmpeg/FFprobe、对象存储、聚合终态和 Post 绑定读取。
- 聚合跃迁、幂等结果回写、ready/rejected 不变量。

### Out of Scope

- 播放器 QoE 与 adaptive streaming。
- 页面发布结果回流。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 视频上传完成后生成可发布 ready 资产

- 带音轨与无音轨输入均产生 H.264/AAC progressive fast-start MP4。
- width/height/duration/audio/cover/preview manifest 与实际派生对象一致。
- Post 发布绑定能读取 ready 资产且只投影 MediaAsset ID 派生的公开引用。

<a id="req-002"></a>
### REQ-002 MediaAsset 只以有效处理结果离开 processing

- 缺主 slice、封面、尺寸、时长或 H.264/AAC/fast-start 约束的 ready 结果被拒绝。
- 基础设施失败不改变聚合状态。

<a id="req-003"></a>
### REQ-003 `MediaAsset` 只允许 `processing → ready|rejected|deleted`

- `MediaAsset` 只允许 `processing → ready|rejected|deleted`；终态不可逆。
- 图片 `ready` 必须具备归一化私有对象、canonical image slice、有效尺寸和交付格式。
- 视频 `ready` 必须同时具备主视频 slice、封面 slice、有效尺寸/时长和探测 descriptor。
- 视频必须为 H.264/AAC、progressive MP4、fast-start、最长关键帧间隔 2 秒。

## 4. 契约引用

- canonical：`quwoquan_service/services/content-service/contracts/media/media_asset/events.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/media/media_asset/fields.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/media/media_asset/preview_track_manifest.schema.json`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 视频上传完成后生成可发布 ready 资产

- GIVEN 用户完成 ownerOnly 视频上传，MediaAsset 状态为 processing 且 outbox 事实已提交。
- WHEN 媒体处理 worker 消费事实并运行 ffprobe、转码、封面和预览轨道生成。
- THEN MediaAsset 进入 ready，公开 slice 可读且 ready descriptor 满足视频不变量。

<a id="gwt-002"></a>
### GWT-002 MediaAsset 只以有效处理结果离开 processing

- GIVEN MediaAsset 处于 processing 并带有权威私有源对象。
- WHEN worker 回写 ready 或 rejected 结果，或重复投递相同事实。
- THEN 合法 descriptor 进入 ready，内容性失败进入 rejected，重复事实对终态 no-op。

## 6. 依赖

- 前置要求：[`media-processing-helper-read`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 视频上传完成后生成可发布 ready 资产

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：带音轨与无音轨输入均产生 H.264/AAC progressive fast-start MP4。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 MediaAsset 只以有效处理结果离开 processing

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：缺主 slice、封面、尺寸、时长或 H.264/AAC/fast-start 约束的 ready 结果被拒绝。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效
