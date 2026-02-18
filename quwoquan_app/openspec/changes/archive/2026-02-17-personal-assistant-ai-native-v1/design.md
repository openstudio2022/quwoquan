## Context

当前 `quwoquan_app` 已具备个人私人助手 UI 入口与部分引擎雏形，但需要把已实现能力系统化为 AI 原生初始版本，并形成可持续扩展的能力边界。核心约束如下：

- 引擎必须内聚在 `quwoquan_app/lib/personal_assistant/`，作为 App 内第一等公民能力。
- Skill 体系必须声明式、无 shell 依赖，支持 iOS/Android intent 与 Flutter 原生 API 桥接。
- 对外渠道（OpenClaw/飞书）必须通过统一网关访问，不可直接耦合 App UI。
- 模型配置必须独立，不以 moltbot 作为运行时依赖；兼容导入仅作为迁移辅助。
- 多设备（手机/平板/PC）下能力差异明显，需要显式能力路由策略。

## Goals / Non-Goals

**Goals:**
- 固化 AgentLoop + ReAct 核心运行时为稳定能力层。
- 形成 Tool/Skill/Model/Gateway 四条可扩展主线。
- 完成 App 内会话与外部渠道两种调用路径统一。
- 明确手机、平板、PC 的能力约束与路由策略。
- 输出可直接进入实现的任务拆解，覆盖“继续扩充 5 块”。

**Non-Goals:**
- 本次不做完整企业级权限中心与多租户网关。
- 本次不引入复杂分布式任务编排系统。
- 本次不要求一次性完成全部本地模型推理后端自研（允许先接 OpenAI 兼容端点 + 本地回退）。

## Decisions

### Decision 1: 采用分层内核并保持最小 UI 入侵
- **选择**：`app gateway -> runtime -> engine/tools/skills/memory -> bridges/connectors` 分层，UI 通过 provider/gateway 调用。
- **原因**：保证现有页面最小改动，同时让核心可独立测试与复用。
- **备选**：直接在页面中内嵌 tool/skill 调度。**放弃原因**：页面耦合高，无法外部复用。

### Decision 2: Skill 采用声明式 manifest + executionTarget 路由
- **选择**：YAML/JSON manifest 描述参数、执行目标和能力元信息；运行时解析执行。
- **原因**：满足“无 shell、可市场化扩展、跨平台映射”。
- **备选**：每个技能写成 Dart 类。**放弃原因**：扩展成本高，无法低门槛上架技能。

### Decision 3: 模型配置独立命名空间
- **选择**：新增 `personal_assistant` 独立配置加载器（目录 + 环境变量），默认不读取 moltbot；仅提供可选兼容导入。
- **原因**：满足“独立生产、去外部耦合”要求，降低部署门槛。
- **备选**：继续默认读取 moltbot 配置。**放弃原因**：运行时耦合外部工程，部署不可控。

### Decision 4: 多设备能力路由前置为显式策略
- **选择**：引入 device profile（mobile/tablet/pc）+ capability matrix（local-only/remote-preferred/hybrid）。
- **原因**：手机端权限与算力受限，PC/Mac mini 可承载重任务，需统一策略避免隐式失败。
- **备选**：全部本地执行。**放弃原因**：重任务稳定性与耗电不可接受。

### Decision 5: 外部集成统一走 HTTP Gateway
- **选择**：对外仅暴露 `/v1/run`、`/v1/skills`、`/v1/skills/invoke` + token 鉴权。
- **原因**：简化接入，保护内部状态边界，满足飞书/OpenClaw 扩展。
- **备选**：直接开放内部 provider 或 websocket 内部对象。**放弃原因**：安全与演进风险高。

## Risks / Trade-offs

- [风险] Skill manifest 缺少静态校验会导致运行时错误 -> [缓解] 增加 schema 校验与启动期预检查。
- [风险] 多模型切换可能引入行为不一致 -> [缓解] 统一 tool call 协议与回归测试集。
- [风险] 手机端系统能力受权限限制 -> [缓解] 路由层返回可解释的降级结果并可转发远程。
- [风险] 外部网关被误用或滥用 -> [缓解] token、限流、审计日志与最小暴露面。
- [风险] 过早引入复杂内存向量方案导致成本上升 -> [缓解] 先稳定接口，再渐进替换存储实现。

## Migration Plan

1. 固化 `personal_assistant` 核心接口（run、invokeSkill、model switch、trace schema）。
2. 将聊天页助手会话切换到 gateway 调用，保留非助手会话原路径。
3. 在助手页接入技能市场数据源与启停逻辑。
4. 启用独立配置目录（如 `personal_assistant/config/`）与独立环境变量前缀。
5. 启用对外网关并配置鉴权，先灰度到 OpenClaw，再扩展飞书。
6. 增加两条端到端验收：外部语音链路触发技能、App 内文本会话触发 AgentLoop。
7. 保留回滚开关：可通过 feature flag 退回旧 mock 路径。

## Open Questions

- 独立配置文件采用 JSON 还是 YAML 作为主格式（当前两者均可支持）？
- 网关部署形态是否与 App 同进程，还是独立 sidecar（桌面端优先）？
- 技能市场首期是否需要远程签名校验与版本策略？
- 远程节点（Mac mini/OpenClaw）健康检测与故障转移策略细则如何定义？
