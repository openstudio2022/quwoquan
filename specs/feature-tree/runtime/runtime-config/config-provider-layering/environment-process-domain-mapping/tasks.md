# 开发任务：environment-process-domain-mapping

## 统一门禁矩阵（简版）

| 阶段命令 | 必过项（最小集） | 不通过处理 |
|---|---|---|
| `/opsx-ff` | ① 特性树新增 L4 节点并补齐四件套；② 产出 `deploy/shared/process_domain_mapping.yaml`；③ 规则文档补充三态约束 | 阻断 FF，先补文档与配置 |
| `/opsx-apply` | ① 增加映射门禁脚本；② 接入 `make verify` 与 `gate_repo.sh`；③ 修复校验失败项 | 阻断 apply，先补门禁 |
| `submit-with-gate` | ① `verify_deployment_domain_mapping.sh` PASS；② integration/prod 拓扑一致；③ 无 domain 重复归属 | 禁止提交入库 |

## 当前交付任务

- [x] D1 新增部署进程映射文件 `deploy/shared/process_domain_mapping.yaml`
- [x] D2 新增门禁脚本 `scripts/verify_deployment_domain_mapping.sh`
- [x] D3 将门禁接入 `Makefile verify` 与 `scripts/gate_repo.sh`
- [x] D4 将设计约束写入特性树文档（spec/design/tasks/acceptance）
- [x] D5 将流程与架构规范补充到 `.cursor/rules` 与主线文档
- [x] D5.1 产出最小运行手册 `deploy/shared/process_domain_mapping_runbook.md`
- [x] D5.2 完成 deploy 目录结构迁移：`shared/service/app` 分层

## 后续演进任务

- [ ] D6 增加“变更影响报告”：当映射变更时自动输出受影响 domain 与进程
- [ ] D7 在 CI 中增加环境级回归（split dev / composed integration）对比测试
