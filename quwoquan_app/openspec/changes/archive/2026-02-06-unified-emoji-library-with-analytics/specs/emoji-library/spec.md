# emoji-library

## ADDED Requirements

### Requirement: 公共 Emoji 库提供唯一编号与 Catalog

系统 SHALL 为每个 emoji 分配全局唯一编号，格式为 `categoryId:emojiIdentifier`（如 smiley:grinning_face）。Catalog 须提供按分类查询、按 id 查 char、按 char 反查 id；与现有七分类（表情符号、动物、食物、饮料、活动、旅行与地点、物体）一致。

#### Scenario: 按分类获取 emoji 列表

- **WHEN** 调用方请求某分类的 emoji 列表
- **THEN** 返回该分类下所有 emoji 的 id 与 char，顺序稳定

#### Scenario: 按 id 或 char 解析为唯一 id

- **WHEN** 调用方传入 emoji 字符或 id
- **THEN** 库返回对应的唯一 id，同一字符始终返回同一 id

### Requirement: 最近使用（LRU）

系统 SHALL 维护最近使用的 emoji 有序列表，最大长度 N（如 24）。每次 recordEmojiUsed 时将该 emoji 置于最近列表首位（若已存在则先移除再插入）；列表持久化并在进程重启后恢复。

#### Scenario: 读取最近使用

- **WHEN** 调用方请求最近使用列表
- **THEN** 返回按使用时间倒序的 emoji 列表（id 或 id+char），不超过 N 项

#### Scenario: 记录使用后更新最近

- **WHEN** 调用 recordEmojiUsed(emoji)
- **THEN** 该 emoji 出现在最近列表首位，且列表持久化

### Requirement: 总使用统计

系统 SHALL 维护每个 emoji 的总使用次数。每次 recordEmojiUsed 时对应 emoji_id 的 total_count 加 1；数据持久化。调用方 SHALL 能按 count 降序获取列表（用于「常用」等）。

#### Scenario: 记录使用后统计增加

- **WHEN** 调用 recordEmojiUsed(emoji)
- **THEN** 该 emoji 对应 total_count 增加 1 并持久化

### Requirement: 统一记录入口

创作（发微趣、美图、视频、文章）、个人介绍、评论、聊天中，用户插入 emoji 后 MUST 仅调用一次 recordEmojiUsed(id 或 char)。该入口 SHALL 同时更新最近使用、总统计、待上报增量。

#### Scenario: 单次插入单次记录

- **WHEN** 用户在任意场景选择并插入一个 emoji
- **THEN** 该场景调用 recordEmojiUsed 恰好一次，且最近、总统计、待上报增量均更新
