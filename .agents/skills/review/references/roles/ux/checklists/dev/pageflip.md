# ux · dev · pageflip

- [MUST] 改动满足 PRE owner identity 指向的功能设计与 Story 验收，不在角色中复制几何事实。
  check: 对照 plan.contexts 与 diff；越界或角色成为事实 owner 时判失败。
- [MUST] 用户可见的层级、连续性、返回与降级行为有聚合证据。
  evidence: app-pageflip-back-mainline
- [MUST NOT] 诊断或测试分支冒充真实绘制路径。
  check: 读取聚合 evidence 覆盖项与改动调用链；仅诊断/test 分支可达时判失败。
