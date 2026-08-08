# L3 Story：群聊头像服务端预合成与统一同步契约 (`group-avatar-server-precompose-and-unified-sync-contract`)

> 所属能力：[`runtime-media`](../spec.md)

> Journey / Scenario：[`JNY-004 / SCN-003`](../../../spec.md#scn-003)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，
我希望`chat-service` 返回非空、可访问的 `avatarUrl`；单聊为对方用户头像，群聊先返回稳定默认头像，再由服务端异步预合成群头像并通过 sync patch 覆盖，
从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- “群聊头像服务端预合成与统一同步契约”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 群聊头像服务端预合成与统一同步契约

- **统一会话头像主链路**：`chat-service` 返回非空、可访问的 `avatarUrl`；单聊为对方用户头像，群聊先返回稳定默认头像，再由服务端异步预合成群头像并通过 sync patch 覆盖。

<a id="req-002"></a>
### REQ-002 需要基于统一对象模型实施头像、媒体和同步链路的服务开发者

- 需要基于统一对象模型实施头像、媒体和同步链路的服务开发者。
- **统一会话头像主链路**：`chat-service` 返回非空、可访问的 `avatarUrl`；单聊为对方用户头像，群聊先返回稳定默认头像，再由服务端异步预合成群头像并通过 sync patch 覆盖。
- **对象标识合同**：群头像、用户头像与聊天/内容媒体统一使用 `AssetRef / MediaAsset`，数据库主存 `assetId + version`。
- **URL 合同**：群头像与成员头像只以 path-versioned canonical public slice 表达资产版本，由 runtime media 使用注入的 HTTPS delivery base 构建 query-free URL；禁止 absolute URL 原样透传、`?v=` 版本信封、无版本 alias、CAS/object key 和失败后回原 source。
- 头像变化传播不能依赖单次推送，必须具备补偿拉取。
- URL 规范必须由 runtime 统一，而不是各服务自行拼接。
- 不为分享链路生成单独头像逻辑；分享如需头像，仍消费统一资产引用。
- 建群第一版群头像必须在会话对 App 可见前生成；成员变更后的重算可异步执行并保留上一版头像。
- sync patch 允许重复投递，但客户端必须幂等消费。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 群聊头像服务端预合成与统一同步契约

- GIVEN 开发、测试或运维角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“群聊头像服务端预合成与统一同步契约”对应的公开行为。
- THEN **统一会话头像主链路**：`chat-service` 返回非空、可访问的 `avatarUrl`；单聊为对方用户头像，群聊先返回稳定默认头像，再由服务端异步预合成群头像并通过 sync patch 覆盖。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`runtime-media`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 群头像统一同步失败语义尚无直接证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：缺 `GWT-001.t2` 的直接证据，3 条绑定测试均无失败路径断言。
- 完成判定：`GWT-001.t1` 与 `GWT-001.t2` 各自被真实测试 `spec_ref` 绑定。
