# L3 Story：commercial-remote-only-message-system

## 最小价值点

确保商用消息体系路径只依赖真实 Remote/服务端持久化事实，不再回退 Mock、prototype bundle 或本地业务拼接。

## 归属

- 领域服务：`chat-conversation`
- 业务能力：`commercial-message-system`
- 关联 Journey / Scenario：商用路径 Remote-only 收口

## 行为范围

### In Scope

- App 商用主路径不从 chat/intersection/app message mock 拼业务列表。
- 服务端生产配置不允许 mock-user、memory store、noop resolver。
- 退役字段不再作为商用主渲染来源。

### Out of Scope

- alpha/test fixture 的开发态存在方式。
- 具体 hosted 部署流程。

## 行为规则

- Given：应用运行在商用消息体系主路径。
- When：页面、Provider 与服务配置加载消息体系相关数据。
- Then：系统只消费真实 Remote/持久化契约，不再以 Mock 或退役字段维持主渲染。

## 接口契约

- API path / operation：消息、通知、交集相关 metadata operation。
- DTO / projection：`MessageHome`、`ContactHome`、`GroupHome`、`AppMessage`。
- error code：消息域、通知域、内容域和 runtime error metadata。
- surface / route：消息体系相关页面的 metadata route / surface。

## 验收关注点

- done_when：商用主路径不再依赖 Mock、prototype bundle 和退役字段。
- edge cases：release 包默认 Remote、配置缺失防回退、缓存存在但远端失败时的结构化降级。
- test evidence：`T1_static_contract`、`T3_service_contract`。
