# 部署环境矩阵（多环境拓扑 · 一套代码）

> **总览**：正式环境语义统一为 **alpha → beta → gamma → prod**。当前冻结拓扑为 **`alpha-local / beta-local / gamma-local / prod-hosted`**。`alpha` / `beta` / `gamma` 都是本地验证（`gamma` 仅本地快速集成 mirror，已无远端 gamma）；唯一远端/hosted 目标是 `prod-hosted`（backend SSH 托管，gray 与 full 因成本共享同一集群）。真实远端集成与 curated 媒体路由复验由 prod `gray-initial` rollout stage 承接。`prod` 是全量生产（**灰度放量与回滚由云侧发布策略、观测与自动回滚在 prod 语义下完成，不单独拆分环境名**）。
>
> **拓扑唯一源**：
> - 领域/进程归属：[`process_domain_mapping.yaml`](process_domain_mapping.yaml)
> - 环境 topology / public bases / subnet / artifact policy：[`environment_topology_manifest.yaml`](environment_topology_manifest.yaml)
> - 本地 host 暴露端口：[`local_env_port_manifest.yaml`](local_env_port_manifest.yaml)

## 1. 环境定义

| 环境 | 阶段语义 | 运行位置 | `APP_ENV` | 拓扑 | 端侧典型注入 |
|------|----------|----------|-----------|------|--------------|
| `alpha` | 单实例独立验证：端侧 App、云侧 service 各自独立跑通 | 开发机 / 模拟器 / 本机依赖 | `alpha` | 每个 domain 独立进程 | `APP_RUNTIME_ENV=alpha`；可用 `APP_DATA_SOURCE=mock` 或单服务网关 |
| `beta` | 本地端云集成验证：本机网关 + 多服务协同 | 开发机 / 局域网 / 模拟器 | `beta` | 与 `gamma/prod` 一致 | `APP_RUNTIME_ENV=beta`、`APP_DATA_SOURCE=remote` |
| `gamma` | 本地快速集成验证：local-gamma mirror + 本地 self-hosted 设备验证（仅本地，无远端 gamma） | 本机容器编排 / 本地 Mac 设备 | `gamma` | 与 `beta/prod` 一致 | `APP_RUNTIME_ENV=gamma`、本地 mirror 网关、测试 token |
| `prod` | 全量生产（含按计划灰度与放量） | 生产集群 | `prod` | 全量生产拓扑 | `APP_RUNTIME_ENV=prod`、`APP_DATA_SOURCE=remote` |

**配置约束**：服务公开 `APP_ENV` 只允许 `alpha|beta|gamma|prod`，运行时只读取同名配置目录。禁止通过 `local` / `integration` 目录做兼容映射。

## 1.0 自动推进主链

`main` 入库后的权威主链固定为：

```text
repo verify/package
  -> alpha-local
  -> beta-local
  -> prod-hosted(gray-initial)
  -> prod-hosted(carry-on/checks)
  -> prod-hosted(full)
```

约束：

- `alpha-local` 与 `beta-local` 保持本地 topology，不新增 hosted beta。
- 远端/hosted 目标只有 `prod-hosted`；`gamma` 仅本地（`gamma-local` 用于提交前 local-gamma mirror），不存在远端 gamma-hosted 阶段。
- 旧 `gamma-hosted` 阻断阶段已退役，其承担的真实远端集成与 curated 媒体路由复验下沉到 `prod-hosted(gray-initial)`。
- `prod-hosted(gray-initial|carry-on|full)` 都属于同一个 `prod` 环境生命周期，不得抽象成 `prod-gray` 或额外环境名。
- `mainline_auto_prod` blocking critical path 必须 `<= 900s`。

## 1.0 环境真相源与官方入口

统一口径：

- 当前环境集合都必须声明完整 `edge / media / service / data` 子网、public base、host allowlist、artifact policy 与 mock boundary。
- `alpha` 不是“删平面”的简化环境，而是“拓扑同构但边界 mock”。
- 本地 host 暴露端口必须来自 `deploy/shared/local_env_port_manifest.yaml` 的 1000 端口块 + plane + 10 端口槽位模型。
- 官方自动化入口统一为 `agent_ops/deploy/stackctl.py`（包装脚本：`agent_ops/deploy/stackctl.sh` / `agent_ops/deploy/stackctl`）。底层脚本可保留，但只作为实现细节。
- GitHub Actions、Cursor skill、runbook 与手动命令都必须复用同一套 `stackctl` 子命令，不得复制第二套健康检查、探针或回滚语义。

