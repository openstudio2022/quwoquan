# L3 契约/任务：article-magazine-cover（Dark Paper）

> 2026-06-11 更新（Work Browser V1.0 Dark Paper）：浏览器内文章舞台为**深色纸张杂志阅读**。上一版“白底杂志阅读”不再作为当前真相源；文章必须与图片、视频保持沉浸连续性。页码 `‹ n / m ›` 为页面内容尾部元素（正文后、作者工具栏前），顶部禁止页码；翻页机制复用 `ArticleReaderFlipHost` / 降级 pager。

## 功能说明

文章作品的杂志感沉浸阅读：在 Work Browser 中以深色纸张承载标题、摘要、封面/插图、正文、结构化块、实体标签与页码。用户仍感知为“浏览作品”，不是进入另一个阅读器。

## 范围

- 纸张主题：深色纸、冷灰纸、暖黑纸、墨绿纸、深棕纸。
- 默认映射：摄影=深色纸、旅行=暖黑纸、历史=深棕纸、科技=冷灰纸、自然=墨绿纸。
- 阅读设置：更多菜单内实时切换 `系统适配 / 深色纸 / 冷灰纸 / 暖黑纸 / 墨绿纸 / 深棕纸`。
- 内容结构：标题、摘要、封面/插图、结构化正文、实体标签、页码。
- 翻页：复用 `ArticleReaderFlipHost` / `ArticleReadOnlyBookDeck`，正面/背面/底页/阴影同源纸张 palette。
- Markdown：QWQ Rich Markdown 实体标签解析为结构化 span，点击进入 `homepageDetail`。

## 适用范围与约束

- 适用：`WorkBrowserItemDto.normalizedWorkType == article`。
- 文章正文唯一真相源为 `articleMarkdown`；`body/cards` 只能作为摘要或空文档降级，不作为第二正文链路。
- 禁止默认白纸、米白纸、暖黄纸；这些只能作为非默认阅读偏好，不参与 Work Browser 默认体验。
- 禁止直接切换、淡入淡出替代翻书动画。
- 禁止 UI 层临时正则识别实体标签；实体必须来自 Markdown AST / Document span / metadata 投影。

## 验收标准概要

- A1：默认深色模式下，图片 → 文章 → 视频连续滑动无白屏或明显亮度跳变。
- A2：五个深色纸张主题色值落地，亮度层级接近。
- A3：垂类默认与更多菜单阅读设置均可实时切换纸张。
- A4：页码 `‹ n / m ›` 位于正文后、作者工具栏前；顶部无页码。
- A5：翻页正面、背面、底页、阴影共用同一纸张 palette。
- A6：Markdown 实体标签可点击进入实体主页。
