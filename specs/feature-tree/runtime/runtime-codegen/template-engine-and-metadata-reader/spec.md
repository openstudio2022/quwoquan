# L3 子特性：template-engine-and-metadata-reader

## 功能说明
- **唯一 Source**：模板只消费
  `quwoquan_service/internal/metadata/codegen` 暴露的 ContractGraph Source。
- **Go Template Engine**：基于 `text/template`，支持确定性的命名与类型函数，按
  Graph descriptor 渲染生成代码。
- **Template Registration**：模板名与产物类型显式映射；模板不能自行读取 YAML，
  也不能根据存储类型猜测业务对象边界。

## 实现要点
- **Compiler Pipeline**：`ast -> load -> validate -> graph -> codegen` 是唯一读取路径。
- **Engine Setup**：初始化 `template.FuncMap`，注册 snake_case、goType、nullable、
  plural 等纯函数。
- **Template Input**：只接受已通过 commercial validate 的 object、operation、
  event、field、Slice 与 store descriptor。
- **派生边界**：模板生成 model/descriptor/transport/migration 等确定性产物；
  Object Facade/Data Ports 的业务语义由 D0 metadata 与手写实现承担，模板不得发明。

## 约束
- 所有 generator 共用同一个 ContractGraph Source，禁止新增第二个 metadata parser。
- compiler 只在构建期运行；服务启动不读取 metadata。
- 模板渲染失败必须返回包含模板名、行号的错误。
- generate/check 必须幂等，missing、stale、orphan 任一失败。

## 验收标准
- A1：Engine 可从同一 Graph 确定性生成 Go、Dart、OpenAPI 与 coverage 产物。
- A7：commercial validate、generate、check 连跑幂等；generator 无直接 metadata
  文件读取。
