# L2 Design：三层测试模型 (`runtime-test-pyramid`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“以 local_contract、api_integration、user_acceptance 形成唯一测试分层和环境证据模型”需要 `three-layer-evidence` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：以 local_contract、api_integration、user_acceptance 形成唯一测试分层和环境证据模型。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`three-layer-evidence`](./three-layer-evidence/spec.md)：已支持验收至少有一个职责匹配且可执行的直接 `spec_ref`；被 OPEN 声明的未完成验收不得计为通过。
- [`branch-coverage-governance`](./branch-coverage-governance/spec.md)：对象级覆盖结果从真实绿测试派生，分支、未归属源码和覆盖回退不会被文件存在或人工基线掩盖。

## 3. 端云与数据流

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 物理测试层只保留三层 canonical 目录
- 决策：物理测试层只保留 local_contract、api_integration、user_acceptance 三层；App 路径与 production 同构为 `<layer>/<domain>/<context>/<object>`，服务 local_contract/api_integration 同构为 `<layer>/<context>/<object>`。
- 决策：App 跨对象 Journey 按依赖真实度单轨归档。使用测试树 typed double、Provider 或 Widget 的本地契约只进入 `test/local_contract/journeys/<journey>/` 并使用 `__local_contract_test.*` 后缀。
- 决策：使用 production Remote composition 的真实 Journey 只进入 `test/user_acceptance/journeys/<journey>/` 并使用 `__user_acceptance_test.*` 后缀；禁止 `api_integration/journeys`。
- 约束与影响：`<journey>` 必须为 `snake_case`，测试文件是 journey 目录的直接子文件，复用 helper 只进入 `test/support`；路径只证明结构归属，不证明 Remote Journey 已执行或通过。
- 决策：support 只存放共享 harness、fixture factory 与 typed double 定义，不能承载测试用例、业务断言或可被 production composition 引用的实现；对象 support 与 production 同构为 `<domain>/<context>/<object>`，真正横切的 runner、platform 与 boundary harness 只进入 `runtime`。
- 决策：support 消费者直接 import 唯一 owner，禁止 `repository_mock_reexports` 或按 `fakes/fixtures/cloud_services` 聚合的跨对象 barrel；普通 fixture/double/golden 使用对象或行为语义命名，部署环境名称只允许出现在真实环境验收 runner 与可信结果回执中。
- 理由：对象同构路径可直接反查 owner 和验收锚点，依赖真实度决定测试层则能阻止 fake HTTP、Memory 集成或 path-UAT 把未验证边界伪装成高层证据。
- 被否决方案：按 `ui/cloud/core/pages/quality` 建测试大桶、按测试框架或运行速度另建层级、让 support 成为不受约束的共享测试包、以集中映射表关联对象。
- 约束与影响：local_contract 可用测试 double，api_integration 必须打真实进程依赖，user_acceptance 必须使用 production Remote composition。
- 约束与影响：路径、spec_ref 与摘要只证明结构入口，runner CaseResult、环境和用户回执另作结果证据。
- 关联要求：`REQ-001`
- 影响 Story：[`three-layer-evidence`](./three-layer-evidence/spec.md)
- 关联验收：`SIT-001`

<a id="dec-002"></a>
### DEC-002 覆盖率按 canonical 对象归属并只从绿测试结果建立棘轮

- 决策：覆盖率计量单元由 production 的 canonical domain/context/object 路径实时派生，不维护人工对象清单；无法归属的生产源码、没有计量单元的受测对象或归属冲突均先阻断。
- 决策：App 使用对象级 line 与 branch 结果；Go 使用对象级 statement 结果并以对象状态机、权限、错误恢复和幂等 decision table 覆盖语义分支，其他 runtime 使用其原生 line/branch 能力。
- 决策：baseline 只能从测试成功且可绑定 commit/config/toolchain 摘要的结果建立；对象覆盖不得回退，新增可判定分支必须被触达或保留明确未准出状态。
- 理由：domain 级总数会让高覆盖对象掩盖零覆盖对象，红测试或静态文件扫描生成的 baseline 又会把“有代码”误报为“已执行”；对象级绿结果才能成为可比较的质量棘轮。
- 被否决方案：手工 coverage registry、只看仓库总百分比、从失败或未执行测试写 baseline、用覆盖率替代 api_integration 或 user_acceptance。
- 约束与影响：本决策只治理代码触达，不替代三层 CaseResult、四环境、Provider 或设备证据；快速变更门可以只计受影响对象，完整准出必须覆盖全部受影响对象且使用同一计算口径。
- 关联要求：`REQ-003`
- 影响 Story：[`branch-coverage-governance`](./branch-coverage-governance/spec.md)
- 关联验收：`SIT-001`

<a id="dec-003"></a>
### DEC-003 结构证据与测试结果由不同 producer 写入不同维度

- 决策：静态派生器只记录测试入口、owner、spec_ref 与内容摘要等结构证据；runner 只在真实执行后写入 CaseResult、环境、制品和用户验收回执等结果证据。
- 理由：将两者折叠成一个布尔值会让入口存在但从未运行、运行失败和真实通过三种状态无法区分，并使 readiness 可以被静态文件伪造。
- 被否决方案：扫描到测试文件即记 pass、由 metadata 作者手写结果、把 App 与服务同层入口混进一个可由任一侧满足的数组。
- 约束与影响：结构证据按 App、Service、Data、Ops producer 分侧；结果证据绑定对象、验收锚点和不可变候选摘要。缺任一必需结果时保持 GATE_BLOCK，不降级为合法空。
- 关联要求：`REQ-001`、`REQ-003`
- 影响 Story：[`three-layer-evidence`](./three-layer-evidence/spec.md)、[`branch-coverage-governance`](./branch-coverage-governance/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 本层不复制父级通用质量清单；特有阈值由对应 REQ、验收锚点、canonical contract 与真实测试共同约束。
