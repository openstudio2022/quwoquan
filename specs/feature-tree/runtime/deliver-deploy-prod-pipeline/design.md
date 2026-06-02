# deliver-deploy-prod-pipeline 设计

## 设计动因

当前仓库已经具备多环境基础设施，但 promotion 链是割裂的：

- `alpha-local / beta-local` 主要由本地脚本与 self-hosted 设备矩阵维护。
- `gamma-hosted` 由 PR 轻量 preflight、手动 ECS deploy、nightly full validation 分散维护。
- `prod-hosted` 已有自动灰度 workflow，但仍保留人工 approval，且 post-deploy probe 置信度偏低。

本设计的目标不是新增环境，而是在保持现有混合拓扑的前提下，把 `main` 入库后的自动主链收敛为一条可审计、可回滚、15 分钟内完成 blocking promotion 的流水线。

## 适用场景与约束

- **适用**：`main` 后多环境自动推进、hosted gamma / prod 部署、prod 自动灰度与自动回滚。
- **约束**：
  - 继续依赖 `process_domain_mapping`、`environment_topology_manifest`、`local_env_port_manifest`、`gray_rollout_stages` 与 `config_release_*` 脚本。
  - 继续支持 `CLOUD_PROVIDER=aliyun|volcengine|huaweicloud` 的多云 prod overlay。
  - 不引入 `beta-hosted`、`prod-gray`、第二套 gamma mirror 命名或第二套 workflow 逻辑。
- **局限性**：beta 仍依赖 self-hosted macOS runner、Flutter 设备可见性与本地网络环境；这是有意保留的拓扑前提。

## 设计原则

### 1. 单一自动 promotion 链

`main` 后只允许一条权威主链：

```text
repo verify/package
  -> alpha-local stage
  -> beta-local stage
  -> gamma-hosted stage
  -> prod initial
  -> prod checks
  -> prod full
```

约束：

- PR 仍由 `03/04/05` 收敛，但 `07` 负责真正的自动 promotion。
- `08/09` 保留为手动复验与 nightly full validation，不再与 `07` 竞争“权威主链”角色。

### 2. stackctl 为唯一命令面

所有 workflow 必须编排以下统一入口，而不是复制环境脚本逻辑：

- `stackctl package/verify`
- `stackctl up/down/status`
- `stackctl health`
- `stackctl inspect`
- `stackctl doctor`
- `stackctl deploy`

对应约束：

- workflow 可以复用 reusable workflow，但 reusable workflow 产出的 probe/evidence 必须能映射回 `stackctl` 同名能力。
- `artifacts/stackctl/<env>/<run-id>/report.json` 与 `summary.md` 是环境证据的单一真相源。

### 3. profile 分层与主链轻重分离

`deploy/shared/gamma_validation_suites.json` 统一定义所有 hosted / self-hosted profile：

| Profile | 作用 | 阻断链职责 |
|---|---|---|
| `pr_light` | PR 默认 preflight | 共享 gamma readiness + advisory smoke |
| `manual_full` | 手动完整 gamma 复验 | ECS deploy + T3 + hosted/high-signal smoke |
| `nightly_full` | 夜间全量验证 | hosted full + Patrol + 全设备矩阵 |
| `release_candidate` | 发布前回归 | 与 nightly_full 同级但更靠近发布 |
| `mainline_auto_prod` | `main` 自动 promotion | beta matrix + gamma hosted 阻断链 + prod initial checks |

设计要求：

- `mainline_auto_prod` 只保留高信号、低时延、可直接证明端云正确性的阻断项。
- full semantic / Patrol / 全量多旅程继续由 `nightly_full` 与 `release_candidate` 承担。

### 4. prod 自动放量必须绑定自动回滚

由于用户已明确选择 full-auto prod，本设计要求：

- `gray_rollout_stages.yaml` 中 `full` 阶段也必须允许自动执行。
- `prod initial` 后必须执行 `stackctl health + inspect + doctor + integration probes + slo gate`。
- 任一 blocking probe 失败时，workflow 必须自动回滚到上一稳定 `image/config`，并把 rollback 结果纳入同一阶段证据。

## 核心编排设计

