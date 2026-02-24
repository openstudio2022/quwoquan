## ADDED Requirements

### Requirement: 声明式无 Shell Skill 清单
系统必须支持通过 YAML/JSON 声明式定义 Skill，并禁止依赖 shell 脚本作为执行前提。

#### Scenario: 加载声明式技能清单
- **WHEN** 应用启动或刷新技能目录
- **THEN** 系统从技能资源目录加载并解析 Skill manifest，且不要求 shell 环境存在

### Requirement: 执行目标路由映射
系统必须将 Skill 的 `executionTarget` 映射到 `ios_intent`、`android_intent`、`native_api` 或 `tool_chain`，并统一返回结构化结果。

#### Scenario: 运行 iOS 或 Android intent 技能
- **WHEN** 某技能声明目标为 `ios_intent` 或 `android_intent`
- **THEN** 系统通过平台桥接执行并返回标准结果结构

#### Scenario: 运行 tool_chain 技能
- **WHEN** 某技能声明目标为 `tool_chain`
- **THEN** 系统按清单执行工具链并合并工具输出为技能结果
