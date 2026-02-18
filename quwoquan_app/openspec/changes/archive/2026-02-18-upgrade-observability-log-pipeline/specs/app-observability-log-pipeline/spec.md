## ADDED Requirements

### Requirement: 统一日志目录与文件命名

系统 MUST 按“日期最外层、类型子目录固定、文件名不重复日期”输出日志，目录结构 SHALL 为：

- `quwoquan_logs/<yyyy-MM-dd>/page_access/events.jsonl`
- `quwoquan_logs/<yyyy-MM-dd>/agent/run_<runId>.json`
- `quwoquan_logs/<yyyy-MM-dd>/integrations/llm.jsonl`
- `quwoquan_logs/<yyyy-MM-dd>/integrations/search.jsonl`
- `quwoquan_logs/<yyyy-MM-dd>/integrations/cloud_api.jsonl`
- `quwoquan_logs/<yyyy-MM-dd>/perf/stats.jsonl`
- `quwoquan_logs/<yyyy-MM-dd>/errors/errors.jsonl`

#### Scenario: 日期目录唯一层级

- **WHEN** 应用在任意一天输出日志
- **THEN** 日期仅出现在最外层目录，内部文件名不重复日期字符串

### Requirement: 统一日志 envelope 与链路关联

每条日志 MUST 包含统一 envelope 字段：  
`ts/env/logType/level/sessionId/journeyId/pageVisitId/runId/traceId/spanId/requestId/payload`，  
并支持从页面访问日志关联到 agent run 与交互日志。

#### Scenario: runId 串联全链路

- **WHEN** 用户发起一次助手问答
- **THEN** 可通过 `runId` 与 `traceId` 串联页面访问、run 聚合、integrations 明细与最终输出

### Requirement: 交互日志请求与响应明细（无阶段抽象）

系统 MUST 对 `llm/search/cloud_api` 三类交互分别记录请求与响应明细，且不以“阶段聚合”替代：

- `kind=llm`: request(url/headers/body) + response(status/body/usage/error)
- `kind=search`: request(provider/url/params/body) + response(status/body/error)
- `kind=cloud_api`: request(service/apiName/url/body) + response(status/body/error)

#### Scenario: 搜索与模型可定位

- **WHEN** 用户天气问答出现异常结果
- **THEN** 可直接在日志中看到对应搜索请求/响应与模型请求/响应细节

### Requirement: 开发态与商用态策略分层

系统 SHALL 支持两套日志策略：

- 开发态：全量详细落盘
- 商用态：成功摘要、失败全量（脱敏），并支持按 `sessionId/runId` 动态提级为详细

#### Scenario: 线上故障快速提级

- **WHEN** 某会话在商用态出现故障
- **THEN** 运维可按会话提级该会话日志明细，而不影响全局采样策略

### Requirement: 模拟器日志一键导出到项目 app_log

系统 MUST 提供一键导出能力，将模拟器中的日志导出到：
`/Users/zhaoyuxi/Projects/quwoquan/quwoquan_app/app_log/`

#### Scenario: 编程助手直接分析

- **WHEN** 开发者执行日志导出操作
- **THEN** `app_log` 目录可直接读取并用于自动化分析，不需手动定位容器路径
