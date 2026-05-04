# 部署环境矩阵（五环境 · 一套代码）

> **总览**：正式环境语义统一为 **alpha → beta → gamma → prod-gray → prod**。`alpha` 与 `beta` 都是开发期本地验证；`gamma` 是云侧类生产集成验证；`prod-gray` 是准生产灰度；`prod` 是全量生产。
> **拓扑唯一源**：[`process_domain_mapping.yaml`](process_domain_mapping.yaml)。`beta`、`gamma`、`prod-gray`、`prod` 的 domain→进程映射必须一致，避免本地集成验证与云侧发布拓扑漂移。
> **Pipeline 细节**：[ci_cd_end_to_end_design.md](ci_cd_end_to_end_design.md)、[deliver_to_production_runbook.md](deliver_to_production_runbook.md)。

---

## 1. 环境定义

| 环境 | 阶段语义 | 运行位置 | `APP_ENV` | 拓扑 | 端侧典型注入 |
|------|----------|----------|-----------|------|--------------|
| `alpha` | 单实例独立验证：端侧 App、云侧 service 各自独立跑通 | 开发机 / 模拟器 / 本机依赖 | `alpha` | 每个 domain 独立进程 | `APP_RUNTIME_ENV=alpha`；可用 `APP_DATA_SOURCE=mock` 或指向单服务网关 |
| `beta` | 本地端云集成验证：本机网关 + 多服务协同 | 开发机 / 局域网 / 模拟器 | `beta` | 与 `gamma/prod` 一致 | `APP_RUNTIME_ENV=beta`、`APP_DATA_SOURCE=remote`、`CLOUD_GATEWAY_BASE_URL=http://127.0.0.1:18080`（iOS）或宿主机地址 |
| `gamma` | 云侧类生产集成验证：CI / 混生产前验证 | 云侧集群 | `gamma` | 与 `beta/prod` 一致 | `APP_RUNTIME_ENV=gamma`、远端测试网关、测试 token |
| `prod-gray` | 准生产灰度：有限用户 / 有审批 / 可回滚 | 生产集群灰度阶段 | `prod-gray` | 与 `prod` 一致 | `APP_RUNTIME_ENV=prod-gray`、`APP_DATA_SOURCE=remote` |
| `prod` | 全量生产 | 生产集群 | `prod` | 全量生产拓扑 | `APP_RUNTIME_ENV=prod`、`APP_DATA_SOURCE=remote` |

**配置约束**：服务公开 `APP_ENV` 只允许 `alpha|beta|gamma|prod-gray|prod`，并且运行时只读取同名配置目录，例如 `APP_ENV=beta` 读取 `configs/beta/config.yaml`。禁止通过 `local` / `integration` 目录做兼容映射。

---

## 2. 波次关系

```text
alpha(本地单实例) → beta(本地端云集成) → gamma(云侧类生产集成)
                                           → prod-gray(生产灰度) → prod(生产全量)
```

1. **alpha**：验证单个 App 页面、单个 Go/Python service、单个 Repository 或 fixture，不要求完整端云链路。
2. **beta**：开发完成前的本地端云闭环，必须能证明 App 通过本地网关访问云侧服务。
3. **gamma**：CI 或云侧集成集群验证，配置版本、镜像版本、Secret、观测与回滚条件必须齐备。
4. **prod-gray/prod**：由 `gray_rollout_stages.yaml` 和生产 runbook 控制；灰度未完成前不得视为全量生产。

### 2.1 local-gamma mirror（提交前本地预测试）

`local-gamma mirror` 是提交前本地预测试拓扑，不是第六个环境：

- 服务仍使用 `APP_ENV=gamma`，端侧仍使用 `APP_RUNTIME_ENV=gamma` 与 `APP_DATA_SOURCE=remote`。
- 本机通过 Docker 镜像栈、DNS/TLS 反代与 `gamma-*.quwoquan-env.test` 域名映射承载 App 流量。
- 测试数据只来自 `app_gamma_seed_manifest.json` 与 metadata fixtures，不新增 `app_local_gamma_seed_manifest.json`。
- 提交前必须完成本地 `T1 -> T4` 左移覆盖，并输出 `artifacts/local-gamma/report.json`。
- 本地通过不替代云侧 gamma、prod-gray、prod；云侧仍负责 K8s、Ingress/LB、Secret、云观测、灰度 SLO 与回滚真实性验证。

