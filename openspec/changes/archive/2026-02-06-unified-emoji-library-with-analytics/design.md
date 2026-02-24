# 统一 Emoji 库与埋点上报 - 设计

## 1. 唯一编号

- 格式：`categoryId:emojiIdentifier`。分类 ID 与现有七类一致：smiley, animal, food, drink, activity, travel, object。
- emojiIdentifier：优先 Unicode CLDR short name 的 slug（小写、空格改下划线）；无则用 `u`+ 码点十六进制。
- 示例：`smiley:grinning_face`、`animal:dog`、`smiley:red_heart`。
- 库内维护「字符 ↔ 唯一 id」映射，保证同一字符全局同一 id。

## 2. 数据模型

- **Catalog**：只读；每项 id、char、categoryId、shortName（可选）；由库常量或配置提供，与现有 EmojiCategoryConstants 对齐并扩展 id。
- **最近使用**：有序列表，每项 emoji id（或 id+char）；最大长度 N（如 24）；LRU 更新；持久化。
- **总使用统计**：emoji_id → total_count；每次使用 +1；持久化。
- **待上报增量**：emoji_id → incremental_count；每次使用 +1；上报成功后清空；持久化。
- **last_report_date**：上次成功上报的日期（自然日）；单独持久化。

## 3. 统一入口与写入时机

- 唯一写入入口：`recordEmojiUsed(id 或 char)`。内部：解析为 id；更新最近使用（LRU）；总统计 +1；待上报增量 +1。
- 所有场景（创作、聊天、评论、个人介绍）在用户插入 emoji 后只调用此入口一次。

## 4. 埋点上报

- **触发**：每天首次登录（或当日首次进入可上报上下文）后，若 last_report_date < 今日且有待上报增量（或策略上允许 0 上报），则执行一次上报。
- **防重**：若 last_report_date == 今日则不再上报。
- **Payload**：report_date、last_report_date、total_emoji_uses（增量总次数）、emoji_count（有使用量的 emoji 种类数）、items: [{ emoji_id, count }]；与现有埋点公共字段（user_id、device_id 等）一并上报。
- **成功后**：更新 last_report_date = 今日；清空待上报增量。
- **失败**：保留增量与 last_report_date，下次再试（可加重试与退避）。

## 5. UI 与集成

- 统一选择器：第一 Tab「最近」（来自库的最近使用），其余七 Tab 为七分类；面板高度使用 SettingsSemanticConstants.emojiPanelHeight；点击 emoji 回调 onEmojiSelected(char)，内部或调用方调用 recordEmojiUsed(char)。
- 创作页、聊天页、评论、个人介绍：均使用该选择器并统一调用 recordEmojiUsed。

## 6. 存储

- 最近使用、总统计、待上报增量、last_report_date 均本地持久化（SharedPreferences 或本地 DB）；上报接口与项目埋点体系一致。

## 7. 风险与取舍

- 编号与 CLDR 的对应需在建库时一次性做好，后续新增 emoji 需扩展 catalog 与映射。
- 「首次登录」定义需与产品统一（如：当日首次冷启动且已登录，或首次调用登录成功）；先按「当日首次 app 启动/可上报上下文」实现亦可。