## 1.0.1 Artifact Policy

| 环境 | App 包 | Service 包 | host allowlist | 纯度约束 |
|---|---|---|---|---|
| `alpha` | `APP_RUNTIME_ENV=alpha`、`APP_DATA_SOURCE=mock` | 允许 fixture/mock boundary | 仅本机/模拟器 host | 允许 seed manifest，不允许 prod host |
| `beta` | `APP_RUNTIME_ENV=beta`、`APP_DATA_SOURCE=remote` | 允许本地联调 fixture | 仅本机/模拟器 host | 不允许 prod host；允许 beta local artifact |
| `gamma` | `APP_RUNTIME_ENV=gamma`、`APP_DATA_SOURCE=remote` | 仅 local-gamma mirror 使用 gamma 语义（无远端 gamma） | 本机/局域网 mirror host | 不允许 prod host 落入 gamma artifact |
| `prod` | `APP_RUNTIME_ENV=prod`、`APP_DATA_SOURCE=remote` | 只读取 `prod` config / release snapshot | 仅正式生产域名 | 禁止 mock/seed/debug/local/test host 与跨环境 artifact 污染 |

## 1.1 多实例与单套服务口径

| 维度 | alpha | beta | gamma |
|---|---|---|---|
| 端侧不同模拟器并行 | 支持 | 支持 | 支持 |
| 端侧同一模拟器多包安装 | 不在当前交付范围 | 不在当前交付范围 | 不在当前交付范围 |
| 云侧多套并行 | 不作为当前目标 | 禁止 | 禁止 |
| 启动新实例前 stop 旧栈 | 仅在涉及本地服务时适用 | 必须 | 必须（部署或 mirror 切换） |

统一口径：

- 端侧“多实例”仅指多个 App 进程可在**不同模拟器**并行运行。
- `beta` 服务端任意时刻只允许一套本地集成栈，新启动前必须停止旧栈并回收固定端口。
- `gamma` 服务端任意时刻只允许一套 local-gamma mirror（无远端 gamma）；并行只允许多个端侧实例同时接入同一套 local-gamma。
- 不得因本地脚本便利性把 beta 或 gamma 扩展成多套长期并行环境。

## 1.1.1 主链 profile 分层

`deploy/shared/gamma_validation_suites.json` 是多环境 promotion 期间 local-gamma / self-hosted 验证 profile 的唯一真相源（已无远端 gamma profile；远端真实集成复验由 prod `gray-initial` 承接）：

| Profile | 主要触发位置 | 作用 |
|---|---|---|
| `pr_light` | `04` / `05` PR 默认 | 轻量收敛，不承担 `main` 后自动 promotion |
| `manual_full` | 手动 | 手动完整 local-gamma 复验 |
| `nightly_full` | `09` | 每晚完整 local-gamma + self-hosted 全量验证 |
| `release_candidate` | 手动发布前 | 发布前高置信度回归 |
| `mainline_auto_prod` | `07` | `main` 自动 promotion 的高信号阻断链 |

设计要求：

- `mainline_auto_prod` 必须只保留能证明端云正确性的最小阻断链，避免 Patrol/full semantic 把主链拖出 900 秒预算。
- full semantic、Patrol、全设备全旅程继续留在 `nightly_full` / `release_candidate`。

## 1.2 本地端口 Profile

| Profile | 端口块 | API Edge | Product Ops Edge | Media Edge | Media Origin | 示例服务槽位 |
|---|---:|---:|---:|---:|---:|---|
| `alpha-local` | `17000-17999` | `17000` | `17010` | `17100` | `17110` | `chat-service=17200`、`assistant-service=17230` |
| `beta-local` | `18000-18999` | `18000` | `18010` | `18100` | `18110` | `chat-service=18200`、`assistant-service=18230` |
| `gamma-local` | `19000-19999` | `19000` | `19010` | `19100` | `19110` | `content-service=19220`、`user-service=19210` |
| `prod-sim` | `20000-20999` | `20000` | `20010` | `20100` | `20110` | 仅用于本地 prod 演练，不新增环境枚举 |

规则：

