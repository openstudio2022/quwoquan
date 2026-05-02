# L4 对象任务：v3-directory-parser-and-validator

## 功能说明
- **Parser**：解析 v3 目录下的 YAML 文件（aggregate.yaml、entity.yaml、fields.yaml、events.yaml、storage.yaml、service.yaml），输出结构化 Go 对象。
- **Validator**：校验 metadata 内部一致性，包括字段引用、事件引用、存储映射的存在性与正确性。

## 实现要点
- **YAML 解析**：使用标准 YAML 库解析，支持 v3 schema 约定（字段名、类型、嵌套结构）。
- **Schema 校验**：校验必填字段、类型、枚举值，非法 schema 返回明确错误。
- **跨文件引用检查**：entity 引用的 fields/events/storage 必须在对应 YAML 中存在；字段引用、事件引用、存储映射必须可解析。

## 约束
- 解析失败必须返回包含文件路径、行号、字段名的错误。
- 校验失败必须阻止加载完成，不静默忽略。

## 验收标准
- A7：Parser 输出与 contracts/metadata/ YAML 完全一致；Validator 覆盖全部引用类型。
- A8：Parser + Validator 单元测试，metadata 一致性 contract 测试。

## Folded current node `runtime-query-api-and-hot-reload`

# L5 横切：runtime-query-api-and-hot-reload

## 功能说明
- **Query API**：提供 GetEntity、GetFieldPolicy、GetCapabilities、GetStorageBackend、GetCacheTTL、GetTagTaxonomy 等运行时查询接口。
- **并发安全**：Registry 读多写少，使用 RWMutex 或 copy-on-write 保证并发安全。
- **Hot-reload**：监听 metadata 目录变更，重新加载并原子替换 Registry，支持配置开关与灰度。

## 实现要点
- **Query API 设计**：接口返回只读视图，避免调用方修改内部状态。
- **并发安全**：读路径无锁或读锁，写路径（Hot-reload）使用写锁或原子指针替换。
- **Hot-reload 机制**：文件变更检测（fsnotify 或轮询）、重新 Load、校验通过后原子替换、失败时保留过往版本本。

## 约束
- 未注册实体查询必须返回明确错误，不返回空值静默。
- Hot-reload 失败不替换现有 Registry，输出错误日志。

## 验收标准
- A3：metadata 加载 < 500ms，不阻塞启动；Hot-reload 可配置。
- A4：加载完成输出 entity/字段总数；Hot-reload 输出变更摘要。
- A8：Query API + Hot-reload 单元测试。
