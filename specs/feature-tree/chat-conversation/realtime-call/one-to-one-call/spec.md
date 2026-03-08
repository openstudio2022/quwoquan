# L3 规格：one-to-one-call — 1v1 语音/视频通话

> **层级**：L3_subfeature（隶属 L2 `realtime-call`）
> **状态**：specified
> **父节点**：`chat-conversation/realtime-call`

## 定位

1v1 语音/视频通话的端到端闭环：发起→呼叫→接听→通话→挂断→通话记录。
包含来电推送（在线 WS + 离线 VoIP Push）和通话控制（静音/关摄像头/翻转/扬声器）。

## 职责边界

- 覆盖 Phase 1 全部功能（F1~F5）
- 呼叫状态机：INITIATED→RINGING→CONNECTING→IN_CALL→ENDED
- 来电唤醒：iOS CallKit / Android FullScreen Intent
- 通话结束→chat-service 插入通话记录消息

## 与父/子节点关系

- 父节点 `realtime-call` 定义全局 spec、acceptance、constraints
- 子节点 `call-lifecycle-contract`（L4 Story）承载呼叫状态机契约的可验收交付

详细规格见父节点 `realtime-call/spec.md` §3.1 Phase 1。
