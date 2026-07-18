# 视频创作—分发—播放 商用端到端全矩阵规格

## 目标（不打折扣声明）

「商用端到端全矩阵完成」指：**在下列环境的每一种运行形态下**，均能产出可追溯、非占位、可与同一业务锚点（如 `postId` / `videoRef` / `mediaAssetId`）关联的 **服务端证据 + 端侧 UI 证据**，且矩阵内 **无一缺项**。  
Dry-run / CI 契约回归 / 本地 mock onebox **不计入**该结论；它们只能支撑「工程就绪」或「功能准出」，不能替代商用矩阵 passed。

本规格与 [`avatar-e2e-validation.md`](../runtime-messaging/reliable-async-task-channel/avatar-e2e-validation.md) 口径一致：**任一必选环境缺少 passed 报告 → `GATE_BLOCK`，不得宣称商用端到端全矩阵完成。**  
内容图片的并行矩阵见 [`image-end-to-end-commercial-matrix.md`](./image-end-to-end-commercial-matrix.md)（声明边界独立，均须各自四条环境齐备方可解除对应 `GATE_BLOCK`）。

## 环境矩阵（必选）

环境真相源为 [`environment_topology_manifest.yaml`](../../../../quwoquan_ops/environments/environment_topology_manifest.yaml)：

| 环境 | 运行 target | 必须验证（视频） | 准出要求 |
| --- | --- | --- | --- |
| `alpha` | `alpha-local` | publicSliceKey、typed resolver、播放器失败/恢复契约、本地 CA preflight、fixture Range/MIME | 工程与功能准出，不作为商用矩阵最终证明 |
| `beta` | `beta-local` | InitUpload → PUT → Complete → ready → publish → Feed/详情播放；Android/iOS 真机或模拟器 | 至少一端非 dry-run passed；发布前覆盖 Android 与 iOS |
| `gamma` | `gamma-local` | `APP_DATA_SOURCE=remote`、真实 gateway/media authority、上传后 publicSliceKey 投影、Feed/详情播放器 ready | 结构化非 dry-run 报告 passed |
| `prod` | `prod-hosted` 的 `gray-initial` | 已发布 release playback canary、真实 public CDN、Feed/详情播放、失败恢复与回滚观测 | canary 失败阻断 `carry-on`/`full` rollout |

`prod-sim` 仅是 `prod` 语义下的本地演练 target，不能替代 `prod-hosted` 生产证据；`gray-initial`、`carry-on`、`full` 是 prod rollout stage，不是额外环境。远端 gamma 已退役，不再使用 `cloud-gamma-pre` 或 `cloud-gamma-prod-smoke` 作为验收对象。

## 核心场景（最小闭环）

下列步骤须在 **beta / gamma-local / prod-hosted gray-initial** 中至少各跑通一次；alpha 覆盖同构的本地契约与 CA preflight（可按环境裁剪观测深度，不得裁剪「真实远端 + 真实 UI」）：

1. **上传事务**：InitUpload → 客户端 PUT → CompleteUpload → **Poll/Get** 直至资产就绪（含转码任务语义若启用）。
2. **封面合同**：默认首帧或用户手工选帧必须落为远端可访问的 `thumbnailUrl` / 同源 `coverUrl`；报告需记录 `coverStrategy`、`coverFrameTimeMs`（若手工选帧）和封面资源锚点。
3. **发帖**：CreateDraft / PublishPost（或等价 API）仅携带稳定 `mediaAssetId` 与展示元数据；服务端绑定后投影 `publicSliceKey`、视频首帧或手工封面，禁止持久化 upload URL、CAS key 或瞬时签名 URL。
4. **分发**：Feed / 会话卡片等入口可见预览；未播放态必须展示 `thumbnailUrl` 或同源 `coverUrl`，不得展示无关 seed 图、作者头像、地点图或把 `videoUrl` 当图片 URL；**viewport / 静音策略**与详情页一致且不误导（参见既有播放器与 Feed UX 契约）。
5. **播放**：详情页完整播放；弱网下至少记录一次 **缓冲/失败/恢复** 的可观测证据（可与 `t4-release-rehearsal.md` 中 VOD 项对齐）。
6. **多端**：同一帖子在第二设备或第二账号可见一致引用（至少在 gamma-local 与 prod-hosted gray-initial 中覆盖）。

## 证据与报告口径

