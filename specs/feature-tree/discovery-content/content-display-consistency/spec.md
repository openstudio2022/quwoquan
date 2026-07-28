# L2 Business Capability：内容展示一致性 (`content-display-consistency`)

> 所属领域：[`discovery-content`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

统一文章、圈子流、沉浸式浏览器与作者主页之间的展示和状态交接

## 2. 范围与非目标

### In Scope

- 由本目录 Story 组合交付“content-display-journey-consistency”的独立业务结果。

### Out of Scope

- 其他 L2 的事实所有权、metadata schema 与实现施工步骤。

## 3. Journey / Scenario 贡献

- [`JNY-003 / SCN-007`](../../spec.md#scn-007)
  - 本能力接收：该 Scenario 进入本能力边界的已授权主体与 canonical 输入。
  - 本能力处理：统一文章、圈子流、沉浸式浏览器与作者主页之间的展示和状态交接。
  - 本能力输出：直属 Story 组合产生的可观察结果与明确失败终态。
  - 失败时终态：保留已确认事实，并返回可恢复的 canonical failure。

## 4. Story



- [`article-display-journey`](./article-display-journey/spec.md)：整个卡片为统一热区，点击直接进入文章沉浸式阅读器。
- [`circle-feed-viewer-handoff-contract`](./circle-feed-viewer-handoff-contract/spec.md)：圈子 post 进入 viewer 时必须传入。
- [`content-action-intent-contract`](./content-action-intent-contract/spec.md)：更多操作面板只展示已具备真实结果或安全终态的能力；禁止“功能开发中”假入口。
- [`feed-item-dto-contract`](./feed-item-dto-contract/spec.md)：`generated/content/feed_item_dto.g.dart` 标记 `// Code generated ... DO NOT EDIT.`，禁止手改。
- [`moment-display-journey`](./moment-display-journey/spec.md)：**行为基线**：作品侵入式浏览器作为统一行为基线；微趣点击图片/视频后进入同等交互能力的侵入式浏览器。
- [`photo-display-journey`](./photo-display-journey/spec.md)：让图片频道、沉浸式浏览器与作者主页使用同一内容身份和互动状态，并在返回时保持上下文。
- [`video-display-journey`](./video-display-journey/spec.md)：首页/视频频道/作品浏览器的同一视频 post 未播放态封面一致，点击后能进入同一 `videoUrl` 的播放态。
- [`viewer-profile-state-sync-contract`](./viewer-profile-state-sync-contract/spec.md)：viewer、profile 与 feed 消费同一 canonical `RelationshipCapabilityView` 关系矩阵。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 内容展示一致性能力组合结果

- 本能力必须组合直属 Story 与公开契约，交付“统一文章、圈子流、沉浸式浏览器与作者主页之间的展示和状态交接”所定义的业务结果；失败终态必须可区分且不得伪造成功。

<a id="req-002"></a>
### REQ-002 两类来源进入媒体浏览器或文章阅读器时都必须传入

- 两类来源进入媒体浏览器或文章阅读器时都必须传入：
- 内部用户 canonical key 统一为 `ProfileSubjectId`。
- post 作者引用统一为 `authorProfileSubjectId`。
- feed、viewer、profile 共用统一 provider 同步关系态与互动状态。
- 图片、视频、微趣、文章进入浏览器/阅读器后，标题（可选）和正文（可选）必须与对应 post 展示一致。
- Web 精品不恢复独立「精品队列」hero/rail；当前商用口径为复用发现内容流的宽屏多列墙 + 统一 `workBrowser` 落点。
- alpha/beta/gamma/prod composition 的所有对象级 Query/Command port 只装配 Remote adapter；typed double 仅存在测试树，代码图、runner 与 UAT support 不得保留 fixture override 或运行时 Mock/Remote 切换。
- 运行时同步参数属于 `sys.*`，不得落到 `ops.*`、业务 feature flag 或 `ui_config.yaml`。
- Web 内容区复用 `HomeMultiFormFeed` 宽屏多列墙；post 点击统一调用 `openHomeFeedPost(...)`，进入 `AppRoutePaths.workBrowser(...)` 与 `WorksImmersiveViewer`。
- 禁止回退到旧「精品队列」hero/rail、右侧说明 rail 或独立精品壳；建立独立 Web 精品容器前必须先更新本 L2 规格、页面契约和测试。

## 6. 契约与依赖

- 上游能力：[`discovery-content`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 content display journey consistency 能力 SIT

- GIVEN 执行“content display journey consistency 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“content display journey consistency 能力”对应动作。
- THEN 直属 Story 共同交付“统一文章、圈子流、沉浸式浏览器与作者主页之间的展示和状态交接”，失败终态可区分且不产生伪成功事实。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 content display journey consistency 能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：统一文章、圈子流、沉浸式浏览器与作者主页之间的展示和状态交接。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效
