# L3 子特性：three-layer-context-model

## 功能说明
- **PageContext**：端侧上报的当前页面上下文（8 种场景：content_detail、feed、chat、circle 等），含 PostSnapshot、userActions 数组；Redis 存储，TTL 可配置。
- **SessionContext**：从 Redis 热路径获取的实时兴趣信号（最近浏览、点击、搜索等）。
- **LongTermProfile**：user_holistic_profile 五维画像，消费全域事件异步构建；向量存储。
- **ContextAssembler**：组装三层上下文，提供给 QA Runner / Skill / Suggested Actions。

## 实现要点
- **接口定义**：PageContextManager、SessionContextReader、LongTermProfileReader、ContextAssembler。
- **数据流**：端侧 → PageContext API → Redis；Projector → LongTermProfile；ContextAssembler 聚合。

## 约束
- 各层 TTL 可配置。
- 上下文按 userId 隔离。
- 结构与 entity_catalog、_vectors/*.yaml 一致。

## 验收标准
- A1：三层模型接口定义完整，ContextAssembler 可组装。
- A7：与 metadata 一致。
- A8：模型接口单元测试。
