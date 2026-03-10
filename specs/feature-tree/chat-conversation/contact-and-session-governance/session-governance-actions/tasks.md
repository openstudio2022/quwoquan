# Tasks: session-governance-actions — 对象级治理动作

## Phase A — 动作边界冻结

- [ ] A1: 明确用户/消息/请求/会话四类治理对象
- [ ] A2: 定义每类对象允许的治理动作与入口
- [ ] A3: 明确群聊设置页不承担举报/拉黑

## Phase B — metadata 与契约

- [ ] B1: 对齐 `user/block_edge` 与 `content/report` 的消费边界
- [ ] B2: 如需新增治理审计对象，补 metadata 与事件
- [ ] B3: 对齐请求箱动作（忽略/拒绝/撤回）的 service 契约

## Phase C — 前后端落地

- [ ] C1: 主页/成员卡片接入举报用户、拉黑用户
- [ ] C2: 消息长按菜单接入举报消息
- [ ] C3: 请求箱接入忽略、拒绝、撤回
- [ ] C4: 会话设置页保留会话管理动作

## Phase D — 测试

- [ ] D1: T2 — 对象级入口正确分流
- [ ] D2: T3 — block/report/request actions 审计链路正确
- [ ] D3: `make gate`
