# L3 Story：多环境环境实例隔离 (`multi-environment-instance-isolation`)

> 所属能力：[`deliver-deploy-prod-pipeline`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，我希望同一工作站上的 Alpha、Beta、Gamma
能够按明确的共享资源策略串行验收，同时保持端口、Compose/Podman 资源、数据卷、
凭据、CA、候选、release 与报告证据完全按 target 隔离；任一启动或清理失败都留下
可恢复回执且不产生伪成功，从而让首页与核心业务的环境结论可重复、可定位。

## 2. 范围与非目标

### In Scope

- `alpha-local / beta-local / gamma-local` 的本机共享资源互斥与串行矩阵。
- target-scoped 端口、Compose project、Podman network/container/volume、部署根、缓存、
  数据卷、JWT secret、local-managed CA、候选、release、运行与报告证据。
- `prepared -> partial -> running -> stopped` 启动事务、partial-up 清理与 fail-closed repair。
- 真实 phase 计时、唯一 matrix run 目录、runtime identity 与 immutable release readback。

### Out of Scope

- 在同一工作站并行运行三个商业 runtime；本地 `localResourceGroup` 明确要求串行。
- 共享数据库、共享 volume、固定容器名、固定测试对象或 fixture 作为隔离捷径。
- 将测试替身输出、固定路径报告或旧 target 回执视为 live 环境证据。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 多环境环境实例隔离

- Alpha、Beta、Gamma 本地 target 共享 `workstation-commercial-runtime`，同一时刻只允许
  一个 runtime 占用；矩阵按 `alpha -> beta -> gamma` 串行运行，每一阶段先确认前一
  target 已停止并释放 canonical ports。
- 共享资源互斥不允许削弱 target 隔离：Compose/Podman 资源、部署根、缓存、数据、
  JWT secret、CA、候选、release、run/report 均必须包含并验证 target identity。
- package、up、health、release verify、feed readback 与 down 必须绑定同一 baselineId、
  runtime identity 和 immutable release；跨 target 回执或数据命中必须 `GATE_BLOCK`。
- matrix 结果只能来自唯一 run 目录内的 live 子报告；测试替身不得写入 canonical live
  report 根，缺 `exitCode`、子报告、状态、environment 或 runtime identity 一律失败。
- matrix 的设备覆盖必须显式选择 `full` 或 `emulator_only`。`emulator_only` 仅覆盖 iOS
  Simulator 与 Android Emulator，结果必须使用独立 claim 并标记 `nonPromotable=true`；
  缺 Android 真机时禁止复用正式 `ALPHA_BETA_GAMMA_LOCAL_GREEN`。

<a id="req-002"></a>
### REQ-002 启动事务、清理与设备实例边界

- 每次启动写 target-scoped startup attempt receipt，状态只能按
  `prepared -> partial -> running -> stopped` 推进，并绑定 Compose project、镜像组合、
  runtime config digest 与启动参数。
- 非正式本地启动在进入 `partial` 后失败必须 best-effort teardown；清理失败保留
  `partial` 与原始错误、清理错误，禁止删除诊断事实或写 `running/stopped` 伪成功。
- `down` 只有在 runtime、App 实例和 canonical ports 均释放后才能提交 `stopped`；
  `repair restart-stack` 在 down 失败时必须短路，禁止继续 up。
- 端侧每次启动必须显式绑定 `device-id` 或等价唯一设备选择结果。
- 端侧实例记录只用于诊断与 stop/list，不得演化为服务端多套编排。
- 环境矩阵、业务数据清单与 runbook 明确“端侧可多实例、本机商业 runtime 串行单套”的统一口径。
- Prod `stackctl up` 只消费已激活的不可变候选；Alpha/Beta/Gamma 开发者冷/热一键会话由 `stackctl dev-session` 从当前工作树实时编排 render、full up、health 与可选 App handoff，App launcher 不得反向拥有环境生命周期。
- `stackctl dev-session --all-nonprod` 必须按 Alpha→Beta→Gamma 串行执行并保留每个 target 的 compile/launch、告警与 health 结果；严格 runtime health 失败不抹除可编译事实，也不产生环境健康伪成功。
- full runtime 已健康运行时，`content-release/content-commercial` 任务必须复用它且不得改写 full startup receipt；无 full runtime 的独立 bounded workload 才拥有自己的启动与停止事实。
- bounded workload 正常、失败或取消后必须恢复进入前 runtime 状态；恢复失败保留 partial/typed blocker，禁止把原本健康的 full runtime 写成 stopped。

<a id="req-003"></a>
### REQ-003 真实计时与隔离证据

- 每个 phase 从命令调用前开始、结束后停止，使用 monotonic 真实时长；phase 与 wall-clock
  预算都必须进入报告并执行 fail-closed 判定。
- matrix run id 必须参与报告目录，重复或并发执行不得覆盖；显式 report dir 必须位于
  canonical output root 且与 target/environment 一致。
- Feed probe 必须校验 canonical `outcome/emptyReason`，并在要求 release content 时证明
  非空结果命中当前 immutable release，禁止仅凭 HTTP 2xx 或空 `items` 判绿。
- Docker 与 Podman 都必须从 target 派生 project/network/container/volume 名称；
  cleanup 只能作用于当前 receipt 绑定资源。
- 同一 target 的重复 `dev-session` 在当前 topology/config 与运行态一致时可走热复用；source/config/generated 漂移进入 `mutableWorkspaceWarnings` 并允许实时重建，安全边界与 target 资源串用仍 fail-closed。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 多环境环境实例隔离

- GIVEN Alpha/Beta/Gamma 当前工作树可编译，且 target/env 与非生产安全边界有效。
- WHEN 执行 canonical local environment matrix。
- THEN Alpha、Beta、Gamma 按序完成实时 render、编译、可选 up、health 与 App handoff；runtime/Provider/content 不健康以独立结果报告，不阻止后续 target 的编译验证。
- THEN 三个 target 的端口、资源名、部署/缓存/数据路径、JWT secret、CA fingerprint与 report 互不相同；test-live 不要求共享 immutable baselineId 或 release receipt。
- THEN 每段使用真实 phase 时长和唯一 report 目录，Feed 证据命中当前 release，最终结果
  只在所有 live 子报告身份一致且成功时为 passed。
- THEN `emulator_only` 通过时只生成
  `ALPHA_BETA_GAMMA_EMULATOR_ONLY_FUNCTIONAL_GREEN`，记录设备覆盖与 Android 真机 waiver；
  final acceptance 与 release receipt 必须拒绝其关闭正式发布 blocker。
- THEN `dev-session --all-nonprod` 复用同一串行资源合同；source/config 漂移只进入告警，严格 health 结果保持真实且不得冒充 compile/launch 失败。
- AND 任一启动、清理、证据或身份失败返回 canonical `GATE_BLOCK`，完成 partial teardown，
  不覆盖旧报告、不继续下一个 target、不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 启动事务与设备系统信任

- GIVEN target 使用 local-managed CA，且调用方选择受管 Simulator/Emulator。
- WHEN `stackctl up` 或 canonical device launcher 启动 App。
- THEN Ops 在设备系统 trust store 安装并按根指纹验证 target CA，App 继续使用默认系统
  信任栈；不得向 Dart 注入私有 CA 或关闭 TLS 验证。
- THEN down/release 只撤销当前 target/device/lease 拥有的信任，并保留可审计 receipt。
- AND down 或撤销失败时保持 fail-closed，不得继续 repair up 或报告 stopped。

## 6. 依赖

- 前置要求：[`deliver-deploy-prod-pipeline`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 多环境环境实例隔离 验收证据

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺 Alpha/Beta/Gamma live matrix 与 Simulator/Emulator 默认系统信任证据。
- 完成判定：`GWT-001/GWT-002` 对应行为满足，且真实三环境与设备测试 `spec_ref` 有效。
