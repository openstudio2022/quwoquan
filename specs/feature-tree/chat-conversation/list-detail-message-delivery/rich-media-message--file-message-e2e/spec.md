# 文件消息端到端（File Message E2E）

> **层级**：L4_story（隶属 L3 `rich-media-message`）
> **状态**：specified

## 功能说明

实现文件消息从选择到对方接收预览的端到端闭环：

```
FilePicker 选择文件 → 校验(大小/类型) → 上传(OSS) → 发送(type=file)
  → 云端存储 → 推送/同步 → 接收方展示(文件卡片气泡)
  → 点击下载 → 根据类型路由到预览器
```

### 发送链路

1. `FilePicker` 选择任意格式文件
2. 校验文件大小 ≤100MB，获取 fileName/mimeType/fileSizeBytes
3. 通过 `MediaUploadManager` 上传 OSS
4. 上传完成后调用 `sendMessage(type='file', media={url, fileName, mimeType, fileSizeBytes})`
5. 本地乐观展示文件卡片气泡 + 上传进度

### 接收链路

6. 接收方收到文件消息
7. 气泡展示：文件类型图标（按类型着色）+ 文件名 + 大小标签 + 下载状态
8. 点击气泡：先下载到本地缓存 → 下载完成后路由到预览器

### 文件预览能力

| 格式 | 预览方案 | 实现库 |
|------|---------|--------|
| PDF | 端侧原生 PDF 阅读器 | `pdfx` / `syncfusion_flutter_pdfviewer` |
| TXT | 文本查看器 | 内置 Text Widget + 编码检测 |
| MD | Markdown 渲染器 | `flutter_markdown` / `markdown_widget` |
| DOCX/DOC | 调用系统应用打开 | `open_file` / Intent |
| PPTX/PPT | 调用系统应用打开 | `open_file` / Intent |
| 其他 | 「用其他应用打开」 | 系统分享 |

### 文件类型图标颜色体系

| 类型 | 颜色 | 图标 |
|------|------|------|
| PDF | 红色 #E53E3E | PDF 图标 |
| Word (DOC/DOCX) | 蓝色 #3182CE | Word 图标 |
| PPT (PPT/PPTX) | 橙色 #DD6B20 | PPT 图标 |
| Excel (XLS/XLSX) | 绿色 #38A169 | Excel 图标 |
| TXT/MD | 灰色 #718096 | 文本图标 |
| 其他 | 灰色 #A0AEC0 | 通用文件图标 |

## 约束

- 文件大小 ≤100MB
- 格式无限制（任意格式均可发送，但端侧预览仅支持上述格式，其余走系统打开）
- 弱网入离线队列，网络恢复后自动重传
- 文件下载到本地缓存（共享 200MB LRU 池）

## 适用范围与约束

- **适用**：趣聊 1v1 私聊和群聊中发送/接收文件消息
- **不适用**：在线文档编辑、云端格式转换（Phase 2）、超大文件（>100MB）

## 验收标准

| 编号 | 标准 | 对应 L3 |
|------|------|--------|
| F-A1 | 端到端闭环：选择→上传→发送→接收→下载→预览 | A5 |
| F-A2 | 气泡 UI：图标+文件名+大小+下载状态 | A6 |
| F-A3 | 预览路由：PDF/TXT/MD 原生预览，Office 系统打开 | A7 |
| F-A4 | 下载与缓存：进度+重试+LRU | A8 |
