# L3 子特性：article-rich-content-blocks

## 功能说明
将 `ArticlePostDto.body: String` 升级为结构化 `blocks: List<ArticleBlock>`，支持创作时指定图片宽度（half/third/full）、floatSide（left/right/none）和图注（caption）。通过 metadata → codegen 生成类型安全的 DTO，端侧块渲染器（`ArticleBlockRenderer`）解析各类 block 类型。

## 范围
- `contracts/metadata/content/fields.yaml`：新增 `ArticleBlock` 多态 schema
- `make codegen`：生成 `article_block_dto.g.dart`（DO NOT EDIT）
- `ArticlePostDto` 更新：新增 `blocks: List<ArticleBlock>`，`body` 字段向后兼容保留（blocks 空时降级）
- 端侧块类型：`TextBlock`（content）/ `ImageBlock`（url, widthFraction, floatSide, aspectRatio, caption）/ `QuoteBlock`（content）

## 适用范围与约束
- **适用**：文章类型帖子（`ArticlePostDto`）
- **前置条件**：`metadata-domain-restructure` 已完成（metadata 基础结构）
- **约束**：
  - `blocks` 字段变更必须走 metadata → codegen；`.g.dart` 禁止手改
  - 图片宽高比约束：最大 9:16（`aspectRatio` 超出时渲染层截断）
  - `widthFraction` 枚举：`half` / `third` / `full`（创作端指定，API 透传）
  - `floatSide` 枚举：`left` / `right` / `none`

## 与父/子节点关系
- **父**：`dual-rail-discovery-redesign`（L2）
- **被依赖**：`article-magazine-cover`（L4）使用本节点生成的 `ArticleBlock` DTO

## 验收标准概要
- A1：`fields.yaml` 中 `ArticleBlock` schema 存在，`make codegen-app` 生成 `article_block_dto.g.dart`
- A2：`ArticleBlockDto.fromMap()` 正确解析 TextBlock / ImageBlock / QuoteBlock
- A3：ImageBlock 包含 `widthFraction` / `floatSide` / `caption` / `aspectRatio` 字段
- A4：`ArticlePostDto.blocks` 为空时，`body: String` 降级渲染（向后兼容）
