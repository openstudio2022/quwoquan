# L3 Story：message-home-filter-contract

## 最小价值点

让消息首页的全部、未读、群聊、私聊、通知五类筛选都由真实 inbox/read model 提供，而不是由 App 端猜测或本地拼接。

## 归属

- 领域服务：`chat-conversation`
- 业务能力：`commercial-message-system`
- 关联 Journey / Scenario：消息首页真实收件箱筛选

## 行为范围

### In Scope

- 五类消息筛选的 read model 与通知 inbox 边界。
- 已读后跨筛选未读数同步一致。
- assistant insight / AppMessage 作为真实通知行展示。

### Out of Scope

- 联系首页关系聚合。
- 群主页与群聊天信息页联动。

## 行为规则

- Given：消息首页存在会话与通知数据。
- When：用户切换不同筛选或执行已读动作。
- Then：五类筛选结果由真实服务契约提供，未读状态在所有聚合引用中保持一致。

## 接口契约

- API path / operation：`ListMessageHome` / `MarkAsRead` 与通知 inbox metadata。
- DTO / projection：`MessageHome`、`AppMessage`。
- error code：消息域、通知域与 runtime error metadata。
- surface / route：消息页筛选 surface 与 route metadata。

## 验收关注点

- done_when：五类筛选和已读同步都由真实 read model 驱动。
- edge cases：通知类型混排、无通知、跨筛选重复会话一致性。
- test evidence：`T1_static_contract`、`T3_service_contract`。
