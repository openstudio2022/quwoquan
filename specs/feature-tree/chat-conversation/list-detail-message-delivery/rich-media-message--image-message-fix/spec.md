# 图片消息修复与增强（Image Message Fix）

> **层级**：L4_story（隶属 L3 `rich-media-message`）
> **状态**：specified

## 功能说明

修复图片消息发送链路缺陷，新增全屏查看和大号 Emoji。

### 图片发送修复

当前问题：`_submitChatInput` 将图片附件降级为 `type=text` 文本占位（`[图片] xxx`），未调用 `MediaUploadManager` 上传。

修复后链路：
```
相册选择/拍照 → MediaUploadManager 上传(category=chatImage)
  → sendMessage(type='image', media={url, thumbnailUrl, width, height, mimeType, fileSizeBytes})
  → 云端存储 → 推送/同步 → 接收方展示图片气泡
```

### 图片全屏查看

点击聊天图片气泡 → Hero 转场 → 全屏图片查看器：
- 双指缩放
- 左右滑动切换同会话其他图片
- 下滑关闭
- 长按保存到相册

复用发现域 `ImageViewer` / `photo_view` 的设计模式。

### 大号 Emoji

纯 Emoji 消息检测与放大显示：
- 消息内容仅包含 1~3 个 Emoji 字符，无其他文字
- 气泡中 fontSize 放大至 ≥40（正常为 16）
- 超过 3 个 Emoji 或混有文字则按正常大小显示

检测算法：使用 Unicode Emoji 范围正则匹配，统计 Emoji 数量。

## 约束

- 图片大小 ≤20MB（`UploadPolicy.chatImage` 已定义）
- 格式：JPEG, PNG, GIF, WebP, HEIC
- 多图发送：逐张上传发送（`media.items[]` 多图合并后续增强）
- 全屏查看器使用 `photo_view` 包

## 适用范围与约束

- **适用**：修复聊天图片发送缺陷 + 新增全屏查看 + 大号 Emoji
- **不适用**：图片编辑（裁剪/标注）、多图合并消息（Phase 2 items[]）

## 验收标准

| 编号 | 标准 | 对应 L3 |
|------|------|--------|
| I-A1 | 图片发送修复：type=image + media 完整字段 | A9 |
| I-A2 | 全屏查看：缩放/滑动/保存/Hero 转场 | A10 |
| I-A3 | 大号 Emoji：1~3 纯 Emoji 放大显示 | A11 |
