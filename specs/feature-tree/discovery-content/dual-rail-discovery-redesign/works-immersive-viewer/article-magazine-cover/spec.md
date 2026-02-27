# L4 契约/任务：article-magazine-cover

## 功能说明
文章作品的杂志感沉浸阅读：第一屏强制封面模式（高清背景图 + 衬线大标题 + 作者徽标），水平翻卡进入正文；正文使用思源宋体，行高 2.0，字间距 0.8，块渲染支持 half/third/full 宽度图片行内布局。

## 范围
- `ArticleCoverItem`：封面屏（`coverUrl` 全屏 + 标题 + 作者）
- `ArticleCardPager`：水平 `PageView`，每卡一页（服务端预切 `pages: List<String>` / blocks 分组）
- 块渲染：`ArticleBlockRenderer`（`TextBlock` / `ImageBlock` / `QuoteBlock`）
- 图片行内布局：`half`/`third` → `Row(Image + Expanded(Text))`；`full` → `Column(Image + caption)`
- 字体：思源宋体（`NotoSerifSC` 或 `SourceHanSerif`），`pubspec.yaml` 注册
- 色彩：`AppArticleColors`（background `#0A0E14`，bodyText `#B8C0CC`，title `#E8EDF3`，accent `#4A8BF5`，caption `#6B7585`）

## 适用范围与约束
- 适用：`ArticlePostDto`（需含 `blocks` 字段，P1 向后兼容 `body: String` 降级为单页）
- 约束：严禁垂直滚动正文（强制水平翻卡）；封面屏不显示任何正文字符
- 图片行内布局不支持 CSS float（Flutter 限制），仅行内块排版

## 验收标准概要
- A1：第一屏为封面模式（高清图全屏，衬线大标题，作者徽标），无正文
- A2：水平翻卡浏览正文，无垂直滚动
- A3：块渲染正确：TextBlock 思源宋体，ImageBlock half/third/full 布局与 floatSide 正确
- A4：AppArticleColors 色彩正确应用（背景 / 正文 / 标题 / 引用 / 图注）
