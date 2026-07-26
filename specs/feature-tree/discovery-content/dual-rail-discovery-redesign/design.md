# L2 Design：双轨发现体验 (`dual-rail-discovery-redesign`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“让用户在“作品”沉浸轨与“点滴”社交轨之间按浏览意图切换，而不是先按图片、视频或文章格式选择入口”需要 `article-rich-content-blocks`、`moment-social-feed`、`works-immersive-viewer`、`works-unified-feed` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：让用户在“作品”沉浸轨与“点滴”社交轨之间按浏览意图切换，而不是先按图片、视频或文章格式选择入口。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`article-rich-content-blocks`](./article-rich-content-blocks/spec.md)：`blocks` 字段变更必须走 metadata → codegen；`.g.dart` 禁止手改。
- [`moment-social-feed`](./moment-social-feed/spec.md)：约束：宫格内图片统一高度（`AspectRatio` 适配）；浏览器无 BackdropFilter 评论 Drawer。
- [`works-immersive-viewer`](./works-immersive-viewer/spec.md)：metadata/codegen/router/UI/test 中无旧三入口残留。
- [`works-unified-feed`](./works-unified-feed/spec.md)：端点必须先在 `service.yaml` 声明，`make verify` → `make codegen` 后方可编写 Repository。

## 3. 端云与数据流

- 上游能力：[`discovery-content`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 以浏览气质分轨而非媒体格式分栏
- 决策：以浏览气质分轨而非媒体格式分栏。
- 理由：让用户在“作品”沉浸轨与“点滴”社交轨之间按浏览意图切换，而不是先按图片、视频或文章格式选择入口。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`article-rich-content-blocks`](./article-rich-content-blocks/spec.md)、[`moment-social-feed`](./moment-social-feed/spec.md)、[`works-immersive-viewer`](./works-immersive-viewer/spec.md)、[`works-unified-feed`](./works-unified-feed/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 观测首屏、下一页、viewer 切换、媒体 ready、文章分页和互动同步延迟。
- 作品轨保持低视觉疲劳和连续垂直翻页；点滴轨优先信息密度与就地互动。
- 布局、色彩和字体使用 App token/asset，不在页面硬编码主题常量。
