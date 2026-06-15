# L3 Story：contact-home-commercial-ia

## 最小价值点

把消息模块内的「联系」页稳定为商用一级状态，明确回答“我和谁建立了连接”，不再退化成传统通讯录。

## 归属

- 领域服务：`chat-conversation`
- 业务能力：`commercial-message-system`
- 关联 Journey / Scenario：消息体系商用重构首页 IA

## 行为范围

### In Scope

- 联系页作为消息模块内独立一级状态的表达。
- 顶部搜索按钮和小趣入口的统一保留。
- 联系页不以内联搜索框承载主 IA。

### Out of Scope

- 互关/圈子/群聊聚合 read model 的细节。
- 群主页能力入口和通知 inbox。

## 行为规则

- Given：用户已进入消息模块。
- When：切换到联系页一级状态。
- Then：页面回答“我和谁建立了连接”，并继续使用统一顶部入口而非旧通讯录心智。

## 接口契约

- API path / operation：消费联系首页 metadata 定义的 operation。
- DTO / projection：`ContactHome` read model。
- error code：沿用消息域与 runtime error metadata。
- surface / route：联系首页对应的 metadata route / surface。

## 验收关注点

- done_when：联系页 IA 独立成立且不回退通讯录心智。
- edge cases：空关系、低于索引阈值时仍保持 IA 一致。
- test evidence：`T2_module_interaction`、`T4_device_journey`。
