# L2 Design：统一发现与聚焦浏览 (`dual-rail-discovery-redesign`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“让统一内容流与媒体、文章聚焦面共享对象与互动事实，取消退役身份分轨而保留有效浏览交互”需要 `article-rich-content-blocks`、`works-immersive-viewer`、`works-unified-feed` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：让统一内容流与媒体、文章聚焦面共享对象与互动事实，取消退役身份分轨而保留有效浏览交互。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`article-rich-content-blocks`](./article-rich-content-blocks/spec.md)：`blocks` 字段变更必须走 metadata → codegen；`.g.dart` 禁止手改。
- [`works-immersive-viewer`](./works-immersive-viewer/spec.md)：共享浏览器壳承载不同聚焦面，保留翻页、阅读与评论交接，不使用 BackdropFilter 评论 Drawer。
- [`works-unified-feed`](./works-unified-feed/spec.md)：统一混排流承接等高图片宫格、任意媒体定位打开与返回上下文。

## 3. 端云与数据流

- 上游能力：[`discovery-content`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 统一内容流按权威目的面进入聚焦浏览

- 决策：复用 [`content-type-framework DEC-004/005`](../content-type-framework/design.md#dec-004) 的单字段投影和云物化目的面，以及 [`content-display-consistency DEC-002/003`](../content-display-consistency/design.md#dec-002) 的 Surface 与布局边界；本能力只拥有浏览会话交接，不创建第二份身份或布局表。
- 理由：相同 Post 的互动和媒体事实不因列表或聚焦面变化而产生新身份；浏览器壳复用不等于媒体与文章目的面合并。
- 被否决方案：保留作品/点滴双轨、从附件嗅探内容形态、用兼容目的面替换真实目的面、保留旧投影作兜底。
- 约束与影响：等高宫格与所选媒体定位由统一内容流拥有；媒体位置、阅读、评论交接和返回由浏览器 Story 拥有。评论沿既有上压分屏，不使用毛玻璃 Drawer；原 pageflip 几何主线与有效交互不随旧轨删除。
- 测试与恢复：真实列表到聚焦面的测试锁定所选对象/媒体、cursor、评论结果及返回位置；缺失投影或加载失败仅保留 canonical 恢复，不改跳另一 feed。接口或能力未就绪时保留 OPEN，禁止回滚到旧身份双读。
- 关联要求：`REQ-001`、`REQ-002`
- 影响 Story：[`article-rich-content-blocks`](./article-rich-content-blocks/spec.md)、[`works-immersive-viewer`](./works-immersive-viewer/spec.md)、[`works-unified-feed`](./works-unified-feed/spec.md)
- 关联验收：`SIT-001`、[`统一流 GWT-002`](./works-unified-feed/spec.md#gwt-002)、[`浏览器 GWT-021`](./works-immersive-viewer/spec.md#gwt-021)

<a id="dec-002"></a>
### DEC-002 pageflip 单一几何主线与作品浏览归属

- 决策：文章与图片书共用一条 pageflip 几何主线；基础几何和文章翻页实现都归属到本能力的 `works-immersive-viewer` Story，不由全局规则、Review 角色或 harness adapter 复制功能事实。
- 影响 Story：[`works-immersive-viewer`](./works-immersive-viewer/spec.md)
- 关联要求：`REQ-003`、`REQ-009`、`REQ-011`、`REQ-016`、`REQ-017`、`REQ-018`、`REQ-019`、`REQ-020`、`REQ-021`
- 几何不变量：单指手势先锁定水平方向，纵向意图交还父级。任意帧只允许一个 moving leaf、一条 seam/fold 和一条 free edge。commit 在应用 animation plan 最后一帧后才能同步 `completeAnimation` 与 page index；cancel 保持当前索引。
- 坐标投影：spread spine 固定为 `bounds.left + bounds.width / 2`。portrait 单页的 `bounds.width = 2 * pageWidth`，可见页左边缘是 `bounds.left + pageWidth`，不得把负值 `bounds.left` 当成可见边缘。book point 投影到 viewport 时，forward 使用 `bounds.left + bounds.width / 2 + point.dx`，BACK 使用 `bounds.left + bounds.width / 2 - point.dx`。
- BACK 视觉输入：页面绑定、提交与 suppression 始终保持 semantic `direction == back`，portrait 视觉几何使用 `visualGeometryDirection == forward`。visual replay 采用反向时间，并允许 X 在 `-pageWidth..pageWidth` 单调推进；不得裁成 `0..pageWidth`。
- 局部裁剪：forward 的 sheet-local X 为 `point.dx - anchor.dx`，BACK 为 `anchor.dx - point.dx`。portrait Route-B 的 recto/front 与 verso/back 必须由同一 canonical moving-sheet polygon 互补切分；landscape/fallback 仍消费原生 BACK 分支。
- BACK 主路径：文章 portrait BACK 固定使用 Route-B：L0 是完整 current/right underlay，L1 是唯一 previous moving leaf，并在同一 `Positioned + Transform.rotate + ClipPath` surface 内按 `ArticlePageBackwardLeafFrame` 切分 recto/front 与 verso/back。禁止 previous-front page-space replacement、独立 front/back 平面或额外 moving sheet。
- 页面与诊断绑定：`bottomLayerPageIndex == currentPageIndex`，`flippingLayerPageIndex == currentPageIndex - 1`；recto/verso 绑定 flipping index，bottom 绑定 current index。`flippingClipArea/bottomClipArea`、anchor/angle、fold/free-edge、face partition 与诊断字段必须直接派生自同一 calculation/frame/resolver，诊断不得反向成为绘制真相源。
- 几何验收：BACK previous moving sheet 必须与 visible current page 形成正面积交集，且不能整体落在当前页左边界之外；动画后段同时存在正面积 recto、verso 与 current 三个互不冒充的可见分区。
- 材质与加载：图片 moving sheet 每帧只绘制一张完整页面的 front 或 back 材质；禁止重叠纹理子页、压缩子纹理、重复完整纹理起点，也不得以黑色舞台填补本应由背面材质覆盖的区域。加载/失败状态冻结到落平后首个静态帧，再应用排队状态。
- 边界：不抽取新 DeckHost、painter、partition 或通用纹理类型，不新建文章翻页主线、诊断坐标链或改写同步 `completeAnimation` 时序。图片展示层位于 `components/media/image/book/`，只接收 URL 列表、页码回调和边界 overflow 回调，不依赖 discovery/content DTO、Riverpod provider、GoRouter 或 `ui/**`。
- 降级与体验：Reduce Motion 下不显示动态翻页层，但仍原子切换页面。失败保留返回和可恢复动作。
- 页码与 chrome：浏览器不因媒体类型改变深色沉浸背景，系统层、媒体层与文章纸张内页尾的页码边界由 Story `REQ-003` 单点声明。不得显示媒体类型标识或常驻筛选 Tab，也不回退到 rubber-band `PageView` 主体验。
- 关联验收：`GWT-003`、`GWT-010`、`GWT-015`、`GWT-016`、`GWT-017`、`GWT-018`、`GWT-019`、`GWT-020`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 观测首屏、下一页、viewer 切换、媒体 ready、文章分页和互动同步延迟。
- 统一内容流保持信息密度与可预测打开行为，聚焦面保持低视觉疲劳与连续浏览；两者不再绑定退役内容身份。
- 布局、色彩和字体使用 App token/asset，不在页面硬编码主题常量。
