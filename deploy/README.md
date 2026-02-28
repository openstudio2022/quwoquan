# Deploy 目录分层说明

`deploy/` 作为端云统一部署根目录，按职责拆分：

- `deploy/shared/`：端云共享部署契约（环境拓扑、全局门禁输入、共享 runbook）
- `deploy/service/`：服务端部署资产（K8s/compose/config-release 等）
- `deploy/app/`：端侧发布资产（构建渠道、签名、分发）

放置原则：
- 同时约束端云或全局流程：放 `shared/`
- 仅服务端部署相关：放 `service/`
- 仅端侧发布相关：放 `app/`
