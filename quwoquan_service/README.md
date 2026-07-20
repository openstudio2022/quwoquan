# quwoquan_service

`quwoquan_service` 是服务域工程根，只保存服务源码、服务契约、共享 runtime、生成产物与服务侧验证工具。跨环境编排、CI/CD 调度、可观测聚合和运行输出归 `quwoquan_ops/` 与根 `.qwq_output/`。

## 目录职责

```text
quwoquan_service/
  contracts/     # 服务契约真相源：metadata、runtime_errors、observability 和横切规范
  generated/     # 由 tools/ 生成的共享服务产物
  runtime/       # Go 公共 runtime：错误、配置、观测、HTTP、MQ、投影、媒体等
  services/      # 各领域服务源码和自治 configs/deploy/releases
  tools/         # Go codegen/verify/render 工具源码，统一 go run ./tools/...
  scripts/       # 服务域 contract/verify/runtime/recommendation 辅助脚本
```

## 边界规则

- 服务发布配置放在 `services/<service>/configs/releases/`。
- 服务私有 Dockerfile、k8s、compose 片段放在 `services/<service>/deploy/`。
- 跨服务 compose、环境拓扑、stackctl、CI/CD gate 放在 `quwoquan_ops/`。
- 本地运行状态、缓存、报告和包产物只写根 `.qwq_output/`。
- `contracts/metadata/**` 是字段、路由、错误码、投影、行为和测试 fixture 的服务契约真相源。
- 根目录不保留构建二进制、历史 specs、历史方案文档、compose 文件、cache 或 state。

## 常用命令

```bash
cd quwoquan_service
make verify-metadata
make codegen
bash scripts/contract/verify_contract_metadata.sh
python3 scripts/verify/verify_service_layout.py
```

跨环境打包与验证使用：

```bash
python3 quwoquan_ops/cli/stackctl.py package --env alpha --kind runtime --include-services
python3 quwoquan_ops/cli/stackctl.py verify --env alpha --kind all --profile smoke
```
