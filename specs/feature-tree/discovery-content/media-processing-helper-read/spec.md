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
- Data 发布侧的媒体存储基线：作为 CDN 四档即时变换输入的存储体准入语义，以及以单对象存储预算为准的对象级体量准入与其对象级终态。
- 上传侧与发布侧的组合约束：两侧共用同一份四档 profile 定义，各自的准入判据、判定时点与失败终态互相独立。

### Out of Scope

- 文章摘要生成由 helper-read-summary 独立 Story 验收。
- HLS/DASH ABR 在 feature flag 关闭时不属于首发交付。
- 单对象存储预算的逐载体数值：本能力只消费该预算而不认领它，其规格 owner 为 [`multi-carrier-release`](../object-homepage-coverage-scaling/multi-carrier-release/spec.md#req-012) 的 `REQ-012`；发布侧判定形态的缺口见 [`image-delivery-variants`](./image-delivery-variants/spec.md) 的 `OPEN-006`。
- 归一化衍生体的格式、重编码质量、EXIF/ICC 去留与源体摘要落点：本能力当前只支持 passthrough，四项裁决见 [`image-delivery-variants`](./image-delivery-variants/spec.md) 的 `OPEN-007`。
- 批次级零合格原因值：发布侧只产出对象级排除码，批次终态原因归 [`multi-carrier-release`](../object-homepage-coverage-scaling/multi-carrier-release/spec.md) 所有。

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

<a id="req-003"></a>
### REQ-003 上传侧与发布侧共用同一批 profile 定义，准入判据与终态各自独立

- 本能力同时服务两条路径：Service 上传侧把 completed 上传推进到 ready 或 rejected 并物化归一化公开切片；Data 发布侧把已过权利与质量准入的源体作为 CDN 四档即时变换的输入送进 immutable release。两条路径除四档 profile 定义外不共享任何判据。
- 四档参数只有一个来源，即 `quwoquan_service/services/content-service/contracts/media/media_asset/image_variant_policy.yaml`。上传侧派生公开切片与发布侧投影有效交付宽度都从该来源解析，任一侧都不得自建 profile 常量、复制档位表或按用途改写档位。
- 两侧的准入判据不得互相推导，也不得互相放宽。上传侧的解码、方向归一与像素守卫由 `REQ-001` 独占，本 REQ 不复制也不改写；发布侧只判存储体可解码性与对象级体量，既不承载上传侧守卫，也不因源体曾经通过上传侧而跳过自身判定。
- 两侧的失败终态互不传染。上传侧 rejected 只终结该 MediaAsset，不使任何发布对象 blocked；发布侧的对象级 blocked 只终结该对象，不改写任何 MediaAsset 的 ready 状态或已冻结 descriptor。
- 发布侧的体量准入以对象闭包为单位，在对象进入 immutable release 之前构成准入而不是事后报告；逐资产层不承载体量封顶。度量口径与逐载体预算数值由既有门禁单点拥有，本能力只消费，不新建第二套体量口径。
- 发布侧只产出对象级终态与对象级排除码。批次级零合格原因归 [`multi-carrier-release`](../object-homepage-coverage-scaling/multi-carrier-release/spec.md) 的 `REQ-006` 闭集所有，本能力不新增批次级原因值，两层以引用衔接而不复制。

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

<a id="sit-002"></a>
### SIT-002 上传侧与发布侧共用同一批 profile 定义且判据互不推导

- GIVEN 同一份 active ImageVariantPolicy 的四档定义、一个走 Service 上传侧推进到终态的图片 MediaAsset，以及一个走 Data 发布侧进入对象闭包的源体。
- WHEN 两侧各自执行本侧准入并解析该 policy。
- THEN 两侧解析到的四档参数逐档相同且来自同一个声明来源，任一侧都不存在独立档位常量、复制的档位表或按用途改写的档位。
- THEN 上传侧对该图片执行解码、方向归一与像素守卫之后才 ready，发布侧对源体只判可解码性与对象级体量，两侧判据互不调用也互不推导。
- THEN 上传侧 rejected 不使任何发布对象 blocked，发布侧的对象级 blocked 也不改写任何 MediaAsset 的 ready 状态或已冻结 descriptor。
- THEN 发布侧对被拦下的对象只产出对象级排除码，不产出批次级零合格原因值。

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

<a id="open-003"></a>
### OPEN-003 上传侧与发布侧的组合约束尚无同时观察两侧的证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：当前两侧各自只被自己的 Story 验收覆盖，没有任何测试同时观察「四档参数只有一个来源」「两侧判据互不推导」「两侧终态互不传染」这三件事。缺该证据时，发布侧新增判据可以悄悄读取上传侧守卫、或反过来让上传侧因为发布侧的对象级 blocked 改写 ready 状态，而两侧各自的既有测试都不会失败。发布侧准入本身尚未落地，因此该组合面在它落地之前无法整体取证。
- 完成判定：`SIT-002` 的全部结果子句成立且有真实测试 `spec_ref`。
- 依赖：先由 [`image-delivery-variants`](./image-delivery-variants/spec.md) 的 `OPEN-006` 落地发布侧存储基线与对象级体量准入，本 SIT 才有发布侧终态可观察。证据层分派为——四条结果子句全部由 `local_contract` 承接：档位同源以两侧各自的解析入口读同一份 policy 声明并逐档比对，判据互不推导以对象级 typed double 让一侧判据缺席时另一侧结论不变，终态互不传染以「上传侧 rejected」与「发布侧对象级 blocked」两个终态各构造一次并断言对侧不变，排除码值域以断言发布侧排除条目取不到批次级零合格原因闭集的任何值。本 SIT 不改变 App 用户可见终态，因此不追加 `user_acceptance`；四环境消费证据继续由 [`image-delivery-variants`](./image-delivery-variants/spec.md) 的 `OPEN-005` 承接。
