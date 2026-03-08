# L3 规格：call-experience — 通话中 UI/UX 体验

> **层级**：L3_subfeature（隶属 L2 `realtime-call`）
> **状态**：specified
> **父节点**：`chat-conversation/realtime-call`

## 定位

通话中的 UI 交互体验：7 种动态网格布局、演讲者视图、通话控制栏、画中画、顶部通话条、弱网质量指示、音频路由。

## 职责边界

- 覆盖 Phase 2~3 功能（F7 网格/演讲者、F10 PiP、F11 通话条、F12 弱网指示、F13 音频路由）
- 7 种网格配置：2人/3人/4人/5-6人/7-9人/10-16人/17-32人
- 演讲者视图：大画面(70%) + 底部缩略行
- 发言人高亮：白色发光边框 + 轻微放大（对标 FaceTime）

## 与父/子节点关系

- 父节点 `realtime-call` 定义性能约束（32人 ≥15fps、60fps 控制栏）
- 子节点 `call-ui-interaction`（L4 Story）承载 UI 组件的可验收交付

详细规格见父节点 `realtime-call/spec.md` §3.1 Phase 2~3。
