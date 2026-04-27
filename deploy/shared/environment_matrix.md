# 部署环境矩阵（五环境 · 一套代码）

> **总览**：本地开发、CI 验证、集成测试、生产灰度、生产全量共用同一套业务与契约代码；差异仅来自 **Kustomize overlay、Secret/环境变量、构建时 `dart-define`**。  
> **拓扑唯一源**：[`process_domain_mapping.yaml`](process_domain_mapping.yaml)（`integration` 与 `prod` 的 domain→进程映射必须一致）。  
> **Pipeline 细节**：[ci_cd_end_to_end_design.md](ci_cd_end_to_end_design.md)、[deliver_to_production_runbook.md](deliver_to_production_runbook.md)。

---

## 1. 命名说明：STAGING_* = integration 对外 URL

Makefile 与部分测试使用 **`STAGING_BASE_URL`**、**`STAGING_PRODUCT_OPS_BASE_URL`** 作为 L3 契约测试的 HTTP 基址变量名。其**语义**为 **integration 集群已部署服务对外的 base URL**，并非独立「staging 集群」概念。  
若更易读，可同时设置 **`INTEGRATION_BASE_URL`** / **`INTEGRATION_PRODUCT_OPS_BASE_URL`**（见根目录 `Makefile` 的 `test-api-contract`：`STAGING_*` 优先，缺省则回退到 `INTEGRATION_*`）。

---

## 2. 五环境对照表

| 代号 | 环境 | `process_domain_mapping` | 部署 / 验证手段 | 端侧典型注入 |
|------|------|--------------------------|-----------------|--------------|
| **A** | 本地开发 | `dev` | 本机进程 / Docker Compose；无强制 K8s | `CLOUD_GATEWAY_BASE_URL` 默认 `http://127.0.0.1:18080`；Debug 下 `APP_DATA_SOURCE=mock` 经 Provider（见工程规范） |
| **B** | CI/CD 验证 | —（不占用映射行） | `delivery-gate` / `make gate`（L1+L2）；`service_pipeline` 构建 + kustomize 校验 | 不依赖真实公网网关 |
| **C** | 集成测试 | `integration` | `kustomize build deploy/kustomization/{cloud}-integration`；CI：`deploy-integration` job；`make deploy-integration` 仅做构建校验 | L3：`STAGING_BASE_URL`、`STAGING_PRODUCT_OPS_BASE_URL`、`TEST_AUTH_TOKEN` |
| **D** | 生产灰度 | `prod`（同拓扑） | [gray_rollout_stages.yaml](gray_rollout_stages.yaml) 中未满副本/需审批阶段；[deploy-prod-gray.yml](../../.github/workflows/deploy-prod-gray.yml) | 生产网关；Release：`APP_DATA_SOURCE=remote` 等 |
| **E** | 生产全量/发布 | `prod` | `full` 阶段 100% 副本、发版元数据/CR；runbook 收尾 | 同 D |

**多云**：`{cloud}` 为 `aliyun` | `volcengine` | `huaweicloud`（与 `deploy/kustomization/` 下目录一致）。逻辑环境（A~E）与**云厂商**正交。

---

## 3. 波次（Wave）关系

1. **大波段**（环境间）：**B 通过** → **C 部署并 L3/L4 通过** → 才进入 **D/E**（与 `ci_cd_end_to_end_design.md` 中 pre-release 链一致）。  
2. **小 wave**（prod 内，类 CodeDeploy）：由 `gray_rollout_stages.yaml` 的 `replicas` + `auto` 驱动；**D** 为中间阶段，**E** 为全量。详见 [deploy_prod_design.md](deploy_prod_design.md)。

```text
A(本地) ─┐
         ├→ B(CI gate) → C(integration + L3) → D(灰度 prod) → E(全量 prod)
```

---

## 4. GitHub Actions Secrets（L3 相关）

| 变量 / Secret | 用途 |
|---------------|------|
| `STAGING_BASE_URL` 或 `INTEGRATION_BASE_URL` | integration 上对外 API 基址（L3 content 等） |
| `STAGING_PRODUCT_OPS_BASE_URL` 或 `INTEGRATION_PRODUCT_OPS_BASE_URL` | integration 上 Ops/产品面 API 基址（L3 ops runner） |
| `STAGING_TEST_AUTH_TOKEN`（`TEST_AUTH_TOKEN`） | L3 鉴权 |
| `INTEGRATION_KUBECONFIG` | `deploy-integration` 的 kubectl apply（缺省则跳过 apply，见 workflow） |

不在仓库中存放明文；本地导出同名环境变量后执行 `make test-api-contract`。

---

## 5. 各环境推荐验证命令（维护者自检）

| 环境 | 命令 / 条件 | 通过判据 |
|------|-------------|----------|
| A | 本地启动 `content-service` 等 + `flutter test` 相关模块 | 本机用例绿 |
| B | 仓库根 `make gate` | 退出码 0 |
| C | `make deploy-integration`；若配置完整则 `STAGING_*` + `make test-api-contract` | kustomize 输出成功；L3 需 URL/token |
| D/E | 生产变更仅限持权流水线；`kustomize build deploy/kustomization/aliyun-prod` | 清单可构建；真部署依 runbook |

**说明**：无 integration 公网与 token 时，**不**将 L3 本地失败视为 B 类门禁失败；B 的门槛是 `make gate`（不含 L3，见 `gate-full` 定义）。

---

## 6. 相关文件索引

- [process_domain_mapping.yaml](process_domain_mapping.yaml)
- [ci_cd_end_to_end_design.md](ci_cd_end_to_end_design.md)
- [branch_strategy.md](branch_strategy.md)
- [deliver_to_production_runbook.md](deliver_to_production_runbook.md)
- [`specs/.../daily-merge-release-strategy/spec.md`](../../specs/feature-tree/runtime/deliver-deploy-prod-pipeline/daily-merge-release-strategy/spec.md)（release 与多环境交叉引用）
- [`specs/.../multi-environment-wave-deployment/spec.md`](../../specs/feature-tree/runtime/deliver-deploy-prod-pipeline/multi-environment-wave-deployment/spec.md)（特性树 L3）
