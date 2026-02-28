# deliver-deploy-prod-pipeline 设计

## 设计动因

当前 deliver 入库后，部署到 integration 与生产依赖人工或分散的 CI；L3/L4 与 pre-release 未串联；部署与单云（如阿里云）强绑定，无法灵活切换到火山引擎或华为云。本设计建立端到端流水线，并支持多云部署切换。

## 适用场景与约束

- **适用**：integration/prod 部署；pre-release 流水线；灰度发布；多云或混合云场景
- **约束**：依赖 process_domain_mapping、config-release、Kustomize；须支持 CLOUD_PROVIDER 或等效环境变量切换
- **局限性**：多云 overlay 初期覆盖阿里云、火山引擎、华为云；其他云（如腾讯云、AWS）可后续扩展

## 业界对标与多方案对比

### 1. 部署编排：Kustomize vs Helm vs Argo CD ApplicationSet

| 方案 | 职责边界 | 多云灵活性 | 实施成本 | 选型 |
|------|----------|------------|----------|------|
| **Kustomize + overlay** | 声明式、无运行时依赖 | 高，overlay 按云/环境拆分 | 低 | ✓ 选定 |
| Helm + values | 模板化、需 Chart 维护 | 中，values 按云区分 | 中 | 备选 |
| Argo CD ApplicationSet | 多集群 GitOps | 高 | 高，需 Argo 部署 | 未来演进 |

**选型**：Kustomize overlay 已在使用（`deploy/service/seed-box/kustomize/overlays/{dev,integration,prod}`），保持并扩展为 `overlays/{env}-{cloud}` 或 `cloud-providers/{cloud}/overlays/{env}`，无需引入 Helm/Argo。

### 2. 多云切换：目录结构对比

| 方案 | 结构 | 切换方式 | 可维护性 |
|------|------|----------|----------|
| **A：overlay 按云拆分** | `overlays/integration-aliyun`, `overlays/integration-volcengine`, `overlays/integration-huaweicloud` | `kustomize build overlays/integration-${CLOUD_PROVIDER}` | 高 |
| B：单一 overlay + 云参数 | `overlays/integration` + `CLOUD_PROVIDER` patch | 需大量 patch 条件 | 中 |
| C：cloud-providers 顶层目录 | `cloud-providers/aliyun/`, `cloud-providers/volcengine/`, `cloud-providers/huaweicloud/` | 每云独立 base，共用 service 定义 | 高 |

**选型**：**C** — `deploy/cloud-providers/{aliyun|volcengine|huaweicloud}/` 顶层目录，云特定 patches 置于各云下；**kustomization 入口统一置于 `deploy/kustomization/`**，命名 `{cloud}-{env}/` 目录（含 kustomization.yaml），kustomize build 仅接受目录参数。切换时 `CLOUD_PROVIDER=volcengine kustomize build deploy/kustomization/volcengine-prod`。

### 3. 云厂商差异抽象

| 云 | 容器服务 | 负载均衡 | 存储/数据库 | 差异点 |
|----|----------|----------|-------------|--------|
| 阿里云 | ACK | SLB/ALB | ApsaraDB、Tair | 典型国内云 |
| 火山引擎 | VKE | CLB | Redis、RDS | 与阿里云 API 类似，部分命名不同 |
| 华为云 | CCE | ELB | DCS、RDS | 华为生态，API 风格略异 |

**抽象策略**：K8s 标准 API 保持一致；云厂商差异通过以下方式隔离：
- **镜像拉取**：各云镜像仓库地址不同，通过 `imagePullSecrets` 或私有 registry 配置在 overlay 中注入
- **LoadBalancer**：各云 Service type=LoadBalancer 自动创建 LB，annotation 按云不同（如阿里云 `service.beta.kubernetes.io/alibaba-cloud-loadbalancer-*`）
- **存储类**：StorageClass 名称按云不同（如 `alicloud-disk-ssd`, `csi-disk`, `csi-nas`），在 overlay 中指定
- **配置来源**：统一用 ConfigMap/Secret + 可选云厂商 ConfigCenter（如火山引擎 APM、华为云 AOM），通过 `CONFIG_PROVIDER` 切换

## 关键决策

### 1. 多云目录结构

```
deploy/
├── shared/                           # 云无关
│   ├── process_domain_mapping.yaml
│   └── deliver_to_production_runbook.md
├── service/
│   └── seed-box/kustomize/base       # 共用 base
└── cloud-providers/
    ├── aliyun/                       # 阿里云
    │   └── seed-box/
    │       └── overlays/
    │           ├── integration/
    │           └── prod/
    ├── volcengine/                   # 火山引擎
    │   └── seed-box/
    │       └── overlays/
    │           ├── integration/
    │           └── prod/
    └── huaweicloud/                  # 华为云
        └── seed-box/
            └── overlays/
                ├── integration/
                └── prod/
```

**kustomization 约定**：入口目录位于 `deploy/kustomization/{cloud}-{env}/`（如 `aliyun-integration`），含 `kustomization.yaml`，resources 使用相对路径 `../../service/seed-box/kustomize/overlays/{env}`。kustomize build 仅接受目录参数。

每云 overlay 目录（`cloud-providers/*/overlays/*`）可含 `patches/`（LB/StorageClass/镜像等）；kustomization 引用云 patch 时用相对路径。

### 2. 切换方式

- **环境变量**：`CLOUD_PROVIDER=aliyun|volcengine|huaweicloud`
- **CI 参数**：workflow 或 pipeline 传入 `cloud_provider`
- **Makefile**：`make deploy-integration CLOUD_PROVIDER=volcengine`

### 3. pre-release 流水线串联

```
v*-rc* tag
  → pre-release-gate.yml
      1. make gate-full
      2. Deploy to integration（CLOUD_PROVIDER 可选）
      3. L3 test-api-contract（STAGING_BASE_URL=integration）
      4. L4 Patrol/FTL
      5. 全部通过 → 允许灰度到 prod
```

### 4. 灰度与 SLO

- 灰度步进、SLO 卡点、回滚与云厂商无关，沿用 `config-gray-rollout`、`config-slo-gate`、`config-rollback`
- 执行灰度时，通过 `CLOUD_PROVIDER` 选择对应 overlay 部署到 prod

## 未来演进

- **Argo CD / GitOps**：若引入 Argo CD，用 ApplicationSet 管理多云多集群
- **更多云**：腾讯云 TKE、AWS EKS 等，按 `cloud-providers/` 模式扩展
- **云厂商 ConfigCenter**：火山引擎、华为云配置中心集成，通过 CONFIG_PROVIDER 切换
- **跨云容灾**：主备双云部署，需额外设计路由与故障切换