- **禁止**：`pending`、`pending_device_lab`、`placeholder`、`dry-run` 报告作为商用矩阵 passed 依据。
- **必须**：每条报告含环境（网关 base、media base、`commitSha` / `githubRunId`）、设备维度、`postId`/`videoRef` 锚点、服务端摘录（任务状态或 API 摘录，按最小侵入原则）、UI 摘录（截图或结构化断言导出）。
- **统一 schema**：优先复用群头像 E2E 报告的顶层字段约定（`schema`、`scenario`、`status`、`environment`、`serviceEvidence`、`uiEvidence`、`steps`）；视频场景下扩展 `media`/`post` 块，而非另起互不兼容格式；禁止数字/后缀协议版本身份。
- **`make gate-runtime-media-full`**：会校验 runtime-media 文档包、既定自动化门禁，以及 `RUNTIME_MEDIA_T4_EVIDENCE` 的非 dry-run 视频 T4 schema（target/stage、commit/config、publicSliceKey、Range/MIME、播放器 ready 与截图/报告）；**不**等价于本节全矩阵完成。

## 本轮视频封面工程闭环边界

本轮视频创作与展示开发的准出目标是把 App / Service / Data 三路视频封面收敛到同一合同：

- 创作者默认首帧或手工选帧后，发布 payload、Post、DiscoveryFeed、WorkBrowser media item 均可表达 `videoUrl + thumbnailUrl/coverUrl`。
- 首页、视频卡、作品浏览器和沉浸播放器未播放态只消费该合同，不做端侧临时抽帧，也不使用无关图片兜底。
- 数据工程 video manifest 和 service importer 与用户上传视频使用同一封面字段与 gate。

这些自动化、契约和本地/集成验证只代表**工程闭环**。在 beta、gamma-local、prod-hosted gray-initial 的非 dry-run 报告与 alpha 的本地 CA/播放器契约均齐备前，本文件的商用全矩阵状态仍为 `GATE_BLOCK`。

## 仓库内可自动化闭环（不冒充商用矩阵）

下列可在 **无 ECS、无 self-hosted 设备** 的会话中持续执行，用于阻断回归与保持工程诚实：

- `make gate-runtime-media`（含 sync/chat avatar 契约、图片策略静态门禁等，见 [`automation-gates.md`](./automation-gates.md)）。
- Content / runtime 相关 **`go test`**、Flutter **`flutter test`** 中与视频上传、播放器、Feed 预览绑定的契约测试（以仓库当前 `gate`/`pre-release` 引用为准）。
- **Dry-run** 形态的矩阵脚本演练（若有）：仅验证脚本与 artifact 路径，**明确标注**不得计入商用矩阵。

## 依赖外部资源的闭环（商用矩阵必要条件）

完成「商用端到端全矩阵」**还必须**同时具备：

| 依赖 | 用途 |
| --- | --- |
| 可达的 **beta / gamma-local** 网关与媒体域名 | 非 localhost 占位 |
| `prod-hosted` 分平面凭证、release playback canary 与 rollout 编排 | `gray-initial` 阻断与发布后 smoke |
| **Self-hosted Android / iOS** runner（或等价受控设备农场） | 非 dry-run 设备矩阵 |
| 对象存储与（若适用）转码外链路就绪 | Complete 之后真实就绪语义 |

缺失任一依赖时：**矩阵结论保持 `GATE_BLOCK`。**

## 当前执行证据与环境前提（2026-07-16 修订）

**环境**：beta 与 gamma 只使用各自本地 target；远端验证归 `prod-hosted` 的 `gray-initial` rollout。设备侧使用本机或 self-hosted Runner 上的 Flutter/Patrol；所有 media authority 必须从 topology 注入，禁止手写 `GAMMA_BASE_URL` 或单一 media base。

在 **`beta-local`、`gamma-local`、`prod-hosted(gray-initial)`** 均未产出与 alpha CA/播放器契约相对应的 **非 dry-run** 可追溯报告前：

- **状态**：`GATE_BLOCK` — **不得**宣称「视频商用端到端全矩阵完成」。
- **已完成**：仅限仓库内契约、静态门禁与文档口径冻结（含本文件）；不以替代环境与设备证据。
- **下一步（执行队列，需在具备凭据与设备后逐项勾掉）**：
  1. 对齐环境巡检：**target health → device-matrix → Patrol ready → evidence schema** 四条链路，产出视频专用 `scenario` 与同构 JSON。
  2. 在 beta/gamma-local 各跑通一轮完整上传—发布—双端播放，归档报告路径写入 acceptance / CR。
  3. 在 `prod-hosted gray-initial` 跑 release playback canary；失败必须停止 rollout 并执行回滚核查。
  4. 将弱网失败/恢复、用户文案与回滚动作写入同一 T4 演练证据，不允许 curl 或 dry-run 替代播放器 ready。

仅在上述队列 **全部**产出真实 passed 报告后，方可移除本节 `GATE_BLOCK` 声明（由责任人更新本文「当前执行证据」段落的日期与条目）。
