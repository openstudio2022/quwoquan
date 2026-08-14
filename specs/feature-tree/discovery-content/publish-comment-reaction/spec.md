# L2 Business Capability：发布评论互动状态 (`publish-comment-reaction`)

> 所属领域：[`discovery-content`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

让用户创建和更新文字、照片或视频内容，完成本地图片编辑、评论、回复与反应，并让发布结果和互动状态在端云一致回流。

## 2. 范围与非目标

### In Scope

- 照片选择/拍摄、纯端侧像素编辑、MediaAsset 上传与发布回流。
- 内容详情、沉浸式内容和个人主页评论入口组合验证。
- 评论提交、回复、展开、赞踩与 post interaction 计数最终一致。
- Comment metadata、App Remote Facet、content-service contract 与 user_acceptance typed operation recipe 对齐；运行环境不读取 seed manifest。

### Out of Scope

- 推荐排序模型训练。
- 评论搜索、置顶、翻译。

## 3. Journey / Scenario 贡献

- [`JNY-003 / SCN-008`](../../spec.md#scn-008)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：publish-comment-reaction 能力级 SIT，验证文字/照片发布、图片本地编辑、评论、回复、反应计数、行为上报和端云状态协同，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。
- [`JNY-004 / SCN-001`](../../spec.md#scn-001)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：publish-comment-reaction 能力级 SIT，验证文字/照片发布、图片本地编辑、评论、回复、反应计数、行为上报和端云状态协同，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。
- [`JNY-004 / SCN-002`](../../spec.md#scn-002)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：publish-comment-reaction 能力级 SIT，验证文字/照片发布、图片本地编辑、评论、回复、反应计数、行为上报和端云状态协同，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。
- [`JNY-004 / SCN-003`](../../spec.md#scn-003)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：publish-comment-reaction 能力级 SIT，验证文字/照片发布、图片本地编辑、评论、回复、反应计数、行为上报和端云状态协同，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。

## 4. Story



- [`capture-metadata-disclosure`](./capture-metadata-disclosure/spec.md)：作者自己决定公开哪几类拍摄信息，关掉的那类彻底不再出现。
- [`comment-thread`](./comment-thread/spec.md)：Gamma 真机完成打开、评论、返回和二次进入。
- [`filter-catalog-release`](./filter-catalog-release/spec.md)：Mongo 真实引擎 contract 覆盖 digest 幂等、状态机和单 active CAS。
- [`image-editing`](./image-editing/spec.md)：全仓无占位符号；工具确认路径全部经 ImageEditorExportEngine 烘焙。
- [`post-create-update`](./post-create-update/spec.md)：从拍摄得到的图片可进入图片选择器底部缩略条或创作编辑器图片列表，并参与排序、编辑和发布。
- [`reaction-state-counter`](./reaction-state-counter/spec.md)：定义“互动状态状态计数”的可观察主路径、失败语义及父能力交接。
- [`text-post-commercial-publication`](./text-post-commercial-publication/spec.md)：micro 与 article 两种确认结果均有 widget 与 payload 合同证据。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 评论与内容互动能力端云组合 SIT

- 平铺文章入口完成内联定位，沉浸式入口完成上压分屏，个人主页评论可跳回原内容评论区。
- 评论创建、回复创建、回复分页、赞踩切换、删除/举报权限态都由云端契约驱动。
- postInteractionStateProvider 与 Comment state 在乐观更新和云端确认后保持最终一致。
- Alpha/Beta/Gamma 经真实测试账号和公开 API 生成 comments、replies、reaction、attachment、mentions，派生计数只由事件投影产生。

<a id="req-002"></a>
### REQ-002 写文字发布、安全准入、分发回流与运营观测组合 SIT

- LocalPostDraft 和 immutable PublishIntent 在断网、重启、限流与鉴权失效后保持可恢复。
- micro/article 由用户显式确认，发布命令经过长度、Persona 频控与安全门后才原子创建 Post。
- published receipt 只创建一个 Post，并立即回流详情或作品浏览器以及 feed/Persona 作品投影。
- tag/entity/location/circle 关联只来自可证实事实，circle placement 失败不重复发布。
- App 产品遥测、服务 RED、dashboard 和 alert 能对账三项黄金指标。
- `DeletedPostTombstone` 是独立且不可变的删除事实，删除保留期、作者与原因只由该对象定义；Post 不复制同名 type 或隐私口径。
- `GetPost` 在墓碑保留期内返回 canonical `CONTENT.USER.content_deleted`（HTTP 410），错误定义与真实 HTTP producer 双向绑定；保留期结束后才回落 404。
- 审核 pending、旧 revision 或 digest 不匹配通过 typed `PublicationEligibilitySlice` 返回 `eligible=false`，发布命令只使用真实可发射的 `publication_rejected`，不得保留未被任何 operation 发射的审核错误码。

<a id="req-003"></a>
### REQ-003 照片选择、像素编辑、MediaAsset 上传与发布回流组合 SIT

- 图片编辑器全部可见工具为真实像素实现；裁剪、旋转/翻转、颜色矩阵、局部径向调整、曲线、马赛克和文字共用 ImageEditorExportEngine。
- 滤镜目录只消费 active FilterCatalogRelease；在线更新、verified cache 离线重启和同源 bootstrap replica 均可验证。
- 编辑确认生成文件快照，撤销/重做/放弃保护可执行；完成后才把本地路径交给 MediaUploadSession。
- 发布 payload 只携带 MediaAsset ID，保持用户排序；失败不产生半成品 Post。
- gamma-local 用户可从选择/拍照进入编辑器，完成编辑、上传、发布并回读真实内容。

<a id="req-004"></a>
### REQ-004 配置统一：业务规则参数（字数限制/回复预览/回复展开/默认排序/附件上限/频控窗口）统一由 config.yaml 管理，端侧通过 App Config 同步

- **配置统一**：业务规则参数（字数限制/回复预览/回复展开/默认排序/附件上限/频控窗口）统一由 config.yaml 管理，端侧通过 App Config 同步
- 契约与字段策略必须引用所属服务 `contracts/`，不得复制 OpenAPI 或中心 metadata 作为第二真相源。
- 写文字创作漏斗属于产品遥测，不得伪装成推荐行为写入 `ReportBehaviors`。
- micro/article 可以由系统建议，但最终类型必须由用户在发布确认页显式确认。
- 评论域业务参数不允许硬编码，必须走 config.yaml 统一管理。
- 图片编辑器所有对用户可见的变换必须经 `ImageEditorExportEngine`；预览、导出与诊断必须读取同一编辑快照。
- 排序真相源唯一在服务端（hotScore 投影 + 复合索引）；禁止端侧重排、禁止旧三档 `recommended/latest/most_liked` 回归、禁止 Redis 排行第二真相源。

## 6. 契约与依赖

- 上游能力：[`discovery-content`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 评论与内容互动能力端云组合 SIT

- GIVEN 执行“评论与内容互动能力端云组合”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“评论与内容互动能力端云组合”对应动作。
- THEN 平铺文章入口完成内联定位，沉浸式入口完成上压分屏，个人主页评论可跳回原内容评论区。
- THEN 评论创建、回复创建、回复分页、赞踩切换、删除/举报权限态都由云端契约驱动。
- THEN postInteractionStateProvider 与 Comment state 在乐观更新和云端确认后保持最终一致。
- THEN alpha/beta/gamma seed 与 verifiedEndpoints 覆盖 comments、replies、reaction、attachment、mentions。

<a id="sit-002"></a>
### SIT-002 写文字发布、安全准入、分发回流与运营观测组合 SIT

- GIVEN 执行“写文字发布、安全准入、分发回流与运营观测组合”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“写文字发布、安全准入、分发回流与运营观测组合”对应动作。
- THEN LocalPostDraft 和 immutable PublishIntent 在断网、重启、限流与鉴权失效后保持可恢复。
- THEN micro/article 由用户显式确认，发布命令经过长度、Persona 频控与安全门后才原子创建 Post。
- THEN published receipt 只创建一个 Post，并立即回流详情或作品浏览器以及 feed/Persona 作品投影。
- THEN tag/entity/location/circle 关联只来自可证实事实，circle placement 失败不重复发布。
- THEN App 产品遥测、服务 RED、dashboard 和 alert 能对账三项黄金指标。
- THEN 删除后读取在墓碑保留期内稳定返回 410 `content_deleted`，服务重启后语义不变；Post contract 不再声明第二份 `DeletedPostTombstone`。
- THEN 当前 revision 的审核资格由 typed Slice 表达，pending 或 stale 只得到 `eligible=false`，不会伪造成成功发布，也不会产生无 producer 的错误码。

<a id="sit-003"></a>
### SIT-003 照片选择、像素编辑、MediaAsset 上传与发布回流组合 SIT

- GIVEN 执行“照片选择、像素编辑、MediaAsset 上传与发布回流组合”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“照片选择、像素编辑、MediaAsset 上传与发布回流组合”对应动作。
- THEN 图片编辑器全部可见工具为真实像素实现；裁剪、旋转/翻转、颜色矩阵、局部径向调整、曲线、马赛克和文字共用 ImageEditorExportEngine。
- THEN 滤镜目录只消费 active FilterCatalogRelease；在线更新、verified cache 离线重启和同源 bootstrap replica 均可验证。
- THEN 编辑确认生成文件快照，撤销/重做/放弃保护可执行；完成后才把本地路径交给 MediaUploadSession。
- THEN 发布 payload 只携带 MediaAsset ID，保持用户排序；失败不产生半成品 Post。
- THEN gamma-local 用户可从选择/拍照进入编辑器，完成编辑、上传、发布并回读真实内容。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 评论与内容互动能力端云组合 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：平铺文章入口完成内联定位，沉浸式入口完成上压分屏，个人主页评论可跳回原内容评论区。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 写文字发布、安全准入、分发回流与运营观测组合 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`。
- 目标：LocalPostDraft 和 immutable PublishIntent 在断网、重启、限流与鉴权失效后保持可恢复。
- 完成判定：`SIT-002` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-003"></a>
### OPEN-003 照片选择、像素编辑、MediaAsset 上传与发布回流组合 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺 gamma-local 真实环境「选择/拍照→编辑→上传→发布→回读」
  user_acceptance 证据，等待环境窗口。已落地：图片编辑器可见工具全部真实
  像素实现且共用 `ImageEditorExportEngine`，由 image-editing REQ-005 及其
  local_contract 承载；图/视频「上传 init/complete→处理 ready→发布准入→
  另一 viewer 作品 feed 可见→详情媒体可读」组合联程与「媒体未 ready
  发布 fail-closed 返回 media_not_ready、ready 后同 publishIntentId 重试
  成功」轮询契约均有真实进程 api_integration，见
  `post_media_lifecycle_journey__api_integration_test.go`。
- 完成判定：`SIT-003` 对应行为满足且真实测试 `spec_ref` 有效
