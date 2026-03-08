# L4 Story：call-ui-interaction — 通话 UI 交互

> **层级**：L4_story（隶属 L3 `call-experience`）
> **状态**：specified
> **父节点**：`chat-conversation/realtime-call/call-experience`

## 定位

通话 UI 交互的可验收交付：7 种网格布局、演讲者视图、控制栏、PiP 画中画、来电 UI（CallKit/FullScreen Intent）。

## 职责边界

- 7 种网格：2人/3人/4人/5-6人/7-9人/10-16人/17-32人，发言人白色高亮
- 演讲者视图：大画面(70%) + 底部缩略行 + 发言人自动切换 ≤ 1s
- 控制栏：静音/关摄像头/翻转/邀请/扬声器/挂断 6 按钮
- PiP：通话中返回→浮窗可见可拖动→点击返回全屏
- 来电：OutgoingCall/IncomingCall 页面 + CallKit/Android FullScreen
- 对应 L2 `realtime-call` acceptance A8~A16、A38

## 与父节点关系

- 父节点 `realtime-call/spec.md` §5 入口体系、§6.1 技术约束、§9 验收重点 T2
- 父节点 `call-experience/spec.md` 定义 UI/UX 职责
- 详细规格与验收标准见 L2 `realtime-call/spec.md` 及 `realtime-call/acceptance.yaml`。
