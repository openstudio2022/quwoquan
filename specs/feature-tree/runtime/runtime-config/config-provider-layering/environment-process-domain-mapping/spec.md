# L4 细节：environment-process-domain-mapping

## 功能说明

定义部署态下“服务进程（非领域服务）→ 领域服务集合（domains）”的统一映射模型，覆盖三种环境：
- `dev`：默认独立进程开发测试，服务名与部署进程名一致
- `integration`：用于集成联调与集成测试，通常与生产拓扑一致
- `prod`：生产发布拓扑

统一配置文件：`deploy/shared/process_domain_mapping.yaml`

部署目录分层：
- `deploy/shared/`：端云共享部署契约
- `deploy/service/`：服务端部署资产
- `deploy/app/`：端侧发布资产

## 核心约束

- 一个 domain 在同一环境中只能归属一个部署进程
- `integration` 与 `prod` 的进程-领域映射必须一致
- 对外接口仍按领域服务暴露（`/v1/content/*`、`/v1/chat/*` 等），不受部署拓扑影响
- 不新增 `all-in-one/`、`content-only/` 目录，代码目录保持按领域服务组织

## 边界说明

本节点负责：
- 拓扑声明格式
- 拓扑一致性门禁
- 开发/集成/生产三态流程约束

本节点不负责：
- 具体业务路由实现
- 运行时网关编排策略细节（由 gateway/orchestrator 节点承担）

## 验收标准

- A1：`deploy/shared/process_domain_mapping.yaml` 可表达 dev/integration/prod 三态拓扑
- A3：门禁可阻断 domain 重复归属与 integration/prod 漂移
- A7：部署进程映射不改变领域 API 契约
- A8：`make verify`/`make gate` 自动执行映射校验
