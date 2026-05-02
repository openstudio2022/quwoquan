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

---

## 3. GitHub Actions Secrets（gamma 相关）

| 变量 / Secret | 用途 |
|---------------|------|
| `GAMMA_BASE_URL` | gamma 对外 API 基址 |
| `GAMMA_PRODUCT_OPS_BASE_URL` | gamma 上 Ops/产品面 API 基址 |
| `GAMMA_TEST_AUTH_TOKEN` | gamma L3/L4 鉴权 |
| `GAMMA_KUBECONFIG` | gamma 部署流水线 kubectl apply |

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
