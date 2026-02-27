# works-immersive-viewer 设计

## 设计动因

三类精品内容（视频/美图/文章）在统一垂直 PageView 中呈现，共享沉浸感体验。核心挑战是在一个 widget tree 中协调多层手势竞争，同时保证各媒体类型的专属细节不互相干扰。

## 适用场景与约束

**适用**：作品频道内所有三类媒体的沉浸式浏览。
**约束**：
- 嵌套 PageView（外层垂直 + 内层水平）是 Flutter 中已知的手势竞争场景，需显式控制竞争策略
- `BackdropFilter` 的 GPU 开销较高，Drawer 关闭时须销毁 `ImageFilter` 节点

## 关键决策

### 1. 垂直 PageView 结构

```dart
PageView.builder(
  scrollDirection: Axis.vertical,
  physics: const PageScrollPhysics(),
  itemBuilder: (context, index) => _buildWorkItem(feed[index]),
)
```

`_buildWorkItem` 根据 `PostBaseDto` 类型派发到 `PhotoGalleryItem` / `VideoAutoPlayItem` / `ArticleCardItem`。

### 2. 手势竞争策略

```
外层 PageView（垂直）：
  ScrollPhysics = PageScrollPhysics + 自定义 drag 起点角度过滤
  ├── 角度 < 45° → 交给子 Widget 的水平手势
  └── 角度 ≥ 45° → 垂直换页

内层子 Widget 水平手势：
  HorizontalDragGestureRecognizer：
    dragStartBehavior = DragStartBehavior.start
    排除边缘 15px（gestureRecognizer 的 onlyAcceptDrags 判断 dx > 15）
```

**方案对比**：

| 方案 | 描述 | 选用原因 |
|------|------|----------|
| **A（选定）外层 angle filter** | 外层 PageView 通过 drag angle 判断是否消费 | 灵活，适合多类子 Widget |
| B NeverScrollableScrollPhysics | 外层完全禁止手势，子 Widget 接管全部 | 子 Widget 需自行实现垂直换页，耦合高 |

### 3. Drawer 定位方案

```dart
Stack(
  children: [
    // 作品内容（全屏）
    _WorksContent(post: post),
    // 右侧 Drawer（Overlay 管理）
    Positioned.fill(
      child: AnimatedSlide(
        offset: _drawerOpen ? Offset(0.6, 0) : Offset(1.0, 0),
        duration: Duration(milliseconds: 280),
        child: Align(
          alignment: Alignment.centerRight,
          child: SizedBox(
            width: MediaQuery.sizeOf(context).width * 0.4,
            child: ClipRRect(child: BackdropFilter(
              filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
              child: WorksGlassDrawer(),
            )),
          ),
        ),
      ),
    ),
  ],
)
```

Drawer 关闭时（offset.dx ≥ 1.0）通过 `Visibility(maintainState: false)` 完全卸载 `BackdropFilter` 节点，避免 GPU 持续开销。

### 4. 主题切换

```dart
// worksForceDarkProvider 激活时包裹整个作品轨
Theme(
  data: AppTheme.worksThemeData,  // 基于 #0A0E14
  child: WorksImmersiveViewer(...),
)
```

`AppTheme.worksThemeData` 仅覆盖 `scaffoldBackgroundColor`, `colorScheme`, `iconTheme`；文章专属字色通过 `AppArticleColors` 常量直接引用，不依赖 ThemeData.textTheme。

### 5. 底部工具栏响应式布局

```
Row:
  [Avatar 40px]  [6px]
  [Expanded →  Row([Flexible(name_col)]  [AnimatedSize(follow_btn)])]
  [SizedBox(divider)]
  [Row(4 actions)]
```

**3 档位参数**（对齐 `AppSpacing.compactBreakpoint=360 / expandedBreakpoint=600`）：

| 档位 | Action 单元宽 | Action 间距 | 跨组分隔 |
|------|--------------|------------|---------|
| compact < 360 | 40 px | intraGroupXs(4) | intraGroupSm(6) |
| regular 360–599 | 44 px | intraGroupSm(6) | intraGroupMd(8) |
| expanded ≥ 600 | 52 px | intraGroupMd(8) | intraGroupLg(12) |

Action 组总宽通过 `_cellWidth(ctx)` 计算后缓存，整个作品轨同一设备保持不变。

**方案对比**：

| 方案 | 描述 | 选用原因 |
|------|------|---------|
| **A（选定）固定 action 宽 + Expanded 名字** | Action 固定右锚，名字 Expanded 吸收剩余空间 | Action 不随名字长度抖动 |
| B Spacer 左侧留白 | Spacer 充满左侧，名字和 Action 两端对齐 | 留白过大，名字呼吸空间太小 |

### 6. 关注按钮延迟与动画策略

**延迟规则**：
- 已关注者：进入即同步显示（状态已建立，无需发现期）
- 未关注图片：3 秒后显示
- 未关注视频/文章：5 秒后显示

**入场动画**：`AnimatedSize(alignment: Alignment.centerRight)`
- `centerRight` 锚定右边缘固定，按钮向左展开
- 视觉效果：按钮从操作区左侧方向滑出，自然推压名字区域

**文字压缩策略**（仅未关注状态触发）：
- `AnimatedDefaultTextStyle(duration: 180ms, curve: Curves.easeOut)`
- 名字：14 px → 12 px；圈子名：10 px → 9 px（`AppTypography.xxs`）
- 已关注状态不压缩（状态已稳定，减少视觉干扰）

**名字截断策略**：
- 无关注按钮：`TextOverflow.ellipsis` 正常截断
- 有关注按钮：`ShaderMask` 固定 18 px 淡出（`shaderCallback` 根据 `bounds.width` 计算起始 stop），配合 `TextOverflow.clip`
- 固定像素淡出优于百分比 stop：保证在窄列（48 px）和宽列（100 px+）上淡出区宽度一致、可预期

### 7. 数字格式化规则（_formatCount）

```dart
String _formatCount(int n) {
  if (n < 10000) return '$n';
  if (n >= 100000) return '10万+';
  final tenK = (n / 10000 * 10).floor() / 10;
  return (tenK * 10).round() % 10 == 0
      ? '${tenK.truncate()}万+'   // 整数万，去掉 .0
      : '$tenK万+';               // 保留一位小数
}
```

规则：< 10 000 原值 → [10 000, 100 000) 显示 `m.n万+`（整数万省略小数）→ ≥ 100 000 显示 `10万+`。

### 8. 更多操作面板设计模式

更多面板（`_WorksMoreOptionsSheet`）为帖级操作，3 组独立卡片：
1. **正向操作**：保存图片/视频（按类型条件显示）、收藏（状态联动）、分享、复制链接
2. **反馈操作**：不感兴趣、举报（红色警示色）
3. **取消**：独立居中卡片

每组用 `_SheetGroup`（圆角 20 px 卡片 + `ClipAntialias`），组间 6 px 间距，条目间 0.5 px 分割线。条目固定高 52 px，`InkWell` 触感反馈。

## 未来演进

- 长按点位评论 P2（坐标持久化）：在 `works-annotation-dot` 节点中扩展，当前 P1 仅 UI 光点
- 视频 Picture-in-Picture：若平台能力具备，后续扩展 `VideoAutoPlayItem`
