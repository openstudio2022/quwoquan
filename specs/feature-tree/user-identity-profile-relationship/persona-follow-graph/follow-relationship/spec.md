# L3 Story：关注关系 (`follow-relationship`)

> 所属能力：[`persona-follow-graph`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为管理身份、Persona 或关系的用户，
我希望owner 不能作为默认 follow 主体参与社交关系建立，
从而安全地维持身份、画像与关系状态。

## 2. 范围与非目标

### In Scope

- “关注关系”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 关注关系

- owner 不能作为默认 follow 主体参与社交关系建立。

<a id="req-002"></a>
### REQ-002 follow / unfollow 的命令主体必须是当前 active persona 或显式选择的 persona

- follow / unfollow 的命令主体必须是当前 active persona 或显式选择的 persona。
- owner 不能作为默认 follow 主体参与社交关系建立。
- follow 边的 `followerId / followeeId` 语义必须统一映射到 `ProfileSubject` 级别，而不是漂移在 owner/user 级别。
- 重复 follow 必须幂等，不得重复计数。
- unfollow 不存在的边应当是安全 no-op 或明确可恢复错误，不允许破坏计数。
- 如果 `BlockEdge` 表示任一方向的强屏蔽，follow 写入必须被拒绝或无效化，具体语义由 user 域统一定义。
- follow 写入侧不能绕过 `BlockEdge` 直接落边。
- follow 写入成功与否，不得泄露不应暴露的屏蔽细节。
- 平台审计可追踪 follow 命令与分身主体；普通读接口不得反推出 owner 映射。
- user 域之外不得复制 follow 写入契约。

<a id="req-003"></a>
### REQ-003 服务本地契约引用边界

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

<a id="req-004"></a>
### REQ-004 联系人发现到关注写入必须保持对象边界与隐私单轨

- 通讯录发现只允许在端侧完成号码规范化与哈希；原始手机号不得进入联系人发现请求、日志、埋点或结果回执。
- 联系人发现、账号搜索与二维码解析只负责返回候选主体；是否允许关注必须重新读取 `persona_relationship` 的 canonical relationship capability，候选结果不得自行推导写权限。
- 关注写入只能由 active persona 经 user-service production Remote 发起；失效二维码、无权限候选、被屏蔽主体或不可见主体不得产生 follow edge。
- 页面切换、权限拒绝、网络失败或 canonical failure 不得清空仍可恢复的搜索条件与候选结果，也不得显示伪成功关系态。

<a id="req-005"></a>
### REQ-005 屏蔽列表读取与解除屏蔽必须以云侧读回为准

- 屏蔽列表必须从 `persona_relationship` 的具名投影分页读取，不得由本地历史关注关系拼装。
- 解除屏蔽只在 typed command 成功且云侧读回不再包含该关系后更新最终 UI；失败时必须保留原列表项和可重试入口。
- 普通用户只能看到产品允许的屏蔽结果，不得从列表、错误或恢复动作推断 owner 映射、对方额外身份或内部治理原因。

<a id="req-006"></a>
### REQ-006 打招呼收发箱与正式会话升级必须保持 User 与 Chat 双 owner 单轨

- canonical `chat.greeting_inbox` 页面必须经 production Remote composition 分别读取收到和发出的 `GreetingRequest`；pending 请求在回复前不得进入普通会话列表，也不得由本地会话或通知记录拼装。
- 收到的请求只允许目标 persona 回复或忽略，发出的 pending 请求只允许发起 persona 撤回；动作成功前不得乐观删除条目，canonical failure 必须保留原状态与可重试动作。
- 回复必须由 `GreetingRequest` owner 先完成状态迁移并取得 `promotedConversationId`，再由 Chat owner 创建或复用唯一正式 1v1 conversation；重放不得创建第二个会话，且升级不得自动建立关注、互关或其它关系事实。
- 忽略与撤回不得创建 Chat conversation；页面不得泄露 owner 映射、对方额外身份、内部风控原因或未获授权的交集事实。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 关注关系

- GIVEN 管理身份、Persona 或关系的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“关注关系”对应的公开行为。
- THEN owner 不能作为默认 follow 主体参与社交关系建立。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 联系人发现、搜索或二维码候选经关系能力确认后完成关注

- GIVEN 用户以 active persona 登录 production Remote composition，并从系统通讯录、账号搜索或可撤销资料二维码进入添加联系人旅程。
- WHEN App 对通讯录权限作出允许或拒绝处理；允许时仅提交端侧规范化后的哈希集合，并分别经 `contact_discovery_record`、`user_account` 或二维码解析公开能力取得候选。
- WHEN App 对选中候选读取 `persona_relationship` 的 relationship capability，并仅在 `canFollow` 成立时提交 follow 命令。
- THEN 原始手机号、ownerId、二维码 bearer 信息和内部屏蔽原因不进入请求、日志、埋点或结果回执。
- AND 成功后由 production Remote 读回 canonical 关系态；失效二维码、不可见或被屏蔽候选不得落 follow edge。
- AND 权限拒绝、网络失败或 canonical failure 保留可恢复的输入与候选状态并提供重试，不得清空页面或展示伪成功。
- AND 只有绑定同一 candidate、真实 Provider 与 production Remote 的 Android 物理设备及 iPhone 物理设备 `ReadinessResultBundle` 均通过时，本验收场景才计通过；Widget、模拟器、动态 skip 或 typed double 不计。

<a id="gwt-003"></a>
### GWT-003 屏蔽列表分页读取、解除屏蔽与失败恢复

- GIVEN 用户以 active persona 登录 production Remote composition，且云侧存在由该 persona 拥有的真实 block edge。
- WHEN App 经 `persona_relationship` 具名 reader 分页读取屏蔽列表并对目标提交解除屏蔽命令。
- THEN 分页使用稳定 cursor，结果不重复、不串页，且不得泄露 owner 映射或目标的额外身份。
- AND 只有 typed command 成功且 production Remote 读回已移除目标时，UI 才移除该列表项。
- AND canonical failure 或读回未收敛时保留原列表项、关系态与重试入口，不得显示解除成功。
- AND 只有绑定同一 candidate、真实 Provider 与 production Remote 的 Android 物理设备及 iPhone 物理设备 `ReadinessResultBundle` 均通过时，本验收场景才计通过；Widget、模拟器、动态 skip 或 typed double 不计。

<a id="gwt-004"></a>
### GWT-004 打招呼收发箱回复、忽略、撤回与正式会话升级

- GIVEN 两个非互关且未互相屏蔽的 persona 之间存在真实 pending `GreetingRequest`，用户从 canonical `chat.greeting_inbox` 进入 production Remote 收发箱。
- WHEN App 分别分页读取 inbox 与 outbox，并由合法 actor 对收到的请求执行回复或忽略、对发出的 pending 请求执行撤回。
- THEN 收到和发出的请求保持正确归属、状态与稳定分页，pending 请求在回复前不进入普通会话列表。
- AND 回复成功只创建或复用一个 Chat 正式 1v1 conversation，返回的 `promotedConversationId` 可打开该会话，重放保持同一会话且关注关系不变。
- AND 忽略或撤回只在 production Remote 确认状态迁移后更新条目，且不创建 conversation。
- AND canonical failure、超时或读回未收敛时保留原条目与可重试动作，不展示伪升级、伪忽略或伪撤回，也不泄露额外身份与内部治理事实。

## 6. 依赖

- 前置要求：[`persona-follow-graph`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 联系人、屏蔽与打招呼收发箱的双真机 user_acceptance 证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：尚缺能够同时证明 `GWT-002`、`GWT-003` 与 `GWT-004` 的 production Remote、隐私边界、User→Chat 升级、成功读回、失败恢复及同一 candidate 双物理设备行为的结果回执。
- 完成判定：`GWT-002`、`GWT-003` 与 `GWT-004` 均由职责匹配的 production journey 覆盖，并绑定同一 commit、ContractGraph、candidate、环境与真实 Provider；Android 物理设备和 iPhone 物理设备的 `ReadinessResultBundle` 均为 passed 后才可关闭。failed、blocked、skipped、模拟器或测试 double 结果均不计通过。
