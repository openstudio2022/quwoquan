# L3 Story：社交图谱读取 (`social-graph-read`)

> 所属能力：[`persona-follow-graph`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计引用：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为管理身份、Persona 或关系的用户，
我希望分页主键与排序必须围绕 `FollowEdge.createdAt` 或等价稳定游标，
从而安全地维持身份、画像与关系状态。

## 2. 范围与非目标

### In Scope

- “社交图谱读取”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 社交图谱读取

- 分页主键与排序必须围绕 `FollowEdge.createdAt` 或等价稳定游标。

<a id="req-002"></a>
### REQ-002 分页主键与排序必须围绕 FollowEdge.createdAt 或等价稳定游标

- 分页主键与排序必须围绕 `FollowEdge.createdAt` 或等价稳定游标。
- 公开读取必须遵守分身可见性与 block 过滤规则。
- 被 block 或 strict isolation 的主体，在列表与能力读取中必须使用一致的不可见或受限语义。
- 列表分页不能因为过滤而串页或重复页。
- 关系能力读取不得泄露超出产品允许范围的 block 事实。
- 内部可以基于 owner 审计映射做治理，但对外列表不得暴露 owner 关联。
- 分身停用后，其记录 follow 图谱如何继续公开展示，必须服从 `persona-profile-subject-and-visibility` 的公开可见性合同。

<a id="req-003"></a>
### REQ-003 服务本地契约引用边界

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

<a id="req-004"></a>
### REQ-004 资料页社交统计、关系列表与私信入口必须由公开对象能力组合

- 关注数、粉丝数、圈子数及其分页列表必须从各 owning object 的具名 reader/public seam 读取，不得在 presentation 或 runtime shell 拼接私有 store、adapter 或派生计数。
- 列表页必须使用稳定 cursor；重复页、过滤后的空洞与局部失败不得被包装成“没有关系”。
- 关注、取关等关系动作必须经 `persona_relationship` command；从资料统计页发起私信只能经 `chat.conversation` 的公开 command 创建或复用会话，不得直写聊天投影。
- 单一区块失败不得清空其他已成功区块；动作失败必须保留动作前关系态与可重试入口。

<a id="req-005"></a>
### REQ-005 双向分页与图内搜索有界组合，安全失败不能变为空页

- 关注与粉丝列表分别经 owning object 的 named reader 读取；公开资料、轻量查看者关系和必要的打招呼/会话能力按页批量组合，依赖往返次数不随页内人数线性增长，普通关注按钮不加载无关完整会话能力。
- cursor 必须绑定列表所属公开主体、方向、查询条件、查看者权限上下文与最后扫描位置并防篡改；错误上下文复用须拒绝。相同关注时间也能稳定 seek，在关系未变更的一次遍历中不重复不遗漏，刷新后能看到新关注，不承诺任意并发取关/再关注下的全局快照。
- 有界权限过滤可以产生短页或空页并继续返回可用的下一游标；依赖失败必须返回失败或合同明确的局部不可用，不吞安全 reader 错误、不过滤成成功空集，不泄露屏蔽细节与 owner 关联。
- 已授权关系列表的搜索保留昵称和公开用户号子串匹配，仅在调用者可读取的图范围内查询；无匹配与达到搜索预算必须可区分，不能为填满一页扫描整个粉丝图，也不能开放全站关系枚举。
- 千级与万级出边、千万级单目标入边下均按显式页大小、扫描预算和截止时间提供结果或明确的预算失败；返回条数上限不等于扫描上限，普通分页与搜索的性能证据分别裁定。

<a id="req-006"></a>
### REQ-006 社交统计按 Persona 隔离，公开总数不等于查看者过滤总数

- 关注数、粉丝数属于各自公开 Persona，而不是 owner 的多分身合计；本人点赞作品数与作品获赞数含义分离，由各自 owning reader 提供，不能共用一个含义不明的数字。
- 同一 owner 下另一分身的关系变化不得改变当前分身计数。实际关系变化由已提交事实驱动统计，no-op、同键重放、重复/旧事件不重复贡献，双向屏蔽、取关和生命周期清理按实际贡献撤销。
- 公开统计遵守自身可披露口径，不承诺等于当前查看者经过过滤的列表总量；不能安全披露时省略或受限，不遍历全图计算个性化总数。
- 统计可在关系确认后短暂落后，按钮确认不等待数字，也不因此重发写入。新鲜、带来源的旧值、不可用及权威零值按 canonical 合同区分，读取失败不能补零；合法取关造成的新版本数字下降必须展示。
- 正常声明负载下，在线前台可见统计从源提交到展示的端到端 P99 收敛目标为 5 秒；未证明刷新成本或超过新鲜度边界时明确陈旧/不可用，不把局部时延分位数相加当成整体证明。

<a id="req-007"></a>
### REQ-007 普通缓存有界陈旧，权限与读己之写始终以权威为准

- 可共享公开资料、社交统计、有限关系候选热页与查看者私有关系状态分离；环境、主体、发布身份及查询上下文不匹配的内容不得回放，不将 owner 私有快照当公开 Persona 真相。
- 同一缓存权威任期内已生效的失效不得被迟到旧读重新覆盖；缓存故障或已知切换只允许有界回源，不能回退无限制、无权限校验或缓存里的成功回执。
- 普通缓存仅承诺包括故障切换在内的有界陈旧。源事实的硬期限不可因重新填充、层间传递或旧副本提升而续长；超过期限、最低可接受版本或无法证明读取资格时返回 canonical failure/不可用，不伪装成新鲜成功。
- 当前权限裁决、名额、命令结果恢复与本主体读己之写不消费普通缓存的陈旧宽限；撤权与删除不因缓存或回滚复活。公开值不得泄露其他查看者的关系事实。
- 关系命令确认只精准更新同主体目标状态并使相关候选页失效；统计缓存须等待统计事实提交后失效，不在统计仍旧时重新获得完整寿命。缓存或可选统计失败不能否定已提交命令。
- 前台进入、恢复与命令后对可见目标合并批量刷新；不得逐控件无限轮询或全图缓存。未取得运行容量证据时，不把持续驻留页的刷新目标视为已实现保证。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。
- canonical：`quwoquan_service/services/user-service/contracts/relationship/persona_relationship/object.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/relationship/persona_relationship/fields.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/relationship/persona_relationship/operations.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/relationship/persona_relationship/errors.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/relationship/persona_relationship/storage.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/persona_management/persona/fields.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/account/user_account/fields.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/account/user_account/operations.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/account/user_account/storage.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/profile_projection/creator_runtime_profile/object.yaml`
- 分页、搜索授权、批量能力、统计可用性与缓存有效性的确切字段、具名读面和错误恢复由 owning User contracts 声明，不在本节点维护第二份 schema。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 社交图谱读取

- GIVEN 管理身份、Persona 或关系的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“社交图谱读取”对应的公开行为。
- THEN 分页主键与排序必须围绕 `FollowEdge.createdAt` 或等价稳定游标。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 资料统计页分页读取关系与圈子并从公开命令发起关系动作或私信

- GIVEN 查看者以 production Remote composition 打开真实用户资料统计页，目标具备可读的关注、粉丝和圈子事实。
- WHEN App 分别经 owning object 的公开 reader 加载计数与分页列表，并按 relationship capability 发起关注或取关。
- WHEN 查看者从目标资料页发起私信，App 只经 `chat.conversation` 公开 command 创建或复用会话，再导航到 canonical conversation。
- THEN 各列表使用稳定 cursor、无重复或串页；统计和明细均受 block、visibility 与 persona isolation 披露策略约束，公开总数不冒充按当前查看者过滤后的列表总量。
- AND 任一区块失败只显示该区块的 canonical recovery，不得把失败包装为空列表或清空其他成功区块。
- AND 关系命令或私信命令失败时保留动作前状态与重试入口；只有 production Remote 读回收敛后才更新最终关系态或进入会话。
- AND 只有绑定同一 candidate、真实 Provider 与 production Remote 的 Android 物理设备及 iPhone 物理设备 `ReadinessResultBundle` 均通过时，本验收场景才计通过；Widget、模拟器、动态 skip 或 typed double 不计。

<a id="gwt-003"></a>
### GWT-003 双向列表、批量能力与搜索游标在权限和预算内收敛

- GIVEN 目标有多页关系、相同关注时间、不同可见性主体及普通 Persona/Creator 资料，查看者仅获准读取其权限内关系。
- WHEN 分页、子串搜索、改变页大小并尝试跨主体、方向、关键词或查看者复用游标；同时使必要资料或安全依赖失败。
- THEN 具名双向 reader 的 seek 顺序稳定，在关系未变更的遍历中无重无漏，刷新可见新关注；过滤后短页或空页仍按最后扫描位置续接，不以填满页面为由无界扫描。
- AND 20 项与 100 项页面的资料和关系 enrichment 保持相同固定批量调用上界，不逐条读取完整 Greeting/Chat 能力；可见性与安全依赖失败不成为假空页或可访问条目。
- AND 错误上下文或被篡改游标拒绝，图内昵称/用户号子串搜索只返回当前权限内关系；无匹配与达到预算明确区分，不开放全站社交图枚举。
- AND 千级、万级出边与千万入边的真实引擎结果证明实际扫描、依赖往返和总耗时符合声明预算，或明确返回预算失败；小数据通过不替代该容量证据。

<a id="gwt-004"></a>
### GWT-004 多分身计数、重复事件与统计延迟不改变已确认关系

- GIVEN 一个 owner 有两个不同 Persona，分别具有关注、粉丝和作品互动事实，且统计消费者可延迟、重放或重建。
- WHEN 一处分身关注、取关或双向屏蔽，并交错投递重复、旧版本、合法版本跳号的事实与同水位重算结果。
- THEN 仅对应 Persona 的实际贡献变化，另一分身计数不串账；本人点赞作品数与作品获赞数不混用，合法更新后的数字下降不会被当旧值丢弃。
- AND no-op、原键重放及重复/旧事件不重复计数；双向屏蔽按双方真实贡献清理，重算与增量不重复或遗漏，永久撤销不复活贡献。
- AND 关系回执完成即可结束命令待确认，统计延迟不重发关系写入；无可靠数字只呈现合同允许的不可用，权威零值、旧值和故障严格分开。
- AND 公开总数仅按其披露口径展示，不能披露则受限，不泄露 owner 关联，也不以 viewer 过滤明细长度冒充全局总数。
- AND 同一事实在声明负载及在线前台可见条件下测量提交至显示的端到端 P99 5 秒目标；缺少生产消费者接线、刷新容量或双物理设备读回时不认定展示闭环。

<a id="gwt-005"></a>
### GWT-005 迟到回填与 Redis 旧副本提升均不能续长旧事实寿命

- GIVEN 公开资料、统计或有限候选热页已缓存，旧源读取被暂停，随后发生权威更新、投影提交和缓存失效；另有复制落后的 Redis 副本。
- WHEN 释放旧填充，并分别触发当前任期内竞争、代际丢失或旧副本提升，再从 App 回放或刷新同一可见对象。
- THEN 当前任期已生效的失效使迟到回填被原子拒绝，缺失代际不能重用旧标识；只有真实缓存命中证据而非两次请求成功才能证明缓存路径接通。
- AND 旧副本提升允许的普通旧值严格受源读取时确定的绝对期限约束，重新填充或跨层回放不能续期；到期或无法证明有效性时明确不可用，不能声称跨切主全局线性一致。
- AND 当前权限、命令恢复、名额和本主体最低版本读取绕过普通缓存；已确认关系不被旧 bundle/hydrate 覆盖，缓存故障的回源有界且不否定已提交命令。
- AND 关系和统计分别在各自事实提交后失效；读取失败不缓存为零或空，公开缓存不含私有 viewer 事实，切主体/环境/发布身份不串数据，删除或收紧权限不复活。
- AND 可见区刷新按合并批次与总预算执行，候选页及内存/磁盘缓存容量有界；服务缓存原子性、真实 failover 与双设备展示各取对应层证据，不相互代替。

## 6. 依赖

- 前置要求：[`persona-follow-graph`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)、[批量读取 DEC-007](../design.md#dec-007)、[统计 DEC-008](../design.md#dec-008)、[缓存 DEC-009](../design.md#dec-009)、[App 确认 DEC-010](../design.md#dec-010)。

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 社交图谱读取 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明 `GWT-001` 的稳定分页语义与 `GWT-002` 的多区块 Remote 组合、关系动作、私信跳转和失败恢复均满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 与 `GWT-002` 均有职责匹配的真实 production runner 与逐场景 `spec_ref`；`GWT-002` 还必须取得绑定同一 candidate 的 Android 与 iPhone 物理设备 `ReadinessResultBundle`，failed、blocked、skipped、模拟器或测试 double 结果均不计通过。

<a id="open-002"></a>
### OPEN-002 有界图读取、Persona 统计与缓存故障边界的合同及证据

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：图内远端搜索与现役仅本地检索声明存在冲突，批量 reader/cursor、Persona 统计归属、统计可用性、源绝对期限及 Redis 同任期原子失效尚缺 User owning contracts 和真实链路证明；不能以接口成功、静态索引或短 TTL 代替性能与一致性。
- 完成判定：`GWT-003`、`GWT-004`、`GWT-005` 全部结果取得逐子句有效 `spec_ref`；真实 PG 证明 seek/搜索权限、批量成本和千级/万级/千万基数预算，真实 worker 证明 Persona 贡献及重算，真实 Redis 证明同任期 CAS 与落后副本提升仍受原硬期限约束，同候选双物理设备证明前台可见状态与统计恢复。缺少容量画像、设备或故障资源时保持未关闭，不拿本地 double、清空缓存或分项 P99 相加替代。
- 依赖：User 关系搜索授权与 batch、Persona 社交统计、缓存 keyspace/期限和配置合同唯一归属；公开发布身份与受管隔离测试资源；关注命令终结的权威依据。
