# 开发任务：content-display-journey-consistency

## 总览（执行顺序）

本 L2 的任务按以下顺序推进（基础层先行，旅程层依赖基础层）：

```
0. app-dir-restructure      ← 先执行（工程目录迁移，记录存留渐进）
1. feed-item-dto-contract   ← 次执行（类型化 DTO 拆分，含 width/height）
2. content-action-intent-contract  ← 再执行（操作意图基础）
3. photo-display-journey    ← 依赖上面三者
4. video-display-journey / article / moment  ← 复用 photo 模式逐一推进
```

---

## 工程目录迁移（R - Restructure）

> 记录代码**存留不删**，新代码按新目录创建，旧页面逐一迁移。

| 任务 | 说明 | 状态 |
|------|------|------|
| R0 | `01-arch-constraints.mdc` §2 更新：`features/` → `ui/`，cloud/runtime/generated 按域组织 | ✅ 完成 |
| R1 | 创建 `lib/ui/discovery/` 目录结构（pages/ providers/ widgets/） | ✅ 完成 |
| R2 | 迁移 `features/home/pages/discovery_page.dart` → `ui/discovery/pages/discovery_page.dart` | ✅ 完成（旧文件加 DEPRECATED 注释保留；`main_app_shell.dart` 已更新 import） |
| R3 | 迁移 `features/discovery/providers/discovery_feed_provider.dart` → `ui/discovery/providers/` | ✅ 完成（旧文件加 DEPRECATED 注释保留；`app_router.dart` 已更新 import） |
| R4 | 将四类内容渲染从 `discovery_page.dart` 拆出为独立 Widget：`photo_feed_grid.dart`、`video_feed_view.dart`、`article_feed_list.dart`、`moment_feed_list.dart` | 待执行（依赖 photo/video-display-journey 各自完成后提取） |

---

## 子特性任务归属

| 子特性 | 任务位置 | 优先级 | 状态 |
|--------|----------|--------|------|
| **feed-item-dto-contract** | feed-item-dto-contract/tasks.md | **优先（前置）** | ✅ 两阶段全部完成（PostBaseDto 类型化拆分、width/height、32 测试通过） |
| **content-action-intent-contract** | content-action-intent-contract/tasks.md | **优先（前置）** | 待开始 |
| photo-display-journey | photo-display-journey/tasks.md | **优先** | 部分完成（D1~D4、D12~D14 已完成） |
| video-display-journey | video-display-journey/tasks.md | 二期 | 部分完成（D1~D6、D9~D12、D14 已完成）；DTO 集成待 |
| article-display-journey | article-display-journey/tasks.md | 二期 | 未开始 |
| moment-display-journey | moment-display-journey/tasks.md | 二期 | 未开始 |

---

## 搁置任务（带规划）

| 任务 | 搁置原因 | 计划重启条件 |
|------|----------|-------------|
| 跨进程状态持久化（冷启动后保持关注/赞/收藏） | 依赖云侧 GetReactionState、UserRepository.followStatus API | content-action-intent-contract 完成后，云侧 API 补全时 |

---

## 未来演进任务

- 圈子流浏览器一致性（若需求）：新增 L3 `circle-feed-display-journey`
- 评论数、转发数从云侧实时拉取（当前用 post 快照）：需 ContentRepository 新增 getPostStats API
- 各类型旅程完成后：`lib/ui/discovery/widgets/` 中的卡片组件提取为可复用的设计系统组件
