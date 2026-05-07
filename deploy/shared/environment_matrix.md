# 部署环境矩阵（五环境 · 一套代码）

> **总览**：正式环境语义统一为 **alpha → beta → gamma → prod-gray → prod**。`alpha` 与 `beta` 都是开发期本地验证；`gamma` 是云侧类生产集成验证；`prod-gray` 是准生产灰度；`prod` 是全量生产。
>
> **拓扑唯一源**：[`process_domain_mapping.yaml`](process_domain_mapping.yaml)。`beta`、`gamma`、`prod-gray`、`prod` 的 domain→进程映射必须一致，避免本地集成验证与云侧发布拓扑漂移。

## 1. 环境定义

| 环境 | 阶段语义 | 运行位置 | `APP_ENV` | 拓扑 | 端侧典型注入 |
|------|----------|----------|-----------|------|--------------|
| `alpha` | 单实例独立验证：端侧 App、云侧 service 各自独立跑通 | 开发机 / 模拟器 / 本机依赖 | `alpha` | 每个 domain 独立进程 | `APP_RUNTIME_ENV=alpha`；可用 `APP_DATA_SOURCE=mock` 或单服务网关 |
| `beta` | 本地端云集成验证：本机网关 + 多服务协同 | 开发机 / 局域网 / 模拟器 | `beta` | 与 `gamma/prod` 一致 | `APP_RUNTIME_ENV=beta`、`APP_DATA_SOURCE=remote` |
| `gamma` | 云侧类生产集成验证：ECS gamma pre + 本地 self-hosted 设备验证 | ECS / 公网入口 / 本地 Mac 设备 | `gamma` | 与 `beta/prod` 一致 | `APP_RUNTIME_ENV=gamma`、远端测试网关、测试 token |
| `prod-gray` | 准生产灰度：有限用户 / 有审批 / 可回滚 | 生产集群灰度阶段 | `prod-gray` | 与 `prod` 一致 | `APP_RUNTIME_ENV=prod-gray`、`APP_DATA_SOURCE=remote` |
| `prod` | 全量生产 | 生产集群 | `prod` | 全量生产拓扑 | `APP_RUNTIME_ENV=prod`、`APP_DATA_SOURCE=remote` |

**配置约束**：服务公开 `APP_ENV` 只允许 `alpha|beta|gamma|prod-gray|prod`，运行时只读取同名配置目录。禁止通过 `local` / `integration` 目录做兼容映射。

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
- `gamma` 服务端任意时刻只允许一套 ECS gamma 或一套 local-gamma mirror；并行只允许多个端侧实例同时接入同一套 gamma。
- 不得因本地脚本便利性把 beta 或 gamma 扩展成多套长期并行环境。

## 2. 波次关系

```text
alpha(本地单实例) → beta(本地端云集成) → gamma(ECS gamma + self-hosted device evidence)
                                                 → prod-gray(生产灰度) → prod(生产全量)
```

### 2.1 local-gamma mirror（提交前本地预测试）

`local-gamma mirror` 是提交前左移预测试拓扑，不是第六个环境，也不是 `main` 的 required check：

- 服务仍使用 `APP_ENV=gamma`，端侧仍使用 `APP_RUNTIME_ENV=gamma` 与 `APP_DATA_SOURCE=remote`。
- 测试数据只来自 `app_gamma_seed_manifest.json` 与 metadata fixtures，不新增 `app_local_gamma_seed_manifest.json`；当前 gamma manifest 允许指向 curated fixture 子集。
- 共享 `deploy/shared/gamma_validation_suites.json` 中的 suite 定义与报告字段。
- `make gate-local-gamma` 仍建议在提交前执行，但它只负责本地左移，不替代云侧 `04` / `05`。

#### 2.1.1 `make gate-local-gamma` 常见失败与缓解（Docker / 磁盘）

- **Docker Hub 429（未认证限流）**：`scripts/start_local_gamma_mirror.sh` 默认将基础镜像指向 `docker.m.daocloud.io/library`；ECS 侧对应变量为 `GAMMA_ECS_CONTAINER_REGISTRY_MIRROR`。
- **Colima / Docker VM 磁盘满**：执行 `docker builder prune -af`；避免将本地 `**/.venv/` 打进构建上下文。
- **本地 beta / local-gamma 端口冲突**：`gate-local-gamma` 默认使用 `18180/18186`，避免与 beta 常用 `18080` 冲突。

## 3. GitHub Actions Secrets / Variables（按工作流）

