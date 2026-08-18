# ux · dev · flutter-page

## PRE 准入

- [MUST] 页面四态（加载 / 空 / 错误 / 权限）都在实现计划内
  check: 读计划或 diff；只实现成功路径，判失败
- [SHOULD] 文案走 i18n / `UITextConstants`，不在 Widget 里写死中文或英文字面量
- [SHOULD] 响应式方案已确定用哪个断点 token，而不是到写代码时临时决定

## DURING 执行中

- [MUST NOT] 页面内手写宽屏断点（如 `width > 900`）；响应式只用 `AppSpacing` 断点 token 与
  `AppSpacing.responsiveValue`
  gate: make verify-app-page-horizontal-quality
- [MUST NOT] 硬编码间距、颜色、圆角、字号；一律取设计系统语义 token
  gate: make verify-app-page-abc-governance
- [MUST NOT] 页面以 `Map` / `dynamic` 充当业务展示模型
  gate: make verify-app-page-abc-governance
- [MUST NOT] 在业务层裸用 `Platform.is*` / `kIsWeb` 做体验分叉；改为读能力位
  gate: make verify-app-page-horizontal-quality

## POST 自检

- [MUST] 页面横向质量通过
  gate: make verify-app-page-horizontal-quality
- [MUST] 页面 ABC 治理通过
  gate: make verify-app-page-abc-governance
- [MUST] 页面对象契约成立（owner、Query Slice、typed presentation、route、surface 引用有效）
  gate: make verify-app-page-object-contract
- [SHOULD] 主题绑定棘轮未退化
  gate: make verify-app-theme-binding-ratchet
- [SHOULD] 双平台可用性基线通过
  gate: make verify-app-dual-platform-usability-baseline

## HANDOFF 交接

- 产出：新增/改动页面路径、使用的 token 与断点、四态实现位置
- 未决项去向：暂缺的状态设计转 `OPEN-###`，不要用占位 UI 假装完成
- 下一步：POST 评审汇总，其 PRE 需要四态的可测入口
- 证据链：上述 gate 的实际输出
