# BACK 几何推导

与业界 page-flip 实现及本仓当前前翻代码逐点对齐。改 BACK 几何前先读完这页，
再回 [backward-mainline.md](backward-mainline.md) 与
[checklists/dev/base.md](../checklists/dev/base.md) 看 MUST / MUST NOT。

## 共享 page-local 与 spread 投影

spread 中线（spine line）是 `bounds.left + bounds.width / 2`。

portrait 单页下 `bounds.width = 2 * pageWidth` 而 `viewport.width < 2 * pageWidth`，
所以 **`bounds.left` 是负值**，`bounds.left + pageWidth` 才是 visible page 的左边缘。
这是最容易踩的一条：把 `bounds.left` 当成可见左边缘会让整套 BACK 几何偏移一个页宽。

`convertBookPointToViewport(point, bounds, direction)`：

- forward：`viewport_x = bounds.left + bounds.width / 2 + point.dx`
- back：`viewport_x = bounds.left + bounds.width / 2 - point.dx`

forward 与 BACK 在 calculation 内部共用同一套 `_rect`，唯一差异只有三处：

| 方法 | forward | back |
|---|---|---|
| `getActiveCorner()` | `_rect.topLeft = pos` | `_rect.topRight ≠ pos` |
| `getAngle()` | `-_angle` | `+_angle` |
| `getBottomPagePosition()` | `(0, 0)` | `(pageWidth, 0)` |

## portrait 单页 BACK 几何契约

当前页可见在 right page，书脊是 `bounds.left + pageWidth`，也就是当前页左边线。
前一页位于书脊左侧的不可见对称面；BACK 时把前一页从左侧围绕该书脊翻到当前页区域。

业界 `HTMLPage.drawSoft()` 对 BACK 使用 direction-aware 局部裁剪：

- forward：`x = p.x - position.x`
- back：`x = -p.x + position.x`

本地 portrait 单页 BACK 的视觉目标是**与 forward 某一静态姿态同构**：
`direction == back` 保留页面绑定与提交语义，`visualGeometryDirection == forward`
负责 S/F/E/C 的视觉几何。

同构输入必须使用**反向时间**：刚开始后翻对应前翻的结束态，随后 previous leaf 从书脊
左侧不可见区向右翻入可见区。继续拿 semantic BACK replay point 当 visual input 是错的。

同构输入必须允许 forward 完成态的负 X 区间 `-pageWidth..pageWidth`。
把它 clamp 到 `0..pageWidth` 会让「刚后翻」错误映射成「前翻刚开始/中段」。

## 视觉契约（M1 验收）

- spine line 视觉锚定 visible page 左边缘，由 staticReadingPage underlay 与 sheet/bottom
  楔形互不重叠保证，与 forward 同机制。
- free edge 视觉起点贴 spine，随 angle 增大向 visible page 右侧 sweep。
- sheet 楔形落在 visible page 左半内，从 spine 朝中部 / 顶 / 底扩展。
- bottom 楔形是 spine 旁的小三角（朝顶或朝底取决于 corner），不出现在 visible page 右半。
- previous front 只经 moving sheet 内的 recto slice 出现；full previous-front baseline
  铺满 visible page 替换 current 是已封死的回归。
- 不出现「书脊在右」「折纸方向反」「不规则四边形」「黑屏」「previous front / back 错乱」。
