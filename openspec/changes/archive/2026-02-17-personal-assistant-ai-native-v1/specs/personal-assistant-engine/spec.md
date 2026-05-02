## ADDED Requirements

### Requirement: 个人私人助手核心 AgentLoop
系统必须在 `quwoquan_app` 内提供 `personal_assistant` 核心引擎，采用 ReAct 循环（Reason -> Act -> Observe -> Respond），并对每次运行输出可追踪事件流。

#### Scenario: 应用内文本对话触发 AgentLoop
- **WHEN** 用户在 App 的私人助手会话中发送文本消息
- **THEN** 系统启动一次 AgentLoop 运行并返回最终回复文本与完整 trace 事件集合

#### Scenario: AgentLoop 产生结构化 trace
- **WHEN** AgentLoop 发生推理、工具调用、技能调用、错误或结束
- **THEN** 系统输出结构化 trace 事件，至少包含 type、message、timestamp 和可选 data 字段

### Requirement: 会话上下文管理
系统必须维护会话级记录消息，并在下一轮推理中可被模型读取，用于多轮上下文连续性。

#### Scenario: 多轮会话保持上下文
- **WHEN** 同一会话中用户连续发起多轮提问
- **THEN** 系统在后续回合可读取前序会话消息并保持语义连续
