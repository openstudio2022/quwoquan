# L3 Story：浏览器与作者主页状态同步 (`viewer-profile-state-sync-contract`)

> 所属能力：[`content-display-consistency`](../spec.md)

> Journey / Scenario：[`JNY-003 / SCN-007`](../../../spec.md#scn-007)

> 设计归属：[L2 DEC-001](../design.md#dec-001)、[DEC-002](../design.md#dec-002)、[DEC-003](../design.md#dec-003)、[DEC-004](../design.md#dec-004)

## 1. 用户价值

作为在内容与作者主页间切换的用户，
我希望关注在云确认后同步、点赞按钮可乐观响应，并能分辨本人状态、命令结果和统计新鲜度，
从而跨页面、切身份和弱网恢复时不会把旧数据或未知结果当作已确认事实。

## 2. 范围与非目标

### In Scope

- “浏览器与作者主页状态同步”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 浏览器与作者主页状态同步

- 必须消费 `owner-persona-homepage-unification` 定义的 canonical `RelationshipCapabilityView` 关系矩阵。

<a id="req-002"></a>
### REQ-002 viewer、profile、feed 同时 watch 统一 provider

- viewer、profile、feed 同时 watch 统一 provider。
- 必须消费 `owner-persona-homepage-unification` 定义的 canonical `RelationshipCapabilityView` 关系矩阵。
- 关系态必须用对象真相源驱动，而不是页面局部状态拼装。
- 网络写回必须与 UI 即时反馈分层。
- 端侧复用 canonical outbox，但已发送意图、尚未发送的最终期望和已确认事实分离；只保存两个 bool 不足以恢复命令身份、actor、依据、版本和期限。Comment 三态保持自己的 typed 状态，不压成 bool。
- 禁止读取 `needsRemoteSync`、guard-only 旧形态或通过缺字段推断确认；旧记录缺稳定命令身份或受信依据时隔离为不可发送的恢复态，不补造字段重发，也不把可能提交的历史静默删成失败。
- 关注/取关只立即显示 pending，云确认才改变最终关系态；点赞只乐观覆盖按钮，不改变统计数字、不扩大私信/通话权限。
- 短暂后台重试不逐卡打扰；长时间未决、明确拒绝、持久化失败及人工恢复入口使用统一 typed recovery 文案。超过本地最大年龄只停发，不凭本地定时器撤去 unknown；权威同键终结语义引用 [Reaction REQ-004](../../publish-comment-reaction/reaction-state-counter/spec.md#req-004) 与 User owning contract。
- Feed/详情的本人互动附着区分成功、明确不适用、暂时不可用；成功的 false 是已验证未赞，合法无关系为初始版本。`null` 仍不覆盖，但不能继续混装匿名、不曾装配和读失败；可信匿名 Persona 也应按真实 actor 读取。
- pending 意图只覆盖当前 actor/target 的按钮；本人态与统计分别校验来源、请求 epoch 和可比较版本后合并，不无条件接收迟到数字。

<a id="req-003"></a>
### REQ-003 actor 分区与逐对象持久恢复

- outbox、共享关系/Reaction、receipt 与私有互动缓存使用同一 environment/account/persona/device 分区；actorDimension 与 actorId 只从 verified principal 取得，不能根据 isGuest 或设备标签推断。
- 切号/切 Persona 停止旧分区发送，迟到查询/ACK 不能污染新分区；A→B→A 只恢复 A 原有且仍可合法恢复的意图。匿名转登录不搬移赞。
- hydrate 按每对象 revision/tombstone 合并：加载期间新增、反转或删除的对象保留新决定，未变动的其他磁盘项仍恢复，不能因任一变化丢弃整个快照。
- 持久写串行且有序，只有写成功才宣布 durable acceptance；失败或达到条数/字节上限明确拒绝新接纳，不能吞错、悄悄丢最旧 unknown 或声称可靠排队。

<a id="req-004"></a>
### REQ-004 单飞命令与结果未知的受控恢复

- 同 actor/target 最多一个在飞行命令；跨目标有界并发且公平。发送后原命令不可变，连续反转只合并未发送最终期望，后继不能绕过仍 unknown 的前驱。
- queued、in-flight、outcome unknown、confirmed 与 rejected 按合同分型；只有已接纳的本地用户命令才有 pending，网络读失败不是命令 pending。
- receipt 校验 actor、target、请求代际与本对象版本；确认后保留版本栅栏并终结该命令，统计落后不保留重试，不因后置读失败重写。
- 权威版本冲突先读取当前事实；当前已满足不证明原命令提交，未满足保留用户恢复入口，不静默换前置版本强行重发。有限窗口外先同键恢复终结，历史不可判定与确定未执行分开。

<a id="req-005"></a>
### REQ-005 本人态、统计与公共内容分层展示

- 本人完全未知时保留稳定操作区布局和 loading/暂不可用态，不画成已确认未赞；点击先有界权威读取后继续，仍失败给可重试反馈，不盲 toggle。同 actor 已知旧态可以按合同标 stale。
- 统计 available/stale/unavailable 按 [Reaction REQ-007](../../publish-comment-reaction/reaction-state-counter/spec.md#req-007) 消费；无可信值只占位数字，有效零须有来源。正常完整投影及 available 分支必填数字错误仍严格失败，不能用 decoder fallback 救坏 DTO。
- 本人 reader 正常且仅统计失败时按钮仍可操作；pending 遇读失败不丢，确认 receipt 不等统计，数字永不由本地 +1 构造。
- REST Feed/detail、单目标和批量 hydrate 使用同一 verified actor reader。公开 persisted GraphQL 是 service-principal 公共内容切片，其 viewer 缺席不得冒充匿名未赞；个性化由独立受信 actor 互动切片组合，不伪造 Persona header、不强迫 App 切换 transport、不将私有互动缓存到公共值。

<a id="req-006"></a>
### REQ-006 旧请求隔离与有界可见区刷新

- enqueue、ACK、明确拒绝及身份切换推进相关 mutation/request epoch；旧网络响应、磁盘 hydrate 和旧 capability 不得进入缓存或覆盖新确认。关系、资料、能力来源版本和统计代际分别比较，不能用一个版本代表整个复合视图。
- 页面导航只传身份与可比较初始值，不把 viewer 返回值作为第二写真相。正文回放须有真实权限/撤权 replay policy，失败不切 Mock/离线替代，源绝对期限不因逐层接收续长。
- 页面进入、前台/网络恢复和命令后合并当前可见目标的单次 batch；唯一生命周期协调器去重、singleflight 并遵守退避与总预算。持续驻留刷新只有一个有 QPS/批大小上限的调度器，不逐控件 timer，不因点赞重排不可变推荐窗口。
- 内存/磁盘与 LRU 有容量上限，但未决意图和版本栅栏不被普通淘汰丢失。正常前台可见目标的 5 秒端到端收敛是待实测目标，后台/断网单列，不以局部刷新成功证明跨设备完成。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 浏览器与作者主页状态同步

- GIVEN 内容创作者或浏览者具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“浏览器与作者主页状态同步”对应的公开行为。
- THEN viewer、profile 与 feed 消费同一 canonical `RelationshipCapabilityView` 关系矩阵。
- AND 同一交互的本地 outbox 只存在一份 canonical entry；旧字段或错误 JSON 类型不会被迁移成待同步命令。
- AND Feed/详情的同 actor 权威结果按本对象版本/epoch hydrate；未附着不回滚当前态，当前 pending 只覆盖本目标按钮，数字不做本地加减。
- AND 关注云确认、点赞按钮乐观和统计最终一致分别呈现，read failure、outcome unknown 与确定拒绝不混淆。

<a id="gwt-002"></a>
### GWT-002 切 actor 与迟到回调不串分区

- GIVEN A 的查询、写入或磁盘 hydrate 尚未结束，A 可分别为登录 Persona、可信匿名 Persona 或 device-only。
- WHEN 切换 B，旧请求返回，再切回 A 或从匿名进入登录身份。
- THEN B 不被 A 的 bool、receipt、数字或 pending 污染；A 停止发送且回到 A 才按原身份/期限恢复，匿名意图不搬移。
- AND 身份来自 verified principal，不从 isGuest 推断 device；错 actor/target/generation 的响应被拒收而非当新事实。

<a id="gwt-003"></a>
### GWT-003 hydrate 与 durable acceptance 按对象合并

- GIVEN 磁盘有多个对象，读取被阻塞。
- WHEN 本地新增一个意图、删除另一个意图，随后释放旧快照；另分别注入持久写失败与容量满。
- THEN 已变动对象保留新 revision/tombstone，其他未变动磁盘对象恢复；不整包覆盖，也不因一项变化丢弃所有磁盘项。
- AND 持久写有序，失败/容量满不宣布 durable acceptance、不悄悄丢弃已有 unknown，非法旧记录不被补字段转成新发送命令。

<a id="gwt-004"></a>
### GWT-004 单飞反转、同键恢复与统计解耦

- GIVEN 同 actor/target 已发送一次赞，响应丢失，用户继续取赞再点赞。
- WHEN 原命令仍 unknown、恢复回执或与到期终结并发，随后统计读取失败。
- THEN 原命令每时刻最多一个 flight，后继不绕过前驱且只保留最终未发送意图；重试原键/依据/版本/期限不变。
- AND authority 终结前本地到期只停发；回执确认后不等统计、不补发，当前态相同不冒充历史成功。明确拒绝只撤本 intent，不回滚其他成功动作。

<a id="gwt-005"></a>
### GWT-005 未知本人态与不可用数字不伪造业务值

- GIVEN 合法主内容，本人态成功/未知与统计 available/stale/unavailable 各组合，且本地命令有/无。
- WHEN 渲染、点击或收到较新 receipt。
- THEN 无命令读失败不显示 pending；本人未知保留稳定加载/恢复入口且先权威读，不盲 toggle；有 pending 时读取失败不删除意图。
- AND 数字无可信值只占位数字，同 actor 旧值按期限标 stale，有效零正常显示；坏 required/available 字段仍 decoder failure，不兜底零。receipt 只确认本人态，统计保持 10 再更新 11，不显示 12。

<a id="gwt-006"></a>
### GWT-006 REST 与公开 GraphQL 的 actor 组合隔离

- GIVEN 登录 Persona、可信匿名 Persona、device-only、无凭据和非法凭据分别读取同一内容。
- WHEN 经 REST Feed/detail/Reaction 点查及公开 GraphQL 加独立私有互动切片组合。
- THEN REST 同 actor 的单/批量互动一致；公开 GraphQL 本人态缺席是声明的不适用而非未赞，私有切片仅由受信 actor/正式委托读取，非法凭据不降级匿名。
- AND 同一公共内容缓存跨 viewer 不包含或泄漏本人态；未承诺个性化的公共切片不伪造 Persona header，也不强迫 App 改 transport。

<a id="gwt-007"></a>
### GWT-007 旧缓存与能力不能覆盖确认，刷新有界

- GIVEN 旧网络/磁盘/主页 capability 请求已发出，随后本地 enqueue、ACK 或明确拒绝推进本目标 epoch。
- WHEN 旧数据迟到、LRU 淘汰、页面重入、前台/网络恢复或另一设备改变关系。
- THEN 旧结果既不入缓存也不覆盖共享新状态，confirmed 版本栅栏与未决意图不会随普通 LRU 丢失；不同版本域不互比，合法更新统计下降可见。
- AND 正文只按真实 replay policy 回放且继承源绝对期限；可见目标一次合并 batch/单飞，生命周期恢复不绕退避，无逐控件 timer、全 Feed 清空或点赞重排旧窗口。在线前台目标以同事实实测收敛，断网/后台不冒充 5 秒通过。

## 6. 依赖

- 前置要求：[`content-display-consistency`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 分区、持久化与 unknown 恢复尚缺当前证据

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：`REQ-001`～`REQ-004` 的当前语义已替换“两个 bool 即足够”和“本地到期直接失败”；旧 `GWT-001` 绑定不证明 actor 分区、逐对象 hydrate、persist 成功与权威同键终结。
- 完成判定：`GWT-001`、`GWT-002`、`GWT-003`、`GWT-004` 按新断言取得 local_contract、真实 Remote 恢复及适用双真机证据；Reaction/User 各自权威仲裁反例通过前不开放新协议发送侧。

<a id="open-002"></a>
### OPEN-002 互动附着与统计分型尚缺单轨端云证据

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：`REQ-005`、`GWT-005`、`GWT-006` 尚待 owner typed slice、严格 mapper、REST/公开 GraphQL 与私有组合及设备 UI 反例；不能把合法公共缺席或 HTTP 200 当互动完整成功。
- 完成判定：`GWT-005`、`GWT-006` 的所有身份/子读组合有当前 `spec_ref`，无本地 +1、假零、假 pending、匿名身份推断或公共缓存泄漏。

<a id="open-003"></a>
### OPEN-003 旧缓存防覆盖与可见刷新成本尚缺证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：`REQ-006` 与 `GWT-007` 尚缺 production replay policy、网络/磁盘 epoch 竞态、跨设备恢复和批准负载下的端到端新鲜度证据。
- 完成判定：`GWT-007` 的可控迟到反例、真实缓存/Remote、前台合并刷新次数、源绝对期限与双真机同候选读回分别通过；未批准峰值/资源或 skip 不证明 5 秒达标。

## 8. 待实现验收的测试绑定

以下仅定义后续 `spec_ref` 的断言落点，不声明现有 runner 已实现或通过新语义；每条 GWT 需逐行为绑定，不以整文件标注代替断言。

- `quwoquan_app/test/local_contract/journeys/viewer_profile_state_sync/viewer_profile_state_sync__local_contract_test.dart` 与 `quwoquan_app/test/local_contract/journeys/cross_page_interaction_consistency/cross_page_interaction_consistency__local_contract_test.dart` 扩展绑定 `GWT-001`、`GWT-002`、`GWT-005`、`GWT-007`。
- `quwoquan_app/test/local_contract/runtime/transport/state_sync/client_state_sync_outbox__local_contract_test.dart`、`quwoquan_app/test/local_contract/service/content_service/content/post/post_interaction_state__local_contract_test.dart` 扩展绑定 `GWT-002`～`GWT-005`；同 Post 目录 `content_cache_services__local_contract_test.dart` 扩展绑定 `GWT-007`。
- `quwoquan_app/test/api_integration/service/content_service/content/content_reaction/content_reaction_remote__api_integration_test.dart` 扩展绑定 `GWT-002`、`GWT-004`～`GWT-006`；公开 GraphQL 与私有组合的 service 专项在 `quwoquan_service/services/content-service/tests/api_integration/content/content_reaction/` 补真实 owner reader 用例，尚未实现。
- `quwoquan_app/test/user_acceptance/service/content_service/content/content_reaction/like_post__user_acceptance_test.dart` 与 `quwoquan_app/test/user_acceptance/journeys/profile/profile_journey__user_acceptance_test.dart` 扩展绑定 `GWT-001`、`GWT-002`、`GWT-004`、`GWT-005`、`GWT-007`，用双真机动作、同 actor/target receipt、服务读回与来源水位区分 UI 和云确认。
- 新协议引用：`quwoquan_service/services/content-service/contracts/content/content_reaction/`、`quwoquan_service/services/content-service/contracts/content/post/projections/`、`quwoquan_service/services/user-service/contracts/relationship/persona_relationship/` 与现役 capability owner；字段、错误/恢复、page surface 和 readiness 登记仍只由 contracts 拥有。