- canonical host 端口必须以 `0` 结尾。
- plane 间不得串用槽位。
- 脚本和 CLI 只读 manifest，不允许继续手写 `18080/18088/18180` 一类常量作为官方默认值。

## 2. 波次关系

```text
alpha(本地单实例) → beta(本地端云集成) → gamma(local-gamma mirror + self-hosted evidence，仅本地)
                                                 → prod(gray-initial → carry-on/checks → full)
```

说明：

- `alpha` 与 `beta` 可在自有阶段内尽量并行；`gamma` 仅本地左移，不在远端阻断链上，远端只有 `prod` 各 rollout stage 必须严格串行。
- `prod gray-initial` 后必须完成 `health + inspect + doctor + integration probes + SLO gate`（含承接自旧 gamma-hosted 的远端集成与 curated 媒体路由复验），才允许自动进入 `prod full`。
- `prod full` 失败时必须自动回滚到上一稳定 `image/config`。
- 当前 rootless `prod-hosted` service plane 的对外 host 端口固定为：`gray-initial=29000/29010/29100/29110`（TLS/Admin=`28443/22019`），`full=19000/19010/19100/19110`（TLS/Admin=`18443/12019`）；必须通过 `render_prod_plane_stack.py` 与 `prod_plane_access_isolation.yaml` 渲染，禁止手写 compose / Caddy 端口。
- 当前共享 ECS 仅 `2G` 内存，`gray-initial` 是短驻验证命名空间，不是长期并存形态；拿到 `health + inspect + doctor + SLO` 证据并完成 `full` 切换后，应及时回收 gray 命名空间。需要与旧 root 数据面短时共存时，Mongo 必须显式使用 `wiredTigerCacheSizeGB=0.25`，避免 OOM 杀进程。

### 2.1 local-gamma mirror（提交前本地预测试）

`local-gamma mirror` 是提交前左移预测试拓扑，不是额外环境，也不是 `main` 的 required check：

- 服务仍使用 `APP_ENV=gamma`，端侧仍使用 `APP_RUNTIME_ENV=gamma` 与 `APP_DATA_SOURCE=remote`。
- 测试数据只来自 `app_gamma_seed_manifest.json` 与 metadata fixtures，不新增 `app_local_gamma_seed_manifest.json`；当前 gamma manifest 允许指向 curated fixture 子集。
- 共享 `deploy/shared/gamma_validation_suites.json` 中的 suite 定义与报告字段。
- `make gate-local-gamma` 仍建议在提交前执行，但它只负责本地左移，不替代云侧 `04` / `05`。

#### 2.1.1 `make gate-local-gamma` 常见失败与缓解（Docker / 磁盘）

- **Docker Hub 429（未认证限流）**：`quwoquan_app/scripts/gamma/start_local_gamma_mirror.sh` 默认将基础镜像指向 `docker.m.daocloud.io/library`。
- **Colima / Docker VM 磁盘满**：执行 `docker builder prune -af`；避免将本地 `**/.venv/` 打进构建上下文。
- **本地 beta / local-gamma 端口冲突**：统一由 `local_env_port_manifest.yaml` 分配；当前 beta 使用 `18000/18010/18100`，local-gamma 使用 `19000/19010/19100`，禁止再手写旧常量规避冲突。

## 3. GitHub Actions Secrets / Variables（按工作流）

> 远端/hosted 目标只有 `prod-hosted`；prod 发布统一走按平面 SSH 私钥（`PROD_EDGE_SSH_KEY` / `PROD_MEDIA_SSH_KEY` / `PROD_SERVICE_SSH_KEY`），不再使用任何 `GAMMA_ECS_*` secret/var，也不再接受 `PROD_KUBECONFIG`。`gamma` 仅本地（local-gamma），默认 URL 从 topology 解析，不需要远端 secret。

