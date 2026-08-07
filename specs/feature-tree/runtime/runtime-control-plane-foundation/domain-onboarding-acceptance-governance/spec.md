# L3 Story：领域引导验收治理 (`domain-onboarding-acceptance-governance`)

> 所属能力：[`runtime-control-plane-foundation`](../spec.md)
>
> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，我希望由物理路径、唯一拓扑与运行证据计算领域接入状态，禁止 onboarding/readiness 注册表，从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- metadata/source/test 路径反向映射
- App、runtime、Ops 与领域服务的生产/测试/生成物/环境输出边界反向映射
- 四环境拓扑、配置和三层证据闭环
- 禁止第二真相源回潮

### Out of Scope

- 新建领域接入登记平台
- 旧 schema 或注册表兼容期

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 无登记领域接入治理

- 不存在第二真相源，且统一门禁能够发现路径、拓扑、配置、部署输出和证据漂移。
- 服务业务测试只能位于 canonical `tests/<layer>/<context>/<object>/`；production `internal/**` 与 `cmd/**` 的测试、production App 的 fixture/Mock 可达图、仓内或 `.qwq_output` 内的部署工作目录均为阻断项。

<a id="req-002"></a>
### REQ-002 没有 gamma/prod 当前证据时，派生状态必须保持未就绪，不得人工改成 ready

- 没有 gamma/prod 当前证据时，派生状态必须保持未就绪，不得人工改成 ready。

<a id="req-003"></a>
### REQ-003 readiness 证据只由 metadata 装载与图构建管线派生

- 装载阶段从受版本控制的物理路径反推对象证据 packet，图构建阶段消费该 packet 派生 `objectReadiness`，这是端云唯一的 readiness 证据派生点。
- metadata 作者不得手写任何 evidence 字段，端侧也不得再建第二个 readiness 判定入口。
- 云侧对象实现证据必须同时覆盖领域服务与 control-plane 两处对象层根；`platform_ops` 上下文的 owner 位于 control-plane，遗漏该根等于把该上下文全部对象误判为无证据。
- 云侧两层对象验证路径按 context 与 object 精确定位，只有落在 canonical 对象路径下的文件才计入该对象证据。
- 端侧实现证据从 `lib/service/<service>/<context>/<object>` 的能力必需层派生；app_client 只取自对象 adapters，page 取自页面对象契约的 source owner/participants 与 source owner `presentation/**` 真实文件的交集，不额外强制 `pages` 子目录。
- page 证据只在对象被页面对象契约认领时才要求；认领事实与页面文件事实必须分列两个字段，认领成立而页面文件缺失只让页面证据为空，不得退化成未认领而免除该项要求。
- App 三层结构证据按 `test/<layer>/service/<service>/<context>/<object>` 精确定位；服务与 App 的本地结构验证入口、真实边界验证入口必须按 producer 分侧表达，任何一侧存在入口都不能替代另一侧的能力义务。
- 端侧对象目录搬迁期内，派生器遇到端侧路径缺失必须记为无证据并让 `objectReadiness.missing` 如实暴露，禁止 fail-fast 中断整个 metadata 装载，也禁止用占位证据补齐。
- 四环境证据只认既有四环境证据产物，查不到即为空并由 missing 暴露，不得编造。

<a id="req-004"></a>
### REQ-004 operation 商用状态与对象 readiness stage 是两条独立轴

- operation 级 `commercial.status` 是对象级 `commercial-ready` stage 的输入，对象 stage 不得反过来成为 operation 状态的前提。
- 对象 stage 派生把「该对象全部 operation 均为 ready」当作输入之一，若 operation 的 ready 判定再依赖对象 stage 或环境证据，判定即成环并永远无法收敛。
- operation 的 ready 只由该 operation 自身的实现与运行依据决定，四环境与用户验收依据只影响对象 stage。

<a id="req-005"></a>
### REQ-005 结构性证据与结果证据必须分开命名且不可互相顶替

- 结构性证据是实现 seam 与三层验证文件真实存在并以内容摘要绑定确切字节，可由静态派生得到，只证明实现与验证入口已就位。
- 结果证据是对象级用例结果、四环境证据与用户验收回执，只能由 runner 在真实执行后附加，不可由任何静态派生器产出。
- `implemented` stage 只要求结构性证据；`commercial-ready` stage 在此之上额外要求结果证据，缺结果证据时派生状态必须停在 `implemented`。
- 红线：静态派生器不得把文件存在解释成验证已执行或已通过，也不得用结构性证据替代任何一条结果证据。
- 两类证据必须在派生输出上分开命名，禁止合并为同一个布尔字段，否则调用方无法区分「入口缺失」与「入口就位但未运行」。
- 结构证据还必须按 Service、App、Data、Ops producer 分侧；平铺的 localContract、apiIntegration 或 userAcceptance 数组若可由任一 producer 单独满足，就不能作为端云闭环判据。
- 用户验收回执属于结果证据，只能由 runner 在真实执行后附加；派生输出当前没有承载该回执的字段。
- 现有的用户验收字段表达的是验收入口是否就位，属于结构性证据，不得被读成回执，也不得据此把对象升到 `commercial-ready`。

