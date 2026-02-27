# L4 契约/任务：works-tab-filter

## 功能说明
作品频道顶部二级分类 Tab：`[全部][视频][美图][文章]`。进入作品频道后 1.5s 自动向上收起，顶部中央保留半透明克莱因蓝下箭头指示器；点击箭头或向下拉动屏幕以 Elastic 弹性动画重新展开。Tab 切换传递 `filter_type` 至 `WorksFeedNotifier`，触发 cursor 重置和重新加载。

## 范围
- `WorksTabFilter` Widget：横向 Tab Row + `AnimatedSlide` 收起 + `ExpandMore` 指示器
- `Timer(1.5s)` 驱动初次自动收起，`worksForceDarkProvider` 重置后重新计时
- Tab 切换 → `ref.read(worksFeedProvider.notifier).load(filterType: ...)`
- 指示器：`AnimatedOpacity` + `GestureDetector`（tap + vertical drag 展开）

## 适用范围与约束
- 仅在作品频道有效；微趣轨无此组件
- 收起状态下指示器不占内容区高度（`Overlay` 或 `Stack` 定位）

## 验收标准概要
- A1：进入作品频道 1.5s 后 Tab 平滑收起，仅箭头可见
- A2：点击箭头或向下拉动 → Elastic 弹性动画展开（`ElasticOutCurve`）
- A3：切换 Tab → `filter_type` 正确传递，`WorksFeedNotifier` cursor 重置，重新加载
