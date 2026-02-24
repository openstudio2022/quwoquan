## Context

日志升级需同时满足两类核心场景：

1. 开发态：快速排障，要求明细可复现、可按 `runId` 追踪到请求与响应。
2. 商用态：稳定低成本，要求合规脱敏、按策略采样、可动态提级详细日志。

当前个人助手已具备 run 级日志写入能力，可作为迁移入口，但需扩展为跨页面访问、跨集成交互、跨性能统计的统一数据面。

## Goals / Non-Goals

### Goals

- 统一日志目录：日期最外层、类型子目录固定、文件名不重复日期。
- 统一日志 envelope：支持 `sessionId/journeyId/pageVisitId/runId/traceId/spanId/requestId` 串联。
- 助手交互日志以“请求-响应”为原子单位，不使用“阶段”聚合表达。
- 支持 LLM / 搜索引擎 / 云端 API 独立日志输出与 run 级聚合。
- 支持模拟器日志一键导出到项目 `app_log` 目录供编程助手分析。

### Non-Goals

- 不在本变更中实现外部日志平台（ELK/Loki）部署。
- 不在本变更中引入新的对外 API 版本路径。

## Architecture

### 1) Storage Topology

- 根目录：`quwoquan_logs/<yyyy-MM-dd>/`
- 子目录：
  - `page_access/events.jsonl`
  - `agent/run_<runId>.json`
  - `integrations/llm.jsonl`
  - `integrations/search.jsonl`
  - `integrations/cloud_api.jsonl`
  - `perf/stats.jsonl`
  - `errors/errors.jsonl`

### 2) Data Model

- 统一 envelope：
  - `ts/env/logType/level/sessionId/journeyId/pageVisitId/runId/traceId/spanId/requestId/payload`
- 交互 payload 统一 request/response：
  - `kind=llm`
  - `kind=search`
  - `kind=cloud_api`

### 3) Runtime Integration

- 页面访问日志：从路由切换与主壳 tab 切换生成 open/browse/return。
- agent 日志：由 run 结果汇聚 input + interactions + output。
- integrations 日志：在 LLM provider 与搜索工具内部写请求/响应。
- perf 日志：页面开关、关键操作点采样内存/CPU并落盘。

### 4) Export Pipeline

- 开发态提供导出接口：
  - 从模拟器容器日志目录拷贝/压缩到 `/Users/zhaoyuxi/Projects/quwoquan/quwoquan_app/app_log/`
  - 产物命名包含时间窗口与可选 runId 过滤。

## Key Design Constraints

- 商用态默认“成功摘要，失败全量（脱敏）”，并允许按 `sessionId/runId` 动态提级。
- 任何日志写入失败不得阻塞主链路（fail-open）。
- 交互日志中 `Authorization/API Key/Token` 必须脱敏。
- 日志目录与文件名遵循“日期最外层、内部不重复日期”的规则。

## Acceptance Mapping

- 目录结构验收：在模拟器运行后可见 `quwoquan_logs/<date>/...` 完整子目录。
- 追踪链路验收：一次天气问答可从页面访问日志串联到 run 与 integrations 日志。
- 导出验收：一键导出后在项目 `app_log/` 目录可直接读取 JSON/JSONL。
- 稳定性验收：日志写入异常时，助手对话与页面交互不受阻断。
