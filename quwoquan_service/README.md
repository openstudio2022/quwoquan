# quwoquan_service

`quwoquan_service` 保存对象优先的领域服务及其自治契约、源码、配置定义、资源、部署基线、四环境入口、观测和测试。`quwoquan_ops/` 只做跨服务环境装配、外部 workload 和平台策略；`.qwq_output/` 只保存可删除的派生包与证据。

## 目录职责

```text
quwoquan_service/
  contracts/metadata/     # 跨服务 schema 与共享协议，不保存对象注册表
  services/               # services/<service> 自治边界
  control-plane/          # platform-ops 等控制面源码
  static/                 # legal 等版本化静态制品
  runtime/                # 错误、HTTP、消息、观测等跨域技术机制
  generated/              # 可重建的跨服务 ContractGraph/codegen 产物
  tools/                  # compiler/codegen/verify 工具
  scripts/                # 服务域专项子门禁与辅助命令
```

每个第一方服务固定采用：

```text
services/<service>/
  contracts/<context>/<object>/
  internal/<context>/<object>/<layer>/
  generated/<context>/<object>/
  config/schema.yaml
  resources/
  deploy/base/
  deploy/compose.yaml
  environments/{alpha,beta,gamma,prod}/{config.yaml,deploy/}
  observability/
  build/Dockerfile
  tests/{local_contract,api_integration,support}/
```

`contracts/domain.yaml` 是服务 metadata domain 的唯一声明，因此 `internal` 不重复 domain 层。`generated` 与人工维护的 `internal` 物理分离。四环境是星型入口：都只引用公共 `config/schema.yaml`、`resources/`、`deploy/base`，环境之间不得继承。Ops 的 Compose/Kustomize 文件只能装配，不得复制第一方 workload 定义。

Go 领域服务共享根 `quwoquan_service/go.mod`，服务内禁止再建嵌套 module 或 `go.work`；这是技术构建边界，不是业务所有权注册。每个 Go 服务仍通过自己的 `Makefile`、`build/Dockerfile` 和环境入口独立构建发布。Python `recommendation-service` 使用本服务 `pyproject.toml`。

## 常用命令

```bash
make verify-service-architecture
make verify-metadata
make codegen
python3 quwoquan_ops/cli/stackctl.py package --service content-service --env alpha
python3 quwoquan_ops/cli/stackctl.py verify --service content-service --env alpha
```

新服务只通过：

```bash
make new-service SERVICE=<service-id> CONTEXT=<domain.context> OBJECT=<business-object> LANGUAGE=go|python
```
