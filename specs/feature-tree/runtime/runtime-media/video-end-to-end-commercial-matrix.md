# 视频创作—分发—播放 商用端到端全矩阵规格

## 目标（不打折扣声明）

「商用端到端全矩阵完成」指：**在下列环境的每一种运行形态下**，均能产出可追溯、非占位、可与同一业务锚点（如 `postId` / `videoRef` / `mediaAssetId`）关联的 **服务端证据 + 端侧 UI 证据**，且矩阵内 **无一缺项**。  
Dry-run / CI 契约回归 / 本地 mock onebox **不计入**该结论；它们只能支撑「工程就绪」或「功能准出」，不能替代商用矩阵 passed。

本规格与 [`avatar-e2e-validation.md`](../runtime-messaging/reliable-async-task-channel/avatar-e2e-validation.md) 口径一致：**任一必选环境缺少 passed 报告 → `GATE_BLOCK`，不得宣称商用端到端全矩阵完成。**  
内容图片的并行矩阵见 [`image-end-to-end-commercial-matrix.md`](./image-end-to-end-commercial-matrix.md)（声明边界独立，均须各自四条环境齐备方可解除对应 `GATE_BLOCK`）。

## 环境矩阵（必选）

| 环境 | 运行形态 | 必须验证（视频） | 准出要求 |
| --- | --- | --- | --- |
| `alpha` | 本地/CI；fixture/mock 或最小 remote | 上传策略、DTO/codegen、播放器契约、图片 URL 策略门禁 | **不作为**商用全矩阵最终证明 |
| `beta` | 本地 beta stack + Android/iOS **真实 runner**（模拟器或真机） | 选素材 → init upload → PUT → complete → **poll 转码就绪** → publish → 多端 pull feed → 预览与详情播放 | 至少一端 passed；发布前应覆盖 Android **与** iOS |
| `local-gamma` | 本地 Docker gamma mirror + seed-box onebox | `APP_DATA_SOURCE=remote`、gateway/media base、content 上传与帖子投影一致 | 结构化报告 **passed**（非 dry-run） |
| `cloud-gamma-pre` | CI：`cloud-gamma-pre`（ECS pre + **self-hosted** 设备矩阵入口） | 真实 `GAMMA_BASE_URL`、真实网关与媒体加载、阻断 prod 前置 | pre 失败不得进入 prod |
| `cloud-gamma-prod-smoke` | ECS prod 就地升级后 smoke | 发布链路 + feed + 详情播放 + 关键降级路径可观测 | smoke failed 必须阻断发布完成结论 |

## 核心场景（最小闭环）

下列步骤须在 **beta / local-gamma / cloud-gamma-pre / cloud-gamma-prod-smoke** 中至少各跑通一次（可按环境裁剪观测深度，不得裁剪「真实远端 + 真实 UI」）：

1. **上传事务**：InitUpload → 客户端 PUT → CompleteUpload → **Poll/Get** 直至资产就绪（含转码任务语义若启用）。
2. **发帖**：CreateDraft / PublishPost（或等价 API）携带稳定 `videoRef`（及封面），避免仅靠瞬时 URL。
3. **分发**：Feed / 会话卡片等入口可见预览；**viewport / 静音策略**与详情页一致且不误导（参见既有播放器与 Feed UX 契约）。
4. **播放**：详情页完整播放；弱网下至少记录一次 **缓冲/失败/恢复** 的可观测证据（可与 `t4-release-rehearsal.md` 中 VOD 项对齐）。
5. **多端**：同一帖子在第二设备或第二账号可见一致引用（至少在 gamma-pre smoke 中覆盖）。

## 证据与报告口径

- **禁止**：`pending`、`pending_device_lab`、`placeholder`、`dry-run` 报告作为商用矩阵 passed 依据。
- **必须**：每条报告含环境（网关 base、media base、`commitSha` / `githubRunId`）、设备维度、`postId`/`videoRef` 锚点、服务端摘录（任务状态或 API 摘录，按最小侵入原则）、UI 摘录（截图或结构化断言导出）。
- **统一 schema**：优先复用群头像 E2E 报告的顶层字段约定（`schemaVersion`、`scenario`、`status`、`environment`、`serviceEvidence`、`uiEvidence`、`steps`）；视频场景下扩展 `media`/`post` 块，而非另起互不兼容格式。
- **`make gate-runtime-media-full`**：仍仅代表 runtime-media **文档包 + 既定自动化门禁 + `RUNTIME_MEDIA_T4_EVIDENCE`**；**不**等价于本节全矩阵完成。

## 仓库内可自动化闭环（不冒充商用矩阵）

下列可在 **无 ECS、无 self-hosted 设备** 的会话中持续执行，用于阻断回归与保持工程诚实：

- `make gate-runtime-media`（含 sync/chat avatar 契约、图片策略静态门禁等，见 [`automation-gates.md`](./automation-gates.md)）。
- Content / runtime 相关 **`go test`**、Flutter **`flutter test`** 中与视频上传、播放器、Feed 预览绑定的契约测试（以仓库当前 `gate`/`pre-release` 引用为准）。
- **Dry-run** 形态的矩阵脚本演练（若有）：仅验证脚本与 artifact 路径，**明确标注**不得计入商用矩阵。

## 依赖外部资源的闭环（商用矩阵必要条件）

完成「商用端到端全矩阵」**还必须**同时具备：

| 依赖 | 用途 |
| --- | --- |
| 可达的 **beta / gamma** 网关与媒体域名 | 非 localhost 占位 |
| **ECS / 云前置** 凭证与流水线编排（`cloud-gamma-pre`、`prod-smoke`） | pre 阻断与发布后 smoke |
| **Self-hosted Android / iOS** runner（或等价受控设备农场） | 非 dry-run 设备矩阵 |
| 对象存储与（若适用）转码外链路就绪 | Complete 之后真实就绪语义 |

缺失任一依赖时：**矩阵结论保持 `GATE_BLOCK`。**

## 当前执行证据与环境前提（2026-05-03 修订）

**环境**：视频矩阵与群头像相同，依赖 **阿里云 ECS gamma onebox**（见 `deploy_gamma_ecs.sh`）与 **本机或 self-hosted Runner** 上的 Flutter/Patrol；`GAMMA_BASE_URL` 必须为 **Caddy 网关端口**。路由自检：`python3 quwoquan_service/scripts/gamma/verify_gamma_public_gateway_routing.py`。

在 **`beta`、`local-gamma`、`cloud-gamma-pre`、`cloud-gamma-prod-smoke`** 四项均未产出 **非 dry-run** 可追溯报告前：

- **状态**：`GATE_BLOCK` — **不得**宣称「视频商用端到端全矩阵完成」。
- **已完成**：仅限仓库内契约、静态门禁与文档口径冻结（含本文件）；不以替代环境与设备证据。
- **下一步（执行队列，需在具备凭据与设备后逐项勾掉）**：
  1. 对齐群头像矩阵：**probe → device-matrix → local-gamma runner → CI workflow** 四条链路，产出视频专用 `scenario` 与同构 JSON。
  2. 在 beta/local-gamma 各跑通一轮完整上传—发布—双端播放，归档报告路径写入 acceptance / CR。
  3. 接入 `cloud-gamma-pre`：ECS + self-hosted 矩阵绿灯后方可解除 pre 阻断语义。
  4. `cloud-gamma-prod-smoke`：升级后脚本化 smoke，失败条款与回滚证据写入发布 Runbook。

仅在上述队列 **全部**产出真实 passed 报告后，方可移除本节 `GATE_BLOCK` 声明（由责任人更新本文「当前执行证据」段落的日期与条目）。
