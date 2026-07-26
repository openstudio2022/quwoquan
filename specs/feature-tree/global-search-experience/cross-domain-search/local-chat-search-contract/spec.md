# L3 Story：本地聊天搜索契约 (`local-chat-search-contract`)

> 所属能力：[`cross-domain-search`](../spec.md)

> Journey / Scenario：[`JNY-005 / SCN-011`](../../../spec.md#scn-011)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为执行搜索的用户，
我希望页面与业务层只允许调用 canonical `search(request)`，不得直接依赖聊天域搜索方法名，
从而找到可理解并可继续操作的结果。

## 2. 范围与非目标

### In Scope

- “本地聊天搜索契约”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 本地聊天搜索契约

- 页面与业务层只允许调用 canonical `search(request)`，不得直接依赖聊天域搜索方法名。

<a id="req-002"></a>
### REQ-002 冻结聊天搜索结果的最小展示字段、跳转字段与统一结果模型映射

- 冻结聊天搜索结果的最小展示字段、跳转字段与统一结果模型映射。
- 页面与业务层只允许调用 canonical `search(request)`，不得直接依赖聊天域搜索方法名。
- 搜索结果必须携带稳定会话定位信息，点击后可直接进入单聊或群聊上下文。
- 登出不清空本地搜索索引，但必须按 owner / sub account 分区隔离。
- 消息撤回、删除或用户显式清理时，必须同步删除对应本地索引项。
- 子账号切换后，不得读到其他子账号的本地聊天索引结果。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 本地聊天搜索契约

- GIVEN 执行搜索的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“本地聊天搜索契约”对应的公开行为。
- THEN 页面与业务层只允许调用 canonical `search(request)`，不得直接依赖聊天域搜索方法名。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`cross-domain-search`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
