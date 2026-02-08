# emoji-picker-ui

## ADDED Requirements

### Requirement: 统一 Emoji 选择器组件

系统 SHALL 提供统一 emoji 选择器组件，供创作（发微趣、美图、视频、文章）、个人介绍、评论、聊天复用。选择器 SHALL 从公共 emoji 库读取：最近使用、七分类 catalog；SHALL 支持 Tab 切换（最近 | 表情符号 | 动物 | 食物 | 饮料 | 活动 | 旅行与地点 | 物体）；面板高度 SHALL 使用 SettingsSemanticConstants.emojiPanelHeight（与键盘同高）；内容可滚动。

#### Scenario: Tab 与内容

- **WHEN** 用户打开 emoji 选择器
- **THEN** 可见「最近」与七分类 Tab；当前 Tab 下展示对应 emoji 网格，可上下滚动

#### Scenario: 选择后插入并记录

- **WHEN** 用户点击某 emoji
- **THEN** 回调 onEmojiSelected(char) 供调用方插入文本；且 recordEmojiUsed 被调用一次

### Requirement: 创作与聊天接入统一选择器

创作页（发微趣及美图/视频/文章的文字编辑）、聊天页输入框的 emoji 入口 SHALL 使用上述统一选择器；插入逻辑与 recordEmojiUsed 调用 SHALL 与 emoji-library spec 一致。

#### Scenario: 发微趣 emoji

- **WHEN** 用户在发微趣编辑态点击 emoji 入口
- **THEN** 展示统一选择器；选择后 emoji 插入到正文光标处，并调用 recordEmojiUsed

#### Scenario: 聊天 emoji

- **WHEN** 用户在聊天输入框点击 emoji 入口
- **THEN** 展示统一选择器；选择后 emoji 插入到输入框，并调用 recordEmojiUsed
