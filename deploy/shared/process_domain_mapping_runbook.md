# Deployment Process-Domain Mapping 最小运行手册

## 1. 目标

在不改变领域 API 契约的前提下，统一管理三态部署拓扑：
- `dev`：独立服务开发测试
- `integration`：集成联调与集成测试
- `prod`：生产发布

唯一配置文件：`deploy/shared/process_domain_mapping.yaml`

---

## 2. 配置模型

```yaml
environments:
  dev:
    content-service:
      domains: [content]
    integration-service:
      domains: [integration]
  integration:
    quwoquan_service:
      domains: [content, integration, chat, user, circle, assistant, gateway, orchestrator]
  prod:
    quwoquan_service:
      domains: [content, integration, chat, user, circle, assistant, gateway, orchestrator]
```

强约束：
- 同一环境下，一个 `domain` 只能出现一次
- `integration` 与 `prod` 映射必须一致
- 对外接口仍按领域服务暴露（如 `/v1/content/*`），不受进程组合影响

---

## 3. dev 运行（默认独立）

1) 确认映射配置合法：

```bash
bash scripts/verify_deployment_domain_mapping.sh
```

2) 按服务名启动独立进程（示例）：

```bash
# content-service
SERVICE_NAME=content-service APP_ENV=dev go run ./quwoquan_service/services/content-service/cmd/api

# integration-service
SERVICE_NAME=integration-service APP_ENV=dev go run ./quwoquan_service/services/integration-service/cmd/api
```

3) 开发态校验：

```bash
make verify
```

---

## 4. integration / prod 运行（组合拓扑）

1) 先验证映射（必须通过）：

```bash
bash scripts/verify_deployment_domain_mapping.sh
```

2) 使用组合进程 `quwoquan_service` 启动（由部署编排注入环境变量）：

```bash
APP_ENV=integration SERVICE_NAME=quwoquan_service CONFIG_ROOT=/etc/qwq-config CONFIG_VERSION=<version> IMAGE_VERSION=<image> <start-command>
```

生产同理，仅 `APP_ENV=prod`：

```bash
APP_ENV=prod SERVICE_NAME=quwoquan_service CONFIG_ROOT=/etc/qwq-config CONFIG_VERSION=<version> IMAGE_VERSION=<image> <start-command>
```

3) 发布前全量门禁：

```bash
make gate-full
```

---

## 5. 常见失败与处理

- 失败：`domain 'x' appears in both ...`
  - 处理：在同一环境内仅保留一个归属进程

- 失败：`integration and prod process-domain mapping must be identical`
  - 处理：将 `prod` 调整为与 `integration` 完全一致

- 失败：进程名不合规
  - 处理：使用 `*-service` 或 `quwoquan_service`

---

## 6. 变更流程（最小）

1) 修改 `deploy/shared/process_domain_mapping.yaml`  
2) 执行 `bash scripts/verify_deployment_domain_mapping.sh`  
3) 执行 `make verify`（至少）  
4) 提交前执行 `make gate-full`

