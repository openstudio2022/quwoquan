# L3 Scenario: unified-presentation-model

## 节点定位

- `L1_domain_service`: `discovery-content`
- `L2_business_capability`: `content-type-framework`
- `L3_story`: `unified-presentation-model`

本场景是「内容多形态统一」的**硬前置债务清零**项（Block D · D1）。目标：在内容多形态统一增量开发前，先收敛端侧四套并行的内容展示模型，建立单一只读 presentation model 作为内容消费 surface 的唯一真相源。本场景仅做读侧收敛，不改变发布写链路、不新增持久化字段；若与既往实现冲突，以本规格为准。

## 背景与动机

当前同一篇内容（micro/image/video/article）在四个消费 surface 上各自维护一套展示数据结构与 fallback 逻辑，形成 R24「展示模型碎片化」债务：

1. **feed（发现流）**：`home_multi_form_feed.dart` 直接消费裸 `PostBaseDto` 子类，字段抽取与 fallback 散落在 widget 内。
2. **immersive（沉浸浏览）**：`works_immersive_viewer.dart` 通过 `_rawArticleDataFor` / `_wireMapForPresentation` 自拼 `Map<String, Object?>` 再构造 `ArticleDetailView`，存在裸 Map 中转。
3. **detail（详情页）**：`post_summary_view.dart` 的 `PostSummaryView.fromDto({wire})` + `PostReadUiBundle` / `post_read_projection_facade.dart` 又一套投影。
4. **share（分享卡）**：`content_share_template.dart` 各自的 fallback 抽取。

四套模型导致：同一帖在不同 surface 字段口径/兜底不一致；新增字段（如 A4 交集理由 `IntersectionReason`）需在四处分别接入；`discoveryPresentationWireForPost` 以 `Map<String, dynamic>?` 弱类型穿透（R04 GATE_BLOCK）；任何展示口径修复都要改四处，回归面不可控。

内容多形态统一在 image/video/article/micro 之上还要求"统一对象卡 / 统一交集呈现"，若不先收敛读侧模型，新形态会再叠一套分叉。因此本场景作为其硬前置先行落地。

## 目标用户（间接）

- 跨 surface 浏览同一内容、期望字段口径一致（标题、作者、统计、交集理由、媒体）的终端用户。
- 后续在统一 model 上接入新交集呈现、不想再踩四套分叉的开发者。

## 核心设计原则

### P1. 单一只读真相源

一篇内容在任一消费 surface 上只通过 `ContentSurfaceView` 读取；surface widget 不再各自从 DTO/Map 抽字段。

### P2. 强类型，零裸 Map 穿透

`ContentSurfaceView` 字段强类型；wire 投影由强类型 DTO/投影对象承载，消除 `Map<String, dynamic>` 中转与 `discoveryPresentationWireForPost` 的弱类型返回。

### P3. 字段口径对齐 metadata

`ContentSurfaceView` 的字段集与 fallback 规则对齐 `contracts/metadata/content/**`（`fields.yaml` / `service.yaml` 投影），不引入第二套口径表。

### P4. 媒体类型分支收敛在 model 内

micro/image/video/article 的差异由 `ContentSurfaceView` 内的强类型可选字段 + `contentType` 判别承载（遵循 04-dart-polymorphism：通过契约字段而非 `is/as`），surface widget 只读结果。

### P5. 灰度可回滚

破坏性单轨切换：只保留 `ContentSurfaceView` 投影路径；禁止 feature flag 双读旧投影，旧投影类必须同变更删除（不得 `@Deprecated` 长期并存）。

## 功能范围

### F1. 定义 `ContentSurfaceView` 只读模型

- 覆盖 micro/image/video/article 四媒体类型的统一只读视图。
- 字段至少包含：`postId` / `contentType` / `authorRef`（id/name/avatar）/ `title?` / `body?` / `coverRef?` / `mediaRefs`（图片/视频，强类型）/ `stats`（like/comment/share/view）/ `createdAt` / `intersectionReasons`（承接 A4）/ `referralContext`（position/feedRequestId 透传位，不参与展示）。
- 四媒体差异通过强类型可选字段表达：image→`mediaRefs` 多图；video→单视频 ref + 时长；article→`title`+`coverRef`+`body` 摘要；micro→`body`。

