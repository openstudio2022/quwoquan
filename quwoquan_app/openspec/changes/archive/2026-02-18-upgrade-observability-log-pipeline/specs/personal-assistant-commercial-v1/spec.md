## MODIFIED Requirements

### Requirement: 商业网关能力完整性

在执行 `POST /v1/assistent/runs` 与 `POST /v1/assistent/runs/stream` 时，系统响应观测字段 MUST 除 `runId/traceId/degraded/errorCode` 外，支持关联日志查询信息（如 `sessionId` 与可选 `logExportRef`）。

#### Scenario: run 响应可回溯日志

- **WHEN** 运行一次私人助理问答
- **THEN** 结果可定位到对应 run 聚合日志与 integrations 明细日志

### Requirement: ReAct++ 推理规划主循环

推理主循环在工具交互时 SHALL 输出可查询交互明细，并与页面访问链路关联：

- 输入快照
- 每次交互（llm/search/cloud_api）请求与响应
- 最终输出结果

#### Scenario: 问天气全链路可追踪

- **WHEN** 用户提问“深圳天气怎样”
- **THEN** 可查询从页面访问、模型调用、搜索调用到最终答案的完整链路
