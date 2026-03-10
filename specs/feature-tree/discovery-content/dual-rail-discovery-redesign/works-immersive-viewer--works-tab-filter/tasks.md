# works-tab-filter 任务清单

## 当前交付任务
- [ ] **W1** 新建 `WorksTabFilter` Widget（`lib/ui/discovery/widgets/works_tab_filter.dart`）
- [ ] **W2** Tab 横排：`[全部][视频][美图][文章]`，选中项克莱因蓝下划线
- [ ] **W3** `Timer(Duration(milliseconds: 1500))` 驱动 `AnimatedSlide` 收起（SlideTransition，Offset(0,-1)）
- [ ] **W4** 箭头指示器：`Positioned` 顶部中央，`AnimatedOpacity`，`#002FA7` 0.7 透明度
- [ ] **W5** 展开：`GestureDetector`（tap + vertical drag down）→ `ElasticOutCurve` 弹性动画 400ms
- [ ] **W6** Tab 切换回调 → `worksFeedProvider.notifier.load(filterType: type)`
- [ ] **T1** Widget test：1.5s 后 Tab 收起，箭头可见
- [ ] **T2** Widget test：tap 箭头展开，Tab 重新可见

## 搁置任务（带规划）
暂无。

## 未来演进任务
暂无。
