# L2 Business Capability：统一发现与聚焦浏览 (`dual-rail-discovery-redesign`)

> 所属领域：[`discovery-content`](../spec.md)
>
> 设计引用：[本层 design.md](./design.md)

## 1. 能力目标

让用户在同一内容流发现图片、视频与文章，进入各自聚焦面后连续浏览、互动并恢复来源上下文；不再以作品/点滴身份拆分内容轨。

## 2. 范围与非目标

### In Scope

- 统一内容流、图片宫格、媒体沉浸、文章阅读及互动回流。
- 保留已有媒体定位、翻页、阅读、评论与返回交互，取消仅服务退役身份的双轨入口。

### Out of Scope

- 对象、Surface、面布局、首页可选 recipe 的定义与能力协商，由 [`content-type-framework`](../content-type-framework/spec.md) 与 [`content-display-consistency`](../content-display-consistency/spec.md) 拥有。
- 永久 HTTP breaking 决定、新 fallback 或新的内容身份。

## 3. Journey / Scenario 贡献

- [`JNY-003 / SCN-007`](../../spec.md#scn-007)
  - 本能力接收：用户选择的可见内容与来源列表上下文。
  - 本能力处理：从统一内容流打开权威目的面，完成媒体浏览、文章阅读与互动。
  - 本能力输出：同一对象的展示、确认后的互动结果和可恢复来源位置。
  - 失败时终态：保留已确认事实及返回动作，不以其他内容或空白成功替代当前失败。

## 4. Story

- [`article-rich-content-blocks`](./article-rich-content-blocks/spec.md)：文章结构化正文与富文内容块。
- [`works-immersive-viewer`](./works-immersive-viewer/spec.md)：媒体与文章聚焦面的翻页、评论、加载恢复与上下文保持。
- [`works-unified-feed`](./works-unified-feed/spec.md)：统一混排流、等高图片宫格、所选媒体定位与返回。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 内容流与聚焦面组合保持对象和状态一致

- 本能力组合统一内容流、媒体聚焦面与文章阅读面，不保留点滴社交轨或退役身份筛选。
- 目的面仅消费云物化结果，列数遵循 canonical SurfaceLayoutPolicy；浏览器壳可复用，但媒体与文章目的面不能互相替代。
- 来源列表、cursor、所选媒体、阅读位置与互动结果在打开、切换和返回时保持一致；实体主页不混入 Post 媒体分页。

<a id="req-002"></a>
### REQ-002 聚焦浏览保留真实媒体与互动体验

- 图片、视频与文章保留各自翻页、播放与阅读位置，具体交互由作品沉浸式浏览器 Story 单点拥有。
- 底部工具栏保留三档响应式动作布局、关注延迟显示（既有 3/5s 策略）与已关注即时显示、从右滑入和尺寸过渡、文字压缩、固定像素渐变遮挡和统一计数；更多打开帖级操作面板，不接助手。
- 筛选只在更多菜单内，不恢复分轨或常驻筛选 Tab；旧分轨 Tab 的呼吸收起不再构成独立交互要求。
- 图片宫格与任意媒体定位打开由统一内容流 Story 承接；评论仍由公开评论入口交接，不恢复毛玻璃评论抽屉。

## 6. 契约与依赖

- 上游能力：[`discovery-content`](../spec.md) 与 [`content-type-framework`](../content-type-framework/spec.md)。
- 跨面状态与布局：[`content-display-consistency`](../content-display-consistency/spec.md)。
- 评论状态：[`publish-comment-reaction`](../publish-comment-reaction/spec.md)。
- 下游能力：本目录直接 Story 及其公开结果。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 统一内容流与聚焦面组合旅程

- GIVEN 真实列表包含图片、视频、纯文字文章与富文图文混排文章，用户已在中段形成列表位置与 cursor。
- WHEN 用户逐项打开出站目的面，进行媒体翻页、文章阅读或评论后返回。
- THEN 各项保持同一对象和来源位置，已确认评论与互动结果回流，不出现按作品/点滴分轨的入口。
- AND 图片与视频使用媒体聚焦面，纯文字与富文文章使用文章阅读面；两者即使共用浏览器壳也不按附件改写目的面。
- AND 图片宫格稳定定位到所选媒体，加载或评论失败保留返回和 canonical 恢复动作，不改跳无关 feed 或伪造成功。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 统一内容流与聚焦面组合证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺当前单轨旅程的真实组合证据；旧轨规格退役不证明列表、媒体定位、阅读与评论回流已完成。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效，并覆盖各 Story 保留的交互要求。