#### 2.1.1 `make gate-local-gamma` 常见失败与缓解（Docker / 磁盘）

- **Docker Hub 429（未认证限流）**：`scripts/start_local_gamma_mirror.sh` 默认将 local-gamma 基础镜像指向 `docker.m.daocloud.io/library`；如需直连 Docker Hub，可设置 `LOCAL_GAMMA_DOCKER_LIBRARY_PREFIX=docker.io/library`，或分别覆盖 `LOCAL_GAMMA_GO_ALPINE_BASE_IMAGE`、`LOCAL_GAMMA_PYTHON_BASE_IMAGE` 等镜像变量。ECS 侧见 Variables `GAMMA_ECS_CONTAINER_REGISTRY_MIRROR`（见下表）。
- **Colima / Docker VM 磁盘满**：执行 `docker builder prune -af`；避免将本地 `**/.venv/` 打进构建上下文（仓库已含 [`quwoquan_service/.dockerignore`](../../quwoquan_service/.dockerignore)，勿删）。
- **本地 beta 端口冲突**：`make gate-local-gamma` 默认使用 `LOCAL_GAMMA_HTTP_PORT=18180`、`LOCAL_GAMMA_PRODUCT_OPS_PORT=18186`，避免与 beta 手动网关常用 `18080` 冲突；如需固定指定端口，可显式导出 `LOCAL_GAMMA_HTTP_PORT` / `LOCAL_GAMMA_GATEWAY_BASE_URL`。
- **门禁文案**：`scripts/verify_retired_terms_zero.py` 扫描全仓文本，环境矩阵等文档避免使用退役词表中的用语（见脚本内 `TERMS`）。

---

## 3. GitHub Actions Secrets / Variables（按工作流）

### 3.1 各工作流必填对照

| Secret / Variable | 04 Pre-Release | 05 App Env Matrix | 07 Deploy Prod Auto | 08 Deploy Gamma ECS | 说明 |
|-------------------|:---:|:---:|:---:|:---:|------|
| `GAMMA_BASE_URL` | 必（gamma 冒烟、L3、L4） | 建议 | — | 可选（vars 可覆盖 URL） | gamma **网关**基址；须指向 **gamma-proxy（Caddy）**，勿用单服务直出端口冒充网关 |
| `GAMMA_PRODUCT_OPS_BASE_URL` | 必（L3/L4） | 可选 | — | 可选 | Ops/产品面 API |
| `GAMMA_TEST_AUTH_TOKEN` | 必（L3/L4） | 建议 | — | 必（T3 / probe / 矩阵） | 测试鉴权 |
| `GAMMA_KUBECONFIG` | 可选 | — | — | — | **base64** kubeconfig；未设置时 `deploy-integration` 跳过 apply（见 workflow） |
| `GAMMA_ECS_PASSWORD` 或 `GAMMA_ECS_SSH_KEY` | — | — | — | **必**其一 | SSH 部署 ECS onebox |
| `vars.GAMMA_ECS_HOST` / `GAMMA_ECS_PUBLIC_HOST` 等 | — | — | — | 建议 | 主机与 URL 解析，见 `deploy-gamma-ecs.yml` |
| `vars.GAMMA_ECS_CONTAINER_REGISTRY_MIRROR` | — | — | — | 建议 | 缓解远端 `docker compose pull` 命中 Hub 限流 |
| `vars.GAMMA_ECS_IMAGE_PULL_TIMEOUT_SECONDS` 等 | — | — | — | 可选 | 拉镜像 / compose 超时 |
| `vars.MEDIA_AVATAR_CDN_BASE_URL` | — | — | — | 可选 | chat-avatar 矩阵媒体基址 |
| `flutter devices --machine` 可见移动设备 | — | — | — | **必** | self-hosted 设备矩阵以当前 Mac 上可见的 Android/iOS 模拟器或真机为准；至少一台可见才能通过发现阶段 |
| Self-hosted Runner | — | **必** | — | **必** | 统一使用当前开发 Mac 注册的 `self-hosted` + `macOS` runner；不再依赖自定义设备标签，见 [ci_cd_end_to_end_design.md](ci_cd_end_to_end_design.md) §4.3、§4.4 |
| GitHub Environment `production` | — | — | **必**（Stage 2） | — | `deploy-prod-auto.yml` 中 `gray-carry-on` 使用；须在仓库 Settings → Environments 创建并配置审批策略，见 [deploy_prod_design.md](deploy_prod_design.md) §1.4 |

