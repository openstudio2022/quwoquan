# 生产部署设计：半自动与全自动

> 目标：在现有 G5a（deploy-integration）、G5b（L3/L4）基础上，明确 G5c 灰度到 prod 的半自动与全自动方案。
> 前置：pre-release-gate 已通过（L1+L2 → deploy integration → L3 → L4）。

---

## 1. 现状与假设

| 项目 | 说明 |
|------|------|
| 已有脚本 | `config_release_gray_rollout.sh`（步进状态）、`config_release_slo_gate.sh`（SLO 决策）、`config_release_rollback.sh`（回滚）、`config_release_apply_stage.sh`（步进 + SLO + 自动回滚） |
| 灰度步进 | STEP ∈ {5, 25, 50, 100}，顺序不可逆；脚本已支持 |
| SLO 决策 | continue(0) / pause(10) / rollback(20)；rollback 时脚本内会调用 `config_release_rollback.sh` |
| 实际部署 | 当前 runbook 未绑定「谁执行 kubectl apply 到 prod」；设计里假定由 workflow 或下游系统根据 state/版本执行 apply |

### 1.1 当前阶段（2 副本，首次上线）

| 项目 | 说明 |
|------|------|
| **背景** | 首次发布，用户尚少，当前 2 副本；随用户增长将增加副本与滚动阶段 |
| **阶段划分** | **初始灰度**（Stage 1）+ **Carry-on 滚动**（Stage 2+） |
| **Stage 1 初始灰度** | 全自动；部署到 **N 个 pod**（可配置，当前 N=1）；deploy → SLO → continue/pause/rollback |
| **Stage 2 Carry-on** | 当前直接到 100%；需人工审批后执行 deploy → SLO |
| **扩展** | 副本增加后（如 4、8 pod），可增加中间阶段（如 1→2→4），每阶段是否审批可配置 |

### 1.2 阶段配置模型（可扩展）

```yaml
# deploy/shared/gray_rollout_stages.yaml（已落地）
total_replicas: 2    # 可从 deployment 读取或显式配置
stages:
  - name: initial
    replicas: 1      # 或 percent: 50
    auto: true       # 全自动
  - name: full
    replicas: 2      # 或 percent: 100
    auto: false      # 需审批
# 未来 4 副本示例：
# stages:
#   - { replicas: 1, auto: true }
#   - { replicas: 2, auto: false }
#   - { replicas: 4, auto: false }
```

### 1.3 方案概要

| 阶段 | 部署目标 | 是否审批 | 当前 2 副本 |
|------|----------|----------|-------------|
| **Stage 1 初始灰度** | N pod（可配置） | 否，全自动 | 1 pod（50%） |
| **Stage 2 Carry-on** | 100% | 是 | 2 pod（100%） |
| **未来 4 副本** | 可配多阶段 | 每阶段可配 | 如 1→2→4，1 自动、2/4 审批 |

### 1.4 与 environment_matrix 中 D（灰度）/E（全量）的对应

- **D（生产灰度）**、**E（生产全量）** 在 `process_domain_mapping` 中均为 **prod**；不引入第二套领域拓扑。
- **D**：对应 `gray_rollout_stages.yaml` 中未达 `total_replicas` 或 `auto: true` 的步进（小流量/自动段）。
- **E**：对应 `full` 阶段或 `replicas == total_replicas`，通常为放量完成与发版元数据锁定。
- 与「大波段」关系：**C（integration）+ L3/L4 通过** 后再进入本节的 prod 步进，见 [environment_matrix.md](environment_matrix.md) 与 [ci_cd_end_to_end_design.md](ci_cd_end_to_end_design.md)。

---

## 2. 半自动方案（workflow_dispatch）

### 2.1 定位

- 人工触发、人工确认步进与 SLO，避免误点到生产。
- 适合：发布频率不高、需要审批、SLO 指标来自监控大盘人工录入。

### 2.2 流程

```
运维/发布负责人
  → 在 GitHub Actions 选择 "Deploy to Prod (Gray)" workflow
  → 填写输入参数（见下）
  → 触发后：单步灰度 + 本步 SLO 校验（可选自动回滚）
  → 下一步需再次手动触发并修改 STEP
```

### 2.3 Workflow 设计要点

**触发**：`workflow_dispatch`，不随 pre-release 自动跑。

**输入参数**（必填 + 选填）：

