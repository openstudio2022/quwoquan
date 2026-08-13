# L3 Story：公开内容 Web 入口闭环（public-content-web-entry） (`public-content-web-entry`)

> 所属能力：[`runtime-client-foundation`](../spec.md)
>
> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)、[`JNY-002 / SCN-005`](../../../spec.md#scn-005)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为无法进入原生应用或从站外访问的用户，我希望在官方 Web 中完成登录、浏览、互动和发布等核心任务，并获得与设备匹配的可信安装入口，从而不因原生故障中断使用，也不下载第三方或不可安装的软件包。

## 2. 范围与非目标

### In Scope

- 公开内容 Web 入口规格。
- 站外分享 HTTPS 链同源。
- Markdown-to-SEO-HTML renderer 骨架。
- public HTML 服务最小闭环（post/circle/user/entity_homepage 四类对象的可索引 HTML envelope）。
- robots.txt、分类型 sitemap.xml、canonical、OG/Twitter card、JSON-LD、noindex 权限过滤。
- open / s/{token} 智能中转页 UA 分流合同与安装转化埋点。
- 响应式 Web/PWA 的登录、会话恢复、首页、圈子、搜索、详情、主页、发布、互动、聊天以及浏览器能力允许的通话、推送降级。
- 顶部安装横幅与通用官网下载页按可信平台提示推荐内容；Android 从趣我圈官方 HTTPS CDN 下载已签名 APK，公众 iOS 使用可添加到主屏幕的 PWA。
- Alpha、Beta、Gamma、Prod 分别使用 `alpha.quwoquan.com`、`beta.quwoquan.com`、`gamma.quwoquan.com`、`quwoquan.com`，页面和静态资源均以 UTF-8 响应；浏览器 API 统一走同源 `/api` 反代，不以 User-Agent 或其他请求头切换产品入口。

### Out of Scope

- 原生 CallKit、系统级后台通话或绕过浏览器权限模型的能力。
- 公众 iOS IPA、静默安装、第三方应用商店和长期 Token URL 传递。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 站外分享默认使用公开 HTTPS 链接

- 分享模板必须同时输出 HTTPS landing URL 与 deep link，且两者指向同一公开对象。
- 复制与系统分享默认输出 HTTPS；deep link 只作为受支持客户端的恢复目标。

<a id="req-002"></a>
### REQ-002 Markdown 可派生安全 SEO HTML

- renderer snapshot 覆盖 heading、paragraph、figure、gallery、callout、HTML escape。
- private 与未知 visibility 权限边界有测试。

<a id="req-003"></a>
### REQ-003 4 类对象公开页输出 SEO 元信息与 JSON-LD

- 四类公开对象网页必须输出一致的 canonical、Open Graph 与 JSON-LD 元数据。
- robots.txt 与分类型 sitemap.xml 生成。

<a id="req-004"></a>
### REQ-004 智能中转页按 UA 分流唤起或下载

- 中转页 UA 分流 contract 覆盖 4 类环境。
- 解析回 link_templates 同一实体行。

<a id="req-005"></a>
### REQ-005 安装转化入口对 4 类对象统一可用

- 安装转化组件必须区分手机与 PC，并只使用受控配置注入的下载地址。

<a id="req-006"></a>
### REQ-006 HTML 只能由 `articleMarkdown + articleAssetManifest + articleRenderProfile` 派生，不能成为作者或业务维护的第二正文

- HTML 只能由 `articleMarkdown + articleAssetManifest + articleRenderProfile` 派生，不能成为作者或业务维护的第二正文。
- URL path 结构来自 `quwoquan_service/contracts/metadata/_shared/link_templates.yaml`，禁止 Web 层手写第二套 `/post/...`。
- Markdown parser 已禁止任意 HTML；renderer 仍必须对全部文本做 HTML escape。
- 下载地址走 `CloudRuntimeConfig` + `--dart-define`，禁止组件硬编码（rule R28）。
- 官网下载页和客户端恢复页必须读取同一 `app_release` 发布事实；显式选择优先于 Client Hint 和 User-Agent，平台识别只决定推荐内容，是否最新只由显式 `platform + appVersion + buildNumber` 查询决定。
- Android 下载不得指向第三方应用商店或可变同名 APK；正式 APK 必须经生产签名、包名、Build、证书摘要和 SHA-256 门禁后发布到不可变官方 CDN 对象。
- Android 二进制下载只能由用户明确点击触发；iOS 安装动作只展示 Safari“添加到主屏幕”指引，standalone 模式隐藏安装横幅。
- Web 首屏必须声明 `lang="zh-CN"`、首部 UTF-8 charset、系统中文字体回退栈；HTML 响应必须使用 `text/html; charset=utf-8`，正文不得套用 icon font。
- Web 启动等待超时不得生成致命恢复事实或“重试”页面；只有捕获到的不可恢复异常才能进入恢复状态机。

## 4. 契约引用

- canonical：`specs/feature-tree/runtime/runtime-client-foundation/public-content-web-entry/spec.md`
- canonical：`quwoquan_service/contracts/metadata/_shared/link_templates.yaml`
- canonical：`quwoquan_service/services/product-ops-service/contracts/product_ops/app_release/operations.yaml`
- canonical：`quwoquan_service/services/product-ops-service/contracts/product_ops/app_release/fields.yaml`
- canonical：`specs/feature-tree/discovery-content/content-type-framework/markdown-article-kernel/spec.md`
- canonical：`specs/feature-tree/runtime/runtime-client-foundation/external-inbound-deeplink-routing/spec.md`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 站外分享默认使用公开 HTTPS 链接

- GIVEN 用户在内容分享 Sheet 点击复制链接或系统分享。
- WHEN 分享模板被构建并交给分享 action handler。
- THEN 站外文本使用 PUBLIC_WEB_BASE_URL + link_templates 的 HTTPS landing URL。
- THEN App deep link 保留在模板中，但不作为站外默认复制文本。

<a id="gwt-002"></a>
### GWT-002 Markdown 可派生安全 SEO HTML

- GIVEN 一篇公开文章提供 articleMarkdown、assetManifest 与公开链接。
- WHEN Markdown-to-SEO-HTML renderer 生成公开页投影。
- THEN 输出安全 HTML、canonical、OG 与 JSON-LD。
- THEN 任意 HTML / script 注入被转义或阻断。

<a id="gwt-003"></a>
### GWT-003 4 类对象公开页输出 SEO 元信息与 JSON-LD

- GIVEN 内容、圈子、用户、实体主页各有一个 public 可见对象。
- WHEN 公开 HTML 服务为对象渲染落地页。
- THEN 每类对象输出 canonical、OG/Twitter card 与对应 schema.org JSON-LD（Article/ImageObject/VideoObject/SocialMediaPosting/Organization/ProfilePage/Place）。
- THEN canonical 与 App 详情同一身份（PUBLIC_WEB_BASE_URL + link_templates path）。

<a id="gwt-004"></a>
### GWT-004 智能中转页按 UA 分流唤起或下载

- GIVEN 站外链接/二维码/口令默认落点为中转页 open / s/{token}。
- WHEN 不同 UA（微信 Android/鸿蒙、微信 iOS、系统浏览器、PC）访问中转页。
- THEN 微信 Android/鸿蒙内嵌 wx-open-launch-app，微信 iOS 用 Universal Link，浏览器用 UL/App Links/scheme，PC 渲染预览 + 下载 CTA。
- THEN 唤起失败按确定性阶梯降级到浏览器引导/下载页/web 预览。

<a id="gwt-005"></a>
### GWT-005 安装转化入口对 4 类对象统一可用

- GIVEN 用户在手机 Web 或 PC Web 浏览任一对象公开页。
- WHEN 用户触发安装/下载/扫码入口。
- THEN Android 手机 Web 明确点击后下载正式签名 APK。
- THEN iOS 手机 Web 展示 PWA 安装指引。
- THEN PC Web 并列提供 Android 下载和 iOS PWA 指引。
- THEN 下载地址来自 CloudRuntimeConfig，不硬编码。

## 6. 依赖

- 前置要求：[`runtime-client-foundation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 4 类对象公开页输出 SEO 元信息与 JSON-LD

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺 circle/user/entity_homepage 三类对象页与公网部署接线
  （gateway 路由、`CONTENT_PUBLIC_WEB_ORIGIN` 环境配置、公网域名证据）；post
  对象页第一段已落地——content-service `/public-web/post/{postId}` 输出
  canonical/OG/JSON-LD envelope 与 `articleMarkdown` 派生的安全正文 HTML，
  robots.txt 与 post sitemap 同面暴露，非公开对象 fail-closed 404，XSS 转义、
  行内样式/列表/引用语义标签均有 local_contract
  （`public_web_handler__local_contract_test.go`）。第二段已补：正文图片经
  `articleAssetManifest` 渲染为 `<figure><img alt>`——公网地址取 cdnUrl 优先、
  否则由 `PublicSliceKey` + `CONTENT_PUBLIC_WEB_CDN_ORIGIN` 派生，无公网
  URL 的 asset fail-closed 跳过；行内链接按 https/http 白名单渲染
  `<a rel="noopener">`，恶意 scheme 保持字面量。
- 完成判定：`GWT-003` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 智能中转页按 UA 分流唤起或下载

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：仍缺短链 token → 对象解析后端、引导页真实 universal
  link/wx-open-launch-app 前端注入与 4 类环境部署证据。第一段已接线——
  content-service `/public-web/open`（query target/id）与
  `/public-web/s/{token}` 消费 `runtime/publicweb` `ResolveTransfer`：
  爬虫/未知 UA 302 到对象 SEO 页，iOS/Android/微信/PC 按 UA 矩阵渲染
  noindex 引导页（`data-transfer-mode`/`data-launch-method` 语义），
  无目标 fallback 首页不伪造跳转，分流矩阵有 local_contract
  （`public_web_handler__local_contract_test.go`）。
- 完成判定：`GWT-004` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-003"></a>
### OPEN-003 安装转化入口对 4 类对象统一可用

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：安装转化组件测试覆盖手机/PC 两形态与下载地址注入。
- 完成判定：`GWT-005` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-004"></a>
### OPEN-004 完整 Web 与四环境公网证据

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：仓内已有响应式 Flutter Web 主 Shell 和核心业务路由，但尚缺四环境 DNS/TLS、真实同源 API、Safari/Android 浏览器、PWA 安装、Web Push/RTC 与完整业务矩阵的公网证据。
- 完成判定：`GWT-003`、`GWT-004` 与 `GWT-005` 在四环境公网真实通过，且 Alpha/Beta/Gamma/Prod 分别通过 UTF-8、登录、浏览、发布、互动、聊天、PWA 安装、Android 下载横幅和同源 API 的 `api_integration` 与 `user_acceptance`；缺项必须保留明确降级，不得宣称完整等价。
