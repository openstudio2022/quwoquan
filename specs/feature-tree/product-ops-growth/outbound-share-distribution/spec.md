# L2 Business Capability：对外分享分发 (`outbound-share-distribution`)

> 所属领域：[`product-ops-growth`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

5 类对象统一对外分享分发（微信卡片/海报/口令/系统分享），携带归因并可靠回流。

## 2. 范围与非目标

### In Scope

- 由本目录 Story 组合交付“outbound-share-distribution（对外分享分发）”的独立业务结果。

### Out of Scope

- 链接/深链/中转页结构定义（runtime/entity-link-templates-metadata）。
- 入站唤起/拦截兜底/延迟深链（runtime/external-inbound-deeplink-routing）。
- 公开 HTML/SEO 渲染（runtime/public-content-web-entry）。
- 第三方票务、酒店或旅游商品的交易、预订与 CPS 联盟导购；本能力只拥有站内对象的对外分享和归因，不承诺外部交易能力。

## 3. Journey / Scenario 贡献

- [`JNY-010 / SCN-023`](../../spec.md#scn-023)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：5 类对象统一对外分享分发（微信卡片/海报/口令/系统分享），携带归因并可靠回流，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。

## 4. Story



- [`object-share-cards`](./object-share-cards/spec.md)：海报渲染快照覆盖 5 类对象差异化主视觉与二维码/口令区。
- [`share-attribution-and-token`](./share-attribution-and-token/spec.md)：口令、二维码与短链必须解析到同一目标与归因上下文。
- [`share-channel-panel`](./share-channel-panel/spec.md)：用户关闭登录后不循环弹窗；登录成功后续接原分享渠道。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 5 类对象对外分享分发端云一致闭环

- 5 类对象 × 渠道（微信会话/朋友圈/海报/系统分享/复制链接/复制口令）组合可用且无盲区。
- 各渠道物料携带 share_id/utm 归因，与入站节点联调可回流到对应对象。
- 可见性分级与登录门行为正确。
- 分享归因可在指标大盘按渠道与对象类型统计转化。

<a id="req-002"></a>
### REQ-002 统一分享面板与渠道编排（微信朋友圈/微信好友/系统分享/复制链接/复制口令/保存海报/二维码）

- 统一分享面板与渠道编排（微信朋友圈/微信好友/系统分享/复制链接/复制口令/保存海报/二维码）。
- `share-channel-panel`：统一分享面板、渠道编排、登录门、可见性分级。
- 微信原生卡片必须经 `external-inbound-deeplink-routing` 的 `WeChatLaunchBridge`（NativeBridge 防腐），UI 不直连微信 SDK，能力位 `wechatShareAndLaunch` 缺失时降级海报/系统分享。
- 设计 token 走 `AppColors/AppSpacing/AppTypography`，文案走 `UITextConstants`/`l10n`，禁止颜色/字号/中文字面量（rule R27）。
- 5 类对象都能从统一面板分享到微信会话/朋友圈/海报/系统分享/复制，渠道与对象组合无盲区。

## 6. 契约与依赖

- 上游能力：[`product-ops-growth`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 5 类对象对外分享分发端云一致闭环

- GIVEN 执行“5 类对象对外分享分发端云一致闭环”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“5 类对象对外分享分发端云一致闭环”对应动作。
- THEN 5 类对象 × 渠道（微信会话/朋友圈/海报/系统分享/复制链接/复制口令）组合可用且无盲区。
- THEN 各渠道物料携带 share_id/utm 归因，与入站节点联调可回流到对应对象。
- THEN 可见性分级与登录门行为正确。
- THEN 分享归因可在指标大盘按渠道与对象类型统计转化。

## 8. 开放事项

<a id="open-002"></a>
### OPEN-002 5 类对象对外分享分发端云一致闭环

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：5 类对象 × 渠道（微信会话/朋友圈/海报/系统分享/复制链接/复制口令）组合可用且无盲区。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效
