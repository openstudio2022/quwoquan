# L3 Story：资料快照版本控制 (`profile-snapshot-versioning`)

> 所属能力：[`auth-profile-snapshot`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为管理身份、Persona 或关系的用户，
我希望当前 Persona 的资料快照按版本读取和更新，且不会混入其他账号事实，
从而安全地维持身份、画像与关系状态。

## 2. 范围与非目标

### In Scope

- “资料快照版本控制”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 资料快照版本控制

- “资料快照版本控制”必须通过父能力公开契约交付可观察结果；失败时返回 canonical failure，不写入成功事实。

<a id="req-002"></a>
### REQ-002 服务本地契约引用边界

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

<a id="req-003"></a>
### REQ-003 资料搜索投影可恢复收敛

- 用户资料创建、资料更新或头像更新已持久化后，搜索投影暂时不可用不得回滚或伪造资料写入成功。
- Persona/User 资料事实与自包含公共投影快照必须同事务写入 `user_profile_search_outbox`；User relay 只发布 durable typed event，不得直接写 Elasticsearch/OpenSearch。
- Search 独占 Provider 投影与 checkpoint；失败不确认 stream，同 event 幂等重放，低版本忽略，资料更新覆盖当前版本，账号关闭以 delete tombstone 防止旧 update 复活。

<a id="req-004"></a>
### REQ-004 资料、统计与查看者互动各按自身版本读取

- Persona 是公开资料唯一写 owner；owner 私有快照、公开作者摘要、社交统计与查看者关系/Reaction 分开读取与缓存，不能从 UserAccount 私有快照回退构造公开 Persona。
- 资料版本只比较同一来源 Persona 的资料；资料更新时间不能充当关系、Reaction 或统计版本，也不能借 Post 发布时间给作者摘要重新计鲜。统计值合法下降不因资料未更新而被拒绝。
- 本地与服务缓存必须保留适用的环境、主体/查看者、发布来源和对象身份，不放宽既有隔离。切账号、切 Persona 或迟到网络/磁盘快照不得覆盖当前主体及更新的已确认互动。

<a id="req-005"></a>
### REQ-005 当前缓存任期的失效与填充原子裁决

- 可缓存资料 miss 在源读取前取得不复用的缓存 generation，回填时仅在该 generation 仍有效、源版本可接受且源绝对期限未到达时填充；代际比较与填充、失效在同一原子裁决中完成，不能先比较再独立写入。
- 同一缓存权威任期内，已生效失效必须拒绝失效生效前启动的旧源读取迟到回填。代际元数据缺失或被驱逐时产生新代际，不复用固定初始值；值、索引、旧代际回收与总容量有上限。
- 资料事实提交成功后才驱动资料失效；统计缓存由统计实际提交后的事实驱动，不能在尚旧的统计回读后获得完整新寿命。可选缓存/投影失败不改变命令已提交结果。

<a id="req-006"></a>
### REQ-006 源绝对期限约束普通缓存，包括旧代际故障切换

- 源读取起点、来源处理水位与不可续长的绝对期限共同约束新鲜度；读取起点不得晚于实际源快照开始。cache 驻留时间不等于源投影延迟，刚填充不代表新鲜，空闲事件流以处理进度而非旧事件时间判断健康。
- 重新填充、服务到 App 传递、缓存恢复或落后副本提升均不得续长同一旧事实寿命；源副本延迟、时钟偏差与各层驻留计入所属新鲜度预算，新的源读取本身也必须满足该预算。
- Redis failover 可能恢复旧 generation 及旧值；当前任期原子填充并不承诺跨 failover 的全局 fencing。普通缓存只承诺在原源绝对期限内有界陈旧，不能把随机新代际或清空缓存测试当作旧代际复活已被杜绝。
- 已知切换、连接或元数据故障按有界回源与并发预算 bypass；超过源硬期限、最低可接受版本或无法证明有效性时返回 canonical unavailable，不补零/空态。负缓存只能来自权威明确不存在，不能缓存依赖失败。

<a id="req-007"></a>
### REQ-007 安全与读己之写不使用普通缓存陈旧宽限

- 当前权限、账号关闭/Persona 退役、关系能力放行与命令结果恢复始终由 authority 裁决；普通公开缓存只有通过当前安全检查后才可展示，旧可见性不授予权限，不承诺撤回已发给客户端的历史数据。
- 已确认互动通过本主体对应回执与权威版本保证读己之写；安全、命令恢复与携带最小版本要求的读己之写查询始终绕过普通缓存，不能因缓存声称版本足够而获得权威资格。权威不可用则明确失败或保持未知，不能以旧缓存宣告历史命令成功。
- App 意图接纳、确认与确定拒绝均使同主体目标的旧读取失效；在飞行网络、磁盘 hydrate 与已存快照同受 mutation epoch 保护，不能只删除缓存项而放过迟到写回。
- 缓存只是加速层，不持有唯一恢复凭据；删除/关闭抑制不因缓存、重建或回滚复活。需要跨 failover 零旧代际接受的更强合同必须另经 durable authority 协调设计与证明，本 Story 不隐式承诺。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。
- 资料 owner：`quwoquan_service/services/user-service/contracts/persona_management/persona/`；owner 私有快照与现役缓存资源声明：`quwoquan_service/services/user-service/contracts/account/user_account/`。
- 独立关系/统计/互动来源：`quwoquan_service/services/user-service/contracts/relationship/persona_relationship/` 与 `quwoquan_service/services/content-service/contracts/content/content_reaction/`；缓存 namespace、generation、源水位/期限、最小版本和 typed 结果只由各对象 `fields/operations/storage` 及服务配置 authoring，不在本 Story 定义 key 或 wire shape。
- 业务可见统计预算与权限口径引用 [social-graph-read REQ-006](../../persona-follow-graph/social-graph-read/spec.md#req-006)、[REQ-007](../../persona-follow-graph/social-graph-read/spec.md#req-007)；资料自身 freshness 由 User owner 显式配置，未冻结不能用现有 TTL 冒充端到端目标。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 资料快照版本控制

- GIVEN 管理身份、Persona 或关系的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“资料快照版本控制”对应的公开行为。
- THEN 通过父能力公开契约交付“资料快照版本控制”的可观察结果。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 资料搜索投影暂时不可用后的重放收敛

- GIVEN 用户资料权威存储可用且搜索投影暂时不可用。
- WHEN 用户创建资料、更新资料或更新头像。
- THEN 资料写入保持已提交，搜索投影不丢失该变化。
- WHEN 搜索投影恢复并执行重放。
- THEN Search consumer 以同一 eventId/profileVersion 幂等收敛到该用户的当前资料版本，Search checkpoint 只在 Provider upsert/delete 成功后推进。

<a id="gwt-003"></a>
### GWT-003 当前任期失效原子拒绝旧填充，故障切换不续旧事实期限

- GIVEN 同一资料缓存已有有效来源与 generation，旧源读取被屏障挂起，随后权威资料更新并完成该任期失效。
- WHEN 释放旧读取回填，或代际元数据被驱逐后旧读取再次返回。
- THEN 旧填充被原子拒绝，后续只返回符合来源/版本的值或明确不可用；代际不因缺失重用初始值。
- WHEN 阻断复制使旧副本仍持旧 generation 与旧值，再经受管授权提升该副本并释放旧填充。
- THEN 普通 cache 至多在原源绝对期限内旧，重新填充或 App 接收不能延寿；当前权限与读己之写仍返回权威事实或明确失败，不从缓存放行。
- AND 源时钟、代际变化、期限、并发屏障、Redis 同槽原子操作及旧代际提升结果分别可核验；清空、重启缓存或替代实现不能证明故障切换边界。

<a id="gwt-004"></a>
### GWT-004 资料与互动独立版本、失效时点及迟到响应安全组合

- GIVEN 当前 Persona 已确认互动，另一 Persona 有独立资料，旧公开摘要、统计、网络请求与磁盘 hydrate 正在返回。
- WHEN 资料更新、统计更新、切换主体及本地命令确认交错，且缓存或可选统计读取发生故障。
- THEN 资料版本/更新时间不覆盖互动版本，合法统计下降可见；只有对应统计提交后才失效统计缓存，缓存失败不推翻命令提交。
- AND 旧主体、旧 mutation epoch 或超过源绝对期限的结果不能覆盖当前已确认态；可共享资料不含私有互动，当前权限失败不以旧可见性放行。
- AND 网络与 hydrate 时序、源期限继承、公开/私有读取隔离、缓存命中、权威失效顺序及双设备同事实呈现分别可核验。

## 6. 依赖

- 前置要求：[`auth-profile-snapshot`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 资料快照版本控制 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“资料快照版本控制”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-002"></a>
### OPEN-002 资料缓存原子代际、源期限与互动隔离尚缺真实证据

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：[REQ-004](./spec.md#req-004)、[REQ-005](./spec.md#req-005)、[REQ-006](./spec.md#req-006)、[REQ-007](./spec.md#req-007) 尚缺当前候选的缓存原子裁决、不可续期来源、Redis 旧代际 failover 与 App 迟到结果隔离证据；现役 owner 私有 cache 或已有 TTL 不证明公开 Persona 读链接通，更不证明安全/读己之写。
- 完成判定：[GWT-003](./spec.md#gwt-003)、[GWT-004](./spec.md#gwt-004) 均有直接完整 `spec_ref` 和分层真实结果；User 先冻结缓存资源/源有效性/资料新鲜度与读合同，再由真实 Redis 并发和旧代际提升、公开/私有 reader、App 网络/hydrate 与双设备读回证明。无故障授权、设备或当前来源证据时保持对应准出阻断，不把本地时序测试当作 Redis 原子/HA 通过。
- 依赖：User Persona/UserAccount 各自 source 与 cache contract；User 关系及 Content Reaction 的独立版本和统计提交失效事实。跨 failover 强 fencing 不在普通缓存承诺内，若未来需要须另行设计，不能以延长 TTL 或扩大旧值放行关闭本项。
