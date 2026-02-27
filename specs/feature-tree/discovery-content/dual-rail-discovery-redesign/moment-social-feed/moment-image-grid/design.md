# moment-image-grid 设计

## 设计动因
微博图片布局已是用户高度熟悉的社交内容范式，直接复用可降低认知负担并快速交付。

## 关键决策
```dart
// 布局选择
if (count == 1) → ConstrainedBox(maxHeight: 400) + Image.network(fit: BoxFit.cover)
if (count == 2) → Row(children: [Expanded(img), Expanded(img)], gap: 2)
if (count >= 3) → GridView.count(crossAxisCount: 3, mainAxisSpacing: 2, crossAxisSpacing: 2)
```
浏览器：`Navigator.push` 全屏 `PageView`（黑背景），`initialPage = tappedIndex`。

## 未来演进
暂无。
