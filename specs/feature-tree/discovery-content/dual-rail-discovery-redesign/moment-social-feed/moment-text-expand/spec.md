# L4 契约/任务：moment-text-expand

## 功能说明
微趣帖子文字超过 5 行时截断，末尾显示"展开"按钮；点击就地展开全文（无跳转）。展开状态为 Widget 本地状态（bool），不需要 Provider。

## 范围
- `MomentTextCard`：`maxLines: _expanded ? null : 5`，`TextOverflow.ellipsis`
- "展开" / "收起" 按钮：内联文字按钮，克莱因蓝颜色 `#002FA7`
- 就地展开：`setState(() => _expanded = !_expanded)`

## 适用范围与约束
- 适用：`MomentPostDto.body` 非空且超过 5 行
- 约束：展开状态纯 Widget 本地，无需全局 Provider；列表复用时（`ListView.builder`）因 key 不稳定可能重置状态 → 使用 `ValueKey(post.id)` 保证稳定

## 验收标准概要
- A1：文字 > 5 行时截断 + 展开按钮
- A2：点击展开 → 全文显示，按钮变"收起"，无页面跳转