<a id="req-006"></a>
### REQ-006 结果证据必须绑定执行对象与不可变候选

- runner 结果必须能反查 object/operation、验收锚点、case、commit、配置与制品摘要；环境结果另需环境、Provider 与设备身份，用户验收回执还需用户可见终态和恢复结果。
- `modeled` 与 `contract-ready` 只由 canonical contracts 决定，`implemented` 只由完整结构证据决定，`commercial-ready` 还要求职责匹配且通过的当前结果证据；失败、跳过、历史候选或缺摘要结果均不得提升 stage。
- 覆盖率、测试入口、环境配置文件或合法业务空结果都不能替代真实边界、用户验收、Provider、四环境、设备或回滚结果。

<a id="req-007"></a>
### REQ-007 Python 脚本 owner、角色与入口闭包必须由实时物理树派生

- 稳定脚本角色闭集为 `gate / cli / lib / generator / runner / tool / migration / hook`；角色由物理位置、命名、入口引用和 import 关系实时派生，不维护 registry、inventory、债务 baseline 或 orphan allowlist。
- App、Service、Ops、Data 物理树内的全部 Python 文件必须由同一派生器唯一归入受管脚本、生产模块、验证资产、测试 support、generated 或 vendor 边界；未知路径不得因不在脚本枚举根内而逃逸治理。生产模块、测试和 generated 的结构结论复用所属架构、测试目录与 codegen 门，不复制第二套规则。
- App 领域脚本的 L1 必须与 `lib/service/<service_name>_service` 一致；只在脚本确实属于单一 context/object 时下钻 L2/L3，且对应生产 owner 目录必须真实存在。runtime、platform 与人工工具按 concern 归档，不得继续平铺。
- Service 领域脚本的 L1 必须与 `services/<kebab-service>` 一致；只在单一 context/object owner 可证明时继续下钻。跨服务 contracts/codegen/runtime/verify/tools 保持 concern-first，`contracts` 不混入 verifier。
- Ops 保持 `cli/ci/gate/hooks/migrations/environments/verify` 等职责树，跨环境验收 runner 保持在 canonical `service_ops/<service>` owner；Data 继续由 Data CLI-first 与既有脚本架构门派生。
- Data canonical release 派生只消费 canonical/release snapshot 与其显式引用的治理快照；环境 import、homepage id、环境 URL 与运行回执只属于 environment append-only evidence，不得进入 immutable release lookup。
- 稳定可执行路径、schema key 与测试标识禁止 `t1..t4 / m6 / m7 / b10 / phase0 / partN` 等阶段名；历史说明文字不作为可执行标识。
- 源码域禁止解释器、测试、lint、编辑器缓存与临时/备份脚本；可再生产输出只进入 `.qwq_output` 或受管仓外缓存。一次性能力必须位于 migration concern，并具有可重复执行、回放或退出证据。
- Make、workflow、gate、CLI 与脚本内帮助路径引用必须指向真实文件。rename 必须同时更新 producer、consumer、import、测试与文档，不提供旧路径 shim。
- gate 或 scanner 必须证明目标根存在且至少命中一份受检源码；空扫描不得产生通过结果。人工 tool 必须能由 CLI、Make、runbook、spec 或测试中的当前引用证明 owner 与用途，否则属于确定性归类错误。
- orphan 只作为报告候选，必须人工裁决为接线、转入 tool 或删除；不能仅凭静态未引用自动删除。`report` 对同一物理树必须字节幂等，`check` 只阻断可确定的路径、角色与命名违规。

## 4. 契约引用

- canonical：`quwoquan_ops/gate/verify_service_architecture.py`
- canonical：`quwoquan_ops/environments`
- canonical：`object.yaml.kind`
- canonical：`quwoquan_service/internal/metadata/load`
- canonical：`quwoquan_service/internal/metadata/graph`
- canonical：`quwoquan_service/services/*/internal/<context>/<object>/<layer>`
- canonical：`quwoquan_service/control-plane/*/internal/<context>/<object>/<layer>`
- canonical：`quwoquan_service/services/*/tests/local_contract/<context>/<object>`
- canonical：`quwoquan_service/services/*/tests/api_integration/<context>/<object>`
- canonical：`quwoquan_app/test/local_contract/<domain>/<context>/<object>`
- canonical：`quwoquan_app/test/api_integration/<domain>/<context>/<object>`
- canonical：`quwoquan_app/test/user_acceptance/<domain>/<context>/<object>`
- canonical：`quwoquan_app/lib/service/<service>/<context>/<object>/adapters`
- canonical：`quwoquan_service/contracts/metadata/_shared/page_object_contract.yaml`
- canonical：`quwoquan_app/test/user_acceptance`
- canonical：`quwoquan_ops/tests/acceptance/user_acceptance`
- canonical：`quwoquan_ops/gate/object_path_map.py`
- canonical：`quwoquan_ops/gate/verify_python_script_governance.py`
- canonical：`quwoquan_ops/gate/verify_entrypoint_script_paths.py`
- canonical：`quwoquan_data/scripts/verify/verify_script_architecture.py`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 无登记领域接入治理

