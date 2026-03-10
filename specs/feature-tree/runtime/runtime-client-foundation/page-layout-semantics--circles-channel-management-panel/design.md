# Design: circles-channel-management-panel

## 设计动因

当前圈子页右上角入口承载助理能力，无法直接管理一级频道；一级 tab 固定且不可用户自定义，不满足「按兴趣配置频道」需求。目标是提供微博式频道管理体验，并保持 iOS 语义与现有设计系统一致。

## 关键决策

| 决策点 | 选项 A | 选项 B（选定） | 原因 |
|--------|--------|----------------|------|
| 管理入口 | 保留助理头像 | 三横频道管理图标 | 语义直接对应“频道管理” |
| 面板承载 | 新路由/全屏页 | 一级 tab 下方内联滑出 | 保持上下文连续，不打断浏览 |
| 频道数据来源 | 独立硬编码频道集 | 复用 `circlesCategoryConfig` | 与当前 app 频道配置一致 |
| 默认选中 | 全量默认选中 | 排除 `car/humanity/sports` | 满足产品默认策略 |
| 排序能力 | 仅增删 | 增删 + 拖拽重排 | 对齐微博频道管理心智 |
| 状态存储 | 仅内存 | `SharedPreferences` 本地持久化 | 重启后保持用户偏好 |
| 主题色 | 跟随历史动作色 | 蓝色主色（`AppColors.primaryColor`） | 明确避免橘色偏差 |

## 状态模型

- `allChannelIds`：来自 `following + circlesCategoryConfig.keys`
- `selectedChannelIds`：我的频道（可重排）
- `unselectedChannelIds`：全部频道中未选集合
- `activePrimaryTab`：当前一级 tab（必须属于 `selectedChannelIds`）

### 状态变更规则

- `remove(id)`：`selected -> unselected`
- `add(id)`：`unselected -> selected`（append 到末尾）
- `reorder(oldIndex, newIndex)`：仅调整 `selected` 内顺序
- 若当前 active tab 被移除：回退到相邻可用 tab，保证页面可用

## 持久化策略

- 存储键：`circles.selected_channels.v1`
- 存储内容：`StringList(selectedChannelIds)`
- 恢复时做纠偏：
  - 过滤不存在于当前 `allChannelIds` 的历史 id
  - 将新增频道追加到末尾
  - 若为空则回落到默认策略（排除 `car/humanity/sports`）

## UI 语义与像素对齐

- 区块结构：`我的频道（拖动排序）`、`全部频道（点击添加频道）`
- 已选项：浅灰底 + 右上角圆形 `x`
- 未选项：白底 + 虚线边框 + 前置 `+`
- 操作色：完成/强调/选中态统一蓝色主色
- 间距、字号、圆角使用 `AppSpacing/AppTypography/AppColors`，禁止硬编码
- 一级 tab 左对齐：Tab 容器水平内边距与内容区一致，首字符与内容区左边缘对齐

## 滚动稳定性约束（新增）

- 参考 `main` 分支当前 `CenteredScrollableTabBar` 的滚动状态机与边界处理策略：
  - 使用实际 tab 区域宽度计算阈值（避免以全屏宽度估算导致切换抖动）
  - 锚定切换时同步控制器并在下一帧对齐 offset
  - 滚动目标在边界处做 clamp/snap，避免首帧和跨阈值时“突跳”
- `CirclesPage` 接入频道管理面板后，不修改上述稳定策略的核心逻辑，仅在其上叠加面板能力。

## 非目标

- 不改变圈子详情页（`CircleDetailPage`）布局规范
- 不引入服务端偏好同步（仅本地持久化）
