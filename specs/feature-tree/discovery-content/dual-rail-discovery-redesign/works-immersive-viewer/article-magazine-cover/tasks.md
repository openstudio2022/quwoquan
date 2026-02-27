# article-magazine-cover 任务清单

## 当前交付任务
- [ ] **A1** 注册思源宋体到 `pubspec.yaml` + `assets/fonts/source_han_serif/`
- [ ] **A2** 新建 `AppArticleColors`（`lib/core/theme/app_article_colors.dart`）
- [ ] **A3** 新建 `ArticleCoverItem`（封面屏：全屏图 + 渐变遮罩 + 衬线标题 + 作者徽标）
- [ ] **A4** 新建 `ArticleCardPager`（水平 `PageView`，blocks 分组为卡片页，禁用垂直滚动）
- [ ] **A5** 新建 `ArticleBlockRenderer`：`TextBlock`（思源宋体）/ `ImageBlock`（行内块）/ `QuoteBlock`（克莱因蓝竖线）
- [ ] **A6** `ImageBlock` 行内布局：`half`/`third` → `Row(Image + Expanded(Text))`；`full` → `Column(Image + caption)`
- [ ] **A7** `ArticlePostDto.blocks` 为空时降级：`body: String` 渲染为单页
- [ ] **T1** Widget test：封面屏无正文字符，标题字体为 NotoSerifSC
- [ ] **T2** Widget test：水平翻卡，无垂直滚动
- [ ] **T3** Widget test：ImageBlock half 宽度 = screenWidth * 0.5，full 宽度 = screenWidth

## 搁置任务（带规划）
| 任务 | 搁置原因 | 计划重启 |
|------|----------|----------|
| 客户端动态文字分页 | RenderParagraph metrics 在不同字体/屏幕尺寸下稳定性待评估 | 服务端预切 P1 交付后，用户反馈驱动 |

## 未来演进任务
- [ ] 客户端动态分页（依赖 RenderParagraph metrics 评估通过）