### F2. 强类型 wire 投影

- 新增强类型投影对象（或复用统一 model）替代：immersive 的 `_rawArticleDataFor`/`_wireMapForPresentation` 自拼 Map、detail 的 `PostSummaryView.fromDto({wire})`、share 的 `ContentShareTemplate` 各自 fallback。
- `discoveryPresentationWireForPost` 返回类型由 `Map<String, dynamic>?` 改为强类型（与 D2 接口去裸 Map 协同）。

### F3. 四 surface 接入统一 model

- feed / immersive / detail / share 四 surface 改为消费 `ContentSurfaceView`。
- 接入顺序与 D3 超大文件强拆协同：接入即顺带拆分 `works_immersive_viewer` / `discovery_page` / `home_multi_form_feed`。

### F4. 迁移与回滚

- 只产出 `ContentSurfaceView`；禁止 `unified_surface_view` 双读旧投影。
- 观测：统一 model 字段完整性打点 + surface 渲染异常上报。
- 旧投影类（`PostSummaryView`/`_wireMapForPresentation`/share 模板内 fallback）必须同变更删除。

## 权限边界与数据生命周期

- 本场景为只读收敛，不改变内容可见性、删除/撤销、权限校验语义。
- `仅自己可见` 等可见性约束仍由上游 Repository/后端裁剪决定，`ContentSurfaceView` 仅承载已授权可见字段。
- 不新增持久化字段；如发现需要新增 metadata 字段，另开 metadata-first slice，不在本轮强绑定。

## 对标输入与吸收结论

| 现状 | 结论 |
|------|------|
| feed 裸 DTO 抽字段 | 收敛为 `ContentSurfaceView`，widget 只读 |
| immersive 自拼 `Map<String,Object?>` | 去裸 Map，改强类型投影 |
| detail `PostSummaryView` | 归并入统一 model，旧类 `@Deprecated` |
| share `ContentShareTemplate` fallback | 复用统一 model 字段口径 |
| A4 `IntersectionReasonChip` | 交集理由位在统一 model 上承载，口径不变 |

## 非功能目标

| 指标 | 门槛 |
|------|------|
| 四 surface 同帖字段口径一致 | 100%（local_contract 同源断言） |
| 抽象接口/投影裸 Map 残留 | 0（R04 GATE_BLOCK 清零） |
| 接入后现有 widget 测试回归 | 0 回归 |
| 切换回滚 | feature flag 单独可回退，旧路径仍可读 |

## 灰度、迁移与回滚

- 灰度：`unified_surface_view` flag 控制四 surface 逐个切换。
- 迁移：旧投影路径并行保留兜底，逐 surface 切到统一 model。
- 回滚：flag 关闭即回退旧投影；旧类未删除前回滚无数据损失。

## Out of Scope

- 不改发布/编辑写链路与持久化结构。
- 不新增 metadata 持久化字段。
- 不动 pageflip 受控文件 `article_read_only_book_deck.dart`。

## 约束

- 遵循 13-coding-discipline R04（去弱类型）/ R24（抽象克制，单一真相源）/ R03（拆超大文件）。
- 遵循 04-dart-polymorphism：媒体类型分支用 `contentType` 契约字段，禁止对 DTO 子类 `is/as/whereType`。
- 进入 `/dev` 前 `spec.md` / `acceptance.yaml` / CR 必须同步完成；设计约束引用上层 L2 design。

## 验收重点

1. `ContentSurfaceView` 已定义并覆盖四媒体类型，字段对齐 metadata。
2. 四 surface（feed/immersive/detail/share）均消费统一 model，无各自投影分叉。
3. 抽象接口与投影无 `Map<String, dynamic>` 穿透（`discoveryPresentationWireForPost` 已强类型化）。
4. local_contract 投影契约 + local_contract 四 surface 同源 widget 测试通过；旧投影类已 `@Deprecated`。
5. 单轨投影、观测与回滚边界已就绪（无旧投影并存）。
6. 接入顺带完成三超大文件强拆，现有测试无回归。
