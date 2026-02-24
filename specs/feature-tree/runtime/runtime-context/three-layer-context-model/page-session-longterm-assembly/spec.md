# L4 对象任务：page-session-longterm-assembly

## 功能说明
- **PageContext Manager**：端侧上报接口 + 解析 + Redis 存储；支持 8 种页面场景（content_detail、feed、chat、circle 等）；含 userActions 数组；TTL 自动过期。
- **Session Context**：从 Redis 热路径（推荐服务写入）读取实时兴趣信号。
- **LongTerm Profile Reader**：从向量存储或 MongoDB 读取 user_holistic_profile。
- **ContextAssembler**：按 userId 聚合三层，耗时 < 50ms。

## 实现要点
- **PageContext API**：POST /v1/context/page，body 含 scene_type、snapshot、userActions；Redis key: context:page:{userId}。
- **Session**：Redis key 与推荐热路径约定一致；读取最近 N 条兴趣信号。
- **LongTerm**：从 user_holistic_profile 集合或向量存储读取。
- **Assembler**：并行读取三层，合并后返回。

## 约束
- PageContext TTL 可配置。
- 组装耗时 < 50ms。
- 按 userId 隔离。

## 验收标准
- A1：PageContext 上报 + 过期 + Session + LongTerm 读取 + 组装端到端正确。
- A2：页面切换时旧 PageContext 自动过期。
- A8：PageContext 单元测试 + ContextAssembler 端到端测试。