| 输入 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `service` | choice | 是 | content-service / recommendation-service 等 |
| `cloud_provider` | choice | 是 | aliyun / volcengine / huaweicloud |
| `from_image` | string | 是 | 当前 prod 镜像版本 |
| `to_image` | string | 是 | 目标镜像版本（与 pre-release 通过版本一致） |
| `from_config` | string | 是 | 当前 prod 配置版本 |
| `to_config` | string | 是 | 目标配置版本 |
| `step` | choice | 是 | 初始阶段（如 50=1/2 pod）→ 100；多副本时可为 25/50 等，由 gray_rollout_stages 决定 |
| `error_rate` | string | 是（SLO） | 当前/本步实测错误率，如 0.005 |
| `p95_ms` | string | 是（SLO） | 当前/本步实测 P95 延迟（ms） |
| `redis_error_rate` | string | 是（SLO） | Redis 错误率 |
| `dry_run` | boolean | 否 | true 仅校验 + 写 state，不执行 prod apply |

**Secrets**：

- `PROD_KUBECONFIG`：生产集群 kubeconfig（base64），用于 `kubectl apply`。

**Job 顺序**（单步）：

1. **validate**：校验 `step` 与 `.release-state/<service>.state` 中上一步是否衔接；校验 `releases/config/<service>/<to_config>.yaml` 存在。
2. **deploy-prod-step**（可选，dry_run=false 时执行）：
   - 使用 `to_image` / `to_config` 构建 `deploy/kustomization/<cloud_provider>-prod`（通过 env 或 kustomize replacements 注入版本）。
   - `kubectl apply -f -` 到 prod 集群（使用 PROD_KUBECONFIG）。
   - 等待 rollout：`kubectl rollout status deployment/... -n seed-box-prod --timeout=5m`。
3. **gray-rollout-state**：执行 `make config-gray-rollout SERVICE=... FROM_IMAGE=... TO_IMAGE=... FROM_CONFIG=... TO_CONFIG=... STEP=...`，更新 `.release-state`。
4. **slo-gate**：执行 `make config-slo-gate ERROR_RATE=... P95_MS=... REDIS_ERROR_RATE=...`。
   - continue：job 成功，输出「本步通过，可进行下一步」。
   - pause：job 失败或 warning，输出「建议暂停，检查监控后再决定是否下一步」。
   - rollback：调用 `config_release_rollback.sh`（或通过 `config_release_apply_stage.sh` 已包含回滚），job 失败，输出「已触发回滚」。

**产出**：

- 更新 `.release-state/<service>.state` 与 audit log。
- 可选：将 state 文件作为 artifact 上传，或提交回仓库（需 token 与谨慎使用）。

### 2.4 使用方式（运维）

- 当前 2 副本：初始灰度 STEP=50（1 pod）→ Carry-on STEP=100；每步执行一次 workflow_dispatch。
- 逐步增大 `step`，并填入当步从监控得到的 SLO 指标。
- 若某步 SLO 为 rollback，workflow 内自动回滚后，人工检查再决定是否重新灰度或修版本。

---

## 3. 全自动方案（pre-release 通过后自动灰度）

### 3.1 定位

- pre-release-gate 全部通过（含 L3/L4）后，**自动**执行 **初始灰度**（Stage 1）。
- **Stage 1 初始灰度**：全自动 deploy → SLO；部署 pod 数可配置（当前 1 个，对应 2 副本下 50%）。
- **Stage 2 Carry-on**：直接到 100%；需人工审批后 deploy → SLO。
- **扩展**：随副本增加可配置更多中间阶段（如 1→2→4 pod），每阶段 auto/审批可配。
- 适合：首次上线、发布节奏固定、SLO 可自动拉取、初始灰度可自动回滚、全量需把关。

### 3.2 流程（当前 2 副本，初始=1 pod）

```
v*-rc* tag push
  → pre-release-gate（L1+L2 → deploy integration → L3 → L4）
  → 全部通过后触发 deploy-prod-auto workflow
  → Stage 1 初始灰度（全自动，1 pod = STEP 50）：
       deploy-prod-step(50) → wait_rollout → 拉取 SLO → slo-gate
       → continue: 进入 Stage 2 审批等待
       → pause: 停止并通知
       → rollback: 执行回滚并通知，workflow 失败
  → 【人工审批】（GitHub Environment / 手动续跑）
  → Stage 2 Carry-on（100%）：
       deploy-prod-step(100) → wait_rollout → 拉取 SLO → slo-gate
       → continue: 完成
       → pause/rollback: 同 Stage 1
```

**阶段与 STEP 映射**（脚本沿用 5/25/50/100）：`STEP = (目标 replicas / total_replicas) * 100`；初始灰度 replicas 由配置决定，当前 1→50%，未来 4 副本可配 1→25%、2→50% 等。

### 3.3 设计要点

**触发**：

- **方案 A**：pre-release-gate 最后一个 job（如 l4-ios）成功后，通过 `workflow_run` 或 `workflow_call` 触发 `deploy-prod-auto.yml`。
- **方案 B**：在 pre-release-gate 内增加 `deploy-prod-gray-auto` job，`needs: [l3-api-contract, l4-android, l4-ios]`，`if: success()`；该 job 内用矩阵或顺序步进调用同一套「单步逻辑」。

