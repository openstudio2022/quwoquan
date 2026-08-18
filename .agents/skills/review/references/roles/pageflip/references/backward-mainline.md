# Pageflip Backward Mainline (Native BACK)

BACK 方向的强收紧版，覆盖本角色（pageflip）的通用几何军规；两者冲突以本文件为准。

适用路径：`quwoquan_app/lib/design_system/pageflip/**`、
`quwoquan_app/lib/service/content_service/content/post/presentation/article_reader/pageflip/**`、
`quwoquan_app/test/**/pageflip/**`。

几何推导（spread 投影公式、forward/BACK calc 差异、portrait 单页几何契约、视觉契约）见
[geometry.md](geometry.md)。动手改 BACK 几何前必须先读。

## 主线定义（Route B 三层组合）

后翻 BACK 主线只允许如下层级（最底层 → 最顶层）：

1. **L0 current/right underlay** — 当前页保持完整可见；若保留 `bottomClipArea` 诊断，
   必须与真实 BACK sheet 同源，不能制造左侧小竖条。
2. **L1 flipping sheet** — `pages[flippingPageIndex]` 的 moving sheet，按 BACK calc 原始
   `flippingClipArea / activeCorner / angle` 走 StPageFlip 原生 BACK soft transform，
   并在同一个 soft surface 内裁出 recto/front 与 verso/back。

L1 内部分段是**同一张纸的分段**，不是新增独立平面：

- **recto/front** — 来自 `ArticlePageBackwardLeafFrame.sheetRectoCoverageNormalized`，
  由 canonical fold/free-edge 几何沿 material-space 方向切分，在 spine side 显示
  `pages[flippingPageIndex]` front。
- **verso/back** — 同一 canonical moving-sheet polygon 的互补分区，显示同一 index 的 back。
- 两者共享同一个外层 `Positioned + Transform.rotate + ClipPath(frame.flippingClipArea)`，
  内部通过 `resolveBackwardCanonicalSheetFaces` 对同一 sheet-local polygon 做互补 `ClipPath`。

层角色固定：`bottomLayerPageIndex == currentPageIndex`，
`flippingLayerPageIndex == currentPageIndex - 1`。

## 真相源（不可绕过）

| 数据 | 唯一真相源 | 消费者 |
|---|---|---|
| `flippingClipArea` / `bottomClipArea` | `StPageFlipCalculation(BACK).getFlippingClipArea()` / `getBottomClipArea()` | `renderFrame.flippingClipArea` / `bottomClipArea` |
| `anchor` / `angle` | `StPageFlipCalculation(BACK).getActiveCorner()` / `getAngle()` | `renderFrame.flippingAnchor` / `angle` |
| BACK viewport position | `convertBookPointToViewport(anchor, bounds, direction: back)` | `_buildSoftPageLayer` / diagnostics |
| BACK local clip | `Offset(anchor.dx - point.dx, point.dy - anchor.dy)` | `_localPolygonFromArea` / diagnostics |
| `foldLine` / `projectedRightEdgeLine` | BACK calc `canonicalFoldGeometry` | `ArticlePageBackwardProjectedFrame`（诊断） |
| recto/verso material 分区 | `sheetRectoCoverageNormalized` + `resolveBackwardCanonicalSheetFaces` | `_buildSoftFlippingPageSurface` / `_resolveBackwardDiagnosticGeometry` |

## MUST

gate: `make verify-app-pageflip-back-mainline`

- `backward_render_frame_builder.dart` 在 portrait BACK 下构造 forward-isomorphic visual
  geometry：`direction == back`、`renderDirection == back`、`visualGeometryDirection == forward`。
- portrait BACK visual calculation 消费 `resolveBackwardVisualReplayLocalPagePoint`，
  **不是** `resolveBackwardReplayLocalPagePoint`。
- `resolveBackwardVisualReplayCanonicalPoint` 以 `-pageWidth` 为 BACK start 的 visual X 起点，
  随拖拽单调推进到 `pageWidth`。
- `_localPolygonFromArea` 同时保留 `anchor.dx - point.dx`（BACK）与
  `point.dx - anchor.dx`（forward）两个分支——前者是 StPageFlip 原生 `drawSoft` 语义，
  landscape / fallback BACK 仍依赖它。
- `_buildSoftFlippingPageSurface` 的 BACK 分支接收 `ArticlePageBackwardLeafFrame` 并调用
  `resolveBackwardCanonicalSheetFaces`；diagnostics 的 `previousFrontLocalPolygon` /
  `previousBackLocalPolygon` 调用同一 resolver 同源输出。
- host soft layer 按 `visualGeometryDirection` 消费 `clip/anchor/angle`，但页面绑定、
  suppression、texture binding 按 semantic `direction == back`。
- BACK texture binding 为 `recto=flippingPageIndex`、`verso=flippingPageIndex`、
  `bottom=currentPageIndex`；current page 不进入 BACK static suppression。
- `routeBSpineMirroredApplied` 保留为诊断字段：portrait BACK 同构几何 `true`，
  landscape/fallback native BACK `false`。
- `backwardFoldX` 推进与层角色稳定由 `ArticleReadOnlyBookDebugState.backward*` 字段承载，
  contract / widget / visual 测试断言这些字段。
- 新增 BACK 测试断言：single-page portrait 的 previous moving sheet 与 visible current page
  有正面积交集，且不整体落在当前页左边界外；后段同时观测到 front/back/current 三段。

## MUST NOT

gate: `python3 quwoquan_app/scripts/content_service/content/post/verify_pageflip_backward_mainline.py`

**禁用符号的完整清单以脚本常量为唯一真相源**，不在本文件复制第二份：
`FORBIDDEN_SYMBOLS`（已退役的 M1-A 架构与 BACK 分支实验符号、screen-space display offset、
full previous-front baseline builder）、`FORBIDDEN_PROJECTED_FRAME_FIELDS`、
`FORBIDDEN_FRAME_BUILDER_STRINGS`、`BASELINE_VALUE_KEY`。新增禁令改脚本常量，别改文档。

脚本判定不了、需要人判断的：

- 不把 `scene.direction` / `StPageFlipRenderFrame.direction` 改成 `forward` 绕过 BACK 页面绑定。
- 不在 `_buildSoftPageLayer` 内引入独立 BACK helper 或自造 polygon；只允许经共享 pipeline 传 `direction`。
- BACK 方向不按 `progress` 切换 face，必须用 `visualAngle`。
- `rectoCoverageNormalized > 0.001` 时不允许整张 sheet 只显示单一 face。
- flipping sheet 的投影位置不随 `rectoCoverageNormalized` 或 recto 是否出现发生离散切换
  （会表现为背面消失、正面跳出的非折纸效果）。
- 不用独立外层 `Positioned` 平面铺 front/back 两块。
- 不把任何旁路推导出来的 polygon / rect / line 当作 BACK 视觉真相源用于诊断或测试断言。
- `ArticlePageBackwardProjectedFrame` 上不恢复多边形字段；诊断字段只允许 `foldLine` /
  `projectedRightEdgeLine` / `replayLocalPoint` / `edgeEnteredPage` / `foldLineSource` / `edgeLineSource`。

## 门禁

两个 gate 都已串联 `make gate` → `quwoquan_ops/gate/gate_repo.sh`：静态扫描随 `run_app`
执行，合约与视觉测试随 L1 执行。
