# 统一 Emoji 库与埋点上报 - 任务列表

## 1. 公共 Emoji 库（数据与编号）

- [x] 1.1 定义 emoji 唯一编号方案：categoryId（smiley/animal/food/drink/activity/travel/object）+ emojiIdentifier（CLDR slug 或 u+码点）；在现有 EmojiCategoryConstants 基础上扩展，为每个 char 分配 id，维护 char↔id 映射
- [x] 1.2 实现 catalog 接口：按分类返回 (id, char) 列表；getCharById(id)、getIdByChar(char)
- [x] 1.3 实现最近使用：持久化有序列表（最大 24），LRU 更新；getRecent()、在 recordEmojiUsed 中更新
- [x] 1.4 实现总使用统计：持久化 emoji_id → total_count；recordEmojiUsed 时 +1；提供按 count 降序查询（可选）
- [x] 1.5 实现待上报增量：持久化 emoji_id → incremental_count；recordEmojiUsed 时 +1；提供 getIncrementalForReport()、clearIncremental()；持久化 last_report_date

## 2. 统一记录入口与 Repository/Service

- [x] 2.1 实现 recordEmojiUsed(String idOrChar)：解析为 id，更新最近使用、总统计、待上报增量；对外单一入口
- [x] 2.2 将上述存储与逻辑封装为 EmojiRepository 或 EmojiService，供 UI 与上报使用

## 3. 埋点上报

- [x] 3.1 定义上报 payload：report_date、last_report_date、total_emoji_uses、emoji_count、items；与现有埋点公共字段对接
- [x] 3.2 实现「每日首次登录/可上报」触发逻辑：读取 last_report_date，若 < 今日则组装 payload、调用上报接口；成功后更新 last_report_date、clearIncremental()；失败保留数据
- [x] 3.3 在 app 启动或登录成功（按产品定义）处调用上述触发逻辑，确保每天最多上报一次

## 4. 统一 Emoji 选择器 UI

- [x] 4.1 实现 UnifiedEmojiPicker 组件：第一 Tab「最近」（从库 getRecent），其余七 Tab 为七分类（从 catalog）；面板高度 emojiPanelHeight；点击 emoji 时 onEmojiSelected(char) + recordEmojiUsed(char)
- [x] 4.2 创作页（发微趣）emoji 面板替换为该组件，插入到 _momentContentController 并调用 recordEmojiUsed
- [x] 4.3 聊天页 emoji 面板替换为该组件，插入到输入框并调用 recordEmojiUsed
- [x] 4.4 （可选）评论、个人介绍若有 emoji 入口则接入同一组件与 recordEmojiUsed

## 5. 设计系统与规范

- [x] 5.1 新代码使用 AppColors、AppSpacing、UITextConstants；无硬编码
- [x] 5.2 导入使用包引用 package:quwoquan_app/...，禁止相对路径
