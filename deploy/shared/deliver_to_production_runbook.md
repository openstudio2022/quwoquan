# Deliver → Prod 端到端运行手册

**五环境与波次**见 [environment_matrix.md](environment_matrix.md)（与本文阶段编号一致：local-gamma mirror → 云侧 gamma → T3/T4 → prod 灰度/全量）。

## 1. 目标

从特性到入库（L1/L2 自测通过），再到集成验证（L3/L4），再到生产端到端打通，含灰度/滚动发布。

```
特性 → dev 完成本地 T1/T2/T3/T4 左移验证并自动归档 → commit 入库 → deploy 到 gamma → 云侧 T3/T4 验证 → 灰度到 prod
```

---

## 2. 阶段划分

| 阶段 | 命令/动作 | 门禁 | 输出 |
|------|-----------|------|------|
| 1. 开发+入库 | `/dev` → `/commit`（或 `/deliver`） | G2 → G3 → G4 | `/dev` 完成四层自验证、gray-release ready 与自动归档；`/commit` 前本地 `gate-local-gamma` 通过并完成入库 |
| 2. 部署 integration | CI/CD 或手动 | G5a | integration 环境运行目标版本 |
| 3. 集成验证 | L3 + L4 测试 | G5b | L3/L4 通过 |
| 4. 灰度到 prod | `config-gray-rollout` | G5c | prod 灰度完成，SLO 通过 |

---

## 3. 前置条件

### 3.1 Deliver 阶段完成

- 代码已合入 `dev1.0`（分支开发模式）或已准备发起进入 `main` 的 PR；分支策略见 `deploy/shared/branch_strategy.md`
- `make gate-local-gamma` 通过并生成 `artifacts/local-gamma/report.json`。该命令必须覆盖本地 `T1 -> T4`，不得只用 `make gate` 替代；见 `/.cursor/commands/commit.md`
- `deploy/shared/process_domain_mapping.yaml` 合法，`verify_deployment_domain_mapping.sh` 通过

### 3.1.1 local-gamma mirror（提交前左移）

提交前必须先在本机运行 local-gamma mirror：

```bash
make gate-local-gamma
```

通过判据：

- `T1`：metadata、拓扑、环境包、seed manifest、错误码、静态语义与生成物校验通过。
- `T2`：Flutter/Go/Ops 模块、Widget、Provider/Journey 测试通过。
- `T3`：本地 gamma 镜像栈真实 API、真实存储副作用、错误响应与 RemoteRepository smoke 通过。
- `T4`：至少一台模拟器或真机 Patrol 核心旅程通过。
- 报告：`artifacts/local-gamma/report.json` 状态为 `passed`。

缺少本地 DNS/TLS、设备、服务依赖或 seed/reset 能力时，状态必须为 `GATE_BLOCK`，不得继续提交。

### 3.2 部署环境

- **gamma**：gamma API 可访问，`GAMMA_BASE_URL`、`GAMMA_PRODUCT_OPS_BASE_URL`、`GAMMA_TEST_AUTH_TOKEN` 已配置
- **prod**：K8s 集群就绪（阿里云 ACK / 火山引擎 VKE / 华为云 CCE），`CONFIG_VERSION`、`IMAGE_VERSION` 已确定
- **多云切换**：通过 `CLOUD_PROVIDER=aliyun|volcengine|huaweicloud` 选择 overlay，见 `deploy/cloud-providers/`

### 3.3 灰度参数

- `FROM_IMAGE`、`TO_IMAGE`：当前与目标镜像版本
- `FROM_CONFIG`、`TO_CONFIG`：当前与目标配置版本
- `STEP`：当前 2 副本为 50（初始灰度 1 pod，全自动）→ 100（Carry-on 全量，需审批）。初始灰度 pod 数可配置；副本增加时可扩展中间阶段。

### 3.4 版本号从哪里获取（图一表单四个字段）

**要区分两个东西**：

- **`.release-state/seed-box.state`** 是**状态文件**，记录「上一次灰度完成后 prod 正在跑的版本」：里面的 `to_image`、`to_config` 就是**当前 prod** 的镜像/配置版本。表单里的 **Current prod** 应从**这个 state 文件**取，不是从 `releases/config/` 取。
- **`releases/config/seed-box/v*.yaml`** 是**某次发布用的配置内容**（该版本的配置快照），用于校验「目标配置版本」是否存在；不表示“当前 prod 版本号”。

| 字段 | 含义 | 获取方式 |
|------|------|----------|
| **Current prod image version** | 当前生产正在使用的镜像版本 | 从 **`.release-state/seed-box.state`** 的 **`to_image`** 读取（上次灰度完成后写入）；若无则从集群查：`kubectl get deployment seed-box -n seed-box-prod -o jsonpath='{.spec.template.spec.containers[0].image}'` 取 tag |
| **Target image version (match pre-release)** | 本次要上的镜像版本，须与预发布一致 | 来自 **merge queue 的 pre-release** 部署到 integration 的版本：tag 触发用该 tag 或解析值；必要时参考 `deploy/service/seed-box/kustomize/overlays/integration/kustomization.yaml` 的 `IMAGE_VERSION` |
| **Current prod config version** | 当前生产正在使用的配置版本 | 从 **`.release-state/seed-box.state`** 的 **`to_config`** 读取；若无则从 deployment 环境变量 `CONFIG_VERSION` 读取 |
| **Target config version** | 本次要上的配置版本 | 与 target image 对应，来自 pre-release 的 `CONFIG_VERSION`（同上） |

