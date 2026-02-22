## Why

当前私人助理仍存在三类限制：提示词与上下文策略部分固化在代码中、垂类能力覆盖不足、以及历史规格分叉导致能力边界不统一。为了提升用户增长与留存，需要将助手升级为“2 个总控模板 + 19 个垂类模板（18 主垂类 + 1 大搜兜底垂类）”的可灰度、可替换、可回放架构，并统一到单一 `personal-assistant` 规格。

## What Changes

- 将私人助理执行链路升级为模板驱动：总规划模板（总1）+ 汇总结论模板（总2）+ 19 个垂类模板（18 主垂类 + 1 大搜兜底垂类）。
- 引入模板注册与灰度选择能力，禁止将核心上下文策略与提示词写死在业务代码中。
- 扩展 run 结构化响应：暴露 `contextAssembly/domainPrecheck/domainResults/synthesisReadiness/fillTasks`，便于前端直接渲染补齐任务。
- 完成 19 垂类输入输出契约与门禁定义，覆盖通用问答、旅行规划、情感陪伴、闲聊陪伴、婚配、卜卦、星座等增长场景。
- 清理历史规格分叉：将 `personal-assistant-commercial-v1` 与 `personal-assistant-domain-orchestration-v1` 合并归档，统一由 `personal-assistant` 维护。
- **BREAKING**：run 响应协议新增结构化字段；下游依赖如严格校验旧响应结构，需要同步兼容。

## Capabilities

### New Capabilities
- `assistant-template-runtime`: 模板注册、变量绑定、版本灰度与回滚能力。
- `assistant-domain-catalog-17`: 19 垂类统一目录（18 主 + 1 兜底）、前后置条件、输入输出契约与差异化模板规范。

### Modified Capabilities
- `personal-assistant`: 从“部分规则硬编码 + 有限垂类”升级为“2 总 + 19 垂类模板驱动 + 双门禁回流补齐”。
- `app-observability-log-pipeline`: 新增模板版本与结构化 run 响应字段在日志中的可回放要求。

## Impact

- Affected code:
  - `lib/personal_assistant/engine/*`
  - `lib/personal_assistant/protocol/*`
  - `lib/personal_assistant/skills/*`
  - `lib/personal_assistant/observability/*`
  - `assets/personal_assistant/prompts/**`
- Affected specs:
  - `openspec/specs/personal-assistant/spec.md`（主规格升级）
  - 历史规格归档与迁移说明更新
- APIs:
  - `/v1/assistent/runs` 与 `/v1/assistent/runs/stream` 响应结构扩展
- Risk:
  - 模板版本切换导致回答风格波动，需要灰度与回滚门禁