- GIVEN 领域对象、源码、部署和测试资产已进入统一扫描范围。
- WHEN 执行统一服务架构门禁并汇总三层测试结果。
- THEN domain/context/object/layer 可唯一反推，接入与 readiness 由证据计算。
- THEN 服务、App、runtime 与 Ops 的 production/test/generated/environment-output 路径均可由 metadata、依赖和环境契约反推，出现旧测试根、fixture/Mock production reachability、第二 composition root 或仓内 deploy work root 即阻断。
- THEN onboarding/readiness/对象服务注册表缺失不会阻断，出现则门禁失败。

<a id="gwt-002"></a>
### GWT-002 端侧目录搬迁期内 readiness 证据仍如实派生

- GIVEN 云侧对象层与对象测试路径齐备，端侧对象目录处于搬迁中且部分对象缺 adapters 或页面文件。
- WHEN 执行 metadata 装载与图构建并派生 `objectReadiness`。
- THEN 云侧证据同时从领域服务与 control-plane 两处对象层根解析，端侧缺失路径记为无证据。
- AND `objectReadiness.missing` 如实列出缺口，装载不中断且不写入占位证据。
- AND 四环境证据查不到时保持为空，派生状态不得升为 ready。

<a id="gwt-003"></a>
### GWT-003 结构入口不能冒充 runner 结果

- GIVEN 同一对象的 Service 与 App 验证入口已经就位，但当前候选缺少用户验收、四环境、Provider 或设备执行回执。
- WHEN metadata 装载器派生结构 packet，runner 汇入当前 CaseResult 并计算对象 stage。
- THEN Service/App/Ops 入口按 producer 分侧保留为结构证据，文件存在不会生成通过结果。
- AND 缺少的结果维度逐项可见，对象最多停在 implemented，不会被覆盖率、另一 producer 的入口或历史候选提升为 commercial-ready。

<a id="gwt-004"></a>
### GWT-004 Python 脚本治理无第二 inventory 且可重复派生

- GIVEN App、Service、Ops、Data 的全部 Python 文件、受管 Shell 脚本和生产 owner 物理树，以及当前 Make/workflow/gate/CLI/import/test/spec/runbook 引用。
- WHEN 对同一提交连续执行脚本治理 `report`，并执行入口路径闭包检查。
- THEN 两次报告字节一致，全部 Python 文件数等于各治理边界分类之和，且每个受管脚本的 scope、角色、引用和 orphan 候选由当前物理树派生，不读取 registry、baseline 或人工 allowlist。
- AND App/Service 的 L1 owner、可证明的 context/object 下钻、Ops/Data concern、里程碑命名与失效入口均产生可定位结果。
- AND 未分类 Python、临时缓存/备份、无 owner tool、空扫描 gate、canonical release 读取环境回执与失效测试/文档路径均产生阻断结果。
- AND acceptance runner、generator 与被 import 的 lib 不被误判为可自动删除的 orphan；orphan 候选只报告、不自动删除。

## 6. 依赖

- 前置要求：[`runtime-control-plane-foundation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 无登记领域接入治理

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺统一门禁对路径、拓扑、配置、部署输出与四环境证据漂移的完整直接证据；端侧对象目录搬迁完成前，派生结果只能如实暴露端侧证据缺口，无法给出全量证据。
- 完成判定：`GWT-001`、`GWT-002` 与 `GWT-004` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 动态结果合同尚未接入可信 runner 与当前候选回执

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：当前尚缺对象级 readiness case、生产 runner、canonical snapshot authority、当前 receipt 解析与 stage 消费的完整接线；动态 result/receipt 类型存在仍不能形成职责匹配的用户验收或四环境结果。
- 缺上述执行链时，调用方仍只能在「把入口声明或调用方自报 digest 当回执用」和「让全部对象停在 `implemented`」之间二选一；前者违反本节点红线，后者是当前必须保留的诚实结果。
- 关闭方式是由对象合同声明 case，可信 runner 只在真实断言后输出结果，并由 evaluator 从 canonical package/activation manifest 解析当前候选摘要、复算 receipt bytes 后消费；case、runner、snapshot authority、receipt 与 stage 消费缺一不可。
- 完成判定：`GWT-003` 对应行为满足且真实测试 `spec_ref` 有效
