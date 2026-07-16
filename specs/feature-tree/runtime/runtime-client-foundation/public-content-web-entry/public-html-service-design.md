# 公开 HTML 服务 / 静态层设计

## 定位

公开 HTML 层只负责搜索引擎可索引承载与首屏可读，不承载完整 App 交互。Flutter Web 继续负责登录后互动、复杂浏览和 App 壳体验。

## 承载形态

首选形态：`public-web-service` 或等价静态/SSR 项目。

要求：

- 消费同一内容读取合同、visibility、审核状态与 `_shared/link_templates.yaml`。
- 使用 `MarkdownSeoHtmlRenderer` 的同等渲染合同：Markdown AST -> 安全 HTML + SEO meta。
- 与 Flutter Web 分工清楚：`/post/{postId}` 首屏 HTML 可读，增强交互再引导到 Flutter Web / App。

## 路由

| 路由 | 输出 | 说明 |
|---|---|---|
| `/post/{postId}` | 公开内容 HTML | canonical 与分享链接默认目标 |
| `/robots.txt` | robots 策略 | 允许公开内容索引，阻断私密/内部路由 |
| `/sitemap.xml` | 可索引公开内容 | 只包含 public + 审核通过内容 |
| `/download` | 安装页 | PC 选择安装包，手机/Pad 直接下载 |
| `/download/ios` | iOS/iPadOS 安装入口 | URL 由配置注入 |
| `/download/android` | Android/鸿蒙安装入口 | URL 由配置注入 |

## `/post/{postId}` 输出

HTML 必须包含：

- `<link rel="canonical" href="...">`
- `<title>` 与 `meta[name="description"]`
- Open Graph：`og:type`、`og:title`、`og:description`、`og:url`、`og:image`
- Twitter card：`twitter:card`
- JSON-LD：`Article`；有媒体时补 `ImageObject` / `VideoObject`
- 首屏正文：标题、摘要、封面、作者、发布时间、正文前几段
- 安装 CTA：顶部 slim CTA、文末 CTA；PC 可有 right rail 下载卡

## 权限过滤

| visibility / 状态 | 输出 |
|---|---|
| `public` + 审核通过 | 完整可索引 HTML |
| `private` | 不生成公开正文；返回 noindex 或 404/403 策略页 |
| 未审核通过 / 下架 | 不进入 sitemap，不输出完整正文 |

Post 不存在圈内可见性；CirclePostPlacement 是 Circle 上下文的分发事实，不参与公开 HTML 权限判断。

## Sitemap

生成规则：

- 只包含 `public` 且审核通过的内容。
- URL 使用 `AppPublicContentLinks.postWebUrl(postId)` 等价的 link template。
- `lastmod` 来自内容更新时间；无更新时间时使用发布时间。
- 可按日期/分片输出，避免单文件过大。

## Robots

基础策略：

```text
User-agent: *
Allow: /post/
Disallow: /app/
Disallow: /internal/
Disallow: /api/
Sitemap: ${PUBLIC_WEB_BASE_URL}/sitemap.xml
```

## 缓存与失效

- 缓存 key：`postId + articleMarkdownDigest + visibility + reviewState + renderProfile`。
- Markdown 或 asset manifest 变化后失效。
- visibility 从 public 改为 private 后必须立即清理公开缓存并从 sitemap 移除。

## 测试

- local_contract：link template 与 `/post/{postId}` 输出一致。
- local_contract：renderer snapshot 覆盖 HTML、canonical、OG、JSON-LD、权限过滤。
- api_integration：服务层请求 `/post/{postId}`、`robots.txt`、`sitemap.xml`。
- user_acceptance：搜索引擎落地页首屏可读，无强安装遮挡。
