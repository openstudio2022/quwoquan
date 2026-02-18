## ADDED Requirements

### Requirement: 统一工具注册与调用
系统必须提供统一 Tool Registry，用于注册、发现和执行工具；工具执行错误必须被捕获并以标准错误结果返回。

#### Scenario: 成功调用工具
- **WHEN** AgentLoop 选择调用已注册工具
- **THEN** Tool Registry 执行对应工具并返回结构化输出

#### Scenario: 工具调用失败
- **WHEN** 工具执行过程中抛出异常或参数不合法
- **THEN** 系统返回标准错误结构并写入 trace 事件

### Requirement: 首期系统能力工具集
系统必须至少提供 websearch、本地上下文、相册访问与 intent bridge 工具，并可由 AgentLoop 与 Skill 复用。

#### Scenario: websearch 工具被知识问答调用
- **WHEN** 用户发起知识/百科类问题
- **THEN** 系统可调用 websearch 工具并将检索结果纳入回复
