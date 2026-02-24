# L5 横切：runtime-query-api-and-hot-reload

## 功能说明
- **Query API**：提供 GetEntity、GetFieldPolicy、GetCapabilities、GetStorageBackend、GetCacheTTL、GetTagTaxonomy 等运行时查询接口。
- **并发安全**：Registry 读多写少，使用 RWMutex 或 copy-on-write 保证并发安全。
- **Hot-reload**：监听 metadata 目录变更，重新加载并原子替换 Registry，支持配置开关与灰度。

## 实现要点
- **Query API 设计**：接口返回只读视图，避免调用方修改内部状态。
- **并发安全**：读路径无锁或读锁，写路径（Hot-reload）使用写锁或原子指针替换。
- **Hot-reload 机制**：文件变更检测（fsnotify 或轮询）、重新 Load、校验通过后原子替换、失败时保留旧版本。

## 约束
- 未注册实体查询必须返回明确错误，不返回空值静默。
- Hot-reload 失败不替换现有 Registry，输出错误日志。

## 验收标准
- A3：metadata 加载 < 500ms，不阻塞启动；Hot-reload 可配置。
- A4：加载完成输出 entity/字段总数；Hot-reload 输出变更摘要。
- A8：Query API + Hot-reload 单元测试。