**版本来源**：

- 由 pre-release tag 解析出 `TO_IMAGE` / `TO_CONFIG`（如从 `v1.0.0-rc.1` 得到 `v1.0.0.rc1`），或从 release 元数据/环境变量读取。
- `FROM_IMAGE` / `FROM_CONFIG`：从当前 prod 状态读取（如从 `.release-state` 的 last 或从集群 annotation/label 拉取），或由 workflow 输入/缓存提供。

**SLO 指标获取**：

- 从监控 API 拉取（如 Prometheus `rate(...)`、`histogram_quantile`），在 workflow 里用 curl/python 请求，解析出 `ERROR_RATE`、`P95_MS`、`REDIS_ERROR_RATE`，再调用 `config_release_slo_gate.sh`。
- 需约定：查询时间窗口（如最近 5 分钟）、指标名与查询语句（与 `deploy/service/config-release/slo_thresholds.yaml` 一致）。

**审批与保护**：

- **Stage 2（100%）审批**：将 Carry-on 对应 job 的 Environment 设为 Protected；或 deploy-prod-auto 在 Stage 1 通过后停止，生成 workflow_dispatch 链接供人工续跑。
- **Stage 1 初始灰度全自动**：无审批要求，自动 deploy + SLO；部署 pod 数由 `gray_rollout_stages` 或等效配置决定。
- **可选**：仅当 tag 匹配 `v*-rc.*` 且非 `*-rc.0` 时才自动灰度（例如 rc.1 起才自动上 prod）。
- **通知**：每步结果（含 pause/rollback）通过 Slack/钉钉/邮件通知，并附带 run 链接与 SLO 数值。

**回滚**：

- 与半自动一致：slo-gate 返回 rollback 时执行 `config_release_rollback.sh`，并 fail job，通知运维。

### 3.4 Job 结构建议（全自动）

- **prepare**：解析 tag → TO_IMAGE/TO_CONFIG；读取 gray_rollout_stages 或等效配置，得到 initial_replicas → STEP 映射（如 1 pod / 2 total → 50）；校验 config 存在。
- **gray-initial**：deploy 到 initial_replicas（STEP 由配置计算）→ wait rollout → 拉取 SLO → slo-gate；continue 则进入 Stage 2；pause/rollback 则 fail 或 warning。
- **gray-carry-on**：needs gray-initial；**要求 Environment approval**；deploy STEP=100 → wait rollout → 拉取 SLO → slo-gate。

**实现方式**：gray-carry-on 使用 `environment: production`（Protected Environment），或 split workflow：initial 在 pre-release-gate 后自动跑，carry-on 由 workflow_dispatch 续跑。

**多副本扩展**：gray_rollout_stages 增加中间阶段后，在 initial 与 carry-on 之间插入 gray-step-N（每阶段 auto 可配）。

---

## 4. 对比小结

| 维度 | 半自动 | 全自动 |
|------|--------|--------|
| 触发 | workflow_dispatch，人工点选并填参 | pre-release 通过后自动触发 |
| 步进 | 每步人工触发一次，改 STEP 与 SLO 输入 | 初始灰度（1 pod）全自动；Carry-on 100% 需人工审批 |
| SLO | 人工从监控抄写填入 | 从 Prometheus/监控 API 拉取 |
| 审批 | 每步人工触发 | 初始灰度无审批；100% Environment approval 或 workflow_dispatch 续跑 |
| 适用 | 发布不频繁、强审批、SLO 人工看 | 首次上线、初始自动、全量需把关；阶段可配置扩展 |

---

## 5. 实施顺序建议

1. **先上半自动**：新增 `deploy-prod-gray.yml`（workflow_dispatch），实现单步灰度 + 手填 SLO + 可选 prod apply；补齐 `PROD_KUBECONFIG` 与 prod 构建/apply 脚本；当前 step 为 50（初始）→ 100（全量）。
2. **再上全自动**：新增 `deploy-prod-auto.yml` 或 pre-release-gate 内 deploy-prod 链：**初始灰度**（1 pod，可配置）全自动 deploy + SLO；**Carry-on 100%** 使用 Protected Environment approval 或 workflow_dispatch 续跑。
3. **配置扩展**：引入 `deploy/shared/gray_rollout_stages.yaml`（或等效），声明 `stages: [{replicas, auto}]`；workflow 按配置计算 STEP、决定各阶段是否审批；副本增加时仅改配置即可增加滚动阶段。

---

## 6. 参考

- `deploy/shared/deliver_to_production_runbook.md` — 端到端 runbook
- `deploy/shared/ci_cd_end_to_end_design.md` — G5c 现状与建议
- `scripts/config_release_apply_stage.sh` — 单步 state + SLO + 回滚
- `deploy/service/config-release/slo_thresholds.yaml` — SLO 阈值
