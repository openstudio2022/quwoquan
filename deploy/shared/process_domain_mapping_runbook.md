# Deployment Process-Domain Mapping 最小运行手册

## 1. 目标

在不改变领域 API 契约的前提下，统一管理五态部署拓扑：
- `alpha`：开发期单实例独立验证
- `beta`：开发期本地端云集成验证
- `gamma`：云侧类生产集成验证
- `prod-gray`：生产灰度
- `prod`：生产全量

唯一配置文件：`deploy/shared/process_domain_mapping.yaml`

模块化部署补充真相源：
- `deploy/shared/module_package_mapping.yaml`：声明 deployment package 启动哪些 runtime module。
- `deploy/shared/reliable_task_module_catalog.yaml`：声明 taskType、module capability、队列路由、payload 白名单与 worker 归属。
- `deploy/shared/reliable_task_retention_policy.yaml`：声明 Outbox/Task/Notification/DLQ 的 TTL、归档、限流与恢复策略。

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
    seed-box:
      domains: [content, integration, chat, user, circle, assistant, gateway, orchestrator]
  gamma:
    recommendation-service:
      domains: [recommendation]
    seed-box:
      domains: [content, integration, chat, user, circle, assistant, gateway, orchestrator]
  prod-gray:
    recommendation-service:
      domains: [recommendation]
    seed-box:
      domains: [content, integration, chat, user, circle, assistant, gateway, orchestrator]
  prod:
    recommendation-service:
      domains: [recommendation]
    seed-box:
      domains: [content, integration, chat, user, circle, assistant, gateway, orchestrator]
```

强约束：
- 同一环境下，一个 `domain` 只能出现一次
- `beta`、`gamma`、`prod-gray`、`prod` 映射必须一致
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

## 4. beta / gamma / prod-gray / prod 运行（组合拓扑）

1) 先验证映射（必须通过）：

```bash
bash scripts/verify_deployment_domain_mapping.sh
```

2) 使用组合进程 `seed-box` 启动 Go 聚合进程，Python 的 `recommendation-service` 保持独立进程（由部署编排注入环境变量）：

```bash
APP_ENV=gamma SERVICE_NAME=seed-box CONFIG_ROOT=/etc/seed-box-config CONFIG_VERSION=<version> IMAGE_VERSION=<image> <start-command>
APP_ENV=gamma SERVICE_NAME=recommendation-service CONFIG_ROOT=/etc/seed-box-config CONFIG_VERSION=<version> IMAGE_VERSION=<image> <python-start-command>
```

生产灰度与生产同理，仅 `APP_ENV=prod-gray|prod`：

```bash
APP_ENV=prod-gray SERVICE_NAME=seed-box CONFIG_ROOT=/etc/seed-box-config CONFIG_VERSION=<version> IMAGE_VERSION=<image> <start-command>
APP_ENV=prod SERVICE_NAME=seed-box CONFIG_ROOT=/etc/seed-box-config CONFIG_VERSION=<version> IMAGE_VERSION=<image> <start-command>
```

运行口径补充：

- `beta` 在开发机本地联调时只允许一套组合拓扑，重新启动前必须停止已有实例。
- `gamma` 在 ECS 或 local-gamma mirror 中都只允许一套组合拓扑；部署 / mirror 切换应先清理已有实例再启动新实例。
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

`gamma/prod-gray/prod` 默认与 `beta` 的 module package mapping 一致。热点模块可在 `prod-gray` 灰度拆分为独立 package，但必须满足：
- 保持 `process_domain_mapping.yaml` domain 唯一归属
- 通过 `env + domain + module + shardId` lease scope 与 onebox 安全竞争
- 具备回滚到 seed-box onebox 的配置路径

---

## 4.1 local-gamma mirror（本地组合拓扑预测试）

`local-gamma mirror` 用于提交前在本机验证组合拓扑，不改变本文件的五环境映射：

1. 运行时仍使用 `APP_ENV=gamma`，不得新增 `local-gamma` 环境名。
2. 本地 Docker compose 的进程/domain 归属必须按 `gamma` 映射设计，不能引入本地独有 domain 绑定。
3. 本地配置版本必须显式绑定，例如 `CONFIG_VERSION=local-gamma-v1`；配置挂载结构遵守 `CONFIG_ROOT/configs/<service>/<env>/config.yaml` 与 `CONFIG_ROOT/releases/config/<service>/<version>.yaml`。
4. App 以 `APP_RUNTIME_ENV=gamma`、`APP_DATA_SOURCE=remote` 连接本地 mirror endpoint，测试数据来自 `app_gamma_seed_manifest.json`。
5. 每次提交前运行 `make gate-local-gamma`，报告写入 `artifacts/local-gamma/report.json`；缺少 DNS、TLS、设备或服务依赖时状态为 `GATE_BLOCK`。

本地通过只证明提交前左移质量，不代表云侧 gamma、prod-gray 或 prod 的发布真实性已通过。

---

## 5. Kustomize（all-in-one Sidecar）

目录：
- `deploy/service/seed-box/kustomize/base`
- `deploy/service/seed-box/kustomize/overlays/dev`（迁移期对应 `APP_ENV=alpha`）
- `deploy/service/seed-box/kustomize/overlays/integration`（迁移期对应 `APP_ENV=gamma`）
- `deploy/service/seed-box/kustomize/overlays/prod`

约束：
- base 只放跨环境稳定模板（Deployment/Service/HPA/PDB）
- 环境差异仅在 overlays 注入
- 参数化覆盖：`CONFIG_VERSION`、`IMAGE_VERSION`、`replicas`、HPA 阈值

示例：

```bash
# 渲染 alpha 兼容 overlay
kustomize build deploy/service/seed-box/kustomize/overlays/dev

# 渲染 gamma 兼容 overlay
kustomize build deploy/service/seed-box/kustomize/overlays/integration

# 渲染 prod
kustomize build deploy/service/seed-box/kustomize/overlays/prod
```

---

## 6. 后续拆分独立 Pod（迁移指引）

- 现态：`seed-box` + `recommendation-service` 同 Pod（Sidecar）
- 拆分触发：某领域服务需要独立扩缩容/独立发布窗口/独立故障域
- 拆分原则：
  - 保持 `process_domain_mapping.yaml` 归属唯一与 beta/gamma/prod-gray/prod 一致性
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

- 失败：`beta, gamma, prod-gray and prod process-domain mapping must be identical`
  - 处理：将 `gamma`、`prod-gray`、`prod` 调整为与 `beta` 完全一致

- 失败：进程名不合规
  - 处理：使用 `*-service` 或 `seed-box`

---

## 8. 变更流程（最小）

1) 修改 `deploy/shared/process_domain_mapping.yaml`  
2) 修改 `deploy/shared/module_package_mapping.yaml`、`deploy/shared/reliable_task_module_catalog.yaml` 或 `deploy/shared/reliable_task_retention_policy.yaml`（如涉及模块/任务/保留策略）
3) 执行 `bash scripts/verify_deployment_domain_mapping.sh`
4) 执行 `python3 scripts/verify_module_package_mapping.py`
5) 执行 `python3 scripts/verify_reliable_task_catalog.py`
6) 执行 `python3 scripts/verify_reliable_task_retention_policy.py`
7) 执行 `make verify`（至少）
8) 提交前执行 `make gate-full`

