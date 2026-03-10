# moment-text-expand 设计

## 设计动因
就地展开减少跳转层级，保持信息流流畅性。本地 bool 状态足够，无需引入 Provider。

## 关键决策
```dart
// MomentTextCard（StatefulWidget）
Text(
  post.body,
  maxLines: _expanded ? null : 5,
  overflow: _expanded ? TextOverflow.visible : TextOverflow.ellipsis,
)
if (!_expanded || _expanded)
  GestureDetector(
    onTap: () => setState(() => _expanded = !_expanded),
    child: Text(_expanded ? '收起' : '展开', style: TextStyle(color: Color(0xFF002FA7))),
  )
```
`ValueKey(post.id)` 保证列表复用时状态不混淆。

## 未来演进
暂无。
