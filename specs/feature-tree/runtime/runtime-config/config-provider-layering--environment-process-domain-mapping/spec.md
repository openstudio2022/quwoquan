# L4 细节：environment-process-domain-mapping

## 功能说明

定义部署态下“服务进程（非领域服务）→ 领域服务集合（domains）”的统一映射模型，覆盖四种交付环境：
- `alpha`：默认独立进程开发测试，服务名与部署进程名一致
- `beta`：本地端云集成与联调，拓扑与云侧发布态对齐
- `gamma`：云侧类生产集成验证
- `prod`：生产发布拓扑

`dev` 可以保留为开发脚手架别名，但不作为当前门禁基线。

统一配置文件：`quwoquan_ops/environments/process_domain_mapping.yaml`

部署目录分层：
- `quwoquan_ops/environments/`：端云共享部署契约
- `deploy/service/`：服务端部署资产
- `deploy/app/`：端侧发布资产

## 核心约束

- 一个 domain 在同一环境中只能归属一个部署进程
- `beta`、`gamma`、`prod` 的进程-领域映射必须一致
- 对外接口仍按领域服务暴露（`/v1/content/*`、`/v1/chat/*` 等），不受部署拓扑影响
- 不新增 `all-in-one/`、`content-only/` 目录，代码目录保持按领域服务组织
- 模块化部署通过 `RuntimeModule` 与 `DeploymentPackage` 表达；onebox 是 package 组合，不是业务代码目录
- `quwoquan_ops/environments/module_package_mapping.yaml` 表达 `deploymentPackage -> modules`，并必须与 `process_domain_mapping.yaml` 的 domain 归属一致
- package 中 module 的 domain 必须属于该 package/process 的 domains
- module 名称必须满足 `{domain}.{capability}`，例如 `chat.task_outbox_dispatcher`
- 同一环境内 domain 仍只能归属一个 process/package，但一个 package 可组合多个 domain 的 module
- `recommendation` domain 固定归属 `recommendation-service`（python process）
- Go 组合进程与 Python 进程独立部署，禁止合并为单进程
- Python 配置校验失败策略为启动即失败（fail-fast）
- 允许采用 K8s Sidecar 实现“逻辑耦合、物理隔离”：`seed-box` 与 `recommendation-service` 同 Pod 双进程
- 同一套 Kustomize overlays（`alpha/beta/gamma/prod`）必须参数化 `CONFIG_VERSION/IMAGE_VERSION/replicas/HPA` 阈值
- 部署形态需支持后续将领域服务（如 content-service）拆解为独立 Pod，而不改变 domain API 语义
- `beta/gamma/prod` 的 package/module mapping 必须一致；prod 内若要灰度拆分 worker package，必须显式声明 override 与回滚条件

## 边界说明

本节点负责：
- 拓扑声明格式
- 拓扑一致性门禁
- 开发/集成/生产四态流程约束

本节点不负责：
- 具体业务路由实现
- 运行时网关编排策略细节（由 gateway/orchestrator 节点承担）

## 验收标准

- A1：`quwoquan_ops/environments/process_domain_mapping.yaml` 可表达 alpha/beta/gamma/prod 四态拓扑
- A3：门禁可阻断 domain 重复归属与 beta/gamma/prod 漂移
- A7：部署进程映射不改变领域 API 契约
- A8：`make verify`/`make gate` 自动执行映射校验
- A8：`make gate-full` 将 `recommendation-service` 的 Python 测试作为必过项
- A1：all-in-one Sidecar 生产增强模板可在 Kustomize 下按环境参数化渲染
- A3：从 all-in-one 到独立 Pod 拆分具备明确迁移路径与兼容策略
- A1：`module_package_mapping.yaml` 可表达 seed-box onebox、单领域 background package、热点 worker package
- A3：门禁可阻断 package 中 module 越权挂载未归属 domain
- A3：门禁可阻断 task catalog 引用不存在的 module 或 package
- A7：module/package 拆分不改变领域 API、Outbox 事实源、队列路由语义
- A8：`make verify`/`make gate` 自动执行 module/package/catalog/retention 校验

## 统一门禁矩阵（FF 配置发布契约）

| 阶段命令 | 必过项（最小集） | 不通过处理 |
|---|---|---|
| `/prd` | spec.md 含 module/package/domain 映射与环境变量范围；acceptance.yaml 含对应验收项 | 阻断 FF，先补文档 |
| `/design` | 每服务 default/alpha/beta/gamma/prod 目录齐；APP_ENV 与进程-领域映射校验有测试；门禁脚本可执行 | 阻断 apply，先补实现与测试 |
| `/commit` / submit-with-gate | strict gate 通过；CONFIG_VERSION 文件存在且可映射；配置-镜像兼容校验通过 | 禁止提交入库 |