### 3.2 与 gamma 网关相关的 Secrets（沿用表）

| 变量 / Secret | 用途 |
|---------------|------|
| `GAMMA_BASE_URL` | gamma **网关**基址，必须指向 **gamma-proxy（Caddy）** 公网端口（`docker-compose.gamma-local.yaml` 中 `LOCAL_GAMMA_HTTP_PORT`→容器 80），**不得**误用仅映射 `content-service` 的 `LOCAL_GAMMA_CONTENT_PORT`（默认 `18083`） |
| `GAMMA_PRODUCT_OPS_BASE_URL` | gamma 上 Ops/产品面 API 基址 |
| `GAMMA_TEST_AUTH_TOKEN` | gamma L3/L4 鉴权 |
| `GAMMA_KUBECONFIG` | **integration** 集群 kubeconfig（**base64**）；`pre-release-gate.yml` 的 `deploy-integration` 使用此名；未配置则跳过 kubectl apply |
| `GAMMA_ECS_PASSWORD` | gamma ECS SSH 密码（`deploy-gamma-ecs.yml`；与 `GAMMA_ECS_SSH_KEY` 二选一即可） |
| `GAMMA_ECS_SSH_KEY` | gamma ECS SSH 私钥（与密码二选一） |

**路由自检（阿里云 ECS / 任意公网 gamma 入口）**：部署或调矩阵前运行  
`python3 scripts/verify_gamma_public_gateway_routing.py --base-url "$GAMMA_BASE_URL"`。  
若报「plain-text catch-all」或 `CONTENT.USER.route_not_found`，说明 `GAMMA_BASE_URL` 指到了错误端口或远端 `deploy/local-gamma/Caddyfile` 与仓库当前版本不一致，需重新执行 `scripts/deploy_gamma_ecs.sh` 或对齐 compose 挂载。

新增流水线、脚本与测试只使用 `GAMMA_*`。记录期 staging / integration 命名不再作为配置入口。

---

## 4. 推荐验证命令

| 环境 | 命令 / 条件 | 通过判据 |
|------|-------------|----------|
| `alpha` | 单服务 `APP_ENV=alpha go test ./...`；端侧 `flutter test` | 单实例用例绿 |
| `beta` | 本地启动网关与服务，App 注入 `APP_RUNTIME_ENV=beta` + `APP_DATA_SOURCE=remote` | 模拟器完成端云交互 |
| `gamma` | `make gate` + gamma 部署构建；有 URL/token 时运行 L3/L4 | 云侧 contract/e2e 通过 |
| `prod-gray` | 生产灰度流水线与 runbook 审批 | 灰度指标与回滚条件达标 |
| `prod` | 全量发布流水线 | 生产观测稳定 |

提交前本地左移新增推荐：

| 范围 | 命令 / 条件 | 通过判据 |
|------|-------------|----------|
| `local-gamma mirror` | `make gate-local-gamma` | `T1/T2` 本地门禁、`T3` 本地真实 API/存储、`T4` 本地模拟器/真机 Patrol 通过并生成 `artifacts/local-gamma/report.json` |

---

## 5. 相关文件索引

- [process_domain_mapping.yaml](process_domain_mapping.yaml)
- [process_domain_plane_mapping.yaml](process_domain_plane_mapping.yaml)
- [ci_cd_end_to_end_design.md](ci_cd_end_to_end_design.md)
- [branch_strategy.md](branch_strategy.md)
- [deliver_to_production_runbook.md](deliver_to_production_runbook.md)
