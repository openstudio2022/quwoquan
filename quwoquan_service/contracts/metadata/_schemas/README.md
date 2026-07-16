# Contract metadata schema

本目录冻结 `qwq-contract` 的严格输入和规范化输出。

- `aggregate.schema.json`：`aggregate.yaml` 顶层合同。
- `entity.schema.json`：`entity.yaml` 顶层合同。
- `service.schema.json`：`service.yaml` 与 operation application binding。
- `contract_graph.schema.json`：所有 generator/coverage 消费的规范化图。

compiler 必须拒绝未知顶层字段、重复 key、重复 object/operation/transport ID 和悬空引用。
本目录只保存当前 schema。变更必须一次性切换全部 metadata、compiler 与 generator；
禁止版本目录、旧格式 loader、迁移 adapter 或运行时兼容分支。
