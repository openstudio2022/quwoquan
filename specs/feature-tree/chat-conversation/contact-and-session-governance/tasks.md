# Tasks: contact-and-session-governance — 关系与请求箱治理

> **顺序**：metadata → codegen → 业务逻辑 → 测试
> **目标**：完成“关注-打招呼-回复建会话-加同好-密友-RTC门禁”闭环

## Phase A — 对象与契约冻结

- [ ] A1: 新增 `GreetingRequest` metadata（entity/fields/service/events/errors/storage）
- [ ] A2: 新增 `relationship_capability_view` 或等价投影，统一输出 `relationTier + capability flags`
- [ ] A3: 扩展 `messages/conversation` metadata，补 `originType/originRequestId/upgradeState`
- [ ] A4: 扩展 `rtc/call_session/errors.yaml`，补关系门禁错误码
- [ ] A5: 补 `request_context`、openapi、contract test 场景定义

## Phase B — codegen 与仓库接口

- [ ] B1: 执行 `make verify-metadata`
- [ ] B2: 执行 `make codegen`
- [ ] B3: 执行 `make codegen-app`
- [ ] B4: 生成并接入 `GreetingRequest` DTO / Repository / 错误码
- [ ] B5: 生成并接入 `RelationshipCapability` DTO / Repository

## Phase C — 服务端业务逻辑

- [ ] C1: user/chat 域实现 `CreateGreetingRequest`
- [ ] C2: 实现请求箱收件箱/发件箱查询
- [ ] C3: 实现 `ReplyGreetingRequest`，回复后升级正式会话
- [ ] C4: 实现 `AddSameInterest`
- [ ] C5: 实现 `SetCloseFriend/UnsetCloseFriend`
- [ ] C6: 取消关注时同步回收同好/密友能力
- [ ] C7: 接入 `BlockEdge`、`allowStrangerMsg`、频控、pending 去重

## Phase D — 端侧关系体验

- [ ] D1: 用户主页五态按钮矩阵接入能力位
- [ ] D2: 新增打招呼发起与请求箱入口
- [ ] D3: 对方回复后自动升级为正式会话
- [ ] D4: 正式会话但未互关时，展示“加同好”关系条
- [ ] D5: 同好/密友解锁 RTC 能力位

## Phase E — 测试与门禁

- [ ] E1: T1 — 请求箱状态机、关系状态机、错误码 round-trip
- [ ] E2: T2 — 主页五态、请求箱/正式列表隔离、加同好关系条
- [ ] E3: T3 — 打招呼→回复→建会话→加同好→密友→取消关注回收能力
- [ ] E4: T3 — block / stranger setting / pending 去重 / 频控场景
- [ ] E5: `make gate`
- [ ] E6: `make gate-full`
