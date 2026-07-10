# Deployment Process-Domain Mapping 最小运行手册

## 1. 目标

在不改变领域 API 契约的前提下，统一管理四态部署拓扑：
- `alpha`：开发期单实例独立验证
- `beta`：开发期本地端云集成验证
- `gamma`：云侧类生产集成验证
- `prod`：生产全量（**灰度、放量与回滚在 prod 发布策略下完成**）

唯一配置文件：`quwoquan_ops/environments/process_domain_mapping.yaml`

模块化部署补充真相源：
- `quwoquan_ops/environments/module_package_mapping.yaml`：声明 deployment package 启动哪些 runtime module。
- `quwoquan_ops/environments/reliable_task_module_catalog.yaml`：声明 taskType、module capability、队列路由、payload 白名单与 worker 归属。
- `quwoquan_ops/environments/reliable_task_retention_policy.yaml`：声明 Outbox/Task/Notification/DLQ 的 TTL、归档、限流与恢复策略。

---

## 2. 配置模型

```yaml
environments:
  alpha:
    content-service:
      domains: [content]
    integration-service:
      domains: [integration]
    recommendation-service:
      domains: [recommendation]
  beta:
    recommendation-service:
      domains: [recommendation]
    product-ops-service:
      domains: [ops]
    seed-box:
      domains: [content, integration, chat, user, circle, notification, entity, tag, assistant]
  gamma:
    recommendation-service:
      domains: [recommendation]
    product-ops-service:
      domains: [ops]
    seed-box:
      domains: [content, integration, chat, user, circle, notification, entity, tag, assistant]
  prod:
    recommendation-service:
      domains: [recommendation]
    product-ops-service:
      domains: [ops]
    seed-box:
      domains: [content, integration, chat, user, circle, notification, entity, tag, assistant]
```

强约束：
- 同一环境下，一个 `domain` 只能出现一次
- `beta`、`gamma`、`prod` 映射必须一致
- 对外接口仍按领域服务暴露（如 `/v1/content/*`），不受进程组合影响
- onebox 只是 deployment package 组合，不是业务代码目录
- package 中 module 的 domain 必须属于该 package/process 的 domains
- module 命名必须采用 `{domain}.{capability}`，例如 `chat.task_outbox_dispatcher`
- `rec-model-service` 保持 Python 独立进程，不并入 Go `seed-box`

---

## 3. alpha 运行（默认独立）

1) 确认映射配置合法：

```bash
bash scripts/verify_deployment_domain_mapping.sh
```

2) 按服务名启动独立进程（示例）：

```bash
# content-service
SERVICE_NAME=content-service APP_ENV=alpha go run ./quwoquan_service/services/content-service/cmd/api

# integration-service
SERVICE_NAME=integration-service APP_ENV=alpha go run ./quwoquan_service/services/integration-service/cmd/api

# recommendation-service (python)
SERVICE_NAME=recommendation-service APP_ENV=alpha PYTHONPATH=. uvicorn main:app --host 0.0.0.0 --port 18090
```

3) 开发态校验：

```bash
make verify
```

4) 模块化本地运行：

alpha 默认允许单服务 all-in-one package，例如 `chat-service` 可以在同进程中启动：
- `chat.api`
- `chat.task_outbox_dispatcher`
- `chat.group_avatar_worker`
- `chat.roster_projection_worker`
- `chat.inbox_projection_worker`
- `chat.notification_outbox_dispatcher`

未启用 background module 的服务必须在 module catalog/config 中显式声明禁用或延期接入。

---

## 4. beta / gamma / prod 运行（组合拓扑）

1) 先验证映射（必须通过）：

```bash
bash scripts/verify_deployment_domain_mapping.sh
```

2) 使用组合进程 `seed-box` 启动 Go 聚合进程，Python 的 `recommendation-service` 保持独立进程（由部署编排注入环境变量）：

```bash
APP_ENV=gamma SERVICE_NAME=seed-box CONFIG_ROOT=/etc/seed-box-config CONFIG_VERSION=<version> IMAGE_VERSION=<image> <start-command>
APP_ENV=gamma SERVICE_NAME=recommendation-service CONFIG_ROOT=/etc/seed-box-config CONFIG_VERSION=<version> IMAGE_VERSION=<image> <python-start-command>
```

