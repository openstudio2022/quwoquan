# L3 Story：统一呈现模型 (`unified-presentation-model`)

> 所属能力：[`content-type-framework`](../spec.md)

> Journey / Scenario：[`JNY-004 / SCN-001`](../../../spec.md#scn-001)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为浏览或创作内容的用户，
我希望让同一作品在内容流、主页和沉浸式浏览器保持标题、媒体、作者与互动语义一致，
从而在跨页面浏览时始终识别同一内容。

## 2. 范围与非目标

### In Scope

- “统一呈现模型”的输入、可观察主路径、失败语义以及与父能力的交接。
- 单一只读 presentation model ContentSurfaceView（micro/image/video/article 四媒体类型）
- 单一映射器 ContentSurfaceViewMapper（含 fromArticleDetailPayload 富渲染桥接）
- feed / detail / immersive / share 四 surface 统一消费 ContentSurfaceView。
- 删除旧投影类 PostSummaryView / projectPostMap / _shareSeedForPost 与 unified_surface_view flag。
- 发布/编辑写链路与持久化字段（仅读侧收敛）

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 统一呈现模型

- retired_terms / dart_semantic / mock_isolation 门禁绿，app 门禁无 FAIL/BLOCK。

<a id="req-002"></a>
### REQ-002 硬切收尾——旧投影类与迁移 flag 删除，无双读共存

- retired_terms / dart_semantic / mock_isolation 门禁绿，app 门禁无 FAIL/BLOCK。

<a id="req-003"></a>
### REQ-003 后续在统一 model 上接入新交集呈现、不想再踩四套分叉的开发者

- 后续在统一 model 上接入新交集呈现、不想再踩四套分叉的开发者。
- 覆盖 micro/image/video/article 四媒体类型的统一只读视图。
- 新增强类型投影对象（或复用统一 model）替代：immersive 的 `_rawArticleDataFor`/`_wireMapForPresentation` 自拼 Map、detail 的 `PostSummaryView.fromDto({wire})`、share 的 `ContentShareTemplate` 各自 fallback。
- 只产出 `ContentSurfaceView`；禁止 `unified_surface_view` 双读旧投影。
- 观测：统一 model 字段完整性打点 + surface 渲染异常上报。
- 旧投影类（`PostSummaryView`/`_wireMapForPresentation`/share 模板内 fallback）必须同变更删除。
- 迁移：旧投影路径并行保留兜底，逐 surface 切到统一 model。
- 遵循 04-dart-polymorphism：媒体类型分支用 `contentType` 契约字段，禁止对 DTO 子类 `is/as/whereType`。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 统一呈现模型

- GIVEN 内容创作者或浏览者具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“统一呈现模型”对应的公开行为。
- THEN retired_terms / dart_semantic / mock_isolation 门禁绿，app 门禁无 FAIL/BLOCK。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`content-type-framework`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
