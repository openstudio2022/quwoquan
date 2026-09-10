# L3 Story：多环境环境实例隔离 (`multi-environment-instance-isolation`)

> 所属能力：[`deliver-deploy-prod-pipeline`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L2 DEC-015](../design.md#dec-015)

## 1. 用户价值

作为开发、测试或运维角色，我希望同一工作站的不同 target 可以持续并行，同一 target 的相同运行身份被安全复用而不是重复建栈；不同设备可连接同一 nonprod 包，启动、更新、故障与清理不得干扰其他环境，从而让内容读取和环境验收可恢复、可定位。

## 2. 范围与非目标

### In Scope

- 本机 `alpha-local / beta-local / gamma-local` 及独立 local slot `prod-sim` 的异 target 并行、同 host-target 单实例；本任务不隐式启动 prod-sim。
- Alpha 离线 App 不创建云栈，只持设备会话绑定；按需 Alpha importer/API gate 的云栈与离线 App 证据分离。
- target-scoped 端口、Compose project、Podman network/container/volume、部署根、缓存、
  数据卷、JWT secret、local-managed CA、候选、release、运行与报告证据。
- `prepared -> partial -> running -> stopped` 启动事务、partial-up 清理与 fail-closed repair。
- 真实 phase 计时、唯一 matrix run 目录、runtime identity 与 immutable release readback。

### Out of Scope

- 自动扩容、采购或生产跨故障域部署；本地并行不承诺宿主机/容器 VM 故障下零中断。
- 共享数据库、共享 volume、固定容器名、固定测试对象或 fixture 作为隔离捷径。
- 将测试替身输出、固定路径报告或旧 target 回执视为 live 环境证据。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 多环境环境实例隔离

- 本机实例键为 hostIdentity + target，跨终端、会话、worktree 与共享 container daemon 使用同一受管运行权威；每个 target 至多一个 active runtime generation，test-live 与 immutable candidate 不得作为两套同时运行。worktree、用户自设锁根和请求 ID 不得绕过单例。
- 相同 runtime/config identity 并发启动只创建一次并等待同一结果，后续 attach 只增加独立使用租约；不同 identity 返回明确冲突，不因工作树源码变化重建现有栈。显式更新与内容 CAS 独立，package 只准备候选，不改变 running identity。
- Compose/Podman project、network、volume、部署根、数据库 namespace、Redis、Search index、对象存储与媒体激活根、凭据、CA、转发、active pointer、run/report、缓存和 outbox 均按 target 隔离。只允许验证后的不可变字节只读共享，GC 尊重所有 target 引用。
- 发布前驱顺序约束资格签发，不要求物理运行串行；设备 slot 可排队，不得因此 down 另一个健康 target。
- package、up、health、release verify、feed readback 与 down 必须绑定同一 baselineId、
  runtime identity 和 immutable release；跨 target 回执或数据命中必须 `GATE_BLOCK`。
- service-core 候选必须同时绑定 11-module manifest 与组合镜像 identity；每个 target 只能运行一种核心 topology，切换或回滚不得与原 split-services workload 并存，不限制其他 target 运行。
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
- 启动事务明确 created/reused 资源 ownership；partial 失败只回收本次新建资源，保留复用的服务、数据、证书和转发。清理失败保留 partial、首错与清理错误，不伪造 stopped；正常退出及最后一个 consumer 离开默认也不 down 共享 runtime。
- `down` 只有在 runtime、App 实例和 canonical ports 均释放后才能提交 `stopped`；
  `repair restart-stack` 在 down 失败时必须短路，禁止继续 up。
- 端侧绑定键为 deviceId + applicationIdentity；不同设备可使用同一 nonprod 包并行，同设备一次只有一个环境，不新增三套 App 包名。跨环境切换先显式结束旧会话、取消请求/播放器/连接，再冷启动或重建完整 ProviderScope，禁止在原 client 动态换 base。
- acquire/bind/release 原子比较独立 nonce、exact leaseId 与 runtime generation；旧退出、PID 复用或 TTL 到期不能释放新会话。direct 连接同样持安全使用租约，但不增加 managed/UAT authority；Alpha 离线仅持设备绑定。
- stop/restart/repair 只有在具备目标 generation、资源 ownership 及受影响 lease 协调结果时才能 mutation，不能凭端口/PID/进程名杀进程；结构化存活性无法确认时保留占用并显式恢复。
- Prod up 只消费准入的不可变候选；Beta/Gamma 及独立 Alpha API gate 的开发会话可由 dev-session 准备并启动/复用 runtime，Alpha 离线 App 不走该云栈路径。App launcher 不反向拥有环境生命周期，也不把新 package 指针当作替换 running 的授权。
- test-live render 必须直接消费当前工作树的第一方 Compose、目标环境 overlay 与 runtime config，并按 target 物化 local-managed TLS、认证 secret、mTLS、对象存储和 Provider substitute；不得读取、创建或激活 immutable candidate/package。Compose project 固定为 `quwoquan_<environment>_test_live`，全部公开端口必须落在该 target 的 canonical 1000 端口块，任一 target/env/project/端口、Compose digest、TLS 或 secret 归属漂移均在 up 前 `GATE_BLOCK`。
- test-live 的 Compose render/build/up 失败属于启动失败并阻断 App handoff；Compose 已成功启动后的服务 health 不健康只形成结构化 `warning`，保留真实 compile/launch 与 health phase，不得把环境宣称为健康，也不得削弱 Prod 的 immutable candidate 准入。
- 多 target 编排按各 target 独立准入、复用并保留 compile/launch、告警与 health；矩阵禁止预先 down 全部 target，失败与取消不得清理未选择或仅复用的实例。严格 health 不通过不抹除真实编译结果，也不产生环境健康伪成功。
- test-live runtime 不拥有非内容 UAT 业务数据。`stackctl verify` 必须从当前选中 CaseResult 的强类型请求图按 target 创建独立 Actor 与交易事实，只加载领域依赖闭包，并在同一 TestDataSession 内完成 provision、业务正文、readback 与 cleanup；执行前必须匹配当前 running runtime、canonical topology、候选绑定和所需 Provider readiness，任一缺失、漂移或创建失败均 `GATE_BLOCK`，结果始终为 run-bound、`nonPromotable=true`。
- test-live 内容绑定默认关闭。显式选择时必须在本次 `running` mutable startup receipt 之后，以完整 `releaseId + verifyRunId + manifestDigest`（commercial 另需 `lifecycleExitRef`）创建 target/attempt-scoped、create-once 的 run-bound binding，再只把同一绑定中的 releaseId、manifestDigest 与 readiness receipt digest 交给 App handoff。缺参、部分参数、跨环境、旧 attempt、symlink/TOCTOU、implicit latest、candidate 或 package 全部失败。consumer release 可不带 lifecycle，但所有 test-live binding 均为 `nonPromotable=true`。
- full runtime 已健康时 bounded 内容任务只复用其能力且不改 baseline receipt；若已有另一种 bounded topology 也不得并建 full runtime。独立 bounded workload 仍占同一 host-target 单例 slot，转换需显式 lifecycle 与 lease 协调。
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
- 同一 target 的重复启动仅在 runtime/config identity 一致时 single-flight 复用；source/config/generated 漂移只影响来源/currentness 诊断，不能自动替换使用中的运行代际。更新只能经显式 target mutation 与版本比较。

<a id="req-004"></a>
### REQ-004 执行权与容量不跨 target 干扰

- scheduler 的请求去重不等于执行权；选中请求后须原子 claim target execution slot，由唯一受管 executor 持有整个有副作用子进程期间的 fence。父任务退出后，在旧子进程终止或可靠隔离前不得新代接管；标记 superseded 不代表清理已完成。
- CPU、RAM、容器 VM 配额、磁盘与构建峰值通过独立 host 预算原子预约，不足仅排队/拒绝新工作，不驱逐既有环境。各环境有资源上限，共享 Docker/VM 管理与全局 GC 保持独立 host 锁和显式授权。
- build 配置与输出按 attempt/target 私有物化，不覆盖源码树共享 generated config；SDK 不支持同目录并发时只锁相应构建输出，共享 codegen 仍串行，不把构建锁扩为环境终身全局互斥。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 多环境环境实例隔离

- GIVEN Alpha/Beta/Gamma 当前工作树可编译，且 target/env 与非生产安全边界有效。
- WHEN 执行 canonical local environment matrix。
- THEN 容量足够时 Alpha API gate、Beta、Gamma 各维持唯一 runtime generation 并持续并行；Alpha 离线客户端不启动云栈。任一 target 的启动失败、更新、回滚或 owned cleanup 不改变其他 target 的运行/内容身份与读取结果。
- THEN 三个 target 的端口、资源名、部署/缓存/数据路径、JWT secret、CA fingerprint与 report 互不相同；test-live 不要求共享 immutable baselineId 或 release receipt。
- THEN 每段使用真实 phase 时长和唯一 report 目录，Feed 证据命中当前 release，最终结果
  只在所有 live 子报告身份一致且成功时为 passed。
- THEN `emulator_only` 通过时只生成
  `ALPHA_BETA_GAMMA_EMULATOR_ONLY_FUNCTIONAL_GREEN`，记录设备覆盖与 Android 真机 waiver；
  final acceptance 与 release receipt 必须拒绝其关闭正式发布 blocker。
- THEN 多 target 编排不预先 down 全环境，只管理本次 created 资源；重复同 target 同 identity 启动复用，异 identity 冲突，package 或工作树漂移不改变运行代际。
- AND 单 target `dev-session` 未显式提供内容四元时保持 unbound 并报告 warning；提供完整当前 attempt 的 run-bound binding 时，App handoff 的内容三元必须与 binding 精确一致，且不得将该绑定写成 immutable candidate、package 或可晋级 release receipt。
- AND 任一启动、清理、证据或身份失败保留首个 canonical blocker 和已有报告，只清理本次 owned partial 资源；未执行依赖 slot 明确 blocked，不扩大失败为其他 target 的停止或伪成功。

<a id="gwt-002"></a>
### GWT-002 启动事务与设备系统信任

- GIVEN target 使用 local-managed CA，且调用方选择受管 Simulator/Emulator。
- WHEN `stackctl up` 或 canonical device launcher 启动 App。
- THEN Ops 在设备系统 trust store 安装并按根指纹验证 target CA，App 继续使用默认系统
  信任栈；不得向 Dart 注入私有 CA 或关闭 TLS 验证。
- THEN down/release 只撤销当前 target/device/lease 拥有的信任，并保留可审计 receipt。
- AND down 或撤销失败时保持 fail-closed，不得继续 repair up 或报告 stopped。

<a id="gwt-003"></a>
### GWT-003 跨工作树竞态、执行接管与设备旧租约安全

- GIVEN 两个 worktree/调度者访问同一 host 与 container daemon，同 target 有延迟子进程或旧设备租约，其他 target 正常读取。
- WHEN 并发启动、package、请求 supersede、父任务崩溃、同设备显式切环境或预算不足。
- THEN 同 target 只允许一个 creator/executor 和运行 generation，同 identity attach 复用、异 identity 冲突；自设锁根或 daemon authority 不一致阻断，package 不替换 running，旧子进程未终止/隔离前新代不能 mutation。
- THEN 独立 nonce/exact lease 使旧 release、PID 复用与迟到响应无法解绑或回写新会话；不同设备共用 nonprod 包，同设备切换重建上下文，direct 租约不签发更高 authority，最后 consumer 离开不自动 down。
- THEN 容量不足只拒绝/排队新任务，矩阵不 down 未拥有实例；失败清理只回收 created 资源，其他 target 的凭据、信任、转发、内容身份和读取预算不受影响。

## 6. 依赖

- 前置要求：[`deliver-deploy-prod-pipeline`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-015](../design.md#dec-015)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 多环境环境实例隔离 验收证据

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：异 target 并行、跨 worktree 单实例、executor 全周期 fencing、exact lease、CPU/RAM/VM 预算与非干扰尚缺 fresh 实现及现场证据；既有全局锁或单环境测试不能证明这些性质。
- 完成判定：`GWT-001`、`GWT-002`、`GWT-003` 由 local_contract 的竞态/旧租约/容量拒绝、api_integration 的共享 daemon/故障清理，以及不同设备持续读取的 user_acceptance 逐条绑定；未测保持阻断。

<a id="open-002"></a>
### OPEN-002 prod 平面发布口与 local canonical block 的主机隔离前提未裁决

- 类型：`external_blocker`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：`quwoquan_ops/cli/prod/render_prod_plane_stack.py` 的 `_prod_plane_admin_publish`
  断言 prod 平面 admin 主机端口（12019/22019/32019）不得落进任何 local port profile 的
  canonical block，理由是「落进去会让 local teardown 把 prod 端口误认成目标 runtime 自有」。
  但同一渲染器的 `render_prod_plane_stack_lib/runtime_outputs.py` 往同一份 prod `stack.env`
  写 `LOCAL_GAMMA_HTTP_PORT=19000`、`CHAT=19200`、`POSTGRES/MONGO/REDIS=19400/19410/19420`，
  全部正是 gamma-local 的 canonical block；`constants.py` 的 `EXTERNAL_*_PORT` 同为 194xx。
  若该理由成立，同文件约 20 个端口都在制造同一危害；若不成立（prod 与 local 不共享主机），
  admin 那条断言的理由本身不成立。二者只能取一，且该断言当前只覆盖 admin 一个端口，
  `80:80`、`443:443`、`39000:80`、`29000:80` 均无同样判据。
- 完成判定：`GWT-001` 的「三个 target 的端口、资源名、部署/缓存/数据路径互不相同」一条
  扩展到覆盖 prod 平面与 local target 之间的主机端口隔离。
  前置事实由 environment topology 裁定：`prod-hosted` 声明为 `ssh-hosted`、`prod-sim`
  声明为 `backend=local`，需先定 `render_prod_plane_stack` 服务其中哪一个。
  据此把 block 检查扩展到本平面全部 published host port，或删除只覆盖 admin 的那条断言并
  改为记录隔离前提；两种取法都必须有绑定 `GWT-001` 的 `local_contract` 判否用例。
