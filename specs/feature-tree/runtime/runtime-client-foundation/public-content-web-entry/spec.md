# L3 Story：公开内容 Web 入口闭环（public-content-web-entry） (`public-content-web-entry`)

> 所属能力：[`runtime-client-foundation`](../spec.md)
>
> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，我希望建立“搜索引擎 -> 公开 HTML 内容页 -> PC 精美内容浏览 -> 轻社交/搜索 -> 安装 App 转化”的公开内容 Web 入口闭环。Web PC 是公开内容和搜索引擎引流入口，不是完整 App 复制品，从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- 公开内容 Web 入口规格。
- 站外分享 HTTPS 链同源。
- Markdown-to-SEO-HTML renderer 骨架。
- public HTML 服务最小闭环（post/circle/user/entity_homepage 四类对象的可索引 HTML envelope）。
- robots.txt、分类型 sitemap.xml、canonical、OG/Twitter card、JSON-LD、noindex 权限过滤。
- open / s/{token} 智能中转页 UA 分流合同与安装转化埋点。
- PC 内容优先体验与安装转化规格。
- 通用官网下载页自动识别 iOS、Android/鸿蒙或桌面；Android 从趣我圈官方 HTTPS CDN 下载已签名 APK，iOS 只进入 App Store。

### Out of Scope

- 完整 PC masonry 首页实现。
- 创作、私信、RTC 的桌面化实现。

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
- 官网下载页和客户端恢复页必须读取同一 `app_release` 发布事实；User-Agent 只决定平台入口，是否最新只由显式 `platform + appVersion + buildNumber` 查询决定。
- Android 下载不得指向第三方应用商店或可变同名 APK；正式 APK 必须经生产签名、包名、Build、证书摘要和 SHA-256 门禁后发布到不可变官方 CDN 对象。

## 4. 契约引用

- canonical：`specs/feature-tree/runtime/runtime-client-foundation/public-content-web-entry/spec.md`
- canonical：`quwoquan_service/contracts/metadata/_shared/link_templates.yaml`
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
- THEN 手机 Web 直接下载并兜底；PC Web 提供多平台安装入口 + 扫码 + 分享到手机/微信。
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
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：4 类对象 SEO 快照测试覆盖 canonical/OG/JSON-LD。
- 完成判定：`GWT-003` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 智能中转页按 UA 分流唤起或下载

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：中转页 UA 分流 contract 覆盖 4 类环境。
- 完成判定：`GWT-004` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-003"></a>
### OPEN-003 安装转化入口对 4 类对象统一可用

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：安装转化组件测试覆盖手机/PC 两形态与下载地址注入。
- 完成判定：`GWT-005` 对应行为满足且真实测试 `spec_ref` 有效
