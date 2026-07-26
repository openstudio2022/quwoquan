# L2 Business Capability：运行时媒体 (`runtime-media`)

> 所属领域：[`runtime`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

统一媒体上传、处理、版本化交付、播放器终态和缓存并发控制，使 App 在四环境使用同一资产语义与恢复路径。

## 2. 范围与非目标

### In Scope

- publicSliceKey / MediaDeliveryReference 命名与 authority-only 交付
- App 图片负缓存与视频控制器槽位退出
- manifest 驱动的 canonical media Range/MIME、Dart define parity 与门禁
- alpha/beta/gamma-local/prod-sim 的本地 target preflight，以及 prod-hosted 三阶段 release canary 证据
- P0 progressive MP4/Range 安全 seek、1 小时时长边界、有效播放和 QoE/readback
- 独立准入的 P1-A storyboard 与 P1-B HLS/CMAF ABR

### Out of Scope

- 独立的视频剪辑、创作型转码策略和内容供给能力

## 3. Journey / Scenario 贡献

- [`JNY-004 / SCN-003`](../../spec.md#scn-003)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：四环境媒体交付、公开 slice key、播放器终态与防羊群验收，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。

## 4. Story



- [`group-avatar-server-precompose-and-unified-sync-contract`](./group-avatar-server-precompose-and-unified-sync-contract/spec.md)：**统一会话头像主链路**：`chat-service` 返回非空、可访问的 `avatarUrl`；单聊为对方用户头像，群聊先返回稳定默认头像，再由服务端异步预合成群头像并通过 sync patch 覆盖。
- [`media-upload-and-storage`](./media-upload-and-storage/spec.md)：上传完成持久化 `assetId`，重复 complete 返回同一 `MediaAsset` 并允许客户端继续发布。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 runtime media 交付与加载恢复 SIT

- 同一逻辑资产在四环境仅 authority 不同
- 404 负缓存阻止 rebuild 羊群
- VideoPlayer dispose 不泄漏槽位；槽满可退出失败态
- fixture/seed 媒体字段无环境字面量与 CAS path
- canonical public video 在每个已启动 target 返回 HTTPS、Range 206 与 video/* MIME；失败会阻断该 target 的 Patrol/UAT
- player ready 与可恢复/不可恢复失败分别有结构化、无 PII 证据

<a id="req-002"></a>
### REQ-002 VOD 权威描述符、P0 seek、独立增强、QoE 与有效播放分轨

- 内容视频以 `{assetId, assetVersion, processorProfile}` 幂等处理，并且只允许 `processing -> ready | rejected`。
- P0 只有真实 probe 验证过 H.264/AAC、时长、尺寸、GOP/keyframe、fast-start、hash 与 canonical video/cover slice 的 ready asset 可被 publish 和投影；seed 不得直接伪造 ready。
- 产品时长上限为 3600000ms；125000ms 资产用于 seek 回归，3605000ms 资产必须被超上限策略拒绝，同时保留接近一小时合法资产的边界验证。
- native duration 只用于 seek 边界和数据质量校验；超容差只产生一次去重事件/修复任务，不覆盖服务端权威值或伪装为播放失败。
- P0 拖动只更新虚拟 target，release 只提交一次 seek；切集/dispose 的过期 generation、buffering、ended/replay 和 seek failure 均有确定状态与结构化恢复。
- P1-A previewTrack、缓存 key、帧访问和取消均绑定 asset/version/profile/access policy；缺轨或预览失败退化为时间浮标，不阻断 P0。
- P1-B HLS/CMAF descriptor、rendition set、codec ladder、segment/keyframe、MIME/CORS/鉴权/cache-control 和平台 capability matrix 独立验收；ABR 关闭或失败时回退 P0。
- video_playback_qoe 只进入 Ops 强类型遥测，effective_play 只进入 content behavior；两条链路的字段、隐私和推荐消费者互不混用。
- alpha fixture bundle 在生成时校验其 media canary profile；`v1` 必须保持 ready 资产、版本、125000ms 时长、public slice 与 preview track 的同源描述，Alpha 证据仅标记为 contract-fixture smoke。

<a id="req-003"></a>
### REQ-003 统一媒体资产引用、处理状态与群头像交付边界

- `content-service` 的上传初始化与完成接口必须产出统一资产引用与明确处理状态，业务服务不得另造媒体对象。
- `user-service` 必须通过版本化头像引用和统一 sync patch 传播用户及群头像变化。
- 端侧只消费稳定的头像或媒体 URL 与统一 sync patch，不拼接 object key，也不根据成员头像自行生成群头像。
- 本能力负责统一媒体基线和群头像交付；内容编辑器、媒资运营与其他业务媒体流程由各自能力负责。
- 业务服务不得直接拼接 OSS/COS URL
- 客户端不得根据成员头像列表自行推导群头像
- 群头像链路必须支持灰度切换
- 必须保留通用图片加载错误态与诊断能力
- 必须具备回滚到“服务端保留上一版 `avatarUrl`、客户端仍只读 `avatarUrl`”的最小回滚路径
- 统一媒体运行时必须覆盖对象引用与 URL 规范，不止是“上传”

## 6. 契约与依赖

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 runtime media 交付与加载恢复 SIT

- GIVEN 执行“runtime media 交付与加载恢复”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“runtime media 交付与加载恢复”对应动作。
- THEN 同一逻辑资产在四环境仅 authority 不同
- THEN 404 负缓存阻止 rebuild 羊群
- THEN VideoPlayer dispose 不泄漏槽位；槽满可退出失败态
- THEN fixture/seed 媒体字段无环境字面量与 CAS path
- THEN canonical public video 在每个已启动 target 返回 HTTPS、Range 206 与 video/* MIME；失败会阻断该 target 的 Patrol/UAT
- THEN player ready 与可恢复/不可恢复失败分别有结构化、无 PII 证据

<a id="sit-002"></a>
### SIT-002 VOD 权威描述符、P0 seek、独立增强、QoE 与有效播放分轨

- GIVEN 执行“VOD 权威描述符、P0 seek、独立增强、QoE 与有效播放分轨”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“VOD 权威描述符、P0 seek、独立增强、QoE 与有效播放分轨”对应动作。
- THEN 内容视频以 `{assetId, assetVersion, processorProfile}` 幂等处理，并且只允许 `processing -> ready | rejected`。
- THEN P0 只有真实 probe 验证过 H.264/AAC、时长、尺寸、GOP/keyframe、fast-start、hash 与 canonical video/cover slice 的 ready asset 可被 publish 和投影；seed 不得直接伪造 ready。
- THEN 产品时长上限为 3600000ms；125000ms 资产用于 seek 回归，3605000ms 资产必须被超上限策略拒绝，同时保留接近一小时合法资产的边界验证。
- THEN native duration 只用于 seek 边界和数据质量校验；超容差只产生一次去重事件/修复任务，不覆盖服务端权威值或伪装为播放失败。
- THEN P0 拖动只更新虚拟 target，release 只提交一次 seek；切集/dispose 的过期 generation、buffering、ended/replay 和 seek failure 均有确定状态与结构化恢复。
- THEN P1-A previewTrack、缓存 key、帧访问和取消均绑定 asset/version/profile/access policy；缺轨或预览失败退化为时间浮标，不阻断 P0。
- THEN P1-B HLS/CMAF descriptor、rendition set、codec ladder、segment/keyframe、MIME/CORS/鉴权/cache-control 和平台 capability matrix 独立验收；ABR 关闭或失败时回退 P0。
- THEN video_playback_qoe 只进入 Ops 强类型遥测，effective_play 只进入 content behavior；两条链路的字段、隐私和推荐消费者互不混用。
- THEN alpha fixture bundle 生成会拒绝缺失或状态不匹配的 media canary profile，`v1` 的 asset/version/duration/public slice/preview track 保持同源；该结果不替代 Beta/Gamma Remote UAT。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 runtime media 交付与加载恢复 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：同一逻辑资产在四环境仅 authority 不同
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 VOD 权威描述符、P0 seek、独立增强、QoE 与有效播放分轨

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：内容视频以 `{assetId, assetVersion, processorProfile}` 幂等处理，并且只允许 `processing -> ready | rejected`。
- 完成判定：`SIT-002` 对应行为满足且真实测试 `spec_ref` 有效
