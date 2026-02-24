# app-observability-log-pipeline

## Purpose

应用可观测性日志管线：统一日志目录与 envelope、页面访问/agent/integrations 埋点、开发态全量与商用态策略分层、一键导出到项目 app_log。

---

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
当 run 使用模板运行时，日志 MUST 额外记录 `templateId/templateVersion` 与 `structuredResponse` 关键阶段摘要。

#### Scenario: runId 串联全链路

- **WHEN** 用户发起一次助手问答
- **THEN** 可通过 `runId` 与 `traceId` 串联页面访问、run 聚合、integrations 明细与最终输出

#### Scenario: 模板版本可回放

- **WHEN** 回放一次 run
- **THEN** 可见总1/分/总2阶段使用的模板ID与版本，以及结构化门禁状态

#### Scenario: 学习闭环可回放

- **WHEN** 回放同一用户的多次同类 run
- **THEN** 可见画像标签变化、满意度信号变化、策略切换原因与切换后的效果

### Requirement: 交互日志请求与响应明细（无阶段抽象）

系统 MUST 对 `llm/search/cloud_api` 三类交互分别记录请求与响应明细，且不以“阶段聚合”替代：

- `kind=llm`: request(url/headers/body) + response(status/body/usage/error)
- `kind=search`: request(provider/url/params/body) + response(status/body/error)
- `kind=cloud_api`: request(service/apiName/url/body) + response(status/body/error)

系统 MUST 记录双门禁阶段结果：`contextAssembly/domainPrecheck/domainExecution/synthesisReadiness`。  
系统 MUST 记录学习相关字段：`userProfileSnapshot/profileTagDelta/retrievalFeedback/learningSignals/strategySelectionReason`。  
系统 MUST 记录 UserProfile 消费与回流字段：`profileVersion/profileReadAt/profileUpdateProposalId/profileUpdateConfirmedByUser`。

#### Scenario: 搜索与模型可定位

- **WHEN** 用户天气问答出现异常结果
- **THEN** 可直接在日志中看到对应搜索请求/响应与模型请求/响应细节

#### Scenario: 门禁回流可定位

- **WHEN** run 触发 `ContextFillTask` 或 `GapFillTask`
- **THEN** 日志可定位触发原因、补齐策略、回流轮次与最终结果

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

### Requirement: 路由与检索策略可观测输出

系统 MUST 输出 19 垂类路由与检索策略的结构化日志，支持回放"为何路由/为何补查/为何兜底"。

#### Scenario: 垂类路由可回放

- **WHEN** planner 完成路由决策
- **THEN** 日志至少包含 `candidateDomains`、`domainScores`、`selectedDomains`、`fallbackTriggered`、`fallbackReason`

#### Scenario: 检索回合可回放

- **WHEN** domain 执行检索与补查
- **THEN** 日志至少包含 `retrievalRound`、`queryId`、`topicId`、`singleTopic`、`providerHint`、`scopeExpansionPolicy`、`usedHistoricalStrategy`

### Requirement: 提案生命周期可观测输出

系统 MUST 输出 `profileUpdateProposal` 全生命周期日志，支持从生成到用户确认/拒绝/应用的链路追踪。

#### Scenario: 提案状态可追踪

- **WHEN** 产生或处理 `profileUpdateProposal`
- **THEN** 日志至少包含 `proposalId`、`proposalStatus(created|approved|rejected|applied)`、`statusChangedAt`、`changedBy`、`idempotencyKey`

### Requirement: 隐私与脱敏日志边界

系统 MUST 对敏感字段执行脱敏与最小化输出，禁止在日志中记录可逆的精确隐私值。

#### Scenario: 敏感字段脱敏

- **WHEN** 日志包含 `birthDateSolar/birthDateLunar/ipResidenceProfile`
- **THEN** 必须输出脱敏值（如年龄段、城市级区域、哈希化标识），并记录数据保留策略与删除标记

### Requirement: 模板边界与章节校验可观测

系统 MUST 输出模板结构校验日志，确保"指令/数据分离"与模板章节完整性可审计。

#### Scenario: 模板边界可回放

- **WHEN** 运行任一模板
- **THEN** 日志至少包含 `templateBoundaryCheck(instructionBeforeData,dataSectionPresent)` 与 `chapterChecklist` 结果

### Requirement: 槽位填充链路可观测

系统 MUST 输出上下文槽位状态与填充动作日志，支持回放"哪些槽位缺失、何时补齐、是否阻断终答"。

#### Scenario: 槽位状态可追踪

- **WHEN** planner/domain/synthesizer 执行
- **THEN** 日志至少包含 `contextSlots(status/source)`、`needQuerySlotCount`、`fillActions`

### Requirement: WebSearch 子流水线可观测

系统 MUST 对 `web_query_plan -> web_result_judge -> web_key_fact_extract -> web_evidence_pack` 全链路输出结构化日志。

#### Scenario: Web 子链路可回放

- **WHEN** 垂类触发 web 检索
- **THEN** 日志至少包含 `webQueryPlan`、`webResultJudgeSummary`、`webKeyFactSummary`、`webEvidencePackSummary`

#### Scenario: 证据包驱动答案可追踪

- **WHEN** 进入垂类 answer 模板
- **THEN** 日志必须记录 `answerInputFromWeb` 与证据覆盖阈值判断结果

### Requirement: 结构化自检与诊断可观测

系统 MUST 输出模型自检与诊断结果，支持排查"为什么给出该答案、是否满足约束"。

#### Scenario: 自检结果可回放

- **WHEN** 输出答案
- **THEN** 日志至少包含 `selfCheck`、`failedChecks`、`needMoreInfo`、`diagnostics.riskFlags/assumptions`