| Secret / Variable | 04 Pre-Release | 05 App Env Matrix | 07 Deploy Prod Auto | 说明 |
|-------------------|:---:|:---:|:---:|------|
| `GAMMA_TEST_AUTH_TOKEN` | 建议 | 建议 | — | local-gamma / self-hosted 链路鉴权（04 pr_light 非强制） |
| `gamma_base_url` workflow input / 本地环境变量覆盖 | 可选 | 可选 | — | 仅在需要覆盖 topology `gamma-local.publicBases.api` 时使用 |
| `vars.MEDIA_AVATAR_CDN_BASE_URL` | 可选 | 可选 | — | chat-avatar 对外媒体基址 |
| `secrets.PROD_EDGE_SSH_KEY` / `PROD_MEDIA_SSH_KEY` / `PROD_SERVICE_SSH_KEY` | — | — | **必** | prod-hosted 发布三平面读写 SSH 私钥 |
| `flutter devices --machine` 可见 Android 设备 | `04/05` **必** | **必** | — | 主干 required checks 要求 Android 可见且全部通过 |
| `flutter devices --machine` 可见 iOS 设备 | `04/05` **必** | **必** | — | 主干 required checks 要求 iOS 可见且全部通过 |
| Self-hosted Runner (`self-hosted` + `macOS`) | **必** | **必** | — | 统一运行在当前开发 Mac |
| GitHub Environment `production` | — | — | **必**（Stage 2） | `deploy-prod-auto.yml` 中 `gray-carry-on` 使用 |

curated 媒体目录与公网路由复验已下沉到 prod `gray-initial` rollout stage：在 `prod-hosted(gray-initial)` 阶段对真实远端入口做集成与 curated 媒体路由检查；本地 local-gamma mirror 只在本机校验同构媒体路径，不依赖任何远端 gamma 入口。

## 4. 推荐验证命令

| 环境 | 命令 / 条件 | 通过判据 |
|------|-------------|----------|
| `alpha` | 单服务 `APP_ENV=alpha go test ./...`；端侧 `flutter test` | 单实例用例绿 |
| `beta` | `python3 agent_ops/deploy/stackctl.py up --env beta`；App 注入 `APP_RUNTIME_ENV=beta` + `APP_DATA_SOURCE=remote` | 本地 Android/iOS 设备矩阵通过，且新启动前会 stop 旧 beta 栈 |
| `gamma-local` | `python3 agent_ops/deploy/stackctl.py up --env gamma` | local-gamma mirror + App 达到 steady state，并生成 `artifacts/local-gamma/report.json` / `artifacts/stackctl/gamma/**` |
| `prod-hosted`（唯一远端目标） | `python3 agent_ops/deploy/stackctl.py deploy --target prod-hosted --service <svc> --from-image <old> --to-image <new> --from-config <old_cfg> --to-config <new_cfg> --step <step> --error-rate <rate> --p95-ms <ms> --redis-error-rate <rate>` | `prod gray-initial -> carry-on/checks -> full` 按 rollout stage 自动推进；`gray-initial` 承接真实远端集成与 curated 媒体路由复验；失败自动回滚；关键路径不超过 900 秒 |

### 4.1 开发者一键启动

日常本地端云联调统一使用：

```bash
make dev-up ENV=<alpha|beta|gamma|prod-sim|prod> [DEVICE_ID=<flutter-device-id>]
```

等价官方入口：

```bash
python3 agent_ops/deploy/stackctl.py up --env <alpha|beta|gamma|prod-sim|prod> [--device-id <id>]
```

### 4.2 prod-hosted rollout stage（唯一远端发布路径）

旧 `gamma-hosted` 三模式（`restart / rollout / cold-build`）已随远端 gamma 退役而移除。当前唯一远端发布路径是 `prod-hosted`，走 `gray-initial / carry-on / full` rollout stage，不暴露三模式命令。

统一约束：

- `gray-initial`：初始灰度，全自动 deploy → 健康/只读集成探针 → SLO gate；同时承接旧 gamma-hosted 的真实远端集成与 curated 媒体路由复验。
- `carry-on`：在 `gray-initial` 通过后按审批推进到更大放量（含 checks）。
- `full`：全量放量；失败自动回滚到上一稳定 `image/config`。

推荐命令：

```bash
python3 agent_ops/deploy/stackctl.py deploy --target prod-hosted --service <svc> --from-image <old> --to-image <new> --from-config <old_cfg> --to-config <new_cfg> --step <step> --error-rate <rate> --p95-ms <ms> --redis-error-rate <rate>
```

说明：

