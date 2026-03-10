# 图片消息修复与增强 设计方案

> 详细方案对比与关键决策见 L3 `../design.md`。本文仅记录 Story 级补充。

## 设计动因

修复图片消息从 text 占位降级为真正的 type=image 消息发送，补齐聊天图片全屏查看器，实现大号 Emoji 纯文本检测与放大显示。

## 上游输入评审

- L3 spec.md F3 (18-20) + F4 (21) 明确
- L3 acceptance.yaml A9~A11 可测量

## 选型决策

| 组件 | 选定 | 理由 |
|------|------|------|
| 图片查看器 | `photo_view`（已安装） | 零新增依赖、缩放/手势已验证 |
| 保存到相册 | `gal` | 轻量、双端、处理权限 |
| Emoji 检测 | Unicode 正则 + `characters` 包 | 无需新包、精确计数 |

## 关键设计决策

- KD-6: 聊天图片全屏查看（见 L3 design.md）
- KD-7: 大号 Emoji 检测算法（见 L3 design.md）
- KD-8: 消息气泡类型扩展策略（见 L3 design.md）

## 图片发送修复方案

当前代码（`_submitChatInput` 1307-1342 行）将图片/文件附件构造为 `type: 'text'` 的 Map：

```dart
// 当前（错误）：
'type': 'text',
'content': '[$kind] ${item.name}',
```

修复后通过 `MediaSendProvider`：

```dart
// 修复后：
await mediaSendProvider.send(MediaSendRequest(
  localPath: item.path,
  category: MediaCategory.chatImage,
  messageType: 'image',
  contentType: item.mimeType,
  ...
));
```

## 适用场景与约束

- 图片 ≤20MB、JPEG/PNG/GIF/WebP/HEIC
- 多图逐张发送（Phase 1），items[] 合并后续
- 大号 Emoji 仅 1~3 个纯 Emoji

## 未来演进

- 多图合并消息（media.items[]）
- 图片编辑（裁剪/标注/马赛克）
- 自定义表情包/贴纸系统
