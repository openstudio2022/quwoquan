## ADDED Requirements

### Requirement: 对外统一调用网关
系统必须提供统一 HTTP 网关，至少包含 `/v1/run`、`/v1/skills`、`/v1/skills/invoke` 三个接口，供外部渠道调用 personal_assistant 能力。

#### Scenario: 外部渠道调用 run
- **WHEN** OpenClaw 或飞书渠道调用 `/v1/run` 并提交消息请求
- **THEN** 系统返回标准运行结果（最终文本 + trace）

#### Scenario: 外部渠道调用技能
- **WHEN** 外部系统调用 `/v1/skills/invoke` 指定技能与参数
- **THEN** 系统执行技能并返回标准化结果

### Requirement: 鉴权与边界隔离
系统必须对外部接口启用鉴权，并确保外部调用仅能访问网关暴露能力，不得直接访问内部 UI 状态或私有会话对象。

#### Scenario: 未授权请求
- **WHEN** 外部请求缺失或携带错误鉴权令牌
- **THEN** 网关拒绝请求并返回授权失败响应
