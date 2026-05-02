# L3 特性：log-schema-and-kv-policy

## 功能说明

建立端云一体可观测日志统一契约，覆盖：

- 统一信封：`logType + level + sourceDomain + sourceService + component + target + action`
- 统一关联：`sessionId + pageVisitId + traceId + requestId`
- 统一失败码：`failureCode` 枚举化，禁止仅靠 message 文本归因
- 小趣助手增强：感知/回写/流式/UI 联动字段标准化

## 范围

- 端侧 `quwoquan_app` 日志模型升级（兼容旧字段）
- 端侧关键链路埋点对齐（agent/llm/search）
- 文档规范同步：日志设计、诊断模板、TDD 门禁要求
- 预留云侧与 Python 字段映射，不在本节点实现云端代码改造

## 非范围

- 不改业务功能逻辑（仅可观测与诊断能力）
- 不引入新外部日志系统（沿用现有 AppLogService）

## 约束

- 与 runtime 上层契约一致，禁止服务内重复定义日志语义
- 兼容记录查询：查询脚本可读取记录 `currentLogType`，新写入链路不得继续写入该字段
- Release 模式遵循采样策略，错误日志必须全量

## 验收标准

- A1：端侧日志事件包含统一信封必填字段
- A3：工具回合与 LLM 回合可通过 `runId + traceId + requestId` 串联
- A4：端云Python联合定位条件文档化并可执行
- A7：日志文档、诊断模板、测试门禁三处一致
