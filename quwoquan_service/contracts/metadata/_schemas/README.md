# Contract metadata schema

本目录冻结 `qwq-contract` 的严格输入和规范化输出。

- `context.schema.json`、`object.schema.json`：bounded context 与独立对象根。
- `fields.schema.json`：对象字段、成员、值对象、类型与 enum 声明。
- `operations.schema.json`：operation application binding；非 body 请求位置只认 `request_bindings.path/query/injected`。
- `storage.schema.json`、`events.schema.json`、`errors.schema.json`：对象存储、事件和错误输入。
- `contract_graph.schema.json`：所有 generator/coverage 消费的规范化图。

JSON Schema 负责单文档结构；compiler 的 typed AST validator 负责跨文档语义，包括 request path 对位、lifecycle↔enum、enum owner、type/semantic type、error surface、event payload/consumer 与 projection output 唯一性。两层任一失败均为硬失败。

compiler 必须拒绝未知顶层字段、重复 key、重复 object/operation/transport ID 和悬空引用。
本目录只保存当前 schema。变更必须一次性切换全部 metadata、compiler 与 generator；
禁止版本目录、旧格式 loader、迁移 adapter 或运行时兼容分支。

`_shared/app_artifact_manifest.yaml` 与 `_shared/app_launch_manifest.yaml` 共同组成
App 启动合同 source set。`app_artifact_manifest.launch_provenances` 是入口来源闭集，
`app_launch_manifest` 中的 `allowed_values_ref` 必须严格解析到该闭集；未知字段、重复 key、
悬空跨文档引用或两份输入任一缺失都必须阻断 codegen。Python、JSON、Swift、Java
投影与 freshness manifest 必须携带同一个按 source path 排序计算的联合 source digest，
任一投影或输入漂移都不得运行消费者。
