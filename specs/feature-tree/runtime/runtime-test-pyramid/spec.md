# L2 Business Capability：三层测试模型 (`runtime-test-pyramid`)

> 所属领域：[`runtime`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

以 local_contract、api_integration、user_acceptance 形成唯一测试分层，使 App 与服务测试按生产对象身份同构，并让对象级覆盖率、结构证据和真实运行结果保持可区分。

## 2. 范围与非目标

### In Scope

- 三层测试命名、case ID、环境语义和执行入口
- App、Service、Data、Ops 测试路径到 service/context/object owner 的反向关联
- support 边界、真实依赖分层、对象级分支覆盖率和运行报告计算
- 测试入口结构证据与 CaseResult、环境及用户验收结果证据的分离
- StaticContractExample、GeneratedTestObject、API provider-state、immutable release、Acceptance Actor、case-run 交易与外部 sandbox 状态的分层边界
- 性能、可靠可用、异常观测闭环、用户体验四条非功能质量轴的复合标签语义、真相源约束与覆盖棘轮

### Out of Scope

- 单个业务 Story 的具体产品行为
- 远端环境和凭证供给
- prod 审批与放量决策

## 3. Journey / Scenario 贡献

- 横切工程能力：不直接拥有 AppRoot Scenario；调用本能力的业务领域仍承担对应 Journey 的产品责任。
  - 本能力处理：以 local_contract、api_integration、user_acceptance 形成唯一测试分层和环境证据模型。
  - 本能力输出：可供业务领域组合的公开结果与明确失败终态。

## 4. Story



- [`three-layer-evidence`](./three-layer-evidence/spec.md)：已支持验收至少有一个职责匹配且可执行的直接 `spec_ref`；被 OPEN 声明的未完成验收不得计为通过。
- [`branch-coverage-governance`](./branch-coverage-governance/spec.md)：对象级覆盖结果从真实绿测试派生，分支、未归属源码和覆盖回退不会被文件存在或人工基线掩盖。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 三层测试模型与门禁单轨收口

- 节点 spec 只登记稳定 UAT/DOM/SIT/GWT；测试或可执行治理门以 `spec_ref` 直接引用验收锚点。
- 已关闭验收至少有一个真实、职责匹配且可运行的 `spec_ref`；未闭合验收由同节点 OPEN 明确完成判定。
- App 三层测试按 `test/<layer>/service/<service>/<context>/<object>` 与 production 对象同构；服务 local_contract/api_integration 按 `tests/<layer>/<context>/<object>` 同构。
- App 跨对象 Journey 只有两种 canonical 边界：`test/local_contract/journeys/<journey>/` 只容纳使用测试树 typed double、Provider 或 Widget 的本地跨对象 Journey 契约，测试文件使用 `__local_contract_test.*` 后缀；`test/user_acceptance/journeys/<journey>/` 只容纳使用 production Remote composition 的真实 Journey，测试文件使用 `__user_acceptance_test.*` 后缀。禁止创建 `api_integration/journeys`。
- Journey 目录名必须为 `snake_case`，测试文件必须是 journey 目录的直接子文件，复用 helper 只能进入 `test/support`；路径存在只证明结构入口，不代表 Remote composition 已执行或通过。
- `support` 只承载共享 harness、fixture factory 与 typed double 定义，不承载测试用例、业务断言或环境 App 可达的生产实现；对象 support 必须位于 `test/support/service/<service>/<context>/<object>/`，真正横切的运行器、平台与边界 harness 只能位于 `test/support/runtime/`。
- support 禁止建立 `repository_mock_reexports`、按框架/类型聚合的 `fakes/fixtures/cloud_services` 等跨对象桶；消费者必须直接 import 唯一对象 owner。普通 fixture、typed double、adapter 与 golden 禁止用 `Alpha*`、`alpha_*` 等部署环境名伪装环境证据，真实 Alpha/Beta/Gamma/Prod 验收只能由相应结果层 runner 绑定候选、Provider 与可信回执。
- App、Service、Data、Ops 的 canonical 三层目录是唯一测试入口；旧 `ui/cloud/core/pages/patrol/quality` 测试大桶和其他迁移 allowance 不能成为长期合法路径。
- 云端横切区（`quwoquan_service` 的 `runtime/internal/tools/cmd`）与各服务装配层（`services/<service>/cmd/**`）允许旁路同包白盒测试，但文件必须带 `__local_contract_test.go` 后缀；api_integration 依赖真实边界，禁止旁路同包，必须进入 canonical `tests/api_integration` 树。服务对象实现（`services/<service>/internal/**`）不适用旁路，对象测试只进 canonical `tests/<layer>/<context>/<object>` 树。
- Ops 测试树的 pytest 套件必须同时满足 `test_` 前缀（与 pytest 收集面对齐）和三层后缀；`tests/local_contract` 根只允许已登记 concern 子目录（`ci/environment/gate/media/observability/provider/release/service_ops/stackctl/test_data`），根平铺套件一律阻断，concern 名册即目录事实，新 concern 随其搬迁批次在门禁名册登记。
- provider conformance 声明矩阵保留在测试树内（`tests/<layer>/service_ops/<service>/ci/`）：每个声明文件是一层 × 一个 Provider adapter 的测试声明点，其 command 路径被 conformance readiness digest 绑定；声明头的 `testLayer` 必须与所在树层一致，每个 `adapterId` 必须三层成对声明，每层声明数量守恒（随 Provider 名册显式增减，防无名册拷贝）。
- Ops `service_ops/<service>/` 的验收角色目录为 `ci/smoke/gamma/gate/support` 闭集：UAT 证据聚合器归 `gamma/`，共享 helper 归 `support/`，静态门禁脚本归 `gate/`；smoke 只承载生命周期 probe。
- 运行报告从测试代码、执行结果、环境和制品摘要实时生成，不提交覆盖清单或证据索引。
- 测试入口路径、spec_ref 与内容摘要属于结构证据；runner 产生的通过/失败/跳过 CaseResult、环境摘要与用户验收回执属于结果证据，静态扫描不得把前者解释为后者。
- 视觉基线的 fixture 必须与执行日期无关；会跨越相对时间阈值的当前日期不得写入 golden 输入。

<a id="req-002"></a>
### REQ-002 禁止新增 T1-T4、L1-L4、contract-test 等第二套分层名称

- 禁止新增 `T1-T4`、`L1-L4`、`contract-test` 等第二套分层名称
- `spec_ref` 与验收锚点必须双向有效，禁止集中映射表或不存在的逻辑 case 冒充测试
- 缺少远端环境、凭证或当前报告时必须 `GATE_BLOCK`，不得以静态声明代替

<a id="req-003"></a>
### REQ-003 测试层由依赖真实度与用户可见边界决定

- local_contract 可使用进程内 typed double、fake 或内存实现，证明对象规则、mapper、Provider/Widget 状态、错误恢复与本地端口；任何测试 double 不得进入 api_integration、user_acceptance 或环境 artifact。
- api_integration 必须连接真实进程形态的 HTTP/WS、数据库副本集、缓存、消息或对象存储边界；把 fake 依赖包装成 HTTP 或把替身测试放入该目录仍按错层阻断。
- user_acceptance 必须使用 production Remote composition 验证 Journey、用户可见终态与恢复动作；文件存在、静态 path-UAT、动态 skip 或环境名不能充当执行结果。
- user_acceptance 主旅程必须包含非空业务数据断言（release 绑定字段、至少一条业务行）或 create-then-readback（经公开 command 创建事实后断言其渲染）；空态只能作为显式构造的场景用例出现，缺数据时空页静默通过按覆盖失真处理。承担触发器角色（数据落地由服务侧 probe/conformance 断言）的旅程必须在文档头声明分工，且自身至少断言可交互壳终态。
- 覆盖率只描述真实测试触达的生产代码，不能替代 api_integration、user_acceptance、Provider、四环境或设备 CaseResult。

<a id="req-004"></a>
### REQ-004 测试数据构造服从三层真实度

- local_contract 使用对象级强类型 builder/generator、固定 seed/clock/ID 和最小 wire/golden，不进入环境测试数据控制面，不加载全应用场景 dump。
- api_integration 通过真实进程的 application command 或 provider-state harness 构造最小前置状态；direct storage 只用于 persistence adapter、migration 或 corruption recovery 专项测试，不能生成环境或用户验收成功事实。
- 专项直插必须显式声明：文件名携带 `__data_consistency__` facet、以 `contract_provider_state_persistence` 开头（provider-state harness 本体），或为包级 seed/setup harness（subject 以 `__support` 或 `_test_support` 结尾，业务断言不得写入）；专项之外的直插存量由门禁棘轮圈住只减不增，消化方向是改走公开 command/provider-state 或补专项声明。
- `contracts/**/errors.yaml` 声明的每个错误码必须有真实测试断言其发射与语义（错误契约语义双向锁或行为负例）；每服务未断言码数由 `verify_error_code_assertion_coverage.py` 棘轮圈住只减不增，新增错误码必须随断言测试合入，确属测试树内不可触发的兜底码按码登记豁免理由。
- user_acceptance 使用 production Remote composition：内容、Creator、Entity 和发布 Media 只读引用当前 immutable release，可变事实由强类型 capability request 经公开 command/event 创建；每个 CaseResult 独立 Actor 与 mutable data，Prod 在 mutation 前拒绝。
- 单个结构化 fixture 不超过 64 KiB、500 个 scalar leaf、单数组 100 项；同一对象 support 下总量不超过 256 KiB。超限数据改为 builder、固定 seed generator、immutable release 或独立 corpus。

<a id="req-005"></a>
### REQ-005 用例正文和性能不得被全域数据准备淹没

- user_acceptance 测试正文保持“需求声明、行为执行、业务断言”，不出现 capability 字符串、裸字典参数、固定业务对象 ID、Provider 实现或 cleanup 细节。
- 数据准备只覆盖选中用例的依赖闭包；单领域用例的无关 Provider 和 operation 为零。
- 性能优化不得减少测试 case、业务断言、错误路径、真实 Provider、readback 或 cleanup；提前失败 run 不得成为完整执行基线。

<a id="req-006"></a>
### REQ-006 非功能质量轴与复合标签单轨

- 性能、可靠可用、异常观测闭环、用户体验四条质量轴共用三层测试模型，以既有复合标签（`__performance__`、`__reliability__`、`__a11y__`、`__visual__`、`__observability__`）内嵌于对象目录表达；禁止为质量轴新建第四层目录、平行测试树或第二套分层名称。
- 性能预算唯一真相源是 operation 契约的 `slo.*` 声明与所属节点 spec 的预算 REQ；性能测试从契约或受版本控制的预算声明读取阈值，禁止在测试正文硬编码第二预算值。
- 端侧性能采样使用固定 seed 数据规模与重复采样中位数；性能证据写入 `.qwq_output` 且可幂等重建，benchmark-only 结果不得计入绿色 CaseResult。
- 可靠性测试的故障语义只引用对象 `errors.yaml` 错误码与 resilience 契约的超时/重试参数，禁止建立第二错误清单；故障 profile 为闭集枚举，注入面只允许环境边缘受控代理与测试树内 typed fault double，production `lib/**` 与服务装配不得携带任何注入开关。
- 异常观测闭环以真实 readback 证明：告警规则只从 contracts alert overlay 派生，演练断言必须查询真实指标/日志面并产出含注入、告警命中、恢复时刻的结构化回执，禁止 mock 观测面充当命中证据。
- 用户体验测试的页面清单唯一真相源是 `page_object_contract.yaml`，禁止另建页面 checklist，a11y 断言集为闭集（触控目标、图像语义标签、文本对比度）；golden 基线更新必须与对应 UI 变更同一变更集提交，禁止孤立刷基线。
- 非功能应测清单从契约、页面契约与验收锚点实时派生，覆盖状态只有 `covered`、`open-registered`、`missing` 三态；`missing` 由门禁按棘轮阻断且基线只减不增，派生报告写入 `.qwq_output`，不构成第二真相源或 tracked inventory。

## 6. 契约与依赖

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 三层测试模型与门禁单轨收口

- GIVEN 执行“三层测试模型与门禁单轨收口”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“三层测试模型与门禁单轨收口”对应动作。
- THEN 节点 spec 不包含测试文件、命令、通过率或历史证据，测试代码以 `spec_ref` 直接关联稳定验收锚点。
- THEN 每个已关闭验收都有真实测试或可执行治理门反向引用；OPEN 中的未完成验收不会被误报为通过。
- THEN App 与服务三层测试均可由物理路径精确反向定位 production 对象，support 不承载测试用例，旧测试大桶与迁移 allowance 不作为合法终态。
- THEN local_contract、api_integration、user_acceptance 按真实依赖和用户可见边界分类，fake HTTP、Memory 集成、path-UAT 与动态 skip 均不能提升证据等级。
- THEN 测试入口结构证据与 runner CaseResult、环境和用户验收结果证据分字段表达，文件存在不会被解释为执行通过。
- THEN golden fixture 使用固定、跨执行日期稳定的输入，不因相对时间阈值自动漂移。
- THEN 动态报告能从当前代码与运行结果定位实际测试、环境和制品摘要，不读取 tracked inventory。
- THEN 三层数据分别由最小 builder/provider-state/强类型环境 capability 构造，fixture 超限、环境 DB seed、Prod mutation 与跨 case 可变数据复用均被阻断。
- THEN 单领域测试只加载依赖闭包，测试正文不暴露数据准备实现，性能报告将数据准备、测试执行和清理分段表达。
- THEN 云端横切区旁路同包测试全部携带 local_contract 层后缀，无 api_integration 旁路；Ops 测试全部满足 `test_` 前缀与层后缀，local_contract 根的 concern 目录、平铺存量与 conformance 残量由布局门禁按棘轮阻断。

<a id="sit-002"></a>
### SIT-002 非功能质量轴覆盖单轨收口

- GIVEN 契约、页面契约与验收锚点已声明性能预算、故障语义、告警规则与页面体验要求。
- WHEN 门禁派生非功能应测清单并对照物理测试树与 OPEN 登记。
- THEN 四条质量轴的测试均以复合标签内嵌于三层目录，不存在第四层测试树、第二套预算值、第二错误清单或第二页面清单。
- THEN 每个应测单元处于 `covered` 或 `open-registered` 状态；`missing` 单元按棘轮阻断且基线只减不增。
- THEN 性能、演练与体验证据可从 `.qwq_output` 幂等重建；benchmark-only 结果与 mock 观测面结果不会计入绿色证据。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 对象同构三层测试与结果证据准出

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：当前测试树仍包含旧技术大桶和不完整的对象路径校验，静态 evidence 也尚未把 App、服务、Ops 的入口与 runner CaseResult 分侧承载，无法证明每个受影响对象的三层测试与真实结果完整。
- 完成判定：`SIT-001` 的 12 条 THEN 组全部具备子句级 `spec_ref`（`sit-001.t1..t12`）绑定的真实测试或可执行门证据。
- 依赖：[`three-layer-evidence`](./three-layer-evidence/spec.md) 与 [`branch-coverage-governance`](./branch-coverage-governance/spec.md) 的开放事项关闭。

<a id="open-002"></a>
### OPEN-002 分层覆盖缺口与测试树结构收敛残量

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：仍有两类最小长期残量在归零前会让覆盖证据失真或依赖门禁棘轮兜底（结构治理已收官：Ops local_contract 根平铺归零并转为 REQ-001 终态规则、conformance 声明矩阵裁决关闭；对象级覆盖审计已确认 recommendation-service 为 Python 测试形态且 7/7 对象两层对齐、realtime-gateway 2/2 对象两层对齐，原「Go 层证据偏薄」残量不成立并关闭）。
- 残量一（环境依赖，缺环境执行证据）：Data user_acceptance 的环境采样 readback 缺活跃 immutable candidate（gamma-local `stackctl health` 0/1，阻塞原因为 `startup Provider runtime identity is not current`，需重新 package/up 后恢复），待环境拉起后补采样 readback 用例；api-edge、entity、notification、tag 四个服务在 Ops `service_ops` 下无验收目录，待各服务首个环境验收 Journey 落地时创建。
- 残量二（harness 改造批次，缺公开 command/provider-state 构造路径）：服务侧 api_integration 未声明专项的直插存量按 `DEC-005` 棘轮圈住（基线随口径收紧与 user_account 首批 harness 归并降至 26），其中 chat 会话组随 chat 会话 provider-state harness 批次消化，content 供给组随 content 供给 harness 批次消化，user/circle 剩余多处直插 contract seed（`close_account`/`follow`/`persona_view`/`circle_feed` 等）随各自对象 harness 批次消化；App 聚合 Mock 替身（棘轮基线 43）随对象级 typed double 迁移消化。
- 完成判定：`SIT-001` 对应行为满足（含分域、棘轮与真实度分层子句），两个棘轮基线归零、环境采样与四服务验收目录补齐，由真实测试 `spec_ref` 关闭。
- 依赖：OPEN-001。

<a id="open-003"></a>
### OPEN-003 非功能质量轴覆盖铺开残量

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：当前存量对象、页面与旅程的非功能覆盖大面积缺失（全仓 `__performance__` 用例个位数、golden/visual 覆盖极窄、无告警演练证据），在压测与故障注入 harness、覆盖棘轮门禁落地并按派生热力图铺开前，性能/可靠性/体验回归不可被门禁发现。
- a11y 残量：设计系统高频交互组件已有 8 件 `__a11y__` 闭集用例，闭集为触控目标、可点目标语义标签与文本对比度，modal 遮罩关闭语义缺陷已随首批修复。
- a11y 页面级断言仍受 `page-horizontal-quality` 登记的首页存量违规阻塞，违规修复后按同一闭集落地页面级用例，其余高频组件随批次铺开。
- privacy 维度残量：`__privacy__` facet 在多数服务为零（实扫仅 integration 3、search/recommendation/user 各 1）；账号关闭清除与可见性边界已有部分覆盖但多以 `__data_consistency__` 或无 facet 形态存在，circle/chat/content 等持有用户数据的服务缺以 privacy facet 声明的删除传播、可见性收敛与数据导出边界用例，随非功能轴按服务铺开。
- 异常路径断言残量：两侧均已关闭——服务侧 `verify_error_code_assertion_coverage.py` 全 15 服务 `MISSING_CEILING` 锁零（declared=567 missing=0），9 条测试树内不可达/App 端发射的码按理由登记 `EXEMPT_CODES`；App 侧 `quwoquan_app/scripts/runtime/error/verify_app_error_code_assertion_coverage.py` 同样锁零（generated 枚举 312 码 declared=312 missing=0，`MISSING_CEILING = 0`，exempt=0），每码均有 `fromCode` 解码、httpStatus/恢复语义与 `CloudErrorMapper` 映射负例断言，新增错误码必须随断言测试合入。
- 完成判定：`SIT-002` 对应行为满足且真实测试 `spec_ref` 有效；错误码断言棘轮各服务基线归零。
- 依赖：[`runtime-testinfra`](../runtime-testinfra/spec.md) 的 `performance-load-harness` 与 `fault-injection-harness` 开放事项、[`observability-and-alerting`](../../platform-ops-governance/observability-and-alerting/spec.md) 的 `alert-drill-closure` 开放事项关闭。
