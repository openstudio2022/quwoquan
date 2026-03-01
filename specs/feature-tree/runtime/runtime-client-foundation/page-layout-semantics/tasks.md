# L3 任务：page-layout-semantics

## 当前交付任务

由 L4 子节点承载，见：
- `top-toolbar-and-selection-pattern/tasks.md`
- `settings-page-structure/tasks.md`
- `circles-channel-management-panel/tasks.md`

## iOS 语义 v1 推进记录

- [x] 规范基线升级：`specs/ux/page-layout-semantics.md` 明确 iOS 语义 v1（导航、选择态、组件边界）
- [x] 创作入口两页样板对齐：地点选择、圈子选择改为统一 Cupertino 语义
- [x] 创作页设置行 trailing 箭头统一为 `CupertinoIcons.chevron_forward`
- [x] 第二批页面推广：`SettingsPage`、`AssistantManagementPage`、`AssistantHomePage`、`ChatSettingsPage`、`CircleStatsPage` 行尾箭头统一 iOS 语义
- [x] 第二批选择器推广：`StartGroupChatPage` 多选勾选控件改为 iOS 选择态图标语义
- [x] 门禁增强：`verify_dart_semantic.py` 新增 iOS 语义风格检查并由 `gate_repo.sh` 持续执行
- [ ] 圈子频道管理面板：完成微博式布局、蓝色主题动作与拖拽排序（见 `circles-channel-management-panel/tasks.md`）

## 遗留事项（后续补充）

- 用户主页、作者主页、圈子主页：后续单独规范「主页设计」
- CreateMediaPickerPage 自定义顶栏：当前保留，若后续统一为 AppBar 需同步更新规范
