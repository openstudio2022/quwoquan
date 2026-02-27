# article-rich-content-blocks 设计

## 设计动因
纯 `body: String` 无法携带"图片在哪里、多宽、朝哪侧"的语义，必须升级为结构化块格式。块格式是移动端富文本的业界通用方案（Notion、Medium 均采用 block-based 模型）。

## 适用场景与约束
适用：所有文章类型内容。约束：创作端编辑器需同步支持块格式输入（超出本节点范围，本节点仅保证 DTO 契约和端侧渲染）。

## 关键决策

### Block DTO 结构（metadata schema）
```yaml
# fields.yaml 新增
ArticleBlock:
  type: enum [text, image, quote]
  # text block
  content: string?
  # image block
  url: string?
  width_fraction: enum [half, third, full]?
  float_side: enum [left, right, none]?
  aspect_ratio: string?  # "4:3", "16:9", 最大 "9:16"
  caption: string?
  # quote block
  quote_content: string?
```

### 向后兼容策略
`ArticlePostDto.blocks` 新增为可选字段（`List<ArticleBlock>?`）。API 返回旧格式（仅有 `body` 字段）时，端侧降级到单页纯文本渲染，不崩溃。

### 端侧解析
`ArticleBlockDto.fromMap(Map)` 通过 `type` 字段派发到各子类，不识别的 type 降级为 `TextBlock`（防御性解析）。

## 备选方案
| 方案 | 描述 | 选用原因 |
|------|------|----------|
| **A（选定）结构化 blocks** | metadata schema → codegen DTO | 类型安全，端云一致，可演进 |
| B Markdown with directives | `![img](url){width=half}` | 解析脆弱，无法 codegen，废弃 |
| C HTML string | `<img style="width:50%">` | 需 `flutter_html` 依赖，排版控制弱，废弃 |

## 未来演进
- 新增 `VideoBlock`（文章内嵌视频）
- `CodeBlock` / `TableBlock`（深度文章排版）
