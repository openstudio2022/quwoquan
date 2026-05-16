# 内容图片—上传—自适应—原图授权 商用端到端全矩阵规格

## 目标（不打折扣声明）

「商用端到端全矩阵完成」指：**在下列环境的每一种运行形态下**，均能产出可追溯、非占位、可与同一业务锚点（如 `postId` / `mediaId` / `imageId`）关联的 **服务端证据 + 端侧 UI 证据**，且矩阵内 **无一缺项**。  
Dry-run / CI 契约回归 / 本地 mock onebox **不计入**该结论；它们只能支撑「工程就绪」或「功能准出」，不能替代商用矩阵 passed。

本规格与 [`avatar-e2e-validation.md`](../runtime-messaging/reliable-async-task-channel/avatar-e2e-validation.md)、[`video-end-to-end-commercial-matrix.md`](./video-end-to-end-commercial-matrix.md) 口径一致：**任一必选环境缺少 passed 报告 → `GATE_BLOCK`，不得宣称商用端到端全矩阵完成。**

## 环境矩阵（必选）

| 环境 | 运行形态 | 必须验证（内容图片） | 准出要求 |
| --- | --- | --- | --- |
| `alpha` | 本地/CI；fixture/mock 或最小 remote | `MediaAsset` 字段契约、`RequestOriginalImageAccess`、`AppImage`/URL 策略静态门禁 | **不作为**商用全矩阵最终证明 |
| `beta` | 本地 beta stack + Android/iOS **真实 runner** | 选图 → `InitMediaUpload` → PUT → `CompleteMediaUpload` → **GetMediaAsset**（含 `lqip`/`contentProfile`/`derivativePolicyVersion`/派生语义）→ 发帖 → feed/详情/沉浸 viewer **AppImage 路径** → （授权场景）`original:access` → 打开或合理错误态 | 至少一端 passed；发布前应覆盖 Android **与** iOS |
| `local-gamma` | 本地 Docker gamma mirror + seed | `APP_DATA_SOURCE=remote`、网关/media、content 上传与帖子 wire 投影一致；**结构化 JSON 报告 passed（非 dry-run）** | 与 [`local-gamma-mirror`](../deliver-deploy-prod-pipeline/local-gamma-mirror/) Runbook 对齐 |
| `cloud-gamma-pre` | CI：`cloud-gamma-pre`（ECS pre + **self-hosted** 设备矩阵或等价农场） | 真实 `GAMMA_BASE_URL`、真实媒体加载与原图授权链路；阻断 prod 前置 | pre 失败不得进入 prod |
| `cloud-gamma-prod-smoke` | ECS prod 就地升级后 smoke | 发布链路 + feed/详情/沉浸 + 原图授权降级与限流/拒绝可观测 | smoke failed 必须阻断发布完成结论 |

## 核心场景（最小闭环）

下列步骤须在 **beta / local-gamma / cloud-gamma-pre / cloud-gamma-prod-smoke** 中至少各跑通一次（可按环境裁剪观测深度，不得裁剪「真实远端 + 真实 UI」）：

1. **上传事务**：`InitMediaUpload` → 客户端 PUT → `CompleteMediaUpload` → **GetMediaAsset** 直至图片交付元数据齐备（含 `dominantColor`/`lqip`/`contentProfile`/`derivativePolicyVersion` 及派生语义；若管线异步则 poll 直至就绪或明确失败态）。
2. **发帖**：创建/发布帖子携带稳定 `mediaId`（及展示 URL 语义），避免仅靠客户端裸拼接 CDN。
3. **分发与自适应**：Feed / 圈子 / 搜索等入口经 **`AppImage` / `ImageUrlResolver` 路径**加载；带 `cw`/`ch`/`dpr`/网络档位的 URL 决策在弱网下可观测（日志或截屏摘要）。
4. **原图授权**：对允许原图的资产调用 `POST .../original:access`，验收授权 URL、拒绝（403）、限流（429）之一与产品预期一致；过期/篡改签名须可解释。
5. **多端**：同一帖子在第二设备或第二账号可见一致引用（至少在 gamma-pre smoke 中覆盖）。

## 证据与报告口径

- **禁止**：`pending`、`pending_device_lab`、`placeholder`、`dry-run` 报告作为商用矩阵 passed 依据。
- **必须**：每条报告含环境（网关 base、media base、`commitSha` / `githubRunId`）、设备维度、`postId`/`mediaId` 锚点、服务端摘录（资产状态或 API 摘录，最小侵入）、UI 摘录（截图或结构化断言导出）。
- **统一 schema**：复用群头像 E2E 报告的顶层字段约定（`schemaVersion`、`scenario`、`status`、`environment`、`serviceEvidence`、`uiEvidence`、`steps`）；图片场景扩展 `media`/`post`/`originalAccess` 块，不与现有格式冲突。
- **`make gate-runtime-media` / `make gate-runtime-media-full`**：**不**等价于本节全矩阵完成（与视频矩阵声明一致）。

