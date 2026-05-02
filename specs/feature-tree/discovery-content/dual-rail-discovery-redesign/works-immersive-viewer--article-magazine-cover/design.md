# article-magazine-cover 设计

> 2026-03-22 更新：本设计基于过往版本“强制纯封面第一页 + 水平翻卡正文”的探索前提，已不再符合最新文章 PRD。进入下一轮 `/design` 时必须以 `article-display-journey/spec.md` 为准重写，本文件仅作记录参考。

## 设计动因
文章的"杂志感"来自三个层面：封面仪式感（吸引进入）、排版克制（呼吸感）、图文混排（视觉张力）。强制封面模式是防止"正文首句就把读者拒之门外"的关键设计。

## 适用场景与约束
适用：`ArticlePostDto`。约束：Flutter 不支持 CSS float，行内块布局（方案 A）在大多数阅读场景下视觉效果等价，且维护成本远低于自定义 RenderObject。

## 关键决策

### 封面屏
```dart
Stack(
  children: [
    // 全屏高清背景图（CachedNetworkImage，BoxFit.cover）
    // 底部 1/3 渐变遮罩（#0A0E14 透明 → 不透明）
    // 左下：大标题（NotoSerifSC，28pt，#E8EDF3）
    // 左下：作者头像 + 名字 + 关注按钮
  ],
)
```

### 分页方案（P1：服务端预切）
`ArticlePostDto.blocks` 按服务端分组，每组为一卡片页；若 `blocks` 为空降级到 `body: String` 单页渲染。

### 图片行内布局
```dart
// half / third
Row(
  children: [
    Image.network(block.url, width: block.widthFraction == 'half'
      ? screenWidth * 0.5 : screenWidth * 0.33),
    Expanded(child: Text(block.floatSide == 'left' ? ... : ...))
  ],
)
// full
Column(
  children: [
    Image.network(block.url, width: screenWidth),
    if (block.caption != null) Text(block.caption!, style: AppArticleTextStyles.caption),
  ],
)
```

## 备选方案
| 方案 | 描述 | 选用原因 |
|------|------|----------|
| **A（选定）行内块** | Row/Column 布局 | 简单稳定，80% 场景效果等价 |
| B 自定义 RenderObject | 真 CSS float | 开发成本高，维护难，暂不采用 |

## 未来演进
- P2：客户端动态文字分页（基于 `RenderParagraph` metrics，待评估稳定性）