**约定**：Target 必须与 pre-release 在 integration 验证通过的版本一致。Workflow 支持**留空 Current prod 两栏**时自动从 `.release-state/seed-box.state` 读取（见下文）。

---

## 4. G5a：部署到 integration

1) 选择云厂商并渲染 deployment（入口：`deploy/kustomization/`）：

```bash
# 阿里云（默认）
CLOUD_PROVIDER=${CLOUD_PROVIDER:-aliyun}
kustomize build deploy/kustomization/${CLOUD_PROVIDER}-integration

# 或 make deploy-integration
make deploy-integration [CLOUD_PROVIDER=volcengine]
```

2) 应用部署（按实际 CI/CD 或 ArgoCD 流程）

3) 验证 integration 可达：

```bash
curl -s -o /dev/null -w "%{http_code}" $GAMMA_BASE_URL/healthz
```

---

## 5. G5b：T3/T4 集成验证

### 5.1 T3 API Contract

```bash
API_CONTRACT_ENV=gamma \
GAMMA_BASE_URL=<gamma-api-url> \
GAMMA_PRODUCT_OPS_BASE_URL=<gamma-product-ops-url> \
GAMMA_TEST_AUTH_TOKEN=<token> \
make test-api-contract
```

失败 → 不得进入 G5c。

### 5.2 T4 Patrol（真机/模拟器）

```bash
cd quwoquan_app && patrol test test/patrol/ \
  --dart-define=APP_RUNTIME_ENV=gamma \
  --dart-define=API_CONTRACT_ENV=gamma \
  --dart-define=API_CONTRACT_BASE_URL=<gamma-api-url> \
  --dart-define=TEST_AUTH_TOKEN=<token>
```

CI 使用 `.github/workflows/pre-release-gate.yml` 在本机 macOS self-hosted runner 执行 L4：通过 `flutter devices --machine` 动态发现当前可见的 Android/iOS 模拟器或真机，并逐台运行 Patrol。

失败 → 不得进入 G5c。

---

## 6. G5c：灰度/滚动发布到 prod

### 6.0 灰度对象：整颗 seed-box（不按服务区分）

在 **integration / prod** 只有一个 K8s Deployment：**seed-box**，内有两个容器（Go seed-box + Python recommendation-service），**一起发布、同一镜像/配置版本**。灰度就是整颗 seed-box 一起滚，不按“服务”拆开。配置与状态统一用 seed-box：`releases/config/seed-box/`、`.release-state/seed-box.state`。见 `deploy/shared/process_domain_mapping.yaml` 与 `deploy/service/seed-box/kustomize/base/deployment.yaml`。

### 6.1 灰度步进

每步执行（灰度对象固定为 seed-box）：

```bash
make config-gray-rollout \
  SERVICE=seed-box \
  FROM_IMAGE=<old> TO_IMAGE=<new> \
  FROM_CONFIG=<old> TO_CONFIG=<new> \
  STEP=50  # 初始灰度（1 pod，全自动）；100 为 Carry-on 全量（需审批）
```

### 6.2 SLO 卡点（每步后）

```bash
make config-slo-gate \
  ERROR_RATE=<实测> P95_MS=<实测> REDIS_ERROR_RATE=<实测>
```

阈值见 `deploy/service/config-release/slo_thresholds.yaml`。

### 6.3 异常回滚

```bash
make config-rollback SERVICE=seed-box TO_CONFIG=<rollback-version>
```

### 6.4 high_risk_fields

变更 `deploy/service/config-release/high_risk_fields.yaml` 中字段时，须：

- 审批（min_approvers: 2）
- 灰度（require_gray_release: true）
- 回滚方案（require_rollback_plan: true）

---

## 7. 端到端检查清单

```
☐ deliver 完成，代码已入库 `dev1.0` 或已准备进入 `main` 的显式 PR（分支策略见 `branch_strategy.md`）
☐ make gate-local-gamma 通过（本地 T1/T2/T3/T4）并生成 artifacts/local-gamma/report.json
☐ verify_deployment_domain_mapping.sh 通过
☐ integration 已部署目标版本
☐ T3 test-api-contract 通过
☐ T4 patrol 通过（或 FTL 通过）
☐ 灰度：初始灰度（1 pod，全自动）→ Carry-on 100%（审批后执行）
☐ 每步 SLO 卡点通过
☐ prod 100% 后监控稳定
```

---

## 8. 参考

- `specs/00_MASTER_DEVELOPMENT_FLOW.md` — 主流程（含 Deploy 阶段 G5）
- `deploy/shared/branch_strategy.md` — **分支策略**（显式 PR + merge queue）
- `deploy/shared/ci_cd_end_to_end_design.md` — **CI/CD 端到端闭环落实方案**（pre-release workflow、secrets、实施顺序）
- `deploy/shared/workflow_consolidation_plan.md` — **Workflow 命名规范**（01～08、merge queue/main-only）
- `.cursor/commands/deploy.md` — 部署命令
- `deploy/shared/process_domain_mapping_runbook.md` — 部署拓扑
- `deploy/service/config-release/runbook.md` — 配置发布与灰度
- `specs/feature-tree/runtime/deliver-deploy-prod-pipeline/design.md` — 多云（阿里云/火山引擎/华为云）设计
