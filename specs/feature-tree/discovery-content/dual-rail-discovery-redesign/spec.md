# L2 Business Capability：双轨发现体验 (`dual-rail-discovery-redesign`)

> 所属领域：[`discovery-content`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

让用户在“作品”沉浸轨与“点滴”社交轨之间按浏览意图切换，而不是先按图片、视频或文章格式选择入口。

## 2. 范围与非目标

### In Scope

- 统一作品 feed、沉浸浏览器、结构化文章和点滴社交流。

### Out of Scope

- 其他 L2 的事实所有权、metadata schema 与实现施工步骤。

## 3. Journey / Scenario 贡献

- [`JNY-003 / SCN-007`](../../spec.md#scn-007)
  - 本能力接收：该 Scenario 进入本能力边界的已授权主体与 canonical 输入。
  - 本能力处理：让用户在“作品”沉浸轨与“点滴”社交轨之间按浏览意图切换，而不是先按图片、视频或文章格式选择入口。
  - 本能力输出：直属 Story 组合产生的可观察结果与明确失败终态。
  - 失败时终态：保留已确认事实，并返回可恢复的 canonical failure。

## 4. Story



- [`article-rich-content-blocks`](./article-rich-content-blocks/spec.md)：`blocks` 字段变更必须走 metadata → codegen；`.g.dart` 禁止手改。
- [`moment-social-feed`](./moment-social-feed/spec.md)：约束：宫格内图片统一高度（`AspectRatio` 适配）；浏览器无 BackdropFilter 评论 Drawer。
- [`works-immersive-viewer`](./works-immersive-viewer/spec.md)：metadata/codegen/router/UI/test 中无旧三入口残留。
- [`works-unified-feed`](./works-unified-feed/spec.md)：端点必须先在 `service.yaml` 声明，`make verify` → `make codegen` 后方可编写 Repository。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 dual rail discovery redesign 能力 SIT

- 本能力必须组合统一 feed、沉浸浏览器、结构化文章和点滴社交流，保持对象、cursor 与互动状态一致；失败终态必须可区分且不得伪造成功。

<a id="req-002"></a>
### REQ-002 作品（Works）轨：沉浸数字画廊，精品内容，三类媒体（视频/美图/文章）统一垂直分页流

- **作品（Works）轨**：沉浸数字画廊，精品内容，三类媒体（视频/美图/文章）统一垂直分页流
- **作品轨**：服务端混排统一 works-feed，垂直强制分页，Tab 1.5s 呼吸收起，筛选参数化
- 新增 API 端点必须走 `service.yaml` → `make verify` → `make codegen` 流程
- ArticleBlock DTO 变更走 metadata → codegen，禁止手改 `.g.dart` 文件
- 色彩常量必须在 `AppColors` / `AppArticleColors` 中定义，禁止硬编码十六进制
- 字体（思源宋体）必须通过 `pubspec.yaml` 声明，通过 `assets/fonts/` 注册
- **作品底部工具栏**：采用 3 档位响应式 action 布局。
- 关注按钮延迟显示（3/5s）+ 已关注即时显示
- AnimatedSize 从右滑入动画
- 文字压缩策略
- ShaderMask 固定像素渐变遮挡
- 数字 `_formatCount` 统一格式
- 更多按钮开帖级操作面板（不接助手）。

## 6. 契约与依赖

- 上游能力：[`discovery-content`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 dual rail discovery redesign 能力 SIT

- GIVEN 执行“dual rail discovery redesign 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“dual rail discovery redesign 能力”对应动作。
- THEN 作品轨跨图片、视频和文章保持同一浏览器与 cursor，点滴轨保持社交信息密度和就地互动。
- AND 失败终态可区分且不产生伪成功事实。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 dual rail discovery redesign 能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：双轨入口、统一 feed 与沉浸浏览器尚需完整 `spec_ref` 证明跨媒体连续浏览和互动状态一致。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效
