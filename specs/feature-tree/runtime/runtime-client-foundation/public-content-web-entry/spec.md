# L3：公开内容 Web 入口闭环（public-content-web-entry）

## L1 / L2 / L3 映射

| 层级 | 标识 |
|---|---|
| L1 capability | `runtime` |
| L2 journey | `runtime-client-foundation` |
| L3 scenario | `public-content-web-entry` |

## 目标

建立“搜索引擎 -> 公开 HTML 内容页 -> PC 精美内容浏览 -> 轻社交/搜索 -> 安装 App 转化”的公开内容 Web 入口闭环。Web PC 是公开内容和搜索引擎引流入口，不是完整 App 复制品。

## 范围

负责：

- 冻结公开 Web URL、App deep link、Flutter route 的同源关系。
- 冻结 Markdown 作为内容真相源、HTML 作为 SEO 派生投影的边界。
- 定义公开 HTML SEO 输出合同：canonical、OG/Twitter card、JSON-LD、robots、sitemap。
- 定义 PC Pinterest 风格内容发现、搜索、详情与安装转化体验。
- 定义首批开发验收：分享 HTTPS 同源、Markdown-to-SEO-HTML renderer 骨架与快照测试。

不负责：

- 完整 PC masonry 首页视觉落地。
- 完整 SSR/静态 public web 服务上线。
- 创作、私信、RTC、复杂登录后社交闭环桌面化。

## 核心原则

- `articleMarkdown` 是长文唯一内容真相源。
- HTML 只能由 `articleMarkdown + articleAssetManifest + articleRenderProfile` 派生，不能成为作者或业务维护的第二正文。
- 站外分享默认 HTTPS 公共链接；App scheme/deep link 只作为打开 App 的目标。
- URL path 结构来自 `quwoquan_service/contracts/metadata/_shared/link_templates.yaml`，禁止 Web 层手写第二套 `/post/...`。
- 公开 HTML 与 App 详情使用同一 visibility / 审核状态判断。
- PC Web 的 route、surface、埋点语义与 App 同源；差异只允许出现在布局密度、导航壳、hover/快捷键增强。

## 当前断点

| 断点 | 现状 | 处理 |
|---|---|---|
| 内容命名 | `ContentSurfaceView.contentHtml` 实际不代表正式 HTML 正文 | 冻结为既有命名，后续重命名或迁移，不作为 SEO 真相源 |
| 分享链接 | 分享 Sheet `copy_link` 复制 `quwoquan://`，沉浸页复制 HTTPS | 分享模板新增 HTTPS landing URL，默认复制/分享 HTTPS |
| SEO 输出 | 无公开 HTML、robots、sitemap、OG/JSON-LD/canonical | 建立 Markdown-to-SEO-HTML renderer 与 public web 服务设计 |
| PC 体验 | 只有顶部安装提示与内容宽度约束 | 后续补 PC header、masonry、详情 right rail、文末 CTA |

## 技术链路

```mermaid
flowchart TB
  mdSource["articleMarkdown + assetManifest"] --> mdParser["QwqMarkdownParser"]
  mdParser --> seoRenderer["MarkdownToSeoHtmlRenderer"]
  seoRenderer --> htmlSnapshot["SEO HTML Snapshot"]
  seoRenderer --> seoMeta["canonical, OG, JSON-LD"]
  htmlSnapshot --> publicPost["/post/{postId} Public HTML"]
  publicPost --> searchEngine["Search Engine"]
  publicPost --> installCta["Install App CTA"]
  publicPost --> flutterWeb["Flutter Web Enhanced Shell"]
```

## Markdown -> SEO HTML 合同

输入：

- `articleMarkdown`
- `articleMarkdownDigest`
- `articleAssetManifest`
- `articleRenderProfile`
- post 公共字段：`postId`、`title`、`summary`、`coverUrl`、`author`、`createdAt`、`visibility`

输出：

- `SeoHtmlDocument.html`
- `SeoHtmlDocument.title`
- `SeoHtmlDocument.description`
- `SeoHtmlDocument.canonicalUrl`
- `SeoHtmlDocument.openGraph`
- `SeoHtmlDocument.jsonLd`
- `SeoHtmlDocument.referencedAssetUrls`

允许渲染的 Markdown 块：

- heading / paragraph / orderedItem / bulletItem / quote
- image / figure / gallery
- callout / card
- codeBlock（转义文本，不执行）
- horizontalRule

安全要求：

- Markdown parser 已禁止任意 HTML；renderer 仍必须对全部文本做 HTML escape。
- URL 只允许 `https://`、站内相对路径、解析后的 CDN 资产 URL。
- 不允许注入 `<script>`、inline event handler、未知标签。

## 公开 URL 与链接合同

| 场景 | 链接 |
|---|---|
| 站外复制/系统分享 | `AppPublicContentLinks.postWebUrl(postId)` |
| App 打开目标 | `AppLinkTemplates.postAppDeepLink(postId)` |
| public HTML path | `_shared/link_templates.yaml` 的 `post.web.path_template` |
| canonical | `PUBLIC_WEB_BASE_URL + post/{postId}` |

## PC 体验规格

### 首页 / 频道页

