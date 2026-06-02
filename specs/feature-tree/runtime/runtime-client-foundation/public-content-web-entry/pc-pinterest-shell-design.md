# PC Pinterest 内容壳设计

## 体验目标

Web PC 首屏应像内容发现站，而不是移动 App 放大版。视觉权重交给内容墙和搜索，安装引导保持低干扰。

## 信息架构

```text
WebPcContentShell
├── WebPcHeader
│   ├── Brand
│   ├── GlobalSearch
│   ├── ChannelTabs
│   └── InstallAppCta
├── WebPcContentHome
│   ├── PinterestMasonryFeed
│   └── RightRail
├── WebPcSearchLanding
│   ├── StickySearchBox
│   ├── ContentMasonryResults
│   └── EntityGroups
└── WebPcPostDetailShell
    ├── SeoReadableArticle
    ├── AuthorAndRelatedRail
    └── InstallFooterCta
```

## 语义 Token

`AppSpacing` 已冻结以下 Web PC token，后续页面不得私写等价字面量：

| Token | 用途 |
|---|---|
| `webPcHeaderHeight` | PC 顶部 header 高度 |
| `webPcMasonryColumnWidth` | Pinterest 卡片理想列宽 |
| `webPcMasonryGap` | masonry 列/行间距 |
| `webPcReadingMinWidth` | 详情正文阅读宽度下限 |
| `webPcReadingMaxWidth` | 详情正文阅读宽度上限 |
| `webPcRightRailWidth` | 详情/首页右栏宽度 |
| `webPcInstallCtaCardWidth` | 右栏/文末安装 CTA 卡片宽度 |
| `webPcMasonryColumns(context)` | 宽屏内容墙列数计算 |
| `webPcReadingWidth(context)` | 详情正文宽度计算 |

## 首页 / 频道页

- Header 固定在内容上方，不抢占内容高度。
- 主区域使用 Pinterest masonry，内容卡按图片/视频/文章视觉权重混排。
- 右侧 rail 只放热门话题、推荐圈子、下载 App 小卡。
- 卡片 hover 才展示保存、分享、打开 App；默认状态只显示图像/标题/作者。
- 未登录用户可继续浏览公开内容；强互动引导 App。

## 搜索页

- 搜索框常驻顶部，结果首屏是内容瀑布流。
- 圈子、用户、话题作为辅助分组，不压过内容。
- 可静态输出 query 落地页摘要，进入交互后由 Flutter Web 接管。

## 内容详情页

- 正文居中，使用 `webPcReadingWidth(context)`，目标 720–820。
- 右栏使用 `webPcRightRailWidth`：作者、相关内容、下载 App 卡。
- 文末 CTA 使用 `webPcInstallCtaCardWidth` 的卡片语义。
- 安装引导只出现顶部 slim banner、右栏卡、文末 CTA，不使用强弹窗阻断阅读。

## CTA 分层

| 位置 | 强度 | 触发 |
|---|---|---|
| 顶部 slim banner | 低 | Web 全局显示，可关闭后本地记忆 |
| 卡片 hover | 低 | 保存、分享、打开 App |
| 右栏下载卡 | 中 | PC 详情 / 首页右栏 |
| 文末 CTA | 中 | 读完详情后 |
| 强引导 | 高 | 评论、收藏、关注、创作、私信等强互动 |

## 约束

- 频道、surface、route、operation 继续来自 metadata，不为 Web 新建第二套 IA。
- PC 组件只消费 `ContentSurfaceView` / 强类型 ViewModel，不直接透传 `Map<String, dynamic>`。
- 布局断点只走 `AppSpacing` 与 `PlatformCapabilities`。
- 新增页面文件时必须更新页面横向质量矩阵与 metadata UI 清单。
