# 开发任务：environment-process-domain-mapping

## 统一门禁矩阵（简版）

| 阶段命令 | 必过项（最小集） | 不通过处理 |
|---|---|---|
| `/opsx-ff` | ① 特性树新增 L4 节点并补齐四件套；② 产出 `deploy/shared/process_domain_mapping.yaml`；③ 规则文档补充三态约束 | 阻断 FF，先补文档与配置 |
| `/opsx-apply` | ① 增加映射门禁脚本；② 接入 `make verify` 与 `gate_repo.sh`；③ 修复校验失败项 | 阻断 apply，先补门禁 |
| `submit-with-gate` | ① `verify_deployment_domain_mapping.sh` PASS；② integration/prod 拓扑一致；③ 无 domain 重复归属 | 禁止提交入库 |

## 当前交付任务

### Wave 1 — 命名与拓扑基线

- [x] D1 新增部署进程映射文件 `deploy/shared/process_domain_mapping.yaml`
- [x] D2 新增门禁脚本 `scripts/verify_deployment_domain_mapping.sh`
- [x] D3 将门禁接入 `Makefile verify` 与 `scripts/gate_repo.sh`
- [x] D4 将设计约束写入特性树文档（spec/design/tasks/acceptance）
- [x] D5 将流程与架构规范补充到 `.cursor/rules` 与主线文档
- [x] D5.1 产出最小运行手册 `deploy/shared/process_domain_mapping_runbook.md`
- [x] D5.2 完成 deploy 目录结构迁移：`shared/service/app` 分层
- [x] D5.3 recommendation domain 固定映射到 `recommendation-service`
- [x] D5.4 deploy 资产统一将 `rec-model-service` 命名迁移为 `recommendation-service`

### Wave 2 — Python 运行时解耦与 fail-fast

- [x] D6 在 `recommendation-service` 增加配置分层加载（default->env->version->env vars）
- [x] D7 增加 `APP_ENV/SERVICE_NAME/CONFIG_VERSION/IMAGE_VERSION/CONFIG_ROOT` 契约校验
- [x] D8 配置或版本兼容校验失败时启动立即失败（fail-fast）
- [x] D9 更新 Python 服务 README/CONFIG.md 与 runbook 对齐新契约

### Wave 3 — gate-full 强制测试

- [x] D10 将 `recommendation-service` Python 测试接入 `make gate-full` 必过
- [x] D11 增加 Python 配置契约校验脚本并接入 `make verify`
- [x] D12 补齐 split-dev / integration-prod 拓扑回归测试与证据

### Wave 4 — 端到端契约一致性

- [x] D13 验证 content-service 到 recommendation-service 调用契约稳定
- [x] D14 验证部署拓扑变化不改变 domain API 语义与错误码行为
- [x] D15 产出 deliver 证据包（gate 日志、契约测试、回归结果）

## 后续演进任务

- [x] D16 增加“变更影响报告”：当映射变更时自动输出受影响 domain 与进程
- [x] D17 在 CI 中增加环境级回归（split dev / composed integration）对比测试