## 仓库内可自动化闭环（不冒充商用矩阵）

在无 ECS 凭据、无 self-hosted Android/iOS 的会话中仍须持续执行，用于阻断回归与保持工程诚实：

- `make gate-runtime-media`（含图片策略静态门禁等，见 [`automation-gates.md`](./automation-gates.md)）。
- `go test`（`content-service` 媒体/原图访问契约）、Flutter `flutter test`（如 `post_summary_view_test`、`AppImage` 相关契约）。
- **Dry-run** 形态的矩阵脚本演练：仅验证脚本与 artifact 路径，**明确标注**不得计入商用矩阵。

**前置自检（不替代四条 JSON）**：

```bash
python3 scripts/check_image_commercial_matrix_prereqs.py --strict
```

## 依赖外部资源的闭环（商用矩阵必要条件）

| 依赖 | 用途 |
| --- | --- |
| 可达的 **beta / gamma** 网关与媒体域名 | 非 localhost 占位 |
| **ECS / 云前置** 凭证与流水线（`cloud-gamma-pre`、`prod-smoke`） | pre 阻断与发布后 smoke |
| **Self-hosted Android / iOS** runner（或等价设备农场） | 非 dry-run 设备矩阵 |
| 对象存储与 CDN（及图片处理外链路若启用） | Complete 之后真实就绪语义 |

缺失任一依赖时：**矩阵结论保持 `GATE_BLOCK`。**

## 执行队列（具备凭据与设备后逐项勾掉）

下列顺序与 [`commercial-e2e-matrix-runbook.md`](../runtime-messaging/reliable-async-task-channel/commercial-e2e-matrix-runbook.md) 同构；**图片**专用 `scenario` 建议在证据 JSON 中固定为 `content.image.upload_display_original_e2e`（或与脚本最终约定一致，全仓库单一真相）。

| 序号 | 阶段 | 产出 | 责任边界 |
| --- | --- | --- | --- |
| Q0 | 工程与文档 | 本文件 + `acceptance.yaml` J4 + 门禁引用齐全 | 研发 |
| Q1 | **local-gamma** 非 dry-run | 双端（或矩阵）JSON：上传—发帖—feed/沉浸—原图 | 研发 + 运维（镜像） |
| Q2 | **beta** 非 dry-run | 同上，对接 beta 网关与 seed | 研发 |
| Q3 | **cloud-gamma-pre** | CI artifact：probe + device JSON，`status=passed` | 平台 + 运维 |
| Q4 | **cloud-gamma-prod-smoke** | 升级后 smoke JSON；失败条款进发布 Runbook | 运维 + 研发值班 |
| Q5 | 归档 | 四条证据路径写入本段「当前执行证据」与 CR / `tasks.md` | 发布负责人 |

**待补齐自动化（当前仓库gap，不计入矩阵 passed 直至落地）**：

- 与 `run_chat_avatar_e2e_probe.py` / `run_chat_avatar_device_matrix*.py` 同级的 **content 图片** probe + device 矩阵脚本（入参、artifact 目录与 workflow 对齐需单独 PR）。
- CI workflow 中挂载 `matrix_kind: content-image`（或等价）与 self-hosted 设备池。

## 当前执行证据与环境前提（2026-05-03 修订）

**环境定义（与仓库对齐）**：

- **云端**：阿里云 ECS onebox 由 `agent_ops/deploy/gamma/deploy_gamma_ecs.sh` 与 [`.github/workflows/deploy-gamma-ecs.yml`](../../../../.github/workflows/deploy-gamma-ecs.yml) 驱动；默认公网宿主参见 `agent_ops/deploy/gamma/deploy_gamma_ecs.sh` 中的 `GAMMA_ECS_HOST`。
- **self-hosted 端侧**：可为 **开发者本机**（`flutter devices` 含 Android/iOS）或注册为 `self-hosted` 的 GitHub Runner，与手册 [`commercial-e2e-matrix-runbook.md`](../runtime-messaging/reliable-async-task-channel/commercial-e2e-matrix-runbook.md) 一致。
- **关键**：`GAMMA_BASE_URL` 必须指向 **gamma-proxy（Caddy）** 端口（compose 中 `LOCAL_GAMMA_HTTP_PORT`，ECS 常见 `18000`），并先用 `quwoquan_service/scripts/gamma/verify_gamma_public_gateway_routing.py` 验证 `/v1/chat`、`/v1/content` 已反代；误用 content 直出端口会得到 `route_not_found` 或 Caddy 占位明文，**不能**作为矩阵 passed 依据。

**诚实结论**：本节不宣称「全矩阵已完成」——须按 Q1–Q4 归档四条环境 **非 dry-run** JSON+UI 证据后方得解除 `GATE_BLOCK`。此前结论若写「仅因无 ECS 即无法矩阵」为**表述过时**，应以 **URL/路由是否正确 + 证据是否齐备** 为准。
