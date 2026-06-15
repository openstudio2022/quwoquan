# L3 Story：message-home-commercial-ia

## 最小价值点

把消息模块首页稳定为商用版「消息」一级状态，明确回答“最近发生了什么”，不再回退旧消息筛选 IA。

## 归属

- 领域服务：`chat-conversation`
- 业务能力：`commercial-message-system`
- 关联 Journey / Scenario：消息体系商用重构首页 IA

## 行为范围

### In Scope

- 消息页作为消息模块内独立一级状态的表达。
- 顶部搜索按钮和小趣入口的保留。
- 旧 `@我 / @小趣 / 提醒` 从商用首页主 IA 退出。

### Out of Scope

- 消息首页五类筛选的数据契约。
- 群主页、通知持久化和交集聚合细节。

## 行为规则

- Given：用户从底栏进入消息模块。
- When：商用消息体系首页渲染完成。
- Then：页面以「消息」作为独立一级状态，继续使用顶部工具栏搜索和小趣入口，且不回退旧消息主 IA。

## 接口契约

- API path / operation：消费消息首页 metadata 定义的 operation。
- DTO / projection：`MessageHome` read model。
- error code：沿用消息域与 runtime error metadata。
- surface / route：消息首页对应的 metadata route / surface。

## 验收关注点

- done_when：消息首页 IA 可独立成立且不回退旧信息架构。
- edge cases：空收件箱和缓存回填场景下保持同一 IA。
- test evidence：`T2_module_interaction`、`T4_device_journey`。
