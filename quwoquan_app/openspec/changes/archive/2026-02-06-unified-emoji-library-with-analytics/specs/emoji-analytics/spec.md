# emoji-analytics

## ADDED Requirements

### Requirement: 待上报增量与每日一次上报

系统 SHALL 维护「待上报增量」：emoji_id → incremental_count。每次 recordEmojiUsed 时对应 incremental_count 加 1。每天 SHALL 最多上报一次；上报内容为自上次上报以来的有使用量 emoji 总次数及可选明细；上报成功后清空待上报增量并更新 last_report_date 为当日。

#### Scenario: 记录使用后增量增加

- **WHEN** 调用 recordEmojiUsed(emoji)
- **THEN** 该 emoji 在待上报增量中的 count 增加 1 并持久化

#### Scenario: 每日首次登录后上报

- **WHEN** 满足「当日首次登录/可上报」且 last_report_date < 今日且有待上报增量（或策略允许 0）
- **THEN** 组装 payload（report_date、last_report_date、total_emoji_uses、emoji_count、items）并调用上报接口；成功后更新 last_report_date、清空待上报增量

#### Scenario: 同一天不重复上报

- **WHEN** last_report_date 已为今日
- **THEN** 不再执行上报，直至次日

### Requirement: 上报 Payload 与埋点对接

上报 payload SHALL 包含：report_date、last_report_date、total_emoji_uses（增量总次数）、emoji_count（有使用量的 emoji 种类数）、items（可选，每项 emoji_id、count）。SHALL 与项目现有埋点体系（如 user_id、device_id、timestamp）对接。

#### Scenario: Payload 结构

- **WHEN** 执行上报
- **THEN** 请求体包含上述字段，且 items 中 emoji_id 为库内唯一编号