| Secret / Variable | 04 Pre-Release | 05 App Env Matrix | 07 Deploy Prod Auto | 08 Deploy Gamma ECS | 说明 |
|-------------------|:---:|:---:|:---:|:---:|------|
| `GAMMA_TEST_AUTH_TOKEN` | **必** | 建议 | — | **必** | gamma hosted/self-hosted 鉴权 |
| `GAMMA_ECS_PASSWORD` 或 `GAMMA_ECS_SSH_KEY` | **必其一** | — | — | **必其一** | ECS gamma SSH 认证 |
| `vars.GAMMA_ECS_HOST` / `vars.GAMMA_ECS_PUBLIC_HOST` | 建议 | — | — | 建议 | ECS 主机与公网入口 |
| `vars.GAMMA_BASE_URL` / `vars.GAMMA_PRODUCT_OPS_BASE_URL` | 可选 | 可选 | — | 可选 | 公网网关 / product ops 覆盖 |
| `vars.MEDIA_AVATAR_CDN_BASE_URL` | 可选 | 可选 | — | 可选 | chat-avatar 对外媒体基址 |
| `vars.GAMMA_ECS_MEDIA_ORIGIN_BASE_URL` | 可选 | — | — | 可选 | gamma-pre 临时本地公网回源地址；仅联调态使用 |
| `vars.GAMMA_ECS_CONTAINER_REGISTRY_MIRROR` | 建议 | — | — | 建议 | 缓解远端拉镜像命中 Docker Hub 限流 |
| `flutter devices --machine` 可见 Android 设备 | `04/05` **必** | **必** | — | `08` **必** | 主干 required checks 要求 Android 可见且全部通过 |
| `flutter devices --machine` 可见 iOS 设备 | `04/05` **必** | **必** | — | `08` **必** | 主干 required checks 要求 iOS 可见且全部通过 |
| Self-hosted Runner (`self-hosted` + `macOS`) | **必** | **必** | — | **必** | 统一运行在当前开发 Mac |
| GitHub Environment `production` | — | — | **必**（Stage 2） | — | `deploy-prod-auto.yml` 中 `gray-carry-on` 使用 |

**路由自检**：部署或调矩阵前运行  
`python3 scripts/verify_gamma_public_gateway_routing.py --base-url "$GAMMA_BASE_URL"`。  
若报 `route_not_found` 或 plain-text catch-all，说明入口指向错误端口，需要重新执行 ECS 部署或校验远端 Caddy/compose。

当前 gamma 默认走 ECS 本地 curated 媒体目录：部署前先生成 `deploy/shared/gamma_curated_media_bundle.json` 与 `artifacts/local-gamma/media`，再单独同步到远端 `/srv/media`。`GAMMA_ECS_MEDIA_ORIGIN_BASE_URL` 只作为应急兜底，且需显式允许后才会生效；默认不会依赖本机公网回源。

## 4. 推荐验证命令

| 环境 | 命令 / 条件 | 通过判据 |
|------|-------------|----------|
| `alpha` | 单服务 `APP_ENV=alpha go test ./...`；端侧 `flutter test` | 单实例用例绿 |
| `beta` | 本地启动单套网关与服务，App 注入 `APP_RUNTIME_ENV=beta` + `APP_DATA_SOURCE=remote` | 本地 Android/iOS 设备矩阵通过，且新启动前会 stop 旧 beta 栈 |
| `gamma` | `04` 触发 ECS gamma hosted pre 链 + 本地 gamma Android/iOS assistant/avatar/feed 旅程 | hosted/self-hosted 全绿并带证据，媒体抽样 URL 可达，且部署 / mirror 切换遵循单套重启 |
| `prod-gray` | 生产灰度流水线与 runbook 审批 | 灰度指标与回滚条件达标 |
| `prod` | 全量发布流水线 | 生产观测稳定 |

提交前本地左移：

| 范围 | 命令 / 条件 | 通过判据 |
|------|-------------|----------|
| `local-gamma mirror` | `make gate-local-gamma` | `T1/T2` 本地门禁、`T3` 本地真实 API/存储、`T4` 共享 gamma patrol/chat-avatar 旅程通过并生成 `artifacts/local-gamma/report.json` |

## 5. 相关文件索引

- [process_domain_mapping.yaml](process_domain_mapping.yaml)
- [process_domain_plane_mapping.yaml](process_domain_plane_mapping.yaml)
- [ci_cd_end_to_end_design.md](ci_cd_end_to_end_design.md)
- [branch_strategy.md](branch_strategy.md)
- [deliver_to_production_runbook.md](deliver_to_production_runbook.md)
- [gamma_validation_suites.json](gamma_validation_suites.json)
