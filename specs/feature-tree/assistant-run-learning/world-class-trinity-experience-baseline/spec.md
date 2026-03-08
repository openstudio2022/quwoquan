# L2 特性：world-class-trinity-experience-baseline

## 功能目标（重定义）

本特性升级为“小趣助手世界水准执行内核基线”，不再只修 UI 断点，目标是建立可持续扩展的 Agent 运行协议：

1. **模型可规划**：每轮输出结构化决策（answer/tool/ask/subagent），不依赖字符串分支。
2. **执行可观测**：run/stream 统一 trace，支持前端稳定渲染与可回放审计。
3. **回答可精排**：用户面向输出统一为 Markdown（支持结构块），且可稳定降级显示。
4. **能力可扩展**：默认系统提示词 + 垂类 skill policy + tools/私有数据 connector 可插拔。
5. **容错可恢复**：remote/local 双引擎、工具失败恢复、补槽追问、权限边界统一治理。

## 范围（本期必须覆盖）

- **端侧运行时**：`AgentLoop`、`ReactRuntime`、`LlmProvider`、`CapabilityGateway`、`OpenClawBridge`。
- **协议层**：`assistant_run` metadata（fields/errors）与 run/stream 响应契约。
- **渲染层**：`ChatDetailPage` 对 markdown + trace + action hints 的稳定呈现。
- **垂类试点**：天气垂类先完成 `md+json` 双通道闭环，作为其它垂类模板。

## 范围（本期不做）

- 新建服务进程与全新领域（仍遵循 `/prd` → `/design` → `/dev` 标准链路）。
- 第三方技能市场化运营（仅保留协议扩展点）。
- Web/Desktop 全端同构渲染（移动端先收敛）。

## 核心契约要求

### 1) 回合输出契约
- 运行时必须支持 `assistant_turn_v2`（或等价版本）：
  - machine channel: JSON 决策（nextAction/toolPlan/slotState/askUser）
  - user channel: Markdown 展示（summary/evidence/action/follow-up）

### 2) 工具观测契约
- 工具返回必须可结构化解析（ok/errorCode/errorClass/retryable/slotDelta）。
- 禁止使用用户文案字符串作为业务判断条件。

### 3) i18n 契约
- 补槽追问与错误提示使用 `l10n_key + args`。
- 业务逻辑层禁止硬编码中文提示判断。

### 4) 子代理契约
- 支持 `subagent_plan_v1/subagent_result_v1` 回注主会话。
- 子代理任务必须具备预算、超时、工具白名单。

## 适用场景

- 天气/出行等实时信息问答（可补槽）
- 多步任务执行与回执（可中断/可重试）
- 内容/社交入口触发的“找小趣”辅助链路

## 关键约束

- 执行顺序强制：`metadata -> verify -> codegen -> logic -> tests`。
- `DO NOT EDIT` 生成文件禁止手改。
- 任何结构块解析失败必须安全降级为普通 markdown，不能中断对话。
- 隐私能力调用（设备/相册/intent）必须通过策略网关与权限语义文案。

## 与父/子节点关系

- 父节点：`assistant-run-learning`
- 强关联：
  - `run-stream-policy`
  - `run-sync-contract/assistant-run-io-contract`
  - `runtime-client-foundation/error-permission-display-semantics`

## 交付结果定义

当以下条件全部满足，视为本特性完成：

1. 天气垂类完成结构化决策闭环（城市已知/未知/定位失败/工具失败四路径）。
2. run/stream 对外输出可被 UI 稳定解析（trace + markdown + actions）。
3. 字符串判断分支从关键执行路径移除（至少天气链路）。
4. 新增/变更契约具备 mock + contract + integration 测试覆盖。
