# L3 Story：互动状态状态计数 (`reaction-state-counter`)

> 所属能力：[`publish-comment-reaction`](../spec.md)

> Journey / Scenario：[`JNY-003 / SCN-008`](../../../spec.md#scn-008)

> 设计归属：[L2 DEC-001](../design.md#dec-001)、[DEC-005](../design.md#dec-005)、[DEC-006](../design.md#dec-006)、[DEC-007](../design.md#dec-007)、[DEC-008](../design.md#dec-008)

## 1. 用户价值

作为内容创作者或浏览者，
我希望 Post 点赞与 Comment 赞踩分别由同一 actor 的服务端事实驱动，按钮及时响应、数字不伪造，并在弱网后可恢复命令结果，
从而完成可恢复的内容创作、发现或互动。

## 2. 范围与非目标

### In Scope

- “互动状态状态计数”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 互动状态状态计数

- Post 仅表示未赞/已赞的布尔意图，Comment 保留未反应/赞/踩三态互斥及登录要求；两者不共用 bool 队列，不将 Post 取赞解释为不感兴趣或 Comment 踩。
- 本人 Reaction、命令投递结果与统计新鲜度分别表达。点赞按钮可乐观，数字始终使用可验证的服务端统计基线，不做本地 +1；命令确认不等待统计追齐。
- 按 [DEC-002](../design.md#dec-002) 不恢复 Post 收藏；实体「想去」维持现役 owner 与入口边界，不是本 Story 的新增功能。
- 确定拒绝不产生成功事实；提交结果未知不冒充拒绝，提交成功后的读回/统计失败不改变既有成功。
- Alpha 经对象级本地 adapter 执行同一 command/query 合同并读回计数；Beta/Gamma/Prod 仍只经 production Remote。游客点赞与需登录动作按现役 authMode 分别验证。

<a id="req-002"></a>
### REQ-002 服务本地契约引用边界

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

<a id="req-003"></a>
### REQ-003 同一 verified actor 的权限与读写身份

- 写入、状态点查、Feed/详情批量附着必须解析同一受信 actor；已登录 Persona、可信匿名 Persona、device-only 凭据分别验证，不能从游客标签推断 device，也不把非法凭据降级成匿名。
- Persona 与 device 的互动不并账；登录、退出或切 Persona 不搬移未决意图，不向其他 actor 披露本人互动。
- 新互动只接受 published 且审核、可见性和当前 actor 访问资格成立的 Post；Comment 还必须自身可互动且父 Post 合格。资格未知或依赖失败拒绝新写，读取不泄露受限目标存在性。签发过写依据不代替本次权限校验。

<a id="req-004"></a>
### REQ-004 有限命令窗口、并发仲裁与确定回执

- 每次用户决定持有稳定命令身份和不可改写的目标意图、前置版本及受信写依据；重试复用原身份，反转是后继意图，不通过客户端墙钟覆盖他人更新。
- 受签名写依据绑定当前 actor、canonical 目标、允许动作、前置版本及服务端发行期限；默认最大写接纳窗口 72 小时，receipt 保留至少 96 小时。重试或重新获取依据不能续长旧命令，签名不授予当前动作权限。
- 每个通过校验的新命令，包括业务值已满足的 no-op，均推进本 Reaction 的版本一次并保存确定回执；同键重放不推进。no-op 不增加计数、不产生业务变化事件，不把“无变化”当成“重放”。
- 命令回执来自冻结提交结果；本人状态/版本即可结束 pending。统计、推荐、序列化或后置读失败均不能把已提交动作改报未提交，响应丢失经同键恢复。
- 超过接纳期限仅停止发写；同键恢复必须与原写争用同一权威命令仲裁，返回已提交、确定拒绝或不可再执行的过期终态后才撤去 unknown。receipt 已清理时只能报告历史不可判定并读取当前事实，不能以当前状态相同证明旧命令成功，也不能复用旧键新写。

<a id="req-005"></a>
### REQ-005 目标撤权后不复活，清理有界可恢复

- Post 删除或权限收缩后的公开读取由目标 owner 当前资格保护；跨 owner 的在途互动可能内部短暂提交，但不能因此恢复公开可见性、统计或推荐贡献。不承诺跨 owner 分布式原子撤销。
- Reaction 观察到永久撤权后必须先封闭该目标全部固定写栅栏，再按每次最多 500 成员及单次时间预算清理，并持久保存续跑位置；尚无成员的写分区同样必须封闭，迟到新增不能复活。
- 清理只接受已验证 owner 生命周期事实，经专用内部授权幂等补偿，不依赖失效用户凭据或 App 72 小时窗口；普通调用者不可伪造清理授权。目标永久关闭及 actor 关闭/退役的抑制事实、成员版本与安全水位不能被回滚或无条件过期清除。

<a id="req-006"></a>
### REQ-006 统计由成员贡献收敛且可对账重建

- target 互动统计归 ContentReaction；Post/Comment 仅组合统计读切片，不因赞/取赞修改作者编辑时间或伪造内容编辑事件。本人点赞作品数、作品获赞数与 User Persona 社交统计不混用。
- 事件重复、乱序与 no-op 造成的合法业务版本跳号不重复计数。每个成员已应用版本、当前贡献与分桶增量原子应用；同版本异内容、负数或来源缺失必须报警，不以钳零掩盖损坏。
- 周期汇总给出可比较的统计版本、来源处理水位和重建代际；取赞造成的新版本数字下降合法。增量与固定来源水位重建不得重复包含同一贡献，旧代际汇总不能覆盖新代际。
- 业务版本与实际运输序列分开；消费者只推进连续已应用水位，毒事件保留原事实与失败原因、停止所属分区而不阻塞其他分区，旧租约不能推进新 owner 的应用水位或产生重复效果。
- 正常事件与点查不执行全目标重算；有界重算只用于修复/对账。源事实不可得或未追平时统计为未就绪/不可用，不返回成功零值；新品有效零须有明确发布初始化或权威空态证明。

<a id="req-007"></a>
### REQ-007 统计新鲜度有界且与命令状态正交

- typed 统计结果区分 available、stale、unavailable：有效结果必须有合法数字和来源水位，旧值必须有可追溯来源；无可信值只占位数字，不能补零、隐藏整个内容或生成假 pending。具体 shape 只由对象 contract 声明。
- 统计缓存沿用来源的绝对失效期限；重新填充、下游缓存接收和缓存故障切换不能续长旧事实寿命。超过硬期限或不满足最小版本时返回 typed unavailable；权限与命令恢复读绕过普通缓存。
- 正常批准负载、在线前台可见目标的 commit→展示端到端 P99 目标不超过 5 秒；投影 2 秒、服务缓存 1 秒和 App 合并刷新 2 秒仅为预算，不能相加各自分位数证明达标。持续驻留刷新成本未取得容量证据前只可报告 last-known，不宣称已满足 5 秒。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。
- Reaction 命令、回执、状态/统计切片、生命周期与保留策略：`quwoquan_service/services/content-service/contracts/content/content_reaction/` 下各自的 `object.yaml`、`fields.yaml`、`operations.yaml`、`errors.yaml`、`storage.yaml`、`events.yaml`。
- Post/Comment 的资格与组合读面：`quwoquan_service/services/content-service/contracts/content/post/operations.yaml`、`quwoquan_service/services/content-service/contracts/content/post/projections/`、`quwoquan_service/services/content-service/contracts/content/comment/operations.yaml`。
- 上述新增写依据、恢复与统计分支须由各 owner 完成 authoring/verify/codegen 后才能进入发送侧实现；本规格不定义新字段 schema、错误码或路由。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 互动状态状态计数

- GIVEN 内容创作者或浏览者具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“互动状态状态计数”对应的公开行为。
- THEN Post 未赞/已赞与 Comment 未反应/赞/踩保持独立；按钮可乐观但总数只展示最近有效服务端事实。
- AND 确定拒绝不产生伪成功，响应丢失保留 unknown；已提交命令不因统计滞后重复发送。

<a id="gwt-002"></a>
### GWT-002 按钮立即响应，计数不重复叠加

- GIVEN 同一 actor 的 Post 已知未赞且有效统计为 10。
- WHEN 点赞后得到确认回执，而统计尚未追上，随后收到有效统计 11 或他人并发后的 15。
- THEN 点击到乐观按钮反馈 P95 目标不超过 100ms，数字仍为 10；回执结束命令 pending，不等待数字、不补发。
- AND 后续分别显示 11 或 15，不显示 12 或 16；取赞后的更新数字下降也被接受。

<a id="gwt-003"></a>
### GWT-003 读失败、合法零和未知本人态独立

- GIVEN 无本地命令或已有 pending，分别遇到本人状态未附着与统计子读失败。
- WHEN 组合合法主内容与 typed 子读结果。
- THEN 无命令不产生 pending；已有意图不因读失败消失。本人完全未知不画成已确认未赞、不盲目 toggle，同 actor 旧态仅作 stale。
- AND 有来源旧数字按期限展示，无可信数字只占位数字；有证明的零正常展示。旧必填数字或新 available 分支缺数字/坏类型均为协议失败，不私自补值或从坏 DTO 救字段。

<a id="gwt-004"></a>
### GWT-004 verified actor 与真实目标资格矩阵

- GIVEN 已登录 Persona、可信匿名 Persona、device-only、无凭据与非法凭据，及 published、draft、hidden、deleted 和 actor 无访问权目标。
- WHEN 经真实 Post/Comment owner 资格 reader 执行写入与同 actor 点查/批量附着。
- THEN 仅获准身份与目标产生对应关系；匿名 Persona 不写入 device 分区，device 状态可由相同 actor 读回，非法凭据不降级匿名。
- AND Comment 额外满足登录、评论可互动和父 Post 资格；reader 故障拒绝新动作，受限查询不泄露存在性。恒返回 active 的替身不构成本验收的权限证据。

<a id="gwt-005"></a>
### GWT-005 新 no-op 是版本栅栏而非重复业务事实

- GIVEN 旧写基于旧版本仍未到达，而较新意图已满足当前业务值。
- WHEN 以新键接纳 no-op，再放行旧写，并以同键重放 no-op。
- THEN 新 no-op 版本恰好加一、回执明确无变化且非重放，旧前置版本被拒绝；同键回放版本不变且明确重放。
- AND 无额外业务变化事件或贡献；事件消费者接受合法版本跳号，不等待不存在的 no-op 事件。

<a id="gwt-006"></a>
### GWT-006 同键恢复与过期终结只产生一个赢家

- GIVEN 已验证写依据、不可变命令身份、72 小时接纳窗口及至少 96 小时回执保留。
- WHEN 提交后丢响应，或原写与到期恢复被屏障控制并发，或 receipt 保留结束后旧写再次到达。
- THEN 原写与恢复通过同一权威仲裁只产生一个确定终态；重试不改变 actor/目标/前置版本/期限，不允许伪造、换 actor 或续期限的依据。
- AND 回执存在时返回原提交结果；已过期依据在 receipt 物理清理后也不得新执行。历史不可判定仅回读当前事实，不伪称从未提交或历史成功；authority 不可用仍为 unknown，不由本地定时器终结。

<a id="gwt-007"></a>
### GWT-007 删除扫空后的迟到互动不能复活

- GIVEN Like 已完成资格检查，分别停在写事务前、事务中和删除清理扫空后的屏障点。
- WHEN 目标 owner 删除，Reaction 先封闭全部固定写栅栏再清理，随后释放 Like 并重启清理消费者。
- THEN Post 公开面立即遵守删除资格；封桶与 Like 真实竞争后不再新增活跃成员，最终无活跃贡献、计数或推荐复活，不宣称跨 owner 原子事务。
- AND 每次清理最多 500 成员且到时间预算即退出，持久续跑不漏成员；未创建分区、旧 worker、重复生命周期事实与同成员新版本均覆盖。外部用户不能调用内部补偿绕过鉴权。

<a id="gwt-008"></a>
### GWT-008 成员贡献、汇总与重建收敛同一事实

- GIVEN Like→Unlike→Like、重复/旧事件、合法版本跳号与删除/actor 关闭事实。
- WHEN 实际后台消费者应用贡献，并在固定来源水位的重建期间继续增量、切换统计代际。
- THEN 成员版本与贡献增量原子应用，重复无效果，同版本异内容和负数明确失败；旧汇总不覆盖新代际，新版本合法下降可读。
- AND 毒事件不被当成已应用，所属分区连续水位停止而其他分区继续；旧租约 worker 不能推进水位或重复效果，恢复保留原事实而不跨洞取最大水位。
- AND 统计与权威成员 oracle 一致，不改 Post 作者编辑时间、不逐事件全量计数；真实 production worker 至少自动追齐一条链，手动 drain 不能证明生产接线。

<a id="gwt-009"></a>
### GWT-009 缓存失效与故障切换不续长陈旧事实

- GIVEN 旧来源读取在飞行，较新统计已提交并失效缓存；另有失效尚未到达和缓存落后副本提升场景。
- WHEN 释放旧填充并在前台读取统计或带最小版本的本人状态。
- THEN 同任期失效后的旧填充被拒绝；失效前或故障切换回退只允许原来源绝对期限内陈旧，重新填充及 App 接收不续期，超期明确 unavailable。
- AND 安全/读己之写绕过普通缓存；统计提交后才触发统计失效。正常目标负载以同一事实的 commit→render 实测 5 秒 P99 目标及刷新成本，不以 HTTP 200 或缓存刚写入证明新鲜。

## 6. 依赖

- 前置要求：[`publish-comment-reaction`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 互动状态状态计数 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“互动状态状态计数”已满足当前规格的真实测试证据。
- 完成判定：`REQ-001`、`REQ-002` 与 `GWT-001` 对应行为满足且真实测试 `spec_ref` 有效；历史数字乐观 +1 的用例不能证明当前规格。

<a id="open-002"></a>
### OPEN-002 按钮、本人态与统计分型尚缺当前证据

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：`REQ-001`、`REQ-007` 的统计分型尚缺 contract、App 单轨实现以及 `GWT-002`、`GWT-003` 对应反例和真实服务/双真机验收证据。工程引用包括 `content_reaction_and_counters__local_contract_test.dart`、`post_interaction_state__local_contract_test.dart`、Reaction Remote api_integration 与 `like_post__user_acceptance_test.dart`；现有结果尚未证明新分型。
- 完成判定：`GWT-002`、`GWT-003` 的严格 decoder、10→10→11、无命令读失败与合法零全部在直接断言处绑定当前 `spec_ref`；不得以旧 UAT 的本地 +1 或文本出现当作 server confirmed。

<a id="open-003"></a>
### OPEN-003 actor 资格与命令仲裁尚缺真实权威证明

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：`REQ-003`、`REQ-004` 的 signed basis、no-op 写栅栏与同键恢复尚缺 owner 合同、实现和真实引擎反例证据，不能启动未经证明的新协议发送侧。工程引用包括 App 的 `guest_device_interaction__local_contract_test.dart` 与 Reaction Remote api_integration、Service Reaction local_contract 和 `http_mongo_transaction__api_integration_test.go`；真实 owner 资格场景尚缺实现。
- 完成判定：`GWT-004`、`GWT-005`、`GWT-006` 的身份/权限、真实并发及 receipt 清理反例在职责匹配的直接断言处绑定当前 `spec_ref`；命令业务结果与当前态不混淆。

<a id="open-004"></a>
### OPEN-004 生命周期封闭与有界清理尚缺竞争证明

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：`REQ-005` 与 `GWT-007` 尚缺全部固定写栅栏封闭、迟到 Like 真冲突、内部授权与有界恢复的实现和验收证据；不能据目标前置检查宣称无复活。工程引用为 Service Reaction local_contract 中的 post deletion consumer/outbox relay 与同对象 API 目录尚缺的真实删除竞争专项。
- 完成判定：`GWT-007` 的真实引擎三个屏障反例、500 成员/时间预算、重启/旧 worker 及不可伪造补偿全部在职责匹配的直接断言处绑定当前 `spec_ref`。

<a id="open-005"></a>
### OPEN-005 统计重建、缓存期限与容量证据缺失

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：`REQ-006`、`REQ-007` 与 `GWT-008`、`GWT-009` 尚缺真实 worker、修复代际、缓存失效/故障切换及前台端到端新鲜度证据；批准峰值、热点基数与故障资源由容量/运行 owner 补齐，不推断已达标。工程引用包括 Service Reaction local_contract、同对象 API 目录尚缺的统计修复与缓存故障专项，以及 `like_post__user_acceptance_test.dart`；存储 race 与容量不由设备 happy path 代证。
- 完成判定：`GWT-008`、`GWT-009` 的当前 source/contract/candidate 贡献 oracle、来源期限、热点有界成本与实测收敛均在职责匹配的直接断言处绑定当前 `spec_ref`；required readiness 仍由 owning operation 登记，无资源、skip、替身或旧指纹不关闭本项。
