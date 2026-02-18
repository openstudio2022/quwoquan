## Why

当前趣我圈日志体系无法稳定支撑“开发态问题快速定位 + 商用态低成本可观测”双目标：

- 页面访问链路缺少统一事件标准，难以从用户旅程反推故障点。
- 个人助手链路虽有 run 级落盘，但缺少对 LLM / 搜索引擎 / 云端 API 的请求与响应统一建模。
- 缺少模拟器日志一键导出到项目 `app_log` 目录的能力，影响编程助手协同分析效率。

需要一次日志体系全面升级，建立统一日志目录、统一字段模型、分环境策略和导出能力，形成可持续演进的 observability 基线。

## What Changes

- 新增 `upgrade-observability-log-pipeline` change 工件，定义日志输出升级的目标结构和验收边界。
- 新增开发态日志目录规范：日期最外层、分类子目录固定、文件命名不重复日期。
- 新增“交互日志不分阶段”的约束：LLM / 搜索 / 云端 API 以请求-响应明细记录。
- 新增商用态日志输出策略：成功摘要、失败全量（脱敏）、支持按 session/run 动态提级。
- 新增模拟器日志一键导出到项目目录：`/Users/zhaoyuxi/Projects/quwoquan/quwoquan_app/app_log/`。

## Capabilities

### New Capabilities

- `app-observability-log-pipeline`: 统一日志目录、统一字段模型、开发态/商用态双策略、导出通道。

### Modified Capabilities

- `personal-assistant-commercial-v1`: run 结果观测从“最终输出”扩展为“输入-交互-输出”全链路。
- `chat`: 助手对话链路的 `runId/traceId` 与页面访问日志、交互日志可串联。

## Impact

- OpenSpec 变更工件：`openspec/changes/upgrade-observability-log-pipeline/*`
- 规格增量：
  - `openspec/changes/upgrade-observability-log-pipeline/specs/app-observability-log-pipeline/spec.md`
  - `openspec/changes/upgrade-observability-log-pipeline/specs/personal-assistant-commercial-v1/spec.md`
- 受影响模块：
  - `lib/personal_assistant/*`
  - `lib/app/navigation/*`
  - `lib/app/shell/*`
  - `lib/features/chat/pages/chat_detail_page.dart`
  - `lib/main.dart`
- 导出目录：`/Users/zhaoyuxi/Projects/quwoquan/quwoquan_app/app_log/`
