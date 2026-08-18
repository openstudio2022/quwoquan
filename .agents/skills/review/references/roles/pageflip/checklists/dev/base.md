# pageflip · dev · base

承接原 `/pageflip-guard` 的六段强制输出。**先只读审视，再动手**；审视发现真实 paint 路径
与既有计划不一致时，必须先更新计划。

## PRE 准入：六段必须输出

- [MUST] 1 真实绘制链路：判断触及 forward、BACK 还是两者；写清
  `scene/calculation -> render frame -> deck layers -> Widget paint`，并指明真实 paint
  使用的函数、Widget、clip、transform
  check: 缺任一环，或只说「改 XX 文件」而未给链路，判失败
- [MUST] 2 分支地图：列出全部 geometry/helper/projection/slices/diagnostics 分支，
  逐个标记 `paint` / `diagnostics-only` / `test-only` / `dead branch`
  check: 未标记即判失败；改动落在未证明进入 runtime paint 的分支上，判失败
- [MUST] 3 业界语义对照：对照 StPageFlip 的 `flippingPage`、`bottomPage`、
  `static current`、`position + angle + area`，写明本地 Flutter 不能照搬的
  layout / clip / transform 差异
  check: BACK 方向缺此段判失败——把 StPageFlip 负坐标 `position` 直接当
  `Positioned(left: negative)` 是历史高频错误
- [MUST] 4 本次不变量：前/后翻各自要守住的 page face、层级、spine、seam、clip、
  texture 方向；BACK 必须明确 previous leaf、current static page、front/back face 的
  page index 语义
  check: 缺 BACK 的 page index 语义，判失败
- [MUST] 5 红测和证据：至少一个会在旧实现失败的测试、日志或诊断指标
  check: 无红测判失败。层级、前一页背面可见、书脊固定必须有 framebuffer 像素或
  viewport overlap 证据；`zOrder=` / `currentLayer=` / `backwardReplaySlices`
  只能作辅助，单独作为唯一证据判失败
- [MUST] 6 删除/封死分叉：列出要删除、薄包装或禁止继续扩展的分支；暂不删除的必须写明
  风险、原因与后续收口点
  check: 未列出判失败

## DURING 执行中

- [MUST NOT] 新增只服务 diagnostics 或测试通过的第二坐标链
  check: diagnostics 与测试断言必须消费与真实 paint 同一个 resolver；
  出现独立推导的 polygon/rect/line，判失败
- [MUST NOT] 用标签、阈值、fallback 或视觉稳定化掩盖主几何问题
  check: 改动只调整了容差、标签或稳定化参数而几何缺陷仍在，判失败
- [MUST NOT] 重新引入已退役的 BACK 旁路符号；清单以
  `verify_pageflip_backward_mainline.py` 的 `FORBIDDEN_*` 常量为准，
  BACK 完整契约见 [backward-mainline](../../references/backward-mainline.md)
  gate: make verify-app-pageflip-back-mainline
- [MUST NOT] 为省时间把关键后翻 visual 阶段降级为 `capturePixels: false`
  check: 对比改动前后的 visual 测试；关键阶段的像素采集被关闭，判失败

## POST 自检

- [MUST] BACK 主线合约成立
  gate: make verify-app-pageflip-back-mainline
- [MUST] 后翻静态几何通过
  gate: make verify-app-pageflip-backward-static
- [MUST] 后翻测试通过
  gate: make verify-app-pageflip-backward-tests
- [MUST] 真实 paint、diagnostics、测试仍共用同一 geometry 输出
  check: 出现第二条坐标链，判失败

## HANDOFF 交接

- 产出：六段输出全文、删除或封死的分支清单
- 未决项去向：暂不删除的分叉转 `OPEN-###`，写明收口点
- 下一步：POST 评审汇总
- 证据链：上述 gate 输出与像素/overlap 证据
