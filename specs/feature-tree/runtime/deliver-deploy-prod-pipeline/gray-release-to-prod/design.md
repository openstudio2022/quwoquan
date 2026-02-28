# gray-release-to-prod 设计

## 设计动因

首次上线时用户尚少，当前 2 副本；灰度需分两阶段：**初始灰度**（小流量全自动验证）与 **Carry-on**（全量需人工把关）。初始灰度部署的 pod 数需可配置，随用户增长可增加中间滚动阶段。

## 适用场景与约束

- **适用**：首次发布、发布节奏固定、SLO 可自动拉取或人工录入
- **约束**：依赖 `config_release_*` 脚本；STEP 沿用 5/25/50/100；需 PROD_KUBECONFIG
- **局限性**：当前实现以脚本 + GitHub Actions 为主；Argo CD / GitOps 为未来演进

## 业界对标与多方案对比

### 1. 灰度策略：固定百分比 vs 可配置阶段

| 方案 | 职责边界 | 扩展性 | 实施成本 | 选型 |
|------|----------|--------|----------|------|
| **可配置阶段** | 每阶段 replicas + auto 可配 | 高，副本增加仅改配置 | 低 | ✓ 选定 |
| 固定 5→25→50→100 | 简单，无配置 | 低，副本变化需改代码 | 低 | 不适用 2 副本 |
| 蓝绿部署 | 一次性切换 | 无灰度 | 中 | 不选 |

**选型**：可配置阶段，通过 `gray_rollout_stages.yaml` 声明；当前 2 副本为 initial(1 pod, auto) + full(2 pod, approval)。

### 2. 审批机制

| 方案 | 实现 | 适用 | 选型 |
|------|------|------|------|
| **GitHub Environment approval** | Protected Environment，人工点 Approve | 集成好 | ✓ 首选 |
| workflow_dispatch 续跑 | Stage 1 完成后停止，生成链接人工触发 | 无 Environment 时 | 备选 |
| 每步人工填参 | 半自动 workflow，每步手动触发 | 强审批场景 | 已有 |

## 关键决策

### 1. 阶段配置模型

```yaml
# deploy/shared/gray_rollout_stages.yaml
total_replicas: 2
stages:
  - name: initial
    replicas: 1
    auto: true
  - name: full
    replicas: 2   # 或 percent: 100
    auto: false
```

- `STEP` 计算：`(replicas / total_replicas) * 100`，向下取整到 5/25/50/100 最接近值
- 当前：1→50，2→100

### 2. 全自动 Job 结构

- **gray-initial**：deploy 到 initial_replicas → wait rollout → SLO → continue/pause/rollback
- **gray-carry-on**：needs gray-initial；`environment: production`（Protected）；deploy 100% → SLO

### 3. 与现有脚本衔接

- `config_release_gray_rollout.sh` 保持 STEP 5|25|50|100，workflow 按配置传入对应 STEP
- 无需修改脚本即可支持可配置阶段

## 未来演进

- **更多中间阶段**：4 副本时可配 1→2→4，每阶段 auto 可单独配置
- **Argo CD / Progressive Delivery**：Argo Rollouts 等可替代脚本 + workflow
- **SLO 自动拉取**：从 Prometheus 等监控 API 自动查询，替代手填或占位