生产环境同理，使用 `APP_ENV=prod`（**灰度与全量由发布编排与配置版本区分**）：

```bash
APP_ENV=prod SERVICE_NAME=seed-box CONFIG_ROOT=/etc/seed-box-config CONFIG_VERSION=<version> IMAGE_VERSION=<image> <start-command>
```

运行口径补充：

- `beta` 在开发机本地联调时只允许一套组合拓扑，重新启动前必须停止旧实例。
- `gamma` 在 ECS 或 local-gamma mirror 中都只允许一套组合拓扑；部署 / mirror 切换应先清理既有实例再启动新实例。
- 多实例能力只属于端侧 App 进程，不属于 `seed-box` / `recommendation-service` 这类组合进程。

3) 发布前全量门禁：

```bash
make gate-full
```

4) 模块化 onebox 约束：

`seed-box` package 至少承载以下模块集合：
- `chat.api`
- `chat.task_outbox_dispatcher`
- `chat.group_avatar_worker`
- `chat.roster_projection_worker`
- `chat.inbox_projection_worker`
- `user.api`
- `user.avatar_propagation_worker`
- `content.api`
- `content.search_index_worker`
- `notification.fanout_worker`

`gamma/prod` 默认与 `beta` 的 module package mapping 一致。热点模块可在 `prod` 灰度拆分为独立 package，但必须满足：
- 保持 `process_domain_mapping.yaml` domain 唯一归属
- 通过 `env + domain + module + shardId` lease scope 与 onebox 安全竞争
- 具备回滚到 seed-box onebox 的配置路径

---

## 4.1 local-gamma mirror（本地组合拓扑预测试）

`local-gamma mirror` 用于提交前在本机验证组合拓扑，不改变本文件的当前环境映射：

1. 运行时仍使用 `APP_ENV=gamma`，不得新增 `local-gamma` 环境名。
2. 本地 Docker compose 的进程/domain 归属必须按 `gamma` 映射设计，不能引入本地独有 domain 绑定。
3. 本地配置版本必须显式绑定，例如 `CONFIG_VERSION=local-gamma-v1`；配置挂载结构遵守 `CONFIG_ROOT/configs/<service>/<env>/config.yaml` 与 `CONFIG_ROOT/quwoquan_service/services/<service>/<version>.yaml`。
4. App 以 `APP_RUNTIME_ENV=gamma`、`APP_DATA_SOURCE=remote` 连接本地 mirror endpoint，测试数据来自 `app_gamma_seed_manifest.json`。
5. 每次提交前运行 `make gate-local-gamma`，报告写入 `.qwq_output/env/gamma/local/gamma-local/report.json`；缺少 DNS、TLS、设备或服务依赖时状态为 `GATE_BLOCK`。

本地通过只证明提交前左移质量，不代表云侧 gamma 或 prod 的发布真实性已通过。

---

## 5. Kustomize（modular-monolith-first + 管理面独立发布）

目录：
- `quwoquan_service/services/seed-box/deploy/kustomize/base`（Go Modular Monolith 单 Deployment + Service/HPA/PDB）
- `quwoquan_service/services/seed-box/deploy/kustomize/overlays/{dev,integration,beta,prod}`（迁移期 dev→`APP_ENV=alpha`、integration→`APP_ENV=gamma`）
- `quwoquan_service/services/recommendation-service/deploy/kustomize/base`（Python 独立 Deployment + Service/HPA/PDB）
- `quwoquan_service/services/recommendation-service/deploy/kustomize/overlays/{dev,integration,beta,prod}`
- `quwoquan_service/services/product-ops-service/deploy/kustomize/base`（管理/运营/运维面独立 Deployment + Service/HPA/PDB）
- `quwoquan_service/services/product-ops-service/deploy/kustomize/overlays/prod`
- `quwoquan_ops/environments/kustomization/{aliyun,volcengine,huaweicloud}-{integration,prod}`（root，聚合独立 overlay）

