# chat-list-ui-polish 设计方案

## 设计动因

趣聊列表页四个 UI 断层需要修复：Tab 居中偏移、小趣助理冗余条目、圆形头像与主流不符、群聊缺少九宫格组合头像。全部为纯前端变更，不涉及新接口。

## 上游输入评审

- `chat-list-ui-polish/spec.md` 已冻结 UI1~UI5 五项功能
- `acceptance.yaml` 已定义 A1~A8 八项验收
- 现有 `CenteredScrollableTabBar` 源码已分析，Tab 居中问题根因明确

## 方案对比

### 对比 1：Tab 居中修复

#### 方案 A：Stack 叠加 trailing 按钮

将 trailing 按钮从 `Row` 子元素改为 `Stack + Positioned` 叠加在右侧，Tab 区域占满全宽居中。

**优点**：Tab 文字真正全宽居中，不受按钮数量影响
**缺点**：trailing 按钮悬浮在 Tab 区域上方，极端情况可能遮挡末尾 Tab

#### 方案 B：两侧对称 padding 补偿（选定）

保持现有 `Row(leading + Expanded + trailing)` 结构不变，在 `chat_page.dart` 的 `_buildMainTabs` 中为趣聊场景添加等宽的 `leadingActions` 透明占位，使 Tab 区域在两侧按钮等宽时自然居中。

**优点**：不改通用组件，影响范围最小；`CenteredScrollableTabBar` 内部 `_buildNormalLayout` 已有 `Center` 逻辑
**缺点**：需要手动计算占位宽度与 trailing 等宽

#### 方案 C：CenteredScrollableTabBar 增加 `centerIgnoringActions` 参数

新增参数，使内部布局改为"先按全宽居中 Tab，再绝对定位 trailing"。

**优点**：通用组件可复用
**缺点**：改通用组件影响所有使用方

**选定方案 B**：趣聊场景仅 2 个 Tab，宽度远小于屏幕，`Center` 已生效，只需补对称 leading 占位。

### 对比 2：圆角方形头像实现

#### 方案 A：`ClipRRect` + `Image` 替换 `CircleAvatar`（选定）

新建 `RoundedSquareAvatar` Widget，内部用 `ClipRRect(borderRadius: 8)` 包裹 `Image`。

**优点**：简单、可控、与 `CircleAvatar` 切换成本低
**缺点**：需要手动处理占位/错误态

#### 方案 B：自定义 `ShapeBorder` + `CircleAvatar`

用 `RoundedRectangleBorder` 替换 `CircleAvatar` 的 `shape`。

**优点**：复用 `CircleAvatar` 的占位/错误态逻辑
**缺点**：`CircleAvatar` 名字语义不符，且 `shape` 参数需要 Flutter 3.x+

**选定方案 A**：更清晰、更可控。

### 对比 3：九宫格头像

单一方案：纯前端 Widget `GroupAvatarGrid`，根据有效头像数量按规则排列，无需对比。

## 关键设计决策

### KD-1：`RoundedSquareAvatar` 通用组件

```dart
class RoundedSquareAvatar extends StatelessWidget {
  final double size;
  final String? imageUrl;
  final String? name;        // fallback 显示首字母
  final double borderRadius; // 默认 AppSpacing.borderRadius (8.0)
  final VoidCallback? onTap;
}
```

所有聊天域头像统一使用此组件，替换 `CircleAvatar`。

### KD-2：`GroupAvatarGrid` 组件

```dart
class GroupAvatarGrid extends StatelessWidget {
  final double size;          // 总尺寸（与单头像一致 56px）
  final List<String> avatarUrls; // 有效头像 URL 列表
  final double borderRadius;  // 外层容器圆角
  final double innerGap;      // 子头像间距 (1px)
}
```

布局算法：

```
1 个 → 单个居中占满
2 个 → 上下居中各一个
3 个 → 品字：上一居中，下二
4 个 → 2×2
5 个 → 上二居中，下三
6 个 → 上三下三
7 个 → 上一居中，中三，下三
8 个 → 上二居中，中三，下三
≥9 个 → 3×3（取前 9）
```

### KD-3：Tab 居中对称补偿

在 `chat_page.dart` 的 `_buildMainTabs` 中，`leadingActions` 添加与 `trailingActions` 等宽的透明占位 Widget，使两侧宽度相等，Tab 自然居中。

### KD-4：移除小趣助理条目

删除 `_buildMessagesContent` 中 `showAssistant` 条件及 `_ConversationTile(isSpecial: true)` 渲染块。

## TDD / ATDD 策略

| Task | 验收项 | 测试层 | Red 先行 |
|---|---|---|---|
| T1: Tab 居中 | A1 | T2 | Widget test 验证 Tab 在不同按钮数量下居中 |
| T2: 移除助理 | A2 | T2 | Widget test 验证列表无助理条目 |
| T3: RoundedSquareAvatar | A3 | T2 | Widget test 验证 ClipRRect borderRadius |
| T4: GroupAvatarGrid | A5~A7 | T2/T4 | Widget test 验证各人数布局 |
| T5: 接入替换 | A3~A4 | T2 | Widget test 端到端 |
| T6: 同好列表 | A3 | T2 | 同步替换 |

## 未来演进

- `RoundedSquareAvatar` 可扩展支持在线状态指示灯
- `GroupAvatarGrid` 可支持动画加载效果
