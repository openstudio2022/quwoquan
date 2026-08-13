# L2 Design：内容类型框架 (`content-type-framework`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“**定位**：content_feed 场景下对四种媒体类型（微趣 micro、图片 image、视频 video、文章 article）的通用内容模型与按类型扩展的约定，不拆表、不拆场景”需要 `creation-mode-and-surface-ia-unification`、`creation-tagging-ia`、`markdown-article-kernel`、`unified-presentation-model` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：**定位**：content_feed 场景下对四种媒体类型（微趣 micro、图片 image、视频 video、文章 article）的通用内容模型与按类型扩展的约定，不拆表、不拆场景。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`creation-mode-and-surface-ia-unification`](./creation-mode-and-surface-ia-unification/spec.md)：用户只需要在入口选择开始动作，系统能根据真实媒体结果进入图片或视频编辑状态，且发布 payload 的 `contentType` 与最终媒体类型一致。
- [`creation-tagging-ia`](./creation-tagging-ia/spec.md)：各类型编辑页提供可选标签，未选择标签不得阻断发布。
- [`markdown-article-kernel`](./markdown-article-kernel/spec.md)：小屏或可访问性大字号下统一降级为 `fullWidth`。
- [`unified-presentation-model`](./unified-presentation-model/spec.md)：retired_terms / dart_semantic / mock_isolation 门禁绿，app 门禁无 FAIL/BLOCK。

## 3. 端云与数据流

- 上游能力：[`discovery-content`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 四类内容共用 Post 生命周期并按 contentType 扩展策略
- 决策：四类内容共用 Post 生命周期并按 contentType 扩展策略。
- 理由：**定位**：content_feed 场景下对四种媒体类型（微趣 micro、图片 image、视频 video、文章 article）的通用内容模型与按类型扩展的约定，不拆表、不拆场景。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`creation-mode-and-surface-ia-unification`](./creation-mode-and-surface-ia-unification/spec.md)、[`creation-tagging-ia`](./creation-tagging-ia/spec.md)、[`markdown-article-kernel`](./markdown-article-kernel/spec.md)、[`unified-presentation-model`](./unified-presentation-model/spec.md)
- 关联验收：`SIT-001`

<a id="dec-002"></a>
### DEC-002 创作工作台壳层使用 CupertinoPageScaffold 而非 AppScaffold

- 决策：`CreatePage`（`content.create`）壳层保留 `CupertinoPageScaffold` + 页面内自建透明
  `Material` ancestor，不收敛到 `AppScaffold`。
- 理由：创作工作台是 iOS 原生沉浸编辑面（全屏编辑器、键盘联动工具条、Cupertino 导航语义），`CupertinoPageScaffold` 是 iOS 语义 v1 的正确基座；`AppScaffold` 面向常规内容页的
  统一 chrome（顶栏/背景/安全区约定），对编辑器场景反而引入多余层级。页面横向质量矩阵
  对壳层的要求以「语义 token + 双模式 + 安全区正确」为准，不强制单一 Widget 基座。
- 被否决方案：把 `CreatePage` 包进 `AppScaffold`（多余 chrome 层且破坏编辑器沉浸布局）；为编辑器新建第三种页面壳（违反材质单层单义与壳层单轨）。
- 约束与影响：`CreatePage` 及其 embedded 子页（排版预览、选圈、选位置）继续满足
  design token、双模式、44×44 热区与 i18n 约束；透明 Material ancestor 只允许由
  `CreatePage` 壳层提供一次，子组件不得再自建。
- 关联要求：`REQ-001`
- 影响 Story：[`creation-mode-and-surface-ia-unification`](./creation-mode-and-surface-ia-unification/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 引擎已按 ContentType 做 maxPerType；运营可配置「各类型占比/上下限」，由通用 pipeline 读取配置并按 contentType 执行。
- 按 contentType 配置不同规则（如视频先审、文章敏感词+人工抽检）。
- 运营配置「content_feed 各类型占比/上下限」，引擎多样性层已具备 typeCount，将配置与 maxPerType 等参数打通。
- 「仅视频专区」「仅文章专题」等在编排层或 feed 配置中按 contentType 过滤/加权即可。
