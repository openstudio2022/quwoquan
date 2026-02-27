# works-tab-filter 设计

## 设计动因
Tab 呼吸逻辑兼顾"引导发现"（首次显示 Tab）与"沉浸优先"（1.5s 后隐藏，最大化内容可视区域）。

## 适用场景与约束
适用于作品频道。约束：收起时不能引起内容区 layout 变化（避免内容跳动），须用 Overlay/Stack absolute 定位。

## 关键决策
```dart
// 收起：SlideTransition(position: Tween(begin: Offset.zero, end: Offset(0, -1)))
// 展开：使用 ElasticOutCurve(period: 0.4)，duration 400ms
// 指示器：Positioned(top: safeAreaTop + 4, center)，半透明克莱因蓝 #002FA7 0.7 opacity
```
Tab 切换时调用 `worksFeedProvider.notifier.load(filterType: selectedType)`，filterType 变更自动重置 cursor。

## 未来演进
暂无演进项，当前即为目标态。