约束：
- base 只放跨环境稳定模板（Deployment/Service/HPA/PDB）
- 环境差异仅在 overlays 注入
- 参数化覆盖：`CONFIG_VERSION`、`IMAGE_VERSION`、`replicas`、HPA 阈值
- seed-box、recommendation-service、product-ops-service 各自独立 Deployment/Service/HPA/PDB；禁止把 recommendation 或 product-ops 作为 seed-box Pod 内 sidecar / child process
- seed-box 调用 recommendation 走集群 Service DNS（`http://recommendation-service:8000`），不走 Pod 内 `127.0.0.1`

示例：

```bash
# 渲染 prod root（聚合 seed-box、recommendation、product-ops 等独立 workload）
kustomize build quwoquan_ops/environments/kustomization/aliyun-prod

# 渲染 seed-box overlay
kustomize build quwoquan_service/services/seed-box/deploy/kustomize/overlays/prod

# 渲染 recommendation-service overlay
kustomize build quwoquan_service/services/recommendation-service/deploy/kustomize/overlays/prod

# 渲染 product-ops-service overlay
kustomize build quwoquan_service/services/product-ops-service/deploy/kustomize/overlays/prod
```

---

## 6. 渐进拆分独立 Deployment（Strangler Fig 迁移指引）

> 完整拆分手册（触发阈值、契约不变门禁、模板与回滚）见 `quwoquan_ops/environments/strangler_split_playbook.md`。

- 现态：`seed-box`（Go Modular Monolith 单 Deployment）、`recommendation-service`（Python 独立 Deployment）与 `product-ops-service`（管理/运营/运维面独立 Deployment）同集群、同 namespace、各自独立 Service/HPA/PDB；`seed-box` 经集群 Service DNS `http://recommendation-service:8000` 调用，已不再 sidecar 共用 Pod
- 拆分触发：某领域服务需要独立扩缩容/独立发布窗口/独立故障域
- 拆分原则：
  - 保持 `process_domain_mapping.yaml` 归属唯一与 beta/gamma/prod 一致性
  - 保持领域 API 路径与契约不变
  - 复用同一参数模型（`CONFIG_VERSION/IMAGE_VERSION/replicas/HPA`）
  - 拆分 package 只移动 module，不移动领域事务事实源
  - dispatcher/worker 必须通过可靠任务租约接管，不得双写或重复 ACK

典型拆分：

```yaml
chat-avatar-worker-package:
  modules:
    - chat.group_avatar_worker
```

拆分触发阈值：
- ready backlog 持续超过阈值
- outbox pending 最大滞留超过阈值
- worker CPU/Memory 长期超过阈值
- fanout P95 超过 SLO
- DLQ rate 或 retry rate 异常

---

## 7. 常见失败与处理

- 失败：`domain 'x' appears in both ...`
  - 处理：在同一环境内仅保留一个归属进程

- 失败：`beta, gamma and prod process-domain mapping must be identical`
  - 处理：将 `gamma`、`prod` 调整为与 `beta` 完全一致

- 失败：进程名不合规
  - 处理：使用 `*-service` 或 `seed-box`

---

## 8. 变更流程（最小）

1) 修改 `quwoquan_ops/environments/process_domain_mapping.yaml`  
2) 修改 `quwoquan_ops/environments/module_package_mapping.yaml`、`quwoquan_ops/environments/reliable_task_module_catalog.yaml` 或 `quwoquan_ops/environments/reliable_task_retention_policy.yaml`（如涉及模块/任务/保留策略）
3) 若涉及部署形态 / 新增 workload / Strangler 拆分，修改 `quwoquan_ops/environments/workload_topology_inventory.yaml`（三态分类 + 标准原语 + `wired_to_prod_root`）
4) 执行 `bash scripts/verify_deployment_domain_mapping.sh`
5) 执行 `python3 scripts/verify_module_package_mapping.py`
6) 执行 `python3 quwoquan_ops/environments/verify/verify_workload_topology_inventory.py`
7) 执行 `python3 scripts/verify_reliable_task_catalog.py`
8) 执行 `python3 scripts/verify_reliable_task_retention_policy.py`
9) 执行 `make verify`（至少）
10) 提交前执行 `make gate-full`

