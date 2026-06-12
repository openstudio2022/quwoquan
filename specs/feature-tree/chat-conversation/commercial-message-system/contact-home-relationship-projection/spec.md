# L3 Story：contact-home-relationship-projection

## 最小价值点

让联系首页的全部、互关、圈子、群聊视图由真实关系聚合和交集摘要支撑，而不是 App 侧拼业务事实。

## 归属

- 领域服务：`chat-conversation`
- 业务能力：`commercial-message-system`
- 关联 Journey / Scenario：联系首页真实关系聚合

## 行为范围

### In Scope

- 联系首页混排用户和群的真实聚合。
- 互关索引阈值、圈子 tab、群聊 tab 的 read model 边界。
- 交集摘要最多展示 2 个具体点。

### Out of Scope

- 消息首页通知 inbox。
- 群主页治理能力细项。

## 行为规则

- Given：用户已建立关系、圈子和群聊数据。
- When：用户查看联系首页不同筛选。
- Then：联系首页展示真实关系聚合、最近互动排序和受限交集摘要，不由 UI 临时拼接。

## 接口契约

- API path / operation：`ListContactHome` 对应 metadata operation。
- DTO / projection：`ContactHome`、`IntersectionSummary`。
- error code：消息域、推荐交集域与 runtime error metadata。
- surface / route：联系首页与圈子联系人页 route / surface metadata。

## 验收关注点

- done_when：联系首页关系、圈子、群和交集都由真实投影支撑。
- edge cases：空交集、互关人数阈值、只有圈子或只有群的混排场景。
- test evidence：`T2_module_interaction`、`T3_service_contract`。
