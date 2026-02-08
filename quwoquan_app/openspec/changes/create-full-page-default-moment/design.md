# 创作全页入口与默认发微趣 - 设计

## Context

- 当前：底部「创作」点击打开 CreateEntrySheet（抽屉），用户选六入口之一后 `context.go('/create?type=...')` 进入 CreatePage。CreatePage 已有四 Tab（微趣、图片、视频、文章）、草稿箱、退出确认、10 秒自动保存、图片选择与 edit-image 路由。
- 原型图一：创作为全页，顶部 X + 标题「发微趣」+ 草稿箱，中部「这一刻的想法...」+ 媒体占位 + 所在位置/提醒谁看/谁可以看，底部四 Tab 微趣/美图/视频/文章；默认即发微趣。
- 约束：沿用现有 CreatePage、CreateEditImagePage、路由与设计系统常量；与 figma-prototype-full-migration 的 create-flow 及 tasks 对齐，实现 1:1 原型创作行为。

## Goals / Non-Goals

**Goals:**

- 创作入口点击直接进入全页创作（/create），默认发微趣 Tab，无前置抽屉。
- 创作页 UI 与图一一致：全页、AppBar（关闭/标题/草稿箱）、底部四 Tab（微趣、美图、视频、文章），标题随 Tab 切换（发微趣/发美图/发视频/写文章）。
- 发微趣/美图/视频/文章四类编辑能力完整：占位符、媒体添加、图片编辑、所在位置、提醒谁看、谁可以看、草稿、退出确认、自动保存等与现有实现及迁移任务一致。
- 更新迁移任务描述，使 CR1/CR2/CR3 明确「全页入口、默认发微趣、四 Tab 与全部操作」为 1:1 原型实现。

**Non-Goals:**

- 不改变 CreatePage 内部数据结构和草稿/保存逻辑；不新增后端 API。
- 入口抽屉（CreateEntrySheet）是否保留或仅从其他入口使用，不在本设计内强制删除。

## Decisions

1. **入口行为**  
   - 决策：底部导航「创作」点击执行 `context.go('/create')`（或等价），不再打开 `/create-entry` 或 CreateEntrySheet。  
   - 理由：与图一「创作即全页」一致，减少一步操作。  
   - 备选：保留先抽屉再全页；已否决，因与需求不符。

2. **默认 Tab 与标题**  
   - 决策：CreatePage 打开时无 `initialType` 或 type 时默认选中第一 Tab（微趣），标题为「发微趣」；Tab 标签文案为「微趣」「美图」「视频」「文章」（与图一底部四 Tab 一致，当前若为「图片」则改为「美图」）。  
   - 理由：图一即默认发微趣且底部为微趣/美图/视频/文章。

3. **全页形态**  
   - 决策：创作页继续使用全屏路由（如 `/create`），不改为弹窗或底部 sheet；AppBar 左侧关闭、中间标题、右侧草稿箱（无内容时）/ 发表（有内容时），底部 TabBar 固定四 Tab。  
   - 理由：与「非弹窗、全页」及图一布局一致。

4. **图片编辑与操作**  
   - 决策：沿用现有 `/create/edit-image` 与 CreateEditImagePage；发微趣/美图/文章中的图片添加、点击编辑入口打开编辑页，返回后更新本地路径/列表。所在位置、提醒谁看、谁可以看使用现有或扩展的 UITextConstants/路由，行为与现有 CreatePage 占位或已有逻辑一致并逐步 1:1 对齐原型。  
   - 理由：避免重复实现，保持与迁移任务 CR2/CR3 一致。

5. **迁移任务同步**  
   - 决策：在 figma-prototype-full-migration 的 tasks.md 中，将创作相关任务（CR1/CR2/CR3）的表述更新为：创作入口为全页（点击创作直接进入 /create）、默认发微趣、四 Tab（微趣、美图、视频、文章）及发微趣/美图/视频/文章的全部操作（含图片编辑）1:1 复制原型。  
   - 理由：保证迁移文档与本次实现一致，便于验收与后续归档。

## Risks / Trade-offs

- **[Risk]** 从「抽屉 → 全页」改为「直接全页」后，习惯六入口的用户少了一步选择。  
  **Mitigation**：全页底部四 Tab 可随时切换类型，与图一一致；若需保留六入口，可后续在发现页或其它入口保留 CreateEntrySheet。

- **[Risk]** 修改 main-nav 行为后，与现有 figma 迁移中「创作打开抽屉」的 spec 冲突。  
  **Mitigation**：本变更在 same change 内提供 main-nav 的 MODIFIED spec，归档时合并为「创作打开全页」；迁移任务同步更新为全页入口。

- **[Trade-off]** 不在此变更中删除 CreateEntrySheet 或 `/create-entry`，避免影响可能引用它们的入口；后续可单独清理。
