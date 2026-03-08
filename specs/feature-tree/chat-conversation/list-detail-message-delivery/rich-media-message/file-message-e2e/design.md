# 文件消息端到端 设计方案

> 详细方案对比与关键决策见 L3 `../design.md`。本文仅记录 Story 级补充。

## 设计动因

实现文件消息从选择→上传→发送→接收→下载→预览/打开的完整链路。核心设计挑战：多格式文件预览策略。

## 上游输入评审

- L3 spec.md F2 (10-17) 明确，约束充分
- L3 acceptance.yaml A5~A8 可测量

## 选型决策

| 组件 | 选定 | 理由 |
|------|------|------|
| PDF 阅读器 | `pdfx` | MIT 无商业限制、原生渲染、轻量 |
| Markdown 渲染 | `flutter_markdown`（已安装） | 零新增依赖 |
| TXT 查看 | 内置 Text Widget + 编码检测 | 无需依赖 |
| Office 打开 | `open_filex` | 活跃维护、双端兼容 |
| 文件缓存 | 共享 `MediaDownloadCache` 200MB LRU | 与语音共享 |

## 关键设计决策

- KD-4: 文件消息气泡设计（见 L3 design.md）
- KD-5: 文件预览路由（见 L3 design.md）

## 文件预览能力矩阵

| 格式 | 渲染方案 | 渲染引擎 |
|------|---------|---------|
| PDF | 端侧原生 | `pdfx`（PdfViewPinch） |
| TXT | Text Widget | 内置 + `charset_detector` 编码检测 |
| MD | Markdown Widget | `flutter_markdown`（MarkdownBody） |
| DOCX/DOC | 系统应用 | `open_filex` → WPS/Office/Pages |
| PPTX/PPT | 系统应用 | `open_filex` → WPS/Office/Keynote |
| XLS/XLSX | 系统应用 | `open_filex` → WPS/Office/Numbers |
| 其他 | 系统分享 | `open_filex` fallback |

## 适用场景与约束

- 文件 ≤100MB、任意格式
- Office 格式依赖用户已安装第三方应用
- 文件下载后缓存，再次打开无需重下

## 未来演进

- 云端 Office→PDF 转换（LibreOffice Headless）
- WebView 在线文档预览
- 文件消息过期策略
- 文件卡片预览缩略图
