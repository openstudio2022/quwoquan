## ADDED Requirements

### Requirement: 多模型提供器抽象
系统必须提供统一模型接口，支持本地模型与远程 OpenAI 兼容模型，并可在运行时切换当前模型。

#### Scenario: 切换当前模型
- **WHEN** 上层调用模型切换接口并指定目标模型
- **THEN** 系统切换后续推理使用的 provider，并返回当前模型标识

### Requirement: 独立配置与默认回退
系统必须提供 `personal_assistant` 独立配置来源，不依赖 moltbot 作为运行时前置；在外部配置缺失时必须回退到本地默认策略。

#### Scenario: 未配置远程模型
- **WHEN** 远程 API key 或 base URL 缺失
- **THEN** 系统使用本地默认模型策略继续运行而不阻断会话

#### Scenario: 使用 personal_assistant 独立配置
- **WHEN** 系统加载模型配置
- **THEN** 优先读取 `personal_assistant` 自身配置目录与环境变量命名空间，不要求存在 moltbot 配置文件
