# L5 横切：event-replay-and-schema-evolution

## 功能说明
- **事件重放**：Replay(aggregate_id, from_version) 返回该聚合自 from_version 起的事件流，用于 Projector 重建 ReadModel。
- **Schema 版本演进**：事件 payload 支持 version 字段；旧版本事件通过 upcaster 或默认值兼容解析。
- **分页**：Replay 支持 offset/limit 分页，避免大结果集 OOM。

## 实现要点
- **Replay**：按 aggregate_id + timestamp 查询；支持 from_version 过滤；可配置 batch_size。
- **Schema 演进**：events.yaml 声明 schema_version；upcaster 映射旧版本 → 新版本。
- **Projector 重建**：全量 Replay 后顺序调用 Projector.Handle，重建 ReadModel。

## 约束
- 事件 schema 版本与 events.yaml 定义一致。
- Replay 不修改原始事件，仅读取。

## 验收标准
- A1：Replay 返回正确事件流；支持 schema 版本兼容。
- A7：事件 schema 版本与 events.yaml 一致。
- A8：Replay 和 schema 演进均有测试。