### 1. alpha / beta 本地阶段

`alpha-local`：

- `stackctl package --env alpha --include-services`
- `stackctl up --target alpha-local`
- `stackctl health --target alpha-local --scope full`

`beta-local`：

- `stackctl package --env beta --include-services`
- `stackctl up --target beta-local`
- `stackctl health --target beta-local --scope full`
- `stackctl inspect --target beta-local --scope all`
- self-hosted 设备矩阵复用 `05. App Env Device Matrix`，但使用 `mainline_auto_prod` profile 的环境默认值与 gate 文案。

### 2. gamma hosted 阶段

gamma 不再在 `07` 中手搓第三套部署逻辑，统一复用：

- `.github/workflows/gamma-ecs-pre-hosted-core.yml` 负责 deploy + readiness + API contract + assistant/chat-avatar probes。
- 新增 `mainline_auto_prod` profile 后，`07` 可直接调用该 reusable workflow 或按同一 contract 消费其输出。

gamma 阶段输出必须至少包含：

- deploy artifact
- readiness report
- API contract report
- assistant smoke report
- chat avatar probe report
- critical path duration

### 3. prod initial / prod checks / prod full

`prod initial`：

- `stackctl deploy --target prod-hosted --step <initial>`

`prod checks`：

- `stackctl health --target prod-hosted --scope full`
- `stackctl inspect --target prod-hosted --scope all`
- `stackctl doctor --target prod-hosted`
- prod 只读集成探针：
  - assistant protocol smoke
  - chat avatar API probe
  - 必要的 hosted API contract smoke

`prod full`：

- `stackctl deploy --target prod-hosted --step <full>`
- 成功后更新 release-state；失败则回滚到 `from_image/from_config`

### 4. 900 秒关键路径预算

主链预算由 `deploy/shared/pr_gate_timing_budgets.json` 扩展承载，新增 mainline 自动 promotion gate。

策略：

- alpha / beta 可尽量并行。
- gamma / prod 必须严格串行。
- 通过 artifact 复用、bundle 复用、self-hosted cache repo、Flutter 依赖缓存、skip upload、镜像预拉取来压缩关键路径。
- `agent_ops/ci/render_ci_timing_summary.py` 继续作为统一耗时摘要渲染器。

## 多云与 overlay 设计

多云 prod overlay 方案保持不变，继续使用：

- `deploy/cloud-providers/{aliyun|volcengine|huaweicloud}/`
- `deploy/kustomization/{cloud}-{env}/`
- `CLOUD_PROVIDER` 作为 workflow / CLI 的统一切换参数

本次变更只调整自动推进链与回滚闭环，不重写多云 overlay 结构。

## 风险与防线

### 1. self-hosted runner 是 beta 阶段硬依赖

风险：

- 设备不可见、Xcode/adb 漂移、runner 缓存损坏会直接阻断 `main` 自动 promotion。

防线：

- 设备发现、artifact 证据、gate hint、失败分类必须可机读。
- `mainline_auto_prod` profile 不得默认要求不存在的平台通过，但已发现的平台必须全部成功。

### 2. prod 自动放量的误放风险

风险：

- 如果 `prod full` 自动推进时只看 `/healthz`，会把低置信度通过当成发布成功。

防线：

- prod checks 必须要求 `health + inspect + doctor + integration probes + slo gate` 全绿。
- rollback 结果必须写回证据与 release-state，不能只停在日志提示。

### 3. 第二套逻辑回归风险

风险：

- workflow 为了追求快速落地，再次在 YAML 里复制 `health`、`probe`、`rollback` 逻辑，导致 `stackctl` 与 workflow 漂移。

防线：

- 新增能力优先沉到 `stackctl`。
- workflow 只保留编排与 artifact 上传，不再维护第二套探针语义。

## 未来演进

- 若后续引入 GitOps，可把 `prod initial/prod full` 的 apply 动作迁移到 Argo CD，但 `stackctl` 与证据 contract 仍保持稳定。
- 若后续新增 hosted beta，只允许通过扩展 topology manifest 与 `stackctl` target，不允许跳过当前 `alpha-local / beta-local / gamma-hosted / prod-hosted` 主线抽象。
