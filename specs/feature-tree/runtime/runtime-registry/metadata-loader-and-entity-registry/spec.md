# L3 子特性：metadata-loader-and-entity-registry

## 功能说明
- 从 metadata v3 模块化目录结构加载全部 YAML 文件。
- 解析 aggregate.yaml / entity.yaml，并解析关联的 fields.yaml、events.yaml、storage.yaml、service.yaml。
- 解析跨文件引用：aggregate → entity，entity → fields/events/storage。
- 组装为 EntityRegistry 运行时结构，供 Repository 和拦截链使用。

## 实现要点
- **v3 目录解析**：遍历 `contracts/metadata/` 下各聚合目录，按约定命名加载 5 类 YAML。
- **跨引用解析**：entity 引用 fields/events/storage 时，按相对路径或约定路径解析。
- **一致性校验**：字段引用、事件引用、存储映射必须在 metadata 内存在，否则加载失败。

## 约束
- 加载失败必须返回明确错误，不静默降级。
- 加载结果与 contracts/metadata/ 源文件内容完全一致。

## 验收标准
- A1：Loader 可正确加载全部 v3 目录，输出完整 EntityRegistry。
- A7：Loader 输出与 contracts/metadata/ YAML 完全一致。
- A8：Loader 单元测试 + metadata 一致性 contract 测试。
