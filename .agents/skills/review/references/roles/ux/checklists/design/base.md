# ux · design · base

prd 定的是「要有哪些状态」，design 定的是「用什么积木实现」。积木选错在 dev 返工最贵。

## PRE 准入

- [MUST] 复用还是新建已裁决：新建组件必须说明现有积木为何不适用
  check: 读设计文档；新建组件无对比说明，或说明只是「现有的不好看」，判失败
- [MUST] surface 分型已确定：全屏页、贴底 sheet、对话态 sheet、设置类 inset 页各归哪一类
  check: 找不到对应分型却新造第三套组合，判失败
- [SHOULD] 断点行为已定义：`compact` / `regular` / `expanded` 下分别是什么密度
- [SHOULD] 已确认所需的语义 token 都存在；缺失的先补 token 再进实现

## DURING 执行中

- [MUST NOT] 在设计里引入视觉字面量（颜色、间距、圆角、字号、导航高度）
  gate: python3 quwoquan_app/scripts/runtime/observability/verify_dart_semantic.py
- [MUST NOT] 新建裸 `showCupertinoModalPopup` 或第二套白卡灰底；对话态 sheet 走
  `AppBottomModalSurface` 与 `ConversationSheet*` 积木
  gate: python3 quwoquan_app/scripts/runtime/page/verify_conversation_sheet_canonical.py
- [MUST NOT] 在组件内定义私有断点阈值（如 `width > 900`）；只用 `AppSpacing` 断点 token
  check: 设计或实现中出现第二套 breakpoint map，判失败

## POST 自检

- [MUST] iOS 原生壳合规
  gate: python3 quwoquan_app/scripts/runtime/page/verify_ios_native_surface_gate.py
- [MUST] 设置类页面同源
  gate: python3 quwoquan_app/scripts/runtime/page/verify_settings_canonical.py
- [SHOULD] 页面对象契约已登记
  gate: make verify-app-page-object-contract

## HANDOFF 交接

- 产出：surface 分型结论、复用/新建决定、断点行为、需要新增的 token
- 未决项去向：缺失且本次不补的 token 转 `OPEN-###`，写明阻塞了哪个视觉需求
- 下一步：`dev`，其 PRE 需要本次的 surface 分型与积木选择
- 证据链：上述 gate 的实际输出
