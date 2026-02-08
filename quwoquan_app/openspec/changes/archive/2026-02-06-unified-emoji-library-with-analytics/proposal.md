# 统一 Emoji 库与埋点上报

## Why

当前 emoji 在创作（发微趣等）、聊天、评论、个人介绍等场景各自维护列表或常量，无统一数据源；无「最近使用」与「使用统计」；无埋点上报，无法分析 emoji 活跃度与用户心情。本变更将建立公共 emoji 库，统一上述场景的数据与 UI 入口，并增加最近使用、每表情使用统计、以及每日增量埋点上报（每天首次登录后上报截止上次上报后的有使用量 emoji 总次数），便于追踪用户行为与 emoji 活跃度。

## What Changes

- **公共 Emoji 库**：提供统一 catalog（每 emoji 唯一编号：分类 + 名字/码点）、最近使用（LRU）、总使用统计；所有插入 emoji 的场景通过单一「记录使用」入口更新最近与统计。
- **统一选择器**：创作（发微趣、美图、视频、文章）、个人介绍、评论、聊天中的 emoji 选择器均基于该库，支持 Tab（最近 | 表情符号 | 动物 | 食物 | 饮料 | 活动 | 旅行与地点 | 物体），面板高度与键盘一致。
- **埋点上报**：维护「待上报增量」（自上次上报以来各 emoji 使用次数）；每天首次登录（或当日首次进入可上报上下文）后上报一次，payload 含 report_date、last_report_date、total_emoji_uses、emoji_count、可选 items(emoji_id, count)；上报成功后清空增量并更新 last_report_date，便于分析 emoji 活跃度与用户心情。

## Capabilities

### New Capabilities

- `emoji-library`: 公共 emoji 库：唯一编号（分类:名字）、catalog 查询、最近使用（LRU）、总使用统计、待上报增量；统一 recordEmojiUsed 入口。
- `emoji-picker-ui`: 统一 emoji 选择器组件，Tab（最近 + 七分类）、与键盘同高、可滚动，供创作/个人介绍/评论/聊天复用。
- `emoji-analytics`: 每日一次增量埋点：首次登录后上报自上次上报以来的有使用量 emoji 总次数及可选明细；持久化 last_report_date 与待上报增量。

### Modified Capabilities

- 创作页发微趣/美图/视频/文章：emoji 入口改为使用公共库与统一选择器，插入后调用 recordEmojiUsed。
- 聊天输入：emoji 面板改为使用公共库与统一选择器，插入后调用 recordEmojiUsed。
- 评论输入、个人介绍输入：接入统一选择器与 recordEmojiUsed（若已有 emoji 入口则替换，否则新增入口）。

## Impact

- 新增 `lib/core/emoji/`（或 `lib/app/emoji/`）：catalog（含 id 与 char 映射）、repository（最近 + 统计 + 增量）、service（record + 上报触发）。
- 新增统一选择器组件，替换或封装现有创作页与聊天页的 emoji 面板。
- 埋点：上报接口与现有埋点体系对接（URL/字段按项目规范）；本地持久化待上报增量与 last_report_date。
