# L3 Story：Human-Agent 全链交付交互 (`human-agent-delivery-interaction`)

> 所属能力：[开发流程治理](../spec.md)
>
> Journey / Scenario：不直接参与用户 Journey；为全部 Journey 提供 Agent 主导且人类 authority 可理解的交付协议
>
> 设计归属：[L2 DEC-008](../design.md#dec-008)

## 1. 用户价值

作为业务发起人、产品与体验负责人、业务验收代表、方案与工程交付负责人、质量与风险负责人、发布运维和渠道运营负责人，我希望 Agent 主动完成可自动化的研究、实施、验证和取证，而只把价值、范围、体验、风险、外部动作、商用和 outcome 决定交给正确角色，从而无需理解仓库内部术语也能掌握交付方向、硬约束、授权边界和最终结果。

## 2. 范围与非目标

### In Scope

- 从概念受理到知识沉淀的 15 个交付阶段，以及每阶段的事前输入、Agent 主导执行、执行中升级、事后验收与准出协议。
- 11 类 `HumanAuthorityRole` 的决定边界，以及每个 `DecisionUnit` 的七类责任、独立输入、硬门和唯一综合裁决。
- 面向人类的选择卡、授权卡、异常卡与事后检查卡，以及补证据、转交正确角色、暂停或停止的安全出口。
- 商用准备、生产 campaign、渠道公开和 outcome 接受的分层决定与 fail-closed 行为。

### Out of Scope

- 具体字段、命令、类、DTO、存储、Harness 投影和外部 authority 接入方式；这些只能由本 Story 将来的独立机器契约与实现细化。
- 用 Reviewer、Agent 建议、多数票、总分或当前聊天参与者身份代替具名 Human Authority。
- 把阶段状态、决定记录、执行日志或结果收据维护为 Feature Tree 之外的产品事实台账。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 十一类 Human Authority 角色保有不可代签责任

每次决定必须指明作答角色；同一自然人可以声明兼任，但不同角色的输入与接受仍分别表达。角色缺失时 Agent 只能请求转交、缩小合法范围或暂停，不得代签。

- **业务发起人**：拥有问题价值、受益对象、紧迫性与不可接受结果；不选择技术实现，以最终问题是否解决为验收。
- **产品负责人**：拥有目标用户、优先级、In/Out Scope、业务规则和产品成功标准；不替方案或风险角色作决定。
- **业务验收负责人或用户代表**：拥有真实任务、目标设备或渠道上的业务可用接受；不得以源码检查或局部测试代替用户场景。
- **体验设计负责人**：拥有信息层级、流程、交互、视觉语义、可访问性与跨设备体验方向；改变产品范围时必须升级给产品负责人。
- **领域方案或架构负责人**：拥有对象边界、依赖方向、事实与契约 owner、质量属性、迁移、恢复和回滚方案；不决定产品价值或视觉偏好。
- **工程交付负责人**：拥有交付拆分、依赖、资源与时间预算、本地实施授权和集成责任；不替产品改范围，不替风险或发布角色接受风险。
- **质量负责人**：拥有风险驱动的验证范围、测试层级、回归、缺陷分级和质量准出；不得把测试存在或 Reviewer PASS 当作执行证据。
- **安全、隐私与法务合规负责人**：拥有权限、敏感数据、第三方、内容权利、保留删除、法规与商用许可硬约束；不可豁免事项不接受其他角色的风险覆盖。
- **发布负责人**：拥有精确候选、发布窗口、放量、停止与回滚 campaign 决定；不单方面宣布产品价值、渠道公开或 outcome 达成。
- **环境运维与可靠性负责人**：拥有环境、容量、健康、SLO、告警、值班、事故止损和恢复接受；不改变产品范围或业务规则。
- **运营、客服与市场渠道负责人**：拥有公开节奏、用户沟通、支持准备、渠道审核上架和反馈闭环；不替代生产技术准入。

<a id="req-002"></a>
### REQ-002 十五阶段均有前中后责任与唯一准出

以下阶段按顺序组成完整交付链；上游准出只提供下游输入，不自动生成下游批准。标明不适用的阶段也必须由对应责任角色给出可理解理由，Agent 不得自行跳过。

#### 阶段 1：概念受理

- 事前输入：业务发起人提供受益者、场景、痛点证据、期望变化、紧迫性与不可接受结果，允许明确“不知道”。
- Agent 主导：只读研究现状、相似能力、owner 和明显约束，形成业务问题摘要。
- 执行中升级：问题主体、场景、证据或期望结果冲突时回到业务发起人，不要求其选择技术方案。
- 事后验收：业务发起人确认问题描述正确、需要补充或停止推进。
- 准出：可理解的问题陈述、初始价值假设和非目标成立，但不产生实施授权。

#### 阶段 2：产品定义

- 事前输入：产品负责人提供目标用户、主路径、业务规则、In/Out Scope、优先级、最小发布范围和成功标准；用户代表提供真实场景。
- Agent 主导：把概念细化为当前 owner 的可观察需求与正反验收，不把内部路径和技术身份变成产品选项。
- 执行中升级：范围、优先级或业务规则存在多个合法取舍时，以对称业务影响交产品负责人裁决。
- 事后验收：产品负责人接受价值与范围，用户代表确认验收场景可执行。
- 准出：产品需求、范围和验收冻结，未知项有具名 owner 与关闭条件。

#### 阶段 3：体验设计

- 事前输入：体验负责人提供体验原则、关键状态、平台设备、可访问性与参考；产品负责人提供不可改变的业务边界。
- Agent 主导：形成旅程、状态和可演示方案，并把技术约束翻译成用户影响。
- 执行中升级：多个合法交互方向交体验负责人；选择改变范围时再交产品负责人。
- 事后验收：体验负责人走查成功、加载、空、错误、权限和恢复，用户代表确认任务可理解且可完成。
- 准出：体验方向与关键状态被接受并可绑定产品验收；纯后台变化需具名说明不适用。

#### 阶段 4：方案与风险设计

- 事前输入：方案负责人提供边界、质量属性、兼容与恢复要求；安全合规、质量和运维按真实影响提供约束。
- Agent 主导：给出可比较方案及其业务影响、代价、可靠性、数据风险、迁移、观测和回滚。
- 执行中升级：仅跨对象边界、不可逆迁移、风险接受或质量属性冲突需要对应 authority；冻结方案内实现细节由 Agent 处理。
- 事后验收：方案负责人接受单轨、可测、可观察和可回滚性，各风险角色只接受本责任域。
- 准出：有效设计、被否决方向、风险、恢复与验证方式冻结；硬风险未解除则停止。

#### 阶段 5：交付规划与授权

- 事前输入：产品负责人确认优先级，工程交付负责人确认拆分、预算、依赖和窗口，各风险 owner 确认前置条件。
- Agent 主导：按独立可验收增量形成实施边界、预期证据、人工检查点和待授权外部动作。
- 执行中升级：范围、预算、时限或依赖漂移时，以保持范围延后、缩小范围、调整预算或停止等中性后果请求裁决。
- 事后验收：工程交付负责人授权限范围、限时、可撤销的本地实施与验证；外部动作仍分别授权。
- 准出：实施授权与停止条件有效，未授权副作用保持不可执行。

#### 阶段 6：Agent 主导实施

- 事前输入：Agent 消费冻结规格、设计、授权范围、证据要求和风险边界。
- Agent 主导：完成 authoring-source-first 的实现、自验证、常规失败修复与未决项裁决，不要求人逐文件操控。
- 执行中升级：需求歧义、体验偏差、边界变化、新风险、预算或范围漂移及外部动作分别路由给有权角色。
- 事后验收：工程交付负责人检查目的、范围、验证和剩余风险，各受影响角色只核对自己的冻结决定。
- 准出：授权范围内实现和本地验证完成、无越权，未决项均有可关闭去向。

#### 阶段 7：质量检查与业务 UAT

- 事前输入：质量负责人冻结风险覆盖、环境数据设备范围和缺陷分级；产品、体验和用户代表声明各自可见验收。
- Agent 主导：运行职责匹配的结构、契约、集成、UAT 与 Review 证据并按失败类型路由。
- 执行中升级：预期歧义交产品、体验落差交体验负责人；硬质量门只允许修复、补证据、缩小到 policy 允许范围或暂停。
- 事后验收：质量负责人接受证据真实性，产品、体验和用户代表分别接受范围、体验与真实任务结果。
- 准出：required evidence 与 required Review 完整且具名验收完成；仍不表示已经集成、部署或可商用。

#### 阶段 8：集成与可信 CI

- 事前输入：工程交付负责人确认集成范围及每项外部写授权，产品角色无需批准 Git 细节。
- Agent 主导：以精确变更和版本完成集成，读取与该版本一致的可信 CI 结果并处理授权内失败。
- 执行中升级：基线漂移、owner 冲突、CI 不可判定或集成副作用超界时请求工程交付负责人裁决。
- 事后验收：工程交付负责人接受集成版本、required checks、范围和残余风险。
- 准出：受审版本在允许的集成主干可追溯且可信 CI 通过；不产生生产资格。

#### 阶段 9：不可变制品

- 事前输入：发布负责人提供目标平台、分发用途、版本与签名责任；安全合规确认凭据和第三方材料边界。
- Agent 主导：从受审版本形成不可变候选及其来源、签名和供应链证据，后续环境与渠道不得改写候选身份。
- 执行中升级：签名身份、正式应用身份、渠道能力或来源不一致时停止并转交对应角色。
- 事后验收：发布负责人接受候选用途，安全合规接受供应链证据，质量负责人接受可安装性。
- 准出：候选可进入环境验证，但尚未证明目标环境和用户场景。

#### 阶段 10：Alpha、Beta、Gamma 非生产验证

- 事前输入：运维负责人提供各环境拓扑、数据、设备与恢复目标；质量和用户代表提供每波次场景。
- Agent 主导：对同一候选按 Alpha、Beta、Gamma 依序验证启动、健康、集成、readback、UAT 与清理，并收集当前回执。
- 执行中升级：首次环境或数据写入需有效授权；波次失败阻断后续，白名单外修复交运维负责人。
- 事后验收：运维接受健康与恢复，质量接受证据层级，产品、体验和用户代表在 Gamma 接受 release-like 体验。
- 准出：候选 deployable；历史或其他环境回执不得替代本波次。

#### 阶段 11：商用准备决定

- 事前输入：产品、用户代表、体验、质量、安全合规、运维、渠道运营和发布负责人分别提交本责任域的准备事实与影响评估。
- Agent 主导：汇总角色可理解的准备包，先裁定硬门与合法选项，再交唯一 AccountableDecider 综合取舍。
- 执行中升级：事实冲突回事实 owner；硬门失败不展示 Go 或 Limited Go，价值和节奏冲突不由 Agent 推荐代替。
- 事后验收：各 EvidenceOwner 接受证据，具名商用 AccountableDecider 记录 Go、Limited Go、Hold 或 Abort。
- 准出：形成 `CommercialReadinessDecision`；该决定不授权任何生产副作用。

#### 阶段 12：Prod campaign

- 事前输入：发布负责人确认精确生产来源、不可变候选、流量阶段、SLO、窗口、停止条件与回滚目标；运维确认值班和控制可用。
- Agent 主导：在一次有效 campaign 授权内自动执行阶段技术 gate、readback、暂停与满足预冻结条件的回滚，正常推进不要求逐阶段点击。
- 执行中升级：SLO 破坏先停止或回滚再请求 resume/abort；外部结果未知先 readback，更换候选、扩大范围或改变约束必须重新决定。
- 事后验收：运维接受健康和恢复能力，发布负责人接受 released、paused、rolled_back 或失败终态。
- 准出：形成生产技术终态；不自动表示渠道已公开或业务 outcome 达成。

#### 阶段 13：渠道分发与公开

- 事前输入：渠道运营负责人提供渠道、公开时间、人群、文案、审核材料与支持准备；产品确认公开范围，发布确认同一候选。
- Agent 主导：在渠道外部写授权内执行上传、状态查询、公开切换与 readback，每个渠道独立留证据。
- 执行中升级：条款、审核反馈、凭据、重签或公开范围变化分别转给合规、渠道、发布或产品角色。
- 事后验收：渠道负责人接受上传、审核与公开结果，质量和用户代表接受真实安装或访问及首启，客服接受支持入口。
- 准出：目标渠道真实可获得且与生产服务和候选一致。

#### 阶段 14：Outcome 观察与接受

- 事前输入：产品与业务发起人冻结目标人群、业务指标、观察窗口和失败判据；运维冻结技术 SLO，运营定义反馈来源。
- Agent 主导：汇总业务 outcome、错误、性能、渠道、支持反馈和成本，明确证据时效与归因限制。
- 执行中升级：事故先止损；样本、窗口或归因不足时只报告 inconclusive，不催促人批准成功。
- 事后验收：产品或业务发起人接受 attained、not_attained 或 inconclusive，运维独立接受运行健康。
- 准出：结果被接受、按预冻结延期策略继续观察，或进入澄清、升级、终止路径；交付数量不得替代用户价值。

#### 阶段 15：反馈与知识沉淀

- 事前输入：各角色提供重复缺陷、等待、回滚、运营 finding 与适用边界，保留来源而不自动上升为规则。
- Agent 主导：聚类为候选并路由到产品、设计、工程治理或风险事实的唯一 owner。
- 执行中升级：候选跨 owner、缺真实证据或无法绑定强制检查时暂停 canonical landing。
- 事后验收：对应 owner 决定采纳、缩小、继续观察或拒绝，旧规则替代关系由 owner 接受。
- 准出：被确认知识进入其 canonical owner 并有真实回归、门禁或评审绑定；否则仅保留为最低 owner 的未决候选。

<a id="req-003"></a>
### REQ-003 DecisionUnit 七类责任闭合且 Human Authority 与 Review 分轨

每个需要人类决定的 `DecisionUnit` 必须在激活前声明以下七类责任；同一角色可以承担多类责任，但每类责任的输入、权限与接受结论不得合并省略：

1. `RequiredInputProviders`：提供原始事实、约束与未知项，不决定其责任外的取舍。
2. `IndependentImpactAssessors`：在彼此输入封存前分别评价每个合法方案对本责任域的价值、影响、风险与未知项。
3. `HardVetoOwners`：只对预冻结、不可豁免的安全、合规、证据、生产或其他硬约束判否。
4. `AccountableDecider`：仅在通过身份、范围与硬门后的合法选项中作唯一综合取舍；不得用多数票、未冻结总分或 Agent 推荐代替。
5. `AuthorizedExecutor`：只执行有效决定明确覆盖的目标、范围、动作、期限与停止条件。
6. `EvidenceOwner`：接受输入、执行与 readback 证据真实、完整且仍然新鲜。
7. `ResultAcceptor`：按自身角色责任接受结果，不得由执行者、Reviewer 或上游批准自动代签。

`HumanAuthorityRole` 与 `ReviewRole` 是物理分轨的职责命名空间。Reviewer 只能产出技术证据、finding 与 PASS/阻断评价；Reviewer PASS 不生成 Human Decision，不派生授权，不接受商用、生产、渠道或 outcome 结果。

<a id="req-004"></a>
### REQ-004 两轮独立输入抑制推荐偏置并使硬门优先

- 第一轮只收原始事实、约束和未知项，不展示方案、其他角色偏好或 Agent 建议；第二轮向所有适用角色展示同一冻结事实包与字段对称的方案，独立提交在汇总前封存。
- 每项选择以中性标识和对称顺序说明用户结果、业务结果、成本、时效、风险、可逆性、范围变化、未知项与下一步；不得预选、视觉突出或只给“接受推荐/拒绝推荐”。
- 产品范围、体验方向、商业节奏和 outcome 接受不展示 Agent 推荐。工程方案仅在可证明客观支配关系时，才可于独立输入封存后附带建议，并同时展示假设、反例与替代方案。
- 裁决顺序固定为身份、角色、范围和证据有效性，随后硬门、合法选项、事实冲突回唯一 owner、价值冲突交 AccountableDecider，最后形成不可改写决定。多数票、总分、风险接受和推荐都不得覆盖硬门。
- 角色缺席、弃权、超时、身份未知、越权作答或证据过期时默认暂停、Hold、升级或 Abort，不得隐式批准。
- `role-record-only` 允许同一 authenticated actor 以多个角色分别提交；`independent-principal-required` 必须由不同 actor 完成。是否需要独立 principal 由预冻结风险 policy 决定，同一人声明兼任不得绕过。

<a id="req-005"></a>
### REQ-005 四类角色卡片提供可理解且可恢复的行为

- **选择卡**：每次只询问一个角色职责内的一个问题，依次说明当前角色、已知与未知事实、2～4 个对称方案及影响、硬约束、选择后会发生与不会发生什么；不得暴露内部阶段代号、路径、工具或摘要身份作为选项。
- **授权卡**：说明 Agent 将达成的业务目标、可见产物、允许与排除范围、自动执行边界、仍需再次询问的外部或不可逆动作、预算、停止和撤销后果；授权只绑定当前范围与版本，漂移后重新确认。
- **异常卡**：说明发生了什么、用户或业务影响、Agent 已完成的安全动作、为何需要该角色、合法恢复方案与最安全默认；超时默认只能 pause、hold、escalate 或 abort。
- **事后检查卡**：只展示当前角色拥有的范围、体验、边界、质量、风险、候选、运行、渠道或 outcome 证据，提供通过、请求修改、转交与暂停及精确后果；一个“通过”不得覆盖多个责任域。
- 所有卡片必须支持“补证据后再决定”“转交正确角色”“暂停或停止”；事实不足时允许“不知道”，Agent 应继续调查或保留 fail-closed 终态。

<a id="req-006"></a>
### REQ-006 商用、生产 campaign 与 outcome 分层决定

- `CommercialReadinessDecision` 只允许 Go、Limited Go、Hold、Abort。Limited Go 仅能在 policy 允许时缩小可逆的人群、渠道、时间或流量范围，并明确退出条件；不得绕过 required evidence、安全、合规、生产 SLO 或回滚硬门。
- `ProductionCampaignApproval` 与商用准备决定分离。正常生产路径只批准一次 campaign，在其绑定的生产来源、不可变候选、流量阶段、SLO、窗口、停止条件与回滚目标内自动执行逐阶段技术 gate；正常阶段推进不重复索要人工批准。
- campaign 遇停止谓词先暂停或按预授权回滚；resume、更换候选、扩大范围或修改 SLO、窗口、停止与回滚条件必须产生新的有效决定。
- 在当前仅允许 `dev1.0` 与 `main` 的 branch policy 下，S4 并发执行保持 `not_admitted`，写并发退回 `1`；不得通过短命分支或同一 authority 并发积压规避职责和决策顺序。
- outcome 只能是 `attained`、`not_attained` 或 `inconclusive`。只有在观察开始前已冻结延期次数、预算、样本、窗口和退出条件时，`inconclusive` 才可经 `observing → paused → observing` 延长；否则必须进入 `clarify`、`escalated` 或 `aborted`，不得无限观察或包装为 attained。

<a id="req-007"></a>
### REQ-007 六类责任覆盖由四类校准主体承担

Human owner 是校准角色类、责任映射、观察动作与状态语义的唯一真相源；governance 只消费版本化 readback，不得另建六角色 schema。治理全应用必须覆盖 `business / product / experience / quality / engineering / release_operations` 六类责任，但校准 quorum 使用 `product / engineering / quality / release_operations` 四类 authenticated principal class，采用以下单轨映射：

- `product` 同时覆盖 `business`、`product` 与 `experience` 责任：能说明业务问题、受益对象、价值与不可接受结果，能理解和裁定目标用户、范围、优先级与业务规则，并能以用户任务、信息层级、关键状态、可访问性、跨设备体验与恢复后果理解体验影响；三类责任必须分开留痕。该映射只用于校准样本归类，不把 Human Authority 的业务发起人、业务验收负责人、产品负责人或体验设计负责人合并为同一决定角色，也不授权产品负责人代签体验方向。
- `engineering` 覆盖工程责任：理解交付边界、依赖、资源、可验证性、可观察性、可回滚性及其对其他角色的影响；该类不吸收 experience 责任，也不授权工程角色替体验负责人选择体验方向。
- `quality` 覆盖质量、风险驱动验证、真实任务证据与缺陷准出责任。
- `release_operations` 覆盖精确候选、环境健康、SLO、暂停/拒绝/中止、回滚恢复、渠道与事后检查责任。

六类责任都必须出现在校准任务与 readback 的责任覆盖中，但 routine calibration 不要求六名不同参与者，也不新增 business/experience principal class。只有预冻结 DecisionUnit policy 判定为 `independent-principal-required` 的安全、合规、不可逆数据、生产关键或其他具名高风险决定，才要求相关责任由不同 authenticated principal 提交；一般跨角色影响记录、咨询、知会和 `role-record-only` 决定允许同一参与者分角色留痕，不得由治理聚合器把职责覆盖自动升级为职责分离。

<a id="req-008"></a>
### REQ-008 校准观察覆盖理解、行动、恢复与事后检查

真实参与者必须在不暴露内部术语的代表任务中，以所属 principal class 覆盖其全部映射责任，并表现出以下可观察结果：

- **理解**：能用自己的话说明当前问题、已知与未知事实、硬约束、谁受影响，以及当前决定会和不会改变什么。
- **方案与影响理解**：能比较中性、字段对称的合法方案，指出用户、业务、体验、质量、工程、发布运维影响与跨角色取舍；产品范围、体验方向、商用节奏和 outcome 不依赖 Agent 推荐。
- **转交**：发现问题超出当前责任时，能选择转交给正确角色并保留事实、未知项、影响和待决问题，而不是代签。
- **暂停、拒绝与中止**：证据不足、硬门失败、越权、超时或影响不可接受时，能选择补证据、pause/hold、deny 或 abort，且理解最安全默认和不会发生的副作用。
- **恢复**：能从暂停或失败事实选择补证据、缩小范围、修复、恢复或停止，并理解重新决定、重新授权与不可恢复边界。
- **事后检查**：能只接受自己责任域的结果，不把 Reviewer PASS、上游批准、released、published 或 attained 互相替代，并能请求修改、转交或继续暂停。

校准记录只保留结构化动作结果、责任覆盖和去标识来源引用；不得保留 prompt、message、raw payload、自由文本、直接身份或 PII。Reviewer 只能提供技术证据，不能授权、代签校准或关闭 Human OPEN；HOTL、Commercial、Prod、渠道与 outcome 的外部 authority 边界保持不变。

<a id="req-009"></a>
### REQ-009 版本化 Human readback 保守表达观察充分性

Human owner 必须提供版本化、可校验且由 exact session bytes 派生的 calibration readback。规格冻结以下可观察结果，wire 字段名、编码和 operation 细节留给 Human contract owner 后续实现：

- readback 可识别 Human contract/schema version、role-model version、observation-model version、生成时间、有效截至时间与适用任务/阶段范围；freshness window 固定为 24 小时，超过窗口或版本不兼容即 fail closed。
- 来源必须是 authenticated participant、明确 consent、direct identifiers removed、free text/raw payload forbidden 的去标识 session；需能证明 source kind、session refs/exact-byte digests 与 separation policy，而不暴露 actor identity、prompt、message 或 PII。
- 最小样本为四类 principal class 各至少 1 份真实参与者样本、每类至少 1 个完成的 qualifying session；同一参与者可覆盖多个 `role-record-only` principal class，但每类必须有独立 session/role record。总样本至少 4 个 qualifying role-session，且六类责任与 REQ-008 六个观察维度全部被覆盖；unique participant 数不因 routine calibration 自动提升到 4，`independent-principal-required` 任务另需满足不同 authenticated principal 的预冻结 policy。
- 状态闭集为 `not_observed / insufficient / calibrated`。无真实 qualifying observation 为 `not_observed`；有真实观察但缺任一 principal class、责任覆盖、观察动作、样本、freshness、consent/authentication/deidentification 或 SoD 条件为 `insufficient`；全部满足且版本兼容才为 `calibrated`。
- readback 至少让消费者观察 required/completed principal classes、required/completed responsibility classes、required/completed observation dimensions、participant/session/qualifying sample counts、freshness、source assurance、separation policy、scope 与 blockers。消费者缺字段、未知版本、摘要或 exact bytes 漂移、过期、machine baseline 自称真实观察时返回 typed incompatibility/blocker，不降级、猜测映射或接受 shadow schema。
- 当前四角色 machine baseline 只能证明结构代理和本地路径可达，状态仍为 `not_observed`，不能产生 `calibrated`、release-ready、Human authority、HOTL 或 Prod 结论。

## 4. 契约引用

- 独立 Human-Agent 交付机器契约：`quwoquan_ops/policies/human_agent_delivery_contract.yaml`，由本 Story 唯一拥有；不得从现有 Review contract 推断字段或 authority。
- 现有 Review manifest、plan 与 terminal：`quwoquan_ops/policies/agent_governance_contract.yaml`；仅作为 Review 证据边界，不拥有 Human Authority、DecisionUnit 或授权语义。
- 人类可见卡片是 canonical 决定语义的投影，不复制或反向拥有机器字段。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 正确角色独立输入且硬门优先

- GIVEN 一个 DecisionUnit 已声明七类责任，既包含可取舍的产品影响，也包含预冻结的不可豁免硬约束，并要求独立 principal。
- WHEN 两轮角色输入完成并由系统形成合法选项后请求综合裁决。
- THEN 第一轮事实输入不暴露方案、他人偏好或 Agent 建议，第二轮各角色获得同一事实包与字段对称、顺序平衡的选项。
- AND 各 IndependentImpactAssessor 的提交在汇总前相互隔离，事实冲突回到唯一 RequiredInputProvider 或事实 owner。
- AND 身份、角色、范围、证据有效性和 HardVetoOwner 的硬门先于合法选项与价值取舍裁定。
- AND 任一硬门失败时相关选项不可被多数票、总分、风险接受、Reviewer PASS 或 Agent 推荐恢复为合法。
- AND AccountableDecider 只在合法集合中作唯一决定，AuthorizedExecutor、EvidenceOwner 与 ResultAcceptor 各自保留独立责任。
- AND 缺席、超时、身份未知、越权或证据过期得到 pause、hold、escalate 或 abort，而不是隐式批准。
- AND 同一 actor 的角色兼任只能满足 role-record-only 的分开提交，不能满足 independent-principal-required。
- AND ReviewRole 的 PASS 只成为证据，不生成 Human Decision、AuthorizationGrant 或结果接受。

<a id="gwt-002"></a>
### GWT-002 卡片可理解且无推荐偏置

- GIVEN 产品负责人需要在两个均合法的范围选项间选择，且非技术角色不掌握内部路径、工具、状态代号或证据摘要身份。
- WHEN Agent 依次展示选择卡、授权卡、执行中异常卡和事后检查卡。
- THEN 每张卡只向当前角色提出一个责任内问题。
- AND 每张卡以角色语言区分已知事实、未知项、硬约束、用户或业务影响与后果。
- AND 合法方案使用中性名称和对称字段，交换展示顺序不改变合法集合。
- AND 卡片不存在预选、视觉突出或“接受推荐/拒绝推荐”的单通路。
- AND 产品范围选择不展示 Agent 推荐。
- AND 存在客观支配关系的工程建议也只能在独立输入封存后附带假设、反例与替代项。
- AND 每张卡都允许补证据、转交正确角色、暂停或停止，事实未知时允许“不知道”并保持可恢复。
- AND 授权卡明确自动执行边界、排除项、预算、需再次询问的外部动作和撤销后果。
- AND 范围或版本漂移使授权失效。
- AND 异常卡先说明安全动作与最安全默认。
- AND 超时不产生隐式批准。
- AND 事后检查卡只允许当前角色接受自己的结果。
- AND 一个通过不覆盖其他责任域。

<a id="gwt-003"></a>
### GWT-003 商用、生产 campaign 与 outcome 状态不互相冒充

- GIVEN 同一不可变候选已进入商用准备，但存在可能的 Limited Go 范围、生产阶段技术 gate、渠道公开和 outcome 观察。
- WHEN 依次作出商用准备、生产 campaign、渠道与 outcome 决定。
- THEN CommercialReadinessDecision 与 ProductionCampaignApproval 分别记录，商用 Go 或 Limited Go 不产生生产副作用授权。
- AND required evidence、安全、合规、生产 SLO 或回滚硬门失败时 Go 与 Limited Go 均不可用，Limited Go 只能缩小 policy 允许的可逆范围。
- AND 一次有效 production campaign 在冻结范围内自动推进阶段技术 gate，停止谓词触发 pause 或预授权 rollback，resume 或约束变化要求新决定。
- AND 当前 branch policy 下 S4 为 not_admitted、写并发为 1，短命分支或同一 authority 并发不能成为旁路。
- AND 渠道公开与 outcome 接受分别需要自己的 evidence owner 和 result acceptor，released 或 published 不自动得到 attained。
- AND outcome 只落 attained、not_attained 或 inconclusive；仅预冻结延期策略允许 observing→paused→observing，否则进入 clarify、escalated 或 aborted。

<a id="gwt-004"></a>
### GWT-004 六责任四主体映射与版本化 readback fail-closed

- GIVEN Human owner 冻结六类责任、四类 principal class、责任映射、24 小时 freshness 与最小样本，governance 只持有一个待消费的 Human readback。
- WHEN 本地 contract fixture 校验 role model、schema/mapping、状态归约与不兼容负例，或真实参与者完成代表任务后产生去标识 session readback。
- THEN `product` 覆盖 business/product/experience、`engineering` 覆盖 engineering、`quality` 覆盖 quality、`release_operations` 覆盖 release_operations；六类责任全部 required，但 routine quorum 不要求六个 distinct principals，也不允许 governance 建 shadow 六角色 schema。
- AND local_contract 证明版本、映射、四类 principal/六类责任、六个观察维度、24 小时 freshness、最小四个 qualifying role-session、三态闭集和 unknown/stale/digest drift/machine-baseline self-claim fail-closed；本地 fixture 只能得到 `not_observed` 或结构性的 `insufficient`，不能关闭真实 observation。
- AND user_acceptance 由四类 principal class 的真实参与者样本在代表任务中直接证明理解、方案与跨角色影响理解、转交、pause/deny/abort、恢复与事后检查；每类 principal 至少一个完整 qualifying session，全部六类责任和观察维度有去标识覆盖，同一参与者跨类仅按 `role-record-only` 分开留痕。
- AND 任一 authentication、consent、deidentification、责任/动作覆盖、freshness、sample、scope 或 decision-specific distinct-principal 条件缺失时状态为 `not_observed` 或 `insufficient`，而不是 `calibrated`。
- AND 只有全部条件满足的兼容 readback 才为 `calibrated`；Reviewer、Agent 建议、machine baseline、HOTL 或 Prod 结果均不能替代或授权该状态。
- AND governance 面对未知 contract/role-model/observation-model version、缺 required outcome、过期、exact session bytes/digest 漂移或 shadow role schema 时返回 Human-owned typed incompatibility/blocker 并维持零 authority、零 mutation。

## 6. 依赖

- 前置要求：[`development-workflow-governance`](../spec.md) 的 `REQ-006`，以及当前仓库 Git、证据与外部动作安全约束。
- 上游事实：各业务 Feature 的价值、范围、体验和验收，各领域 design/contracts 的硬约束，Review 产生的技术证据，以及外部 authority 的 authenticated 决定。
- 下游结果：人类可理解的角色卡、不可代签决定、限界授权、分层商用与生产终态，以及 outcome 接受。
- 父级设计：`DEC-008`。

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 真实身份与 authenticated Human Authority provider 尚未接入

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：Human Authority contract、角色路由与本地非执行投影已经冻结，但仍无真实 identity provider、authenticated actor/role claims、隔离的 durable authority provider 与 exact-byte readback；objective executor 的本地 journal 与 test provider 不能关闭身份/授权真实性边界。
- 完成判定：`GWT-001.t1`、`GWT-001.t2`、`GWT-001.t3`、`GWT-001.t4`、`GWT-001.t5`、`GWT-001.t6`、`GWT-001.t7`、`GWT-001.t8` 均由真实 authenticated authority 集成证据直接绑定，且授权 consumer 与外部 effect readback 证明 actor、role、scope、expiry、evidence 与职责分离。
- 依赖：真实身份提供方、独立 append-only authority provider、provider 签名与 anti-replay、exact-byte readback、受限 executor 与外部 effect provider。

<a id="open-002"></a>
### OPEN-002 真实多角色可理解性校准尚未观察

- 类型：`external_blocker`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：六类责任到四类 principal class 的 canonical 映射、观察维度、三态与 fail-closed 结果已经由 `REQ-007` 至 `REQ-009` 冻结；当前四角色 machine baseline 仍只有结构代理，真实校准保持 `not_observed`，不得声称 business/experience 责任或全链人类可理解性已闭合。
- 完成判定：先由后续 Human contract/local_contract 直接绑定 `GWT-004.t1`、`GWT-004.t2`、`GWT-004.t4`、`GWT-004.t5`、`GWT-004.t6`；再由 `GWT-004.t3` 的 external `user_acceptance` 使用四类 principal class 的真实参与者样本、至少四个 qualifying role-session 覆盖六类责任及理解、方案/影响理解、转交、pause/deny/abort、恢复与事后检查。每条 observation 均来自 authenticated/consented/deidentified source 并绑定 fresh exact session bytes；本地 fixture、Reviewer 或 machine baseline 不能关闭本 OPEN。
- 依赖：Human contract owner 的 versioned readback/mapping 实现与 local_contract、四类真实参与者、代表任务、authenticated/consented/deidentified observation source、decision-specific distinct-principal 策略与 24 小时内的 fresh external `user_acceptance` 回执。

<a id="open-003"></a>
### OPEN-003 外部商用、生产、渠道与 outcome authority 尚未闭合

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：缺少正式商用 authority、durable production campaign approval、真实生产阶段 gate/readback/rollback、渠道审核安装和 outcome 观察接受证据；本地规格与测试不得宣称商用闭环。
- 完成判定：`GWT-003.t1`、`GWT-003.t2`、`GWT-003.t3`、`GWT-003.t4`、`GWT-003.t5`、`GWT-003.t6` 均由 exact candidate 的外部 authority、生产与渠道 readback、真实 UAT 和 outcome 接受证据直接绑定。
- 依赖：正式 branch protection、生产与渠道 authority、SLO/回滚控制、真实渠道和观察窗口。
