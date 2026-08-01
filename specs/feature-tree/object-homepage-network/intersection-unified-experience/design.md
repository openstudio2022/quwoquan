# L2 Design：交集统一体验与推荐 (`intersection-unified-experience`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“以统一的交集事实、置信度、保鲜期和展示契约驱动发现、对象主页、圈子、聊天、个人主页与助理场景”需要 `circle-homepage-intersection-redesign`、`entity-homepage-intersection-redesign`、`home-recommend-intersection-redesign`、`intersection-algorithm-closure`、`intersection-sentence-unification`、`object-homepage-gamma-real-data-closure`、`user-profile-intersection-redesign` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：以统一的交集事实、置信度、保鲜期和展示契约驱动发现、对象主页、圈子、聊天、个人主页与助理场景。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`circle-homepage-intersection-redesign`](./circle-homepage-intersection-redesign/spec.md)：标题统一为「圈子打动的人」，文案口径与 `intersection_kind_registry.yaml` 登记的 kind / dimension / actionHint 口径一致。
- [`entity-homepage-intersection-redesign`](./entity-homepage-intersection-redesign/spec.md)：定义“实体主页交集重做”的可观察主路径、失败语义及父能力交接。
- [`home-recommend-intersection-redesign`](./home-recommend-intersection-redesign/spec.md)：spotlight 文案口径与 `intersection_kind_registry.yaml` 登记的 kind / dimension / actionHint 口径一致。
- [`intersection-algorithm-closure`](./intersection-algorithm-closure/spec.md)：ranking-signal-fusion spec 登记 intersection fact/affinity 权重入口。
- [`intersection-sentence-unification`](./intersection-sentence-unification/spec.md)：seed、服务响应与展示口径均与 `intersection_kind_registry.yaml` 及本 Story Display Contract 一致。
- [`object-homepage-gamma-real-data-closure`](./object-homepage-gamma-real-data-closure/spec.md)：metadata 与 compose 静态契约通过。
- [`user-profile-intersection-redesign`](./user-profile-intersection-redesign/spec.md)：他人/我的主页二级过滤同一实现。

## 3. 端云与数据流

- 上游能力：[`object-homepage-network`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 把交集的展示与推荐统一到一套契约和一组共享组件上
- 决策：把交集的展示与推荐统一到一套契约和一组共享组件上。
- 理由：以统一的交集事实、置信度、保鲜期和展示契约驱动发现、对象主页、圈子、聊天、个人主页与助理场景。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`circle-homepage-intersection-redesign`](./circle-homepage-intersection-redesign/spec.md)、[`entity-homepage-intersection-redesign`](./entity-homepage-intersection-redesign/spec.md)、[`home-recommend-intersection-redesign`](./home-recommend-intersection-redesign/spec.md)、[`intersection-algorithm-closure`](./intersection-algorithm-closure/spec.md)、[`intersection-sentence-unification`](./intersection-sentence-unification/spec.md)、[`object-homepage-gamma-real-data-closure`](./object-homepage-gamma-real-data-closure/spec.md)、[`user-profile-intersection-redesign`](./user-profile-intersection-redesign/spec.md)
- 关联验收：`SIT-001`

<a id="dec-002"></a>
### DEC-002 垂类扩展只允许「vertical + objectKind + taxonomy 子树 + 事实生产者」四件套

- 决策：新增一个垂类 = 注册一个 `vertical` 值 + 注册若干 `objectKind`（每个必须映射到已有 homepage 类型或已有对象，且 `routeId` 在 `app_routes.yaml` 真实存在）+ 建一棵 taxonomy 子树 + 建一个事实生产者（把原始素材或行为转成 tagRef 与对象引用）。**禁止新增 kind、dimension、actionKey，禁止端侧引入任何垂类分支。**
- 理由：`kind + vertical + objectKind` 是正交三元组。垂类的差异化应体现在**事实的丰富度**，而不是结构分叉。一旦为垂类开 kind，同一件事就有 general 与垂类两套句子与两套排序权重（第二真相源），并且端侧不得不按 `vertical` 分叉渲染，垂类数量与端侧分支数线性绑定。
- 推论：旅行摄影**零新 kind**，三类事实各自归位到已登记的通用 kind 或推荐通道。
  - 同地到访 = 已登记的 `coVisitedEntity` / `followeeVisited`，只缺 `post.visitedAt` + `geoTagRef` 生产者，不缺 kind。
  - 器材 / 焦段 / 曝光参数**不做成交集句**，只作为作者可控披露、推荐解释与内容理解事实。`gear` objectKind 只保留既有 homepage 结构能力，不因 EXIF 自动生成交集。
  - 光线条件进入画面氛围语义轴；它可以参与推荐与内容理解，但仍不得作为不可导航 tag 生成交集主句。上述事实统一登记在 `recommendationOnlyFacts`。
- 被否决方案：为旅行摄影新增 `sameGearUsed` / `sharedPhotoSpot` / `sameLightWindow` 等 `travel.*` 私有 kind；或在端侧按 `vertical` 分支渲染垂类专属卡片与专属页面。
- 约束与影响：契约与四条禁令（`forbidNewKind` / `forbidNewDimension` / `forbidNewActionKey` / `forbidClientVerticalBranch`）登记在 `intersection_kind_registry.yaml` 的 `verticalExtensionContract`，事实生产者只引用同文件 `factProducerShapes` 的受控输入与输出 shape，并由 `verify_intersection_kind_registry.py` 阻断自由文本生产者、recommendation-only 事实回流成交集句和当前 kind 缺模板。端侧 `IntersectionTargetNavigator` 只按生成的当前 `actionKeyMeta.dispatch` 闭集分发。
- 关联要求：`REQ-005`
- 影响 Story：[`intersection-algorithm-closure`](./intersection-algorithm-closure/spec.md)、[`intersection-sentence-unification`](./intersection-sentence-unification/spec.md)
- 关联验收：`SIT-005`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 冷却窗口与保鲜期交叉：以 `policy.yaml` 单一真相源配置，避免双处硬编码。
- 隐私门槛：`commonContact` 必须先过双向可见性才产出。
- 性能与容量弹性（冷热三档，云侧部分后置）
