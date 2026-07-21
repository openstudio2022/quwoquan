# L3 Story：会话偏好即时生效与记忆可撤销

## 归属

- AppRoot Journey：`assistant-omnipresent-private-assistant`
- Scenario：`assistant-context-grounded-answering`
- L1：`assistant-run-learning`
- L2：`world-class-trinity-experience-baseline`
- L3：`session-preference-memory-control`
- 验收意图：GWT / contract
- 测试证据：`local_contract` 为主，`api_integration` 与页面
  `user_acceptance` 为辅。

## 用户价值

用户选择“更简洁、更多细节、更口语化、深度思考”后，同一会话的下一次回答立即按该偏好生成；
小趣长期保存的偏好事实必须在管理页可见，用户可以遗忘并在本次操作后撤销恢复。

## 范围

1. 偏好是结构化事实，不把风格指令前缀拼进用户问题。
2. 会话偏好绑定 `conversationId`，服务端在创建下一次 Run 前完成读取并注入模型请求。
3. 长期偏好由用户显式设置或确认，不从隐式行为静默升级。
4. 记忆管理只展示当前有效的偏好事实；反馈流水、评分卡和内部诊断不得冒充用户记忆。
5. 遗忘使用 owner-scoped 状态迁移，保留审计事实但立即停止召回；恢复只允许原 owner 在撤销窗口内执行。
6. 所有写操作幂等，错误使用 metadata 生成的 `RuntimeFailure` 语义。

## 非范围

- 不做向量记忆、自动人格推断或跨账号记忆合并。
- 不删除合规审计所需的原始交互事件；“遗忘”只移除偏好事实的可见性与运行时召回。
- 不允许 UI、本地存储或 prompt 维护第二套偏好状态。

## 核心契约

- `SetAssistantPreference`：创建或更新 owner 的结构化偏好事实。
- `ListAssistantPreferences`：读取 active/revoked 偏好事实。
- `RevokeAssistantPreference`：将 active 事实转为 revoked，并返回可恢复状态。
- `RestoreAssistantPreference`：在撤销窗口内恢复事实。
- `StartAssistantRun`：服务端从同一 Reader 装配 session + long-term 偏好快照。

偏好键和值必须来自 metadata 闭集；当前至少覆盖：

- `response_detail = concise | detailed`
- `response_tone = casual | neutral`
- `reasoning_depth = standard | deep`

## 验收

- 相同用户、相同会话选择风格后，下一 Run 的模型请求包含该 session preference；原始问题不带风格前缀。
- 其他会话不继承 session preference；显式 long-term preference 才跨会话生效。
- 管理页删除后条目立即消失，后续 Run 不再注入；撤销恢复后重新出现并恢复注入。
- 非 owner 读写返回 not-found 语义，不泄露事实是否存在。
- 重复 set/revoke/restore 不产生重复事实或非法状态。
