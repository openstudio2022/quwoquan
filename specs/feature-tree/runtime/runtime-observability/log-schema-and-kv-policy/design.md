# 设计说明：端云一体日志统一模型

## 设计动因

当前日志可用但语义不统一，存在：

- `logType` 与交互对象混用
- 跨端云/跨 Python 关联字段缺失
- 同类故障无法稳定聚合（failureCode 非标准）

目标是把“人工拼图式排障”升级为“单 Run 可回放 + 跨栈可归因”。

## 设计决策

1. **统一五元组**
   - `logType`（类型）+ `level`（级别）+ `component`（组件）+ `target`（对象）+ `action`（动作）
2. **两层来源标识**
   - `sourceDomain`（assistant/content/discovery/chat/create）
   - `sourceService`（quwoquan_app/quwoquan_service/python_worker）
3. **关联键标准化**
   - `sessionId + pageVisitId + traceId + requestId`
4. **兼容策略**
   - 查询脚本兼容记录 `currentLogType`，新日志信封不再写入该字段

## 方案对比

- 方案 A（仅补字段不改语义）：成本低，但后续仍会混乱
- 方案 B（统一语义 + 兼容旧字段）：一次改透，后续治理成本最低（采纳）

## 风险与缓解

- 风险：日志查询脚本依赖旧 `logType`
  - 缓解：查询层双读记录 `currentLogType` 与新 `logType`，写入层只保留新字段
- 风险：Release 采样导致成功链路不完整
  - 缓解：Boost run/session + 错误全量保留

## 演进路径

- Phase 1：端侧模型与关键埋点统一（本节点）
- Phase 2：云侧与 Python 对齐同一 Canonical 映射
- Phase 3：统一查询视图与自动根因聚合
