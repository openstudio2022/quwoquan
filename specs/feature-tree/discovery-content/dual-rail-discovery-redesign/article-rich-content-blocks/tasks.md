# article-rich-content-blocks 任务清单

## 当前交付任务
- [ ] **M1** 在 `contracts/metadata/content/fields.yaml` 中新增 `ArticleBlock` 多态 schema（type / content / url / width_fraction / float_side / aspect_ratio / caption）
- [ ] **M2** 在 `ArticlePost` entity 的 fields 中新增 `blocks: List<ArticleBlock>?`（可选，向后兼容）
- [ ] **C1** `make verify` → `make codegen-app`（生成 `article_block_dto.g.dart`）
- [x] **R1** 更新 `MockContentRepository`：Mock 文章 DTO 包含 blocks（各类型各 1 条示例）（以 `cards` 结构先行落地多卡片阅读样本）
- [ ] **T1** Contract test：`ArticleBlockDto.fromMap()` 正确解析 TextBlock / ImageBlock / QuoteBlock
- [ ] **T2** Unit test：`width_fraction=half` → `widthFraction = ArticleWidthFraction.half`
- [x] **T3** Unit test：`blocks=null` → 降级到 `body: String` 渲染，不抛异常（当前详情投射支持 cards 缺省回退）

## 当前实现备注

- 已完成：文章详情页横向卡片阅读结构、封面模式、`full/half/third` 布局渲染与图注展示。
- 待完成：metadata 契约化 `ArticleBlock` 并用 codegen DTO 替换当前 `cards` 过渡结构。

## 搁置任务（带规划）
暂无。

## 未来演进任务
- [ ] 新增 VideoBlock（文章内嵌视频）
- [ ] CodeBlock / TableBlock