- `deploy --target prod-hosted` 成功后会自动串联 `health --scope full`、`inspect --scope all`、`doctor`，每个 rollout stage 留下机器可读证据。
- prod-hosted 为 backend SSH 托管，gray 与 full 因成本共享同一集群；这是有意保留的共享集群拓扑，不抽象成 `prod-gray` 第二环境。
- 本轮已验证的 gray/full 证据分别见 `artifacts/stackctl/prod/20260617T164119Z-deploy-prod-hosted`（`gray-initial` 成功，`4/4 healthy`）与 `artifacts/stackctl/prod/20260617T172537Z-deploy-prod-hosted`（`full` 成功，`4/4 healthy`，doctor 无问题）。

约束：

- 用户面只允许选择 **环境** 与 **端侧设备**；gateway / media / seed / host 不作为一键启动独立参数暴露。
- `gamma` 的一键启动指 `gamma-local` mirror（gamma 仅本地，无远端 gamma）；远端/hosted 只有 `prod-hosted`，走 `stackctl deploy --target prod-hosted`。
- `prod` 的一键启动不在本地 `up` 服务栈，只做 `prod-hosted` edge health 检查后拉起本地 App/浏览器连接已部署云端。
- `--target` 保留给 hosted 运维、CI / runbook / 高级调试；开发者本地联调优先使用 `--env`。

提交前本地左移：

| 范围 | 命令 / 条件 | 通过判据 |
|------|-------------|----------|
| `local-gamma mirror` | `make gate-local-gamma` / `python3 agent_ops/deploy/stackctl.py up --env gamma` | `T1/T2` 本地门禁、`T3` 本地真实 API/存储、`T4` 共享 gamma patrol/chat-avatar 旅程通过并生成 `artifacts/local-gamma/report.json` |

## 5. 相关文件索引

- [process_domain_mapping.yaml](process_domain_mapping.yaml)
- [process_domain_plane_mapping.yaml](process_domain_plane_mapping.yaml)
- [ci_cd_end_to_end_design.md](ci_cd_end_to_end_design.md)
- [branch_strategy.md](branch_strategy.md)
- [deliver_to_production_runbook.md](deliver_to_production_runbook.md)
- [gamma_validation_suites.json](gamma_validation_suites.json)

## 6. 推荐模型服务环境变量

| 变量 | 说明 | alpha/beta | gamma | prod |
|------|------|------------|-------|------|
| `REC_MODEL_SERVICE_URL` | rec-model-service 内网地址 | `http://rec-model-service:8000`（compose） | config.yaml 硬编码 | `${REC_MODEL_SERVICE_URL}` 注入 |
| `CONFIG_ROOT` | 版本化配置根目录 | 镜像内默认 `/app`；本地 compose 可不显式注入 | `/etc/seed-box-config`（initContainer 组装） | `/etc/seed-box-config` |
| `CONFIG_VERSION` | 配置版本 | 可空 | release-state / workflow input | workflow input |
| `IMAGE_VERSION` | 镜像版本 | 可空 | release-state / workflow input | workflow input |
| `MONGODB_DATABASE` | 训练 / registry 数据库 | `quwoquan_content` | `quwoquan_content` | `quwoquan_content_training`（训练） |
| `MODEL_ARTIFACT_ENDPOINT` | S3/MinIO/OSS endpoint | 本地 MinIO 或留空 | CI Secret | CI Secret |
| `MODEL_ARTIFACT_BUCKET` | 模型制品桶名 | `quwoquan-models` | `quwoquan-models` | `quwoquan-models` |
| `MODEL_ARTIFACT_ACCESS_KEY` | OSS Access Key | 本地 MinIO key | CI Secret | Secret |
| `MODEL_ARTIFACT_SECRET_KEY` | OSS Secret Key | 本地 MinIO secret | CI Secret | Secret |
| `MODEL_CACHE_DIR` | 模型本地缓存目录 | `/app/cache` | `/app/cache` | `/app/cache` |
| `MONGODB_URI` | 训练管线读取 events/samples | `mongodb://127.0.0.1:27017/?directConnection=true`（本地 dry-run / compose） | CI Secret `GAMMA_MONGODB_URI` | 生产 MongoDB |

### 实验配置（experiments block in config.yaml）

| 实验 | gamma | prod |
|------|-------|------|
| `rec_model_vs_rule` | rule:50 / model:50 | rule:90 / model:10 |
| `rec_scoring_weights` | control:60 / engagement_heavy:15 / freshness_heavy:15 / explore_heavy:10 | control:80 / 其余各 5~10 |
