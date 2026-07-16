# L2 特性：outbound-share-distribution（对外分享分发）

## 功能说明

为 5 类对象（内容 post 含 article/photo/video/micro 四形态、实体主页 entity_homepage、用户 user、圈子 circle、「我」=user 自我视角）建立**统一的对外分享分发能力**：用户从对象详情页打开统一分享面板，把对象以**微信会话/朋友圈原生卡片、海报图（含二维码与口令）、系统分享、复制链接/口令**等渠道分发到站外，吸引点击并可靠回流，全链路携带归因。

本能力是 `external-acquisition-and-deeplink` Journey 的**出站支柱**，与 runtime 域的 `entity-link-templates-metadata`（链接结构）、`external-inbound-deeplink-routing`（入站回流）、`public-content-web-entry`（落地/SEO/中转）形成完整闭环。

## 能力边界

拥有（owns）：

- 统一分享面板与渠道编排（微信朋友圈/微信好友/系统分享/复制链接/复制口令/保存海报/二维码）。
- 5 类对象 × 各渠道的**分享卡视觉与文案设计**（设计师口径：信息层级、配色、缩略图比例、CTA、吸引点击策略）。
- 分享归因（`share_id`/UTM/口令）、口令生成与识别契约、海报渲染规格。
- 登录门策略（复用 `AuthGateReason.shareRecord`）与可见性分级（public/private，未知值 default-deny）。

不拥有（does not own）：

- 链接/深链/中转页**结构定义** → `runtime/entity-link-templates-metadata`。
- 入站唤起/拦截兜底/延迟深链 → `runtime/external-inbound-deeplink-routing`。
- 公开 HTML/SEO 渲染 → `runtime/public-content-web-entry`。
- 各对象**可分享字段**与分享**落库计数** → 各自领域（content/circle/user/entity）。
- 邀请拉新归因奖励主链路 → `user/invite_record` + `product-ops-growth` 既有增长能力（本能力对接其归因维度）。

## 下属 Story（L3）

- `object-share-cards`：5 类对象 × 渠道的卡片视觉与文案设计规格。
- `share-channel-panel`：统一分享面板、渠道编排、登录门、可见性分级。
- `share-attribution-and-token`：分享归因、口令、跨 App（小红书/今日头条）引流落库与识别。

## 约束

- 单一真相源：链接/口令/中转页结构只来自 `_shared/link_templates.yaml`，分享侧不另写 path/scheme。
- 微信原生卡片必须经 `external-inbound-deeplink-routing` 的 `WeChatLaunchBridge`（NativeBridge 防腐），UI 不直连微信 SDK，能力位 `wechatShareAndLaunch` 缺失时降级海报/系统分享。
- 站外默认分享 HTTPS landing（或中转页），App scheme 仅作打开 App 目标（与 `public-content-web-entry` 一致）。
- 设计 token 走 `AppColors/AppSpacing/AppTypography`，文案走 `UITextConstants`/`l10n`，禁止颜色/字号/中文字面量（rule R27）。
- 归因不丢：分享链路携带 `referralSource/share_id/utm`（rule R21/R23）；分享埋点 `shareIntent/shareClick/shareSuccess` 全覆盖（rule R20/R32）。
- 生产纯净：分享面板在 release 默认 Remote 数据源，无 mock 入口（rule R29）。

## 验收标准（SIT 概要）

- A1：5 类对象都能从统一面板分享到微信会话/朋友圈/海报/系统分享/复制，渠道与对象组合无盲区。
- A2：每个渠道生成的卡片/海报/口令携带正确归因，站外点击可回流到对应对象（与 inbound 节点联调）。
- A3：可见性分级正确（private 阻断、public 完整、未知值拒绝），登录门关闭后不死循环（对齐 rule 15）。
- A4：分享归因可在指标大盘按渠道与对象类型统计转化（对接 `analytics-metric-dictionary`）。

详见同目录 `acceptance.yaml` 与 `design.md`。