- 顶部 PC header：品牌、全局搜索框、频道导航、下载 App CTA。
- 主体 Pinterest masonry：图片、视频、文章卡按视觉权重混排。
- 右侧 rail：热门话题、推荐圈子、下载 App 小卡。
- hover 操作：分享、收藏、打开 App；默认卡面保持干净。

### 搜索页

- 搜索框常驻顶部。
- 首屏以内容瀑布流为主，圈子、用户、话题作为辅助分组。
- 搜索引擎落地页可静态展示 query 相关内容，进入交互后加载 Flutter Web。

### 内容详情页

- SEO HTML 首屏可读：标题、摘要、封面、作者、正文前几段。
- PC 详情正文宽度 720–820，整体内容容器与右栏不超过 Web 主内容宽。
- 右栏：作者卡、相关内容、下载 App 小卡。
- 安装引导：顶部 slim banner、右栏下载卡、文末 CTA；不使用强遮罩。

## 安装转化

- 手机/Pad Web：直接下载 App + 分享安装页。
- PC Web：选择 iPhone/iPad、Android/鸿蒙安装入口 + 分享安装页到手机/微信。
- 下载 URL 走 `CloudRuntimeConfig` 与 `--dart-define`，不在组件硬编码安装包地址。

## 首批开发验收

- 分享模板同时含 HTTPS landing URL 与 App deep link。
- `copy_link` / `system_share` 默认使用 HTTPS landing URL。
- Markdown-to-SEO-HTML renderer 能输出安全 HTML、canonical、OG、JSON-LD。
- Snapshot 覆盖 heading、paragraph、figure、gallery、callout、HTML escape、权限过滤。
- 规格与 `cross-platform-portability` 保持一致。

## 多对象公开 Web 扩展（external-acquisition-and-deeplink，本次新增）

公开 Web 从「仅内容」扩展到 **4 类对象**，作为搜索引擎与站外引流的统一落地面。「我」对外等同 user 公开视角，不单独建页。

### 对象 → 公开 path → SEO 类型映射

| 对象 | public path（来自 link_templates） | schema.org JSON-LD | 首屏可读字段 |
|------|-----------------------------------|--------------------|--------------|
| 内容/post | `post/{postId}` | Article（文章）/ ImageObject（图文）/ VideoObject（视频）/ SocialMediaPosting（动态） | 标题、摘要、封面/首帧、作者、时间、正文前几段 |
| 圈子/circle | `circle/{circleId}` | Organization | 名称、封面、简介、成员数、精选内容预览 |
| 用户/user | `u/{username}` | ProfilePage | 昵称、头像、简介、作品数、代表作预览 |
| 实体主页/entity_homepage | `homepages/{homepageId}` | Place / LocalBusiness | 名称、品类、评分、地址、封面、内容预览 |

### SEO 输出合同（落地）

- `canonical`：`PUBLIC_WEB_BASE_URL + 对象 web.path_template`，与 App 详情同一身份。
- `OG / Twitter card`：每类对象输出 `og:title/og:description/og:image/og:type` 与 `twitter:card`，图片走 CDN 资产，比例适配（内容 1.91:1，主页 1:1 头图）。
- `JSON-LD`：按上表类型输出结构化数据。
- `robots.txt` + 分类型 `sitemap.xml`（content/circle/user/homepages 各一组 sitemap index）。
- 权限过滤：Post 只允许 public/private；public 完整可索引，private/审核未过 `noindex` 且不渲染正文，与 App 详情同一 visibility 判断。圈内分发由 CirclePostPlacement 拥有，不改变 Post 可见性。

### 智能中转落地页（universal landing，协同 external-inbound-deeplink-routing）

- path：`open?target_entity&target_id&token` 与短链 `s/{token}`（来自 `link_templates.yaml` 的 `transfer_pages`）。
- 服务端按 UA 分流：
  - 微信 Android/鸿蒙 → 内嵌 `wx-open-launch-app`（extinfo 透传 target+归因）。
  - 微信 iOS → Universal Link 唤起。
  - 系统浏览器 → UL/App Links/scheme 唤起。
  - PC → 渲染对象公开 HTML 预览 + 下载 App CTA + 扫码安装。
- 唤起失败按 external-inbound-deeplink-routing 的确定性降级阶梯兜底。
- 中转页**只做解析与分流**，对象正文真相源仍是各领域；本节点不复制业务字段。

### 安装转化（扩展到 4 类对象）

- 手机/Pad Web：直接下载 + 分享安装页；唤起失败兜底下载。
- PC Web：iPhone/iPad、Android/鸿蒙安装入口 + 扫码安装 + 分享到手机/微信。
- 下载地址走 `CloudRuntimeConfig` + `--dart-define`，禁止组件硬编码（rule R28）。

### 与口令/海报引流协同

- 海报二维码默认指向短链 `s/{token}`，扫码进入中转页分流。
- UGC 平台口令（`share_token`）经短链表解析回 `target_entity/target_id`，与中转页同源。

## 设计文档

- [公开 HTML 服务 / 静态层设计](./public-html-service-design.md)
- [PC Pinterest 内容壳设计](./pc-pinterest-shell-design.md)
