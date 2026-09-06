# L3 Story：三层测试证据追踪 (`three-layer-evidence`)

> 所属能力：[三层测试模型](../spec.md)
>
> Journey / Scenario：不直接参与用户 Journey；证明各层 UAT/DOM/SIT/GWT 是否真实达成
>
> 设计归属：[L2 DEC-001](../design.md#dec-001) 与 [DEC-003](../design.md#dec-003)

## 1. 用户价值

作为开发者或审核者，我希望从节点验收直接找到职责匹配的测试，并能区分未完成验收与环境阻断，从而不把文件存在或单层绿灯误报为准出。

## 2. 范围与非目标

### In Scope

- local_contract、api_integration、user_acceptance 三层目录与 `spec_ref` 双向校验。
- App 与服务测试按 production 对象身份同构，support 只承载共享测试支撑。
- 结构入口与真实 CaseResult、环境及用户验收回执分侧、分字段表达。
- App 与 app↔cloud 边界合入候选在更新 `dev1.0` 前的端云真实启动闭环结果证据。
- 无证据验收必须由同节点 OPEN 声明；环境缺失必须保留 GATE_BLOCK。

### Out of Scope

- tracked coverage map、证据索引、测试排列组合和历史运行台账。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 验收与真实证据双向一致

- 已支持验收至少有一个职责匹配且可执行的直接 `spec_ref`；被 OPEN 声明的未完成验收不得计为通过。
- App 测试必须位于 `test/<layer>/service/<service>/<context>/<object>`，服务 local_contract/api_integration 必须位于 `tests/<layer>/<context>/<object>`；路径的每一级均能反查 canonical owner，不能只校验 service 顶层或文件后缀。

<a id="req-002"></a>
### REQ-002 测试所属层由依赖真实度决定

- 使用进程内替身、内存实现或 fake 依赖的测试只能位于 `local_contract`，无论它验证的是 HTTP 传输还是内部端口。
- 只有打真实依赖的测试才计为 `api_integration`，真实依赖指真实进程形态的缓存、数据库副本集、消息与对象存储。
- 替身测试挂在 `api_integration` 下会让真实缺口被绿灯掩盖，出现即按错层阻断。
- user_acceptance 使用 production Remote composition 验证 Journey、用户可见终态与恢复动作；动态 skip、静态 path-UAT、环境名或页面文件存在均不构成用户验收结果。

<a id="req-003"></a>
### REQ-003 support 与测试 double 不能越过本地合同边界

- support 只允许共享 harness、fixture factory 和 typed double 定义，不得包含测试用例或业务断言。
- typed double、fake、Memory、Noop 与 Provider override 只能被 local_contract 测试可达，api_integration、user_acceptance 和四环境 production artifact 的依赖图均不得包含它们。

<a id="req-004"></a>
### REQ-004 结构证据与结果证据不可互相满足

- 测试路径、owner、spec_ref 与内容摘要属于结构证据，只证明入口已就位；通过、失败、跳过、环境、制品和用户验收回执属于 runner 结果证据，只能在真实执行后产生。
- App、Service、Data、Ops 的结构入口必须分侧表达，任一侧存在测试不能替代另一侧的对象义务；结果证据必须绑定对象、验收锚点与不可变候选摘要。
- 缺少必需结果时保持 GATE_BLOCK，不得以结构入口、覆盖率、合法业务空或历史结果替代。

<a id="req-005"></a>
### REQ-005 App 端云真实启动闭环证据

- 影响 App 或 app↔cloud 边界的exact candidate，在更新`dev1.0`前必须由Alpha及conditional Beta产生真实启动、Service `api_integration` CaseResult和受影响Journey readback，全部绑定同一candidate；更新后Gamma必须对完全相同的current dev head验证跨增量组合并形成IntegrationQualificationFact。
- analyzer、widget test、进程内替身 API、编译或打包成功均属结构或本地证据，不得替代上述结果证据；受影响 required case 身份必须由 current ContractGraph 的 App `api_integration` readiness case 选择结果派生并与 CaseResult 精确闭合，CaseResult 必须唯一、`status=passed`、`executed>0`、`failed=0`、`skipped=0`，缺选择身份、缺 raw result、失败或重复均保持 GATE_BLOCK。
- 模拟器/仿真器可支撑Alpha/Beta/Gamma源码集成事实但必须标记`nonPromotable`；`dev1.0 -> main`不把它升级为包发布证据。真实Android/iOS物理设备只验证RC最终签名包，并进入QualificationFact而非五分钟promotion。
- 候选的三档集成深度定义保持为 `no_live`（runtime-neutral 免真启）、`alpha_integration`（默认 Alpha 集成）、`abg_release_sensitive`（release-sensitive 全 ABG），只能由 typed impact 派生，不得人工改档或降档。

## 4. 契约引用

- trace gate：`quwoquan_ops/cli/feature_tree.py`
- test layout：`quwoquan_ops/gate/scaffold/verify_test_directory_layout.py`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 区分真实证据与开放事项

- GIVEN 一个验收有直接测试引用，另一个验收仅在同节点 OPEN 的完成判定中出现。
- WHEN 三层测试追踪门禁扫描规格与测试。
- THEN 前者计为证据，后者保持未完成；不存在的锚点、错误测试层或悬挂引用被阻断。

<a id="gwt-002"></a>
### GWT-002 对象同构路径与结构结果证据分离

- GIVEN 同一对象在 App、服务与验收执行面声明了职责匹配的测试入口。
- WHEN 治理能力反向解析路径、依赖真实度、support 可达图和当前 runner 结果。
- THEN 每个入口精确归属到 canonical 对象与正确测试层，support 与测试 double 不越过 local_contract 边界。
- AND 静态入口只形成结构证据，真实 CaseResult 单独形成结果证据；缺失、失败或跳过不会被文件存在或另一 producer 的结果掩盖。

<a id="gwt-003"></a>
### GWT-003 端云真启闭环证据缺一即阻断

- GIVEN 一个影响App或app↔cloud边界的exact candidate请求更新dev，并在更新后请求main promotion。
- WHEN 集成准入与promotion核对分层结果证据。
- THEN Alpha/Beta三项真实结果齐备且绑定candidate时才允许trusted publisher CAS；Gamma绑定同一current dev head时才允许promotion。模拟器事实保持`nonPromotable`，真实物理设备事实只在RC qualification产生。
- AND 缺任一项、缺受影响 required case/Journey 身份、CaseResult 或任意状态/候选摘要的 Journey readback 重复、`status=failed|error`、`failed>0`、`executed=0`、`skipped>0`、原始/verified/required Journey 身份集合不完全相等、证据绑定到其他候选摘要，或以 analyzer/widget/编译/替身 API/无关 Journey 结果冒充时，保持 GATE_BLOCK。

## 6. 依赖

- 前置要求：节点验收 ID 稳定，测试目录采用 canonical 三层名称。
- 上游事实：spec 验收、OPEN 和测试 `spec_ref`。
- 下游结果：可执行证据关系或 GATE_BLOCK。
- 父级设计：`DEC-001`、`DEC-003`

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 对象同构路径与分侧结果证据尚未完整强制

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：当前物理测试门仍容纳旧技术大桶，App 路径未逐级验证 context/object，readiness 入口也未把 App、服务与 Ops 的结构证据和 runner 结果完整分侧承载，因此局部文件存在仍可能掩盖另一侧缺口。UAT 与 ops 层测试义务由 `quwoquan_ops/gate/verify_readiness_case_coverage.py` 看护：磁盘验收测试必须有契约 readiness case，UA 声明 runner 路径 strict-zero，无缺口容忍基线。全部有 UAT 测试的对象声明 `layer: user_acceptance` case，全部有环境验收脚本的服务声明 `producer: ops, layer: environment_acceptance` case，runner 均携带 `readiness_case`/`spec_ref` 双向标注并由 loader 校验；ops runner 的 canonical 位置是 `tests/acceptance/user_acceptance/service_ops/<service>/` 内的实现脚本（loader 与根 AGENTS 条款同源单轨）。
- 完成判定：`GWT-001` 与 `GWT-002` 对应行为满足且真实测试 `spec_ref` 有效；`readiness_case_coverage_baseline.json` 两个缺口清单清零后删除。
- 依赖：对象级 case、生产 runner、canonical snapshot authority、结果 receipt 与 stage 消费边界完成。

<a id="open-002"></a>
### OPEN-002 端云真启闭环 gate 尚未接入合入执行路径

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：`REQ-005` 的 gate 已核对三项 exact candidate 结果证据，并对真实 Service CaseResult 与 Journey readback 的显式 required 身份、唯一性、精确闭合、成功状态/计数及稳定 recovery fail-closed；typed impact 档位由 `impact_planner_core.derive_integration_depth` 派生，Delivery Gate 的 Service PR job 已改为 synthetic merge candidate，App 重活仍由 lane push 生产 exact head 证据。剩余缺口是受影响 App `api_integration` readiness case 与 required Journey 尚未由 current ContractGraph 自动投影进 bundle，且该 gate 尚未接入 lane PR 合入执行流程；在此之前更新 `dev1.0` 仍须由集成执行者使用 ContractGraph 选择结果组装 bundle 并执行本 gate，执行遗漏或自报不完整 selection 不得冒充闭环。
- 完成判定：current ContractGraph 自动投影受影响 App `api_integration` required case 与 required Journey，由 canonical producers 为 exact merge candidate 组装完整 bundle；至少一个 App/app↔cloud 候选按 `GWT-003.t1` 放行且负例按 `GWT-003.t2` 阻断，并归档执行 receipt。
- 依赖：ContractGraph automatic required selection、canonical launcher/Journey/Service CaseResult producers 与 lane PR 合入 gate 接线。
