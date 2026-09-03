# L3 Story：环境拓扑与打包 (`environment-topology-and-packaging`)

> 所属能力：[`runtime-config`](../spec.md)

> Journey / Scenario：[`JNY-002 / SCN-005`](../../../spec.md#scn-005)

> 设计归属：[L2 DEC-001](../design.md#dec-001)、[L2 DEC-002](../design.md#dec-002)、[L2 DEC-003](../design.md#dec-003)、[L2 DEC-004](../design.md#dec-004)

## 1. 用户价值

作为打包或部署环境的工程角色，
我希望从每个环境的 `runtime.yaml` 解析完整网络、公开入口与 workload 装配，并生成可复现发布包，
从而确保 alpha、beta、gamma 与 prod 使用同一拓扑规则且差异可审计。

## 2. 范围与非目标

### In Scope

- “环境拓扑与打包”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 环境拓扑与打包

- 子网四平面与结构化 `urlRoles` 的声明要求由 [`system-topology-and-networking` REQ-002](../../system-topology-and-networking/spec.md#req-002) 拥有；本 Story 消费其 topology resolver 投影完成环境装配与打包。

<a id="req-002"></a>
### REQ-002 各环境 runtime.yaml 声明完整网络与公开入口

- `publicBases` 只能由 target resolver 生成；子网四平面与 `urlRoles` 的声明要求见 [`system-topology-and-networking` REQ-002](../../system-topology-and-networking/spec.md#req-002)。
- `alpha` 与其他环境使用同一 Remote composition/schema/网络平面（平面同构事实由 [`system-topology-and-networking` REQ-002](../../system-topology-and-networking/spec.md#req-002) 拥有），只能在容量、endpoint、访问控制、数据 release 和第三方 sandbox 策略上差异化；本条是环境差异化维度的唯一清单。
- App / Service env package 都必须携带 canonical unversioned schema identity、artifact policy 摘要与机器可读报告。
- App 产品支持面固定为 Android、iOS 与 Web；未持有平台工程、包身份、签名和真实安装启动证据的平台不得进入 metadata、schema、CI 或发布矩阵。
- Android 与 iOS 可执行制品必须由 `stackctl package` 从同一只读 source capsule 按 `buildProfile(nonprod|prod)` 构建，Web 只生成一份共享 bundle；每次组件构建必须显式选择 build product，并在写 manifest 前回读包身份、签名、artifact digest 与生产纯度。AppArtifact 只携带 build-profile 级 trust envelope，不携带 target runtime config package；任何 buildMode 与 buildProfile 的制品都不得嵌入 runtime package，构建期默认供给（`embedded_default_package`）已退役、不得回潮。Alpha/Beta/Gamma 的签名 runtime config package 必须在安装后由 canonical activation 写入同一 nonprod App 的平台私有容器，不得触发重编、重签或改变完整 APK/`.app`/IPA 摘要。
- production App 的 pub/plugin/Pod/registrant/linker/filelist/SBOM 与最终 APK/AAB/IPA 可达图不得含 Patrol、integration_test、PatrolJUnitRunner、XCTest 或其他 test runner；设备 UAT 只能由物理隔离的 test host 单向依赖 production App。
- 日常与 CI 构建只消费已锁定依赖；Dart lock、Flutter plugin podspec、Podfile.lock、Pods/Manifest.lock 与 CocoaPods executable/version 任一漂移时在编译前返回 typed blocker，启动路径不得自动 update 锁定声明或联网修复。唯一有界例外是依赖 staleness 的交互式同步恢复：live worktree 的外层 hermetic launcher 在创建 private workspace projection 前检出 active dependency bundle 与当前 source/toolchain identity 漂移时，先输出 canonical `APP.DEPENDENCY.bundle_stale`（detail 只携带白名单字段名，如 `field=nativeResolutionInputDigest`）；仅当 stdin 与 stderr 均为 TTY、处于 live workspace 且同一次 launcher 调用内尚未执行过同步时，才允许自动执行一次 canonical `stackctl app-dependency-sync`，成功且 active readback 与本次 sync attempt 一致后仅重试一次 projection。同步失败、activation ambiguous、第二次 stale、非交互/CI/UAT 或 private projection 内一律 fail-closed，首个 stale blocker 必须先输出且不得被替换；该例外绝不更新任何锁定声明。direct/lightweight 路径不创建 private projection，只对本次直接执行所需的 pub 输入负责。
- 显式 App 依赖同步每次只在 fresh、attempt-scoped 私有 Gradle home 内联网解析，禁止强制 refresh、跨 attempt seed 或 global cache fallback。
- 同一 invocation 只对可辨识的 TLS/connection EOF、reset、timeout、HTTP 408/429/5xx 与 Gradle wrapper 精确空下载摘要做有总时限的最多三次尝试（含首次）；证书/信任/hostname 错误、404、非空 checksum mismatch 和其他确定性失败立即返回，尝试耗尽保留首次失败。
- 每次依赖子进程必须独占 process group；单进程或总时限到达时按 TERM→短 grace→KILL 回收整个后代树后才可重试或返回。恢复成功的日志只持久化 attempt 序号、closed typed cause、backoff 与结果，不得写环境变量、trust path 或 key material。
- 在线解析成功后必须封存依赖闭包，并在另一 fresh 私有 home 完整离线重放；在线成功不得代替离线可复现性。
- CocoaPods 在线安装同样只能在本 attempt 的私有 `CP_HOME_DIR/CP_CACHE_DIR` 内对上述网络暂态做有界重试并保留已下载字节；Flutter config、确定性 Pod 解析失败与封存后的离线 Pod replay 均不得重试或联网，重试耗尽仍以首次失败为 canonical blocker。
- `prod` 只能读取 `prod` 包；禁止 `prod-gray` 环境、目录或 artifact。
- 同一环境存在多个部署 target 时，每个 target 必须写入独立 package 目录，并从环境 `urlRoles + target urlOverrides + portProfile` 的解析结果投影 App 运行时端点；禁止复制环境默认 target 的 URL 或跨 target 复用可变产物。
- `prod-hosted` artifact 禁止包含 mock/seed/debug/local/test host 与跨环境 URL；`prod-sim` 仍属于 `prod` 环境，但全部公共入口必须使用 `*.sim.quwoquan.com`，不得命中生产 host、增加第五环境或放宽 `prod-hosted` 纯度门。
- 南北向公开入口（URL role、gateway 数据流、公网 DNS、TLS profile、CDN、derived link）与东西向端口块模型由 [`system-topology-and-networking`](../../system-topology-and-networking/spec.md) 拥有；本 Story 只消费 topology resolver 投影完成打包、装配与验收，不复制组网规则。
- local environment matrix 的 `emulator_only` rehearsal profile 只要求 iOS Simulator 与 Android Emulator，并且只能签发 `ALPHA_BETA_GAMMA_EMULATOR_ONLY_FUNCTIONAL_GREEN`、`nonPromotable=true` 与 Android 真机 waiver；它保留原始 canonical `ReadinessCaseResult`，但不得写入正式 Green Matrix、Provider 140-cell、`EnvironmentAcceptanceFact` 或 Prod artifact closure。正式 `ALPHA_BETA_GAMMA_LOCAL_GREEN` 使用同一套 `ReadinessCaseResult` schema，必须为 Alpha、Beta、Gamma 的 Android 与 iOS physical slots 逐项声明受测 production-behavior artifact、已登记物理设备、平台 trust/runtime package 与独立机器回执。不得把模拟器结果改标、复制或聚合为 promotable 证据。
- 四环境分别拥有配置与部署 composition，不从 Prod 继承，但引用同一 Web bundle 摘要；非生产 Web hosting 的 `noindex` 与 DNS/证书策略由 [`system-topology-and-networking`](../../system-topology-and-networking/spec.md) 拥有。
- `stackctl status` 是严格只读诊断：只能读取既有进程、package、receipt 与 HTTP 状态，禁止创建或刷新 secret、物化 Provider、启动服务、执行修复或改变环境事实；缺失依赖必须以失败状态返回。
- `stackctl package` 的 immutable candidate 合同用于显式内容验收与 Prod 发布。package plan 必须先派生本次实际读取的 `deploymentInputClosure`，在短 capture 窗口把 staged、unstaged、untracked 精确字节复制到 target-scoped、只读、content-addressed package input capsule，并绑定 target-scoped 唯一 `baselineId`；Alpha/Beta/Gamma 的环境配置输入不同，因此 baseline 允许且预期不同，跨 target 的共同冻结身份只取每份 fresh active candidate manifest 中 `environmentArtifact.releaseTrainId`。capture 期间闭包变化使该次 capture fail closed 并可重试。
- capsule 不得 hardlink 回 live tree，不得跟随仓库外 symlink，且拒绝 FIFO、device 与 socket。App、Service、Ops、ContractGraph、GraphQL、OCI 与 candidate/rollback release 只能从同一 capsule 构建。长构建结束只复核 capsule manifest/tree digest、各 artifact 的同 capsule provenance 与 candidate CAS，不再比较 live workspace；capsule 封存后的任意工作区变化不影响该 candidate。已存在 candidate 只能在全部 package digest 一致时复用且禁止覆盖。
- 完整候选根 `manifest.json` 必须绑定 canonical unversioned schema identity、source/workspace/package/build input/image/runtime digest、正式规格引用，以及候选和回滚 Data release attestation。
- 每个第一方镜像的 build input 必须覆盖服务 owner 与实际编译消费的共享 runtime、generated ContractGraph binding、platform package 和 module lock，不能只散列 owner 目录。
- 当环境部署输入选择 `service-core` 时，11 个核心 Go 服务的 workload 必须由同一服务自治输入生成一个组合镜像；该镜像同时绑定 module 清单、每个 module 的源码/config/migration digest、OCI SBOM 与 provenance。组合不改变原 hostname、port、route、数据源或服务可观测 identity，Python Recommendation、Realtime、RTC 及两个 Ops 服务继续独立。
- 同一 source release train 必须在候选就绪前按 `nonprod/prod` 信任域生成不可交换的组件 artifact。
- Alpha/Beta/Gamma 的 composition 复用同一 owner 的 nonprod `service-core` 与独立服务镜像摘要，Prod 只引用 prod 摘要。每个环境继续独立绑定配置、SecretRef、endpoint authority、runtime topology 与 activation receipt。
- 每个组件摘要都必须绑定 SBOM、provenance 和 purity attestation，禁止跨信任域复用。
- 单环境 BindingCompiler 与环境配置只从同一只读 capsule 生成 candidate-scoped 派生物，不改源码树或 capsule；封存后 live workspace 漂移不得改变当前候选。运行时 Binding API 不接受 environment 参数。
- composition 内 OCI manifest 必须记录实际 image ID；`up` 只能使用该精确 ID，不能使用可漂移 tag。
- 环境 identity 与配置由部署面挂载并绑定配置摘要，不得写入镜像字节。
- `APP_ENV`、`CONFIG_VERSION` 等迁移期变量只能对已挂载配置做相等断言，错配在 listener 前阻断，不得选择 Adapter、endpoint、数据源或策略。
- immutable candidate 的 `up / health / verify / down / rollback` 只能消费候选内部自验证通过的 manifest、签名、GraphQL registry、镜像、release 与唯一 `environment_runtime.yaml`，不得隐式 package、build、从当前工作树重建候选内容或重选候选。候选与当前源码不同只影响 `currentness` 和晋级声明，不得阻止精确旧候选的 status、启动、诊断、验收或退出；候选自身字节漂移仍须阻断。
- 同一 target 的 immutable candidate 只允许一种核心服务 topology：切换到 `service-core` 后，package、up、health、inspect、verify 与 CI 不得同时投影原 11 个独立核心 workload；回滚仅可启动上一份候选的精确 topology bytes，禁止用运行时 flag、mutable tag 或混合 Compose 服务切换。
- Alpha/Beta/Gamma 的 `stackctl dev-session` 是开发者显式拥有的可变冷/热编排入口：直接从当前受治理拓扑与工作树实时 render 临时 runtime config、Compose 与 App handoff，不创建或激活 immutable candidate，也不要求 Data release attestation。开始/结束 source、config 与 generated digest 的变化写入 `mutableWorkspaceWarnings`，不得阻止编译或 App handoff；严格 health/verify 仍独立返回真实失败。
- `dev-session --all-nonprod` 在单工作站按 Alpha→Beta→Gamma 串行运行；隔离 runner 可并行执行不同 target，但不得共享端口、Compose project、secret、CA、release 或 runtime receipt。
- full runtime 是 App 会话的唯一 baseline。bounded content workload 在 full 健康时只复用其能力且不得覆盖 baseline receipt；独立 bounded runtime 必须使用 workload-scoped receipt，并在结束后恢复进入前状态。
- 四环境内容 consumer/commercial readiness 必须绑定同一份 immutable release 的 `releaseId + manifestDigest + sourceOwner=qwq_data`，并校验 discovery `identity=work`、视频书 `identity=work&type=video` 与 `premium_stream` 的 release-bound 非空读回；缺少 Data readiness receipt 或任一 exact query 为空时不得产生通过回执。
- Data release owner 必须从同一 release 对象闭包 create-once `ReleaseUatSamplePlan`，冻结 homepage、article、image、video、Creator、Tag、attribution 的 sample identity 与二维 required cells；Ops 只通过 exact-byte `TargetUatBinding` 将该 plan 绑定到 target/runtime/package/config/platform/device/runner slot。App 自动验收不得从手工环境变量、fixture、旧回执或任何 retired envelope 重建计划或 target binding。
- 应用消费验收必须建模为二维矩阵：`entry ∈ {feed, search, recommendation, direct_or_object_route}`，`carrier ∈ {homepage, article, image, video}`；每个 cell 只能声明 `required` 或 `not_applicable`，后者必须携带 plan-owned reason。entry 是到达内容的入口，carrier 是被消费的内容载体，禁止把二者混称为同一组“四 surface”、以一维列表替代矩阵，或以一个通过 cell 覆盖另一个 required cell。

<a id="req-003"></a>
### REQ-003 双端本地运行按三层 ownership 隔离 direct、managed 与 UAT 证据

- 启动 ownership 唯一分为三层，且不得跨层提升 authority：direct/lightweight `run.sh` 只拥有当前工作树的开发启动；managed/hermetic stackctl launcher 由控制面拥有 runtime preparation、transport receipt 与 consumer lease；UAT/evidence 层只能消费 managed/hermetic 启动链形成 promotable evidence。`content-live` 是未指定 mode 时的默认；`ui-only` 仅用于调试安全 Shell 与页面布局，所有结果必须显式 `nonPromotable=true`。
- `quwoquan_app/run.sh --mode content-live|ui-only --env alpha|beta|gamma [-d <device>]` 在普通调用下是 direct/lightweight 路径：它自身不得 acquire、bind、release `stackctl consumer-lease`，不得创建 managed runtime transport、执行 `adb reverse` 或签发 transport receipt，也不得把 lease/receipt 缺失伪装为已准备；但若 stackctl 外层已交付经 exact readback 验证的 receipt/lease/handoff 与 cleanup obligation，则它必须按同一身份正确绑定和透传给 build/install/activation/attach，并只履行外层明确委托的本 invocation teardown，不得重获、改写、释放或清理不属于该 invocation 的资源。direct 仍拥有自身直接执行所必需的真实 SDK 解析、pub 输入检查与 `pub get`、设备发现/校验、签名 handoff/trust、真实 build/install/activation/attach；显式或自动选择的未知、不可见、非移动或不受支持设备必须在 executor 前 fail closed。direct 的任何输出只属于开发观测，不构成 managed preparation receipt、`app-launch-attempt`/test-live report 或 promotable UAT evidence。
- `dev-session --app-mode content-live|ui-only` 默认 `content-live`。Alpha/Beta/Gamma 的 direct `test_live` 是开发启动严格度：两种 App mode 都不得因服务、Provider、内容或观测 readiness 不可用而跳过真实编译、安装、activation 与启动；`ui-only` 始终标记 `nonPromotable=true`，`content-live` 还必须在启动后真实请求 Remote 内容并如实呈现成功、合法空态或 typed unavailable。direct/lightweight 的 warning+degraded 结果无论 mode 都不得进入 promotion authority 链。
- `make app-dev ENV=alpha|beta|gamma [DEVICE_ID=<id>] [MODE=content-live|ui-only]` 是面向人类的公开一键入口，仅作为 `stackctl dev-session --launch-app --app-mode` 的薄 adapter；`ENV` 默认 `alpha`，`MODE` 默认 `content-live`。设备选择只委托 canonical device authority：唯一设备自动选择，多设备必须显式 `DEVICE_ID`。Make 不拥有设备发现、env/target 扩展、交互、状态机、provenance 或 receipt。
- `make app-uat TARGETS=... PLATFORM=... DEVICE_ID=...` 是面向 AI/自动化的无交互公开入口，只委托 `stackctl app-content-uat`；`TARGETS` 仅允许 `alpha-local`、`beta-local`、`gamma-local` 的非空子集，禁止 Prod。它只编排自动验收，不替代受管字面 `flutter run` 或 IDE surface 的用户验收。
- `quwoquan_app/run.sh --mode content-live --env alpha|beta|gamma -d <device>` 是内容联调与 Hot Restart 的 canonical direct 开发启动执行体，不是完整或 promotable 启动证据链；具名激活入口把受管 bin 目录注入 PATH 后，`run.sh` 在任意工作目录全局可调用，PATH wrapper 只 `exec` 仓库内同一脚本，不复制参数、状态或第二套逻辑。受控制的 IDE Run/Debug（`workspace_ide_debug`）可以薄包装该 direct 执行体，但除非由 stackctl UAT/evidence 控制面显式提供 managed/hermetic launch control，否则同样只有 non-promotable 开发观测 authority。
- managed/hermetic launcher 是 runtime preparation 的唯一 owner：受管 PATH 中的字面 `flutter run` 由 launcher `flutter` dispatcher 对本 App `run` 子命令注入 managed intent，固定 environment=alpha、target=`alpha-local`、mode=`content-live`、launch policy=`test_live`；显式 `run.sh --hermetic` 和 stackctl UAT actor 也进入该层。stackctl 控制面按固定顺序解析 exact device → 启动或复用 full runtime → 获取真实 consumer lease 并准备平台 transport/receipt（Android 需要时才执行 `adb reverse`）→ 以同一 lease 安装并验证 device trust → 解析并绑定 exact 当前内容（禁止 latest 猜测）→ 执行严格 preflight → 写 private managed preparation/launch control；随后 `run.sh` 验证并消费这些外层事实，完成 build/install/activation/attach。资源 lifecycle 仍由 stackctl 控制面拥有：它创建 lease/transport、把 teardown obligation 显式交给受管 launcher cleanup 并验证释放结果；`run.sh` 只履行该显式 obligation，不能让无 managed control 的 direct 路径 acquire/release 或清理外部资源，也只能回收该 invocation 实际 owned 的 lease/transport。任一 managed readiness 不可用必须在 Flutter build 前 typed fail-closed；direct `run.sh`、`make app-dev`/dev-session 维持 `test_live` warning+degraded 语义。其他 Flutter 子命令与其他项目由 dispatcher exact 透传真实 SDK；非 alpha ambient 选择器 typed 拒绝。Alpha 当前 Research release 的匿名隔离保持：managed 启动只要求登录服务可用，真实内容验收仍要求已登记白名单账号登录。
- `native_flutter_run` provenance 与 `embedded_default_package` supply mode 已退役：Debug-nonprod 构建在无 canonical handoff 时不再物化或嵌入默认 alpha trust/package；raw SDK 绝对路径绕过 dispatcher 直接构建时，在既有 trust gate 以 `APP.LAUNCH.runtime_config_trust_missing` fail-closed，Profile/Release、prod buildProfile、`prod-sim` 与 `prod-hosted` 的无 canonical handoff 构建同样 fail-closed。ZDOTDIR shim、terminal carrier receipt 与 `workspace_flutter_run` provenance 不得恢复；`app_launch_attempt` 的 terminalCarrierReceiptDigest/terminalCarrierReceiptRef 固定为空值。
- 设备选择：`run.sh` 未给 `-d` 时委托 canonical device authority——唯一可用移动设备自动选择，多台且 stdin/stderr 均为 TTY 时显示 canonical 数字列表并接受一次交互选择，任一流非 TTY 时以 typed blocker 要求显式 `-d`，不得按最近使用猜测设备；显式 `-d` 必须按 exact device identity 保留并校验。`workspace_ide_debug` 由 profile 的显式设备选择或同一 canonical authority 解析；受管字面 `flutter run` 的设备选择同样由 canonical device authority 裁决——单设备自动、多设备双 TTY 数字选择、非 TTY typed block、显式 `-d` 按 exact device identity 校验。
- 终端注入必须可凭受版本控制真相源重建且可逆：具名激活入口向 Cursor terminal profiles 与显式 opt-in 的 user-zsh managed source block 注入同一受管 PATH bin 目录（含 launcher `flutter` dispatcher）与钉定的 Flutter SDK/CocoaPods/Python 身份，不改 ZDOTDIR、不生成 terminal receipt；dispatcher 只对本 App 工作区的 `run` 子命令进入 managed 入口，其余子命令与其他项目 exact 透传真实 SDK。新终端自动生效，既有 shell 只能通过显式 source 刷新接入；移除注入并重载、或移除 user-zsh managed block 即完全回退，不得要求修改 Flutter 安装或遗留第二 launcher。
- `run.sh` 前台会话与并发语义：TTY 下 r/R/q 分别桥接为同一 attach 会话的 hot reload、hot restart 与停止，非 TTY 保持无键盘面。跨设备并行 canonical run 互不阻塞——deploy work state 按 run/设备隔离；direct/lightweight 不执行 `adb reverse`，managed/hermetic 控制面的 Android `adb reverse` 必须幂等且只清理本 invocation 新建的映射，不清理预存或他会话映射；同设备重复启动即重启既有实例。
- canonical launcher 固定选择 metadata 声明的 `nonprod` build profile，默认 target 为 `alpha-local`，显式环境只选择对应签名 runtime config package。它禁止选择 Prod 或直接覆盖 URL、密钥、target、manifest 与 release。
- `QWQ_ENVIRONMENT` 只允许选择 nonprod 信任域内的 runtime package，不得反向选择原生包身份或进入 Flutter 编译输入。
- `workspace_ide_debug` surface 没有自建的 mode 协议；run mode 与环境同构，经 `QWQ_RUN_MODE`（`content-live|ui-only`，默认 `content-live`）选择并交同一 canonical 执行体校验，IDE profile 只投影同一输入，非法值 fail closed。受管字面 `flutter run` 不参与 mode 选择协议：managed 入口固定 alpha/content-live，任何非 alpha 的 ambient 环境或 mode 选择器对字面命令 typed 拒绝。
- canonical Debug 必须先安装或复用同一 nonprod AppArtifact，再由 executor 写入完整 activation request、经冷启动原生 activation coordinator 把当前 topology 派生的 test-live package 原子激活到 App 私有容器，最后启动或 attach Flutter。冷启动和 Hot Restart 由原生 reader 返回 active package 与制品内 profile trust envelope，Dart 不得读取 endpoint define、环境变量或第二份 keyring。配置变化只要求重新签发和 activation，不触发 Flutter/原生重编或 AppArtifact 重签；实际 environment 只在启动握手后成立。
- App 构建不得读取或改写共享的“当前环境”文件，nonprod 组件只编译一次。
- `alpha → beta → gamma → alpha` 顺序切换只推进 target-scoped activation pointer，不得要求 clean、重试、重编或重装同一制品。
- 并发 activation 必须以 expected active digest 条件更新，不能共享可写 handoff 或相互覆盖。AppArtifact digest 与签名必须保持不变。
- `app_effective_launch_manifest` 只拥有 environment、target、endpoints 与 launch provenance，不携带任何内容 release 身份或 `contentBindingState`。内容激活是服务端运行时事实：App 冷启动后从 Content API 响应携带的 canonical release identity（`releaseId + manifestDigest`）解析当前内容身份，不得伪造 releaseId 或 receipt。`content-live` 模式与环境验收的期望 release 只写入 UAT evidence 与环境侧 readiness 回执，不烘焙进 App 制品；内容发布与回滚不要求重新打包或重新审核 App。
- canonical Debug 仅在操作者未选择环境时默认 Alpha；两个环境选择器冲突、Prod、任意 target override、过期/缺失 package、trust envelope 缺失、摘要不一致或 activation readback 失败均 fail-closed。Profile、Release 与 Prod 启动禁止隐式推断。
- Android managed/hermetic 控制面从 topology 推导包名、设备与所需 `adb reverse` 端口，在 Flutter 构建前获取 release-bound lease 并准备可验证 transport receipt；其 teardown 在退出时释放本次创建的 lease 并仅移除本次 owned reverse 映射。direct/lightweight 不执行这些动作；若外层已有有效 receipt/lease，只消费其绑定事实。异常中断后的 managed provisional lease 由 App 进程 liveness 判为 stale 并等待显式 GC。
- iOS managed/hermetic 控制面为 Simulator 与已登记 iPhone 同源准备签名 runtime package、安装后 activation 与同一 `consumer-lease` 对象，Simulator 额外执行系统公共 CA 预检；direct/lightweight 不创建该 lease。
- iOS lease 绑定 platform、设备标识、bundle ID、target、active package digest、启动宽限期与 handoff digest，且不携带 transport ports。
- 宽限期后，Simulator 必须结合 `simctl get_app_container`、`user/<uid>` launchd 域中的 `UIKitApplication:<bundleId>` service 与 executable path 判定存活。已登记 iPhone 必须结合 `devicectl device info apps/processes` 的结构化 App URL 与 process executable 判定存活。
- 结构化状态读取失败只能保留 `active_unverified` 证据，不得代偿为已停止或已存活。
- 已验证存活的 App lease 不受 12 小时 provisional 上限影响；`consumer-lease status` 和 down/package/roll 前检查必须严格只读，不得删除 stale 文件。只有显式 `release`/GC 可以清理 lease。
- canonical launcher 固定编译 production `lib/main_prod.dart`；`lib/main.dart` 只能薄委托同一入口，不能建立裸 Flutter 启动协议。
- 所有受支持路径都连接完整 Remote topology，并由同一 activation command、native reader 与 Dart resolver 消费 active runtime package，禁止 alpha runner、fixture override 或只提供 mock/public-plane 子集的本地进程。
- Gradle/Xcode 只验证所选 `nonprod/prod` profile、build-profile trust envelope、build product 摘要与设备证明；target runtime package 不进入 build phase、bundle resource 或 assets。
- canonical Debug 只允许从 metadata/topology 构建所选 handoff并在安装后执行 activation；本平台 consumer lease/transport 仅由 managed/hermetic 外层获取并绑定，direct/lightweight 不得自行补造。两层均不得推断 URL、复制配置到源码/构建树或吞掉 activation 失败；只有显式 managed/hermetic 控制面可按其合同启动或复用 runtime。
- Android/iOS 的 target package activation 必须验证 runtime package、制品内独立 trust envelope、build profile、target 与 effective manifest digest，并以 expected active digest 原子更新私有容器。缺一或 readback 不一致即在进入业务 Shell 前 `GATE_BLOCK`，失败时保留上一 active digest；endpoint、environment 和 runtime config 摘要不得进入 `DART_DEFINES`。
- 已激活旧 package 的时间窗（`expiresAt`）过期只使消费读取 fail-closed，不得阻断以其身份为 expected active digest 的下一次替换激活：activation 流程读取 CAS 前值时仍必须验证 trust envelope、签名与结构完整性，仅豁免时间窗判定；该豁免不得扩展到冷启动/Hot Restart 的 native reader 消费路径，也不得放松对新 package 自身的 freshness 校验。过期即死锁、要求删除重装才能恢复的实现是违约。
- active receipt schema 新增必填观测字段时，不得让已安装旧 App 永久死锁或要求卸载/清数据。当前迁移只允许在下一次 activation 的 CAS 前值读取阶段接受“精确等于当前 receipt 字段集减去 `launchProvenance`、`runtimeConfigSupplyMode`”的上一版 canonical receipt。它必须是 `activated`、摘要字段合法、`activePackageDigest=packageDigest`、环境/target/buildProfile 自洽且无 error/validation issue，且唯一输出是 `expectedActiveDigest`。同字段集的上一版 launch receipt 只允许作为等待原生用当前 schema 原子替换的 stale 文件被忽略，绝不构成本次 request 的成功证据。上一版 receipt 不得进入 cold start、Hot Restart、Dart/runtime readback 或成功证据。新 activation 仍须完整验证新 package 并由原生以当前 schema 原子覆盖 active receipt。任意额外缺字段、额外字段、非 canonical JSON 或身份/摘要不自洽都 fail-closed。不存在仍可生成上一版 receipt 的受支持 artifact 且设备基线证明迁移完成后必须删除该单代迁移读口。
- Alpha/Beta/Gamma 的 `test_live` 中，无论选择 `ui-only` 还是 `content-live`，runtime/startup/service/Provider/TLS/transport/content readiness 不健康、startup receipt 缺失、active candidate 过期及 source/config/generated digest 漂移都只形成结构化 warning，不得使 Xcode/Gradle build phase 失败或跳过真实编译、安装、activation 与启动。任一 warning 必须使最终 launch report 和 runtime health 保持 `degraded`，不得提升为 `healthy`。`content-live` 启动后必须真实请求 Remote 内容；依赖不可用时只能到达 canonical `no_active_release`、typed unavailable 或 `runtime_degraded`，不得伪造首页成功。依赖解析、身份/信任、最小 handoff/runtime package 生成、真实编译、设备选择、target 冲突、命名空间逃逸、Prod endpoint/credential 泄露与不安全 secret 始终硬阻断。
- `app-debug-preflight` 必须显式选择 `test_live` 或 `immutable_candidate`，不得以默认 mode 替调用方决定严格度。receipt 的 `details` 只记录安全编译/启动 blocker，`warnings` 只记录 test-live readiness 诊断。`gate_block` 对应非零退出，`warning|passed` 对应零退出；preflight 的零退出只允许继续构建，不等于 runtime healthy 或 UAT passed，平台启动器不得重新解释同一事实的严重级别。
- `test_live` 中缺失、停止、过期或漂移的 runtime/startup/service/Provider/TLS/transport lease/content readiness 与本地容量诊断必须保留完整脱敏 warning 并继续构建；它们不得被重新分类为 identity/security blocker。非法环境/target、环境命名空间逃逸、显式 handoff 冲突或不完整、无法生成 canonical runtime package/native manifest、build-profile trust 缺失或不一致、工具链/真实编译失败与不可用设备仍阻断。`immutable_candidate`、严格 health/verify、内容 UAT 与 Prod 不复用该降级。
- direct/lightweight App launcher 不拥有环境生命周期，不得隐式执行 `stackctl up/down/repair`，只可调用只读 `stackctl app-debug-preflight/status`；managed/hermetic 外层仅可按其显式合同启动或复用 full runtime。
- `--ensure-runtime` 不得让 direct/lightweight 路径接管环境生命周期；只有 managed/hermetic 控制面持有显式 frozen candidate identity 时，`content-live` 才可委托 `stackctl` 启动该 exact candidate，且不得执行 package、repair 或重选 release。
- `ui-only` 与 `content-live` 的 `test_live` 预检都以 `warning` + exit 0 报告服务、Provider、内容、观测、容量与漂移问题。`content-live` 不得把 warning 重新解释为内容可用，而是在真实启动后的 Remote 请求中产生可观察 outcome；warning 运行的最终健康度只能是 `degraded`。只有零 warning 的 `immutable_candidate`、内容 UAT 与 Prod readiness 才能消费严格 delivery 结果。
- direct/lightweight Debug 在设备执行前必须调用 `stackctl app-debug-preflight`，但该只读诊断不转移 lease/transport ownership；managed/hermetic launcher 在 Flutter build 前消费由控制面签发并 exact readback 的严格 preflight/receipt。Alpha/Beta/Gamma direct test-live 只校验安全环境选择与最小 handoff并收集运行时诊断，不委托商业 `app-content-preflight`；Prod release 与 UAT/evidence 启动继续验证 immutable candidate、必要服务/Provider，并委托 `app-content-preflight` 绑定 commercial readiness、rollback/replay、首页/视频书、Creator 与媒体证据。
- 只有 managed/hermetic 与 UAT/evidence 启动入口必须写 canonical `app-launch-attempt` receipt，并等待最长 15 分钟直到真实达到 `launched`、`runtime_degraded` 或产生首个 typed failure；direct/lightweight 只输出开发阶段观测，不得签发该 receipt 或据此宣称通过。PID 存活、进程已创建、1.5 秒未退出与 Flutter VM attach 都不是成功。只有本次已安装 `artifactDigest` 发出的 canonical `startup_safe_terminal` 与同一 managed launch attempt 关联，且回执持久化非空 `startupTerminalAttemptId + startupTerminalEvidenceDigest + startupTerminalEvidenceRef` 后才能标记 `launched`；任一 warning 只能到达 `runtime_degraded`。编译、安装或启动失败分别使用 canonical typed blocker，正常 Ctrl-C 记为 `stopped`。
- Android `prod-sim` 只安装并启动 exact Release artifact；Flutter 不支持 iOS AOT Release/Profile simulator，故 iOS Release 基础编译生成 unsigned iphoneos `.app`，Simulator 只允许 non-promotable Debug 启动且不得冒充 Release/Prod 证据。`prod-hosted` 只消费已签名 artifact、manifest、安装回执和严格 readiness，禁止 `flutter run`、Debug 或未经授权的真实 rollout。
- 每次 Dart isolate 启动必须先生成新 `attemptId`，再调用原生 `beginStartupAttempt(attemptId)`。原生返回 `attemptKind=cold|hotRestart`、`processElapsedMs`、`attemptElapsedMs` 与 `deadlineOrigin=nativeProcess|dartHotRestart`。
- `startup_attempt_started` 只能在 native runtime package 已水合且 `configurationState=complete` 后发送；Cold Start 的 6 秒预算可使用进程时钟，Hot Restart 只能使用本次 attempt 时钟。进程总存活时间只作诊断，不得写入 `welcomeExitMs` 或消耗 Hot Restart 预算。
- `stackctl app-content-uat` 必须在唯一 environment operation owner 已完成同一 `releaseTrainId`、逐 target 精确 baseline 与同一 release activation 后，顺序对 Alpha、Beta、Gamma 执行上述严格预检、canonical `run.sh` 启动、首页 Feed、`environment_app_core_readback` 与视频播放 Patrol。严格预检和 launch report 都必须零 warning，任一 warning 立即阻断本 target 页面 suite。
- iOS UAT parent 必须在 attempt-1 前一次性解析并冻结 exact `PATH` 与同一 six-field physical CocoaPods binding，attempt-1 与 retry 原样复用；不得依赖 parent shell ambient identity、在 attempt 间重新发现，或由 Flutter child/其他子进程反向传回 binding。binding 被篡改或不能保持一致时，必须在启动 Flutter child 前返回 typed blocker。
- 每个 target 的页面 suite 前必须解析 fresh active candidate，并校验 manifest 的 `candidateDigest`、`packageDigest` 与只读 input capsule。runner 只能把该 capsule 复制到 attempt-scoped 私有 writable projection 后从 projection build/launch，不得从 live `APP_DIR` 取源码；复制前后 tree digest 漂移即返回首个 typed blocker。
- 每个 target 的页面 suite 必须新建并消费紧邻的同 target、platform、device、immutable source capsule、application ID、runtime package 与 trust envelope 的 canonical launch report 和 `app-launch-attempt`。Android 与 iOS 均不得跳过 canonical launcher；原生 `flutter run` 面不产生 UAT 证据。
- 只有 attempt 真实完成 compiled、installed、configured，并由本次已安装 APK/`.app` 的同一 `artifactDigest` 产生关联 startup safe terminal 后才可进入页面 suite。VM attach 只记观测，不得替代 safe terminal；回执必须含非空 `startupTerminalAttemptId + startupTerminalEvidenceDigest + startupTerminalEvidenceRef`。
- 页面 suite 必须从自动化实际安装并启动的 App 读取 `testedAppArtifactBinding`，并把其 `applicationId`、`artifactDigest`、`sourceProjectionDigest`、`runtimeConfigPackageDigest`、`trustDigest` 与 `launchAttemptId` 逐字段绑定到同 target canonical launch。test host 自身的包名或制品摘要、从 canonical report 复制的 comparison 字段以及缺少安装/启动 readback provenance 的报告都不能证明实际受测 AppArtifact；任一字段缺失、来源非法或不一致时必须以 canonical `APP.UAT.page_artifact_binding_missing` 作为首个 blocker，停止该 target 页面 suite 且不得生成页面通过结果。
- 聚合回执必须逐 target 写入 `launchAttemptId`、launch provenance、artifact/trust/attempt digest、`candidateDigest`、`packageDigest`、`startupTerminalAttemptId`、`startupTerminalEvidenceDigest` 与 `startupTerminalEvidenceRef`，并写入非空 `releaseTrainId` 与 `packageBaselines[target]`。每个 UAT runtime binding 的 `candidateDigest` 必须等于对应 startup receipt 和 target baseline，launch source 必须等于该 binding 的 immutable source capsule。回执不得保留空 scalar、从 Alpha 取值代替其他 target，或接受上一代 UAT。
- UAT/evidence 层必须经 `stackctl app-content-uat` 或等价受控入口使用 managed/hermetic ownership：在整个执行窗口持有 runtime-use lock，由控制面准备并释放 consumer lease/transport，逐 target 绑定 immutable source capsule、strict zero-warning preflight、canonical launch receipt、safe terminal 与 raw `ReadinessCaseResult`。任一 target 失败即停止并输出首个 typed blocker 和可机读 receipt。禁止消费、复制、改标或聚合 direct/lightweight 的 warning/degraded 输出、截图、VM attach、启动日志或无 receipt 运行作为 promotable evidence；禁止以 dry-run、旧 receipt 或单环境成功替代三环境结论。
- 本地主机共享 runtime 的 operation/use lock 必须位于 `~/.cache/quwoquan/host-locks/local-runtime/` 并记录 pid、worktree、lane 与 HEAD；不得落在任一 worktree 的 `.qwq_output` 后把跨 worktree 并发误判为隔离。Alpha/Beta/Gamma runtime host 只从只读 `integration/` worktree 以 canonical `dev-session` 启动，lane worktree 只消费该 host 并启动 App；lane 确需自带 runtime 时只能走 hermetic 路径并先取得同一主机级锁。runtime 可达性由主机端口和只读运行事实判定，worktree-local pid/receipt 不得冒充主机级可达性。
- 自动验收必须在每个 target 的正向内容读回之后执行受控 API Edge 故障窗口：故障控制器只可操作当前 runtime receipt 绑定的 Compose project 与精确容器，App 必须在同一次安装中呈现与已确认原因匹配的唯一用户恢复动作；控制器恢复原容器并重新通过健康检查后，App 点击该动作必须无需重装即可恢复 release-bound 首页内容。任一步骤异常都必须在 `finally` 恢复环境并使验收失败，禁止遗留人为故障或以本地 double 替代。
- 活跃 lease 存在时，`stackctl down`、环境矩阵强制清理和端口强制回收必须 `GATE_BLOCK`。

<a id="req-004"></a>
### REQ-004 所有有效构建、安装与启动路径行为等价

- 有效路径集合固定为：canonical launcher `run.sh`（content-live/ui-only/Hot Restart，launch provenance=`canonical_launcher`）、受控制 IDE profile（`workspace_ide_debug`）、受管 PATH 中经 launcher `flutter` dispatcher 进入 canonical launcher 的字面 `flutter run`（managed one-command 入口，launch provenance=`canonical_launcher`，固定 alpha/content-live）、`stackctl package` 产物 Debug 安装到 Simulator/Emulator/登记设备并由 canonical activation 后点击图标、Android `prod-sim` exact Release、Android/iOS `prod-hosted` Release、应用市场 Release 安装（Apple App Store/TestFlight、华为、小米、OPPO、vivo、应用宝）、官网签名 APK 安装，以及上述任一渠道的同包名覆盖升级。未经 canonical handoff 的原始 Xcode/Gradle backend 调用与绕过 dispatcher 的 raw SDK 绝对路径调用不属于有效路径；iOS Simulator 只允许 non-promotable Debug，不属于 Release 安装路径。
- 等价定义：同一环境与同一服务端状态下，各路径的规范化行为指纹一致——配置完成态、首个安全终态、路由/登录态、内容 outcome 与 release identity、恢复动作均相同，且无 fatal recovery 差异。BuildMode、launch provenance 与 install channel 只允许作为观测事实记录，不得参与业务分支。本条与上条是有效路径集合与等价指纹定义的唯一 owner，AppRoot 与其他节点只引用不复制。
- 每类安装渠道产出独立、按 store/device/build 追加的 install receipt。应用市场渠道的准出证据必须来自真实市场客户端下载安装与安装后冷启动 telemetry 回读，官网 APK 渠道必须来自官网下载对象的 SHA-256/签名/包名比对与安装后启动回读。package-only 编译、side-load 或另一渠道回执不得互相替代。
- Debug 签名制品仅限开发者本机、Simulator/Emulator 与已登记设备，不进入 TestFlight、任何应用市场或官网公开下载；市场与官网只接受 Release 签名制品。
- 每个渠道的验收 CaseResult 声明自动化分级：CI 全自动、设备实验室定期自动、或人工执行加机器回执；人工动作缺机器回执时按失败处理。

<a id="req-005"></a>
### REQ-005 canonical raw ReadinessCaseResult 是唯一 UAT 结果事实

- canonical raw `ReadinessCaseResult` 是唯一可承载 UAT outcome、verdict 与 failure/blocked/skipped 原因的结果事实。每个 `required target × platform × device × entry × carrier` slot 必须 create-once；`not_applicable` cell 由 plan 声明且不生成伪通过结果。required slot 缺失、`failed`、`blocked` 或 `skipped` 均保持原状并阻断相应 acceptance，不得被父 report、所谓 `AppUatResultBundle`、summary、重跑或其他 slot 掩盖。
- 父 report/所谓 `AppUatResultBundle` 只能是对 required raw refs、exact-byte digests、矩阵覆盖率与缺口的只读完整性投影：无独立 verdict、无 promotion authority、不可写回 raw result 或 acceptance fact，也不得另造第二套 CaseResult。任何聚合层出现独立 `passed`、丢弃非通过结果或把模拟器 evidence 提升为 promotable 时必须 `GATE_BLOCK`。
- Alpha、Beta、Gamma rehearsal 内容验收继续让 Android Emulator 与 iOS Simulator 对同一 `releaseId + manifestDigest + sourceIdentitySetDigest` 分别生成 canonical raw `ReadinessCaseResult`，覆盖 [`AppRoot UAT-001`](../../../spec.md#uat-001) 的内容、Creator、搜索和可恢复终态，以及 [`UAT-003`](../../../spec.md#uat-003) 的同状态、同内容 identity 与同恢复动作；这些 slot 全部明确 `nonPromotable=true`。
- `stackctl app-content-uat --targets alpha-local,beta-local,gamma-local` 按冻结顺序编排三个 target。rehearsal 父 report 只读投影完整性并声明 `nonPromotable=true`；不得生成单环境 aggregate、canonical matrix passed 或 promotion 事实。
- `acceptanceProfile=environment_promotion` 的 promotable physical profile 不新建结果类型：Alpha/Beta/Gamma 的正式 acceptance 必须为 Android/iOS physical slots 使用 canonical `ReadinessCaseResult`，绑定已登记物理设备与受测 artifact；Alpha 垂直切片至少补齐 Alpha 的 Android physical 与 iOS physical required slots，正式 promotion 则补齐计划要求的全部环境 physical slots。M100/Gamma acceptance 与 Prod 始终走该 profile；Prod 只接受 production artifact、Android/iOS physical devices 与 production authority 共同绑定的 required slots。Simulator/Emulator、Debug App、API integration result 或 nonprod authority 一律不得替代。
- `acceptanceProfile=m1_api_consumer` 的 `requiredRawResults` 仍引用 canonical `ReadinessCaseResult` envelope，但结果层固定为 API 集成 consumer readback，不是 raw App UAT，也不携带 UAT/promotion authority；raw 的 `objectId` 始终保留 plan 的 source identity，导入后的 `runtimeObjectId` 只存在于其 `artifactPath` 指向的 exact observation，不得向 canonical raw 添加 `observedObjectId` 或用 runtime identity 改写 source identity；这不创建第二种 CaseResult，更不得让 API result 顶替上述 environment-promotion physical slots。
- `no_active_release` 只作为 Alpha 独有的独立 lifecycle drill：在 active-release suite 外保存 previous release identity 与 readback，通过正式环境命令应用已核验 empty baseline，依次取得两端 `outcome=empty + emptyReason=no_active_release` 的 raw `ReadinessCaseResult`，再 same-digest replay previous release并逐 entry 复核 lifecycle/readback。`no_active_release` 或 empty baseline 绝不等同 `deleted`；rollback/replay 的 raw 结果 append-only 保留，且 `feed/search/recommendation/direct_or_object_route` 均须回到 previous release identity。任一步中断都必须先恢复原 release。该 drill 不代替 Beta/Gamma 正向与恢复结果，也不能单独关闭矩阵。
- `CONTROLLED_EDGE_RECOVERY_UAT_TEST_TARGET` 必须分别进入 Alpha、Beta、Gamma suite。每次故障控制只操作当前 target runtime receipt 绑定的精确 API Edge 容器，App 显示唯一重试动作；`finally` 恢复容器并通过 health 后，同一安装点击重试必须重新读取原 release。
- 网络不可用显示 typed unavailable 与唯一重试，恢复网络后在原页续接同一 release；白名单或身份权限拒绝只提供重新登录或返回安全 Shell，登录成功沿用 canonical AuthContinuation，取消不循环。
- 新账号或无历史用户不形成第二套 feed：有 active release 时读取同一 public/research projection，无 active release 时进入同一 canonical 空态。相机与 RTC 不参与本验收。

<a id="req-006"></a>
### REQ-006 Release UAT plan、target binding 与环境 acceptance 单向派生

- `ReleaseUatSamplePlan` 由 Data release owner 在 release 层 create-once，环境无关，并冻结 release identity、source identity、二维 `entry × carrier` cell 的 `required/not_applicable`、sample identity 与 raw case expectation；Ops、App runner 与环境不得修改、补写或按 target 分叉该 plan。
- canonical `EnvironmentAcceptanceFact` 只使用同一当前 schema、append-only store 与 validator，必填 `acceptanceProfile=environment_promotion|m1_api_consumer` 并在同一 validator 内按 profile fail-closed 分支；禁止另建 M1 fact schema、validator、store 或把普通 fact 的 promotable 语义模糊放宽。
- `acceptanceProfile=environment_promotion` 保持既有单向事实链 `ReleaseUatSamplePlan → TargetUatBinding → raw App ReadinessCaseResult → EnvironmentAcceptanceFact`。`TargetUatBinding` 由 Ops 为每个 target/runtime/package/config/platform/device/runner slot create-once；只有 fresh active candidate 的 CAS/readback 已确认，且受测 artifact、物理或模拟设备及 runner 均就绪后才能创建。fact 的 `targetBindingRefs` 必须 exact 覆盖 profile 要求的非空 binding，`requiredRawResults` 必须直接绑定其全部 required App raw exact bytes；上游对象与父 report均不能回写该 authority 链。
- `acceptanceProfile=m1_api_consumer` 只允许 `environment=alpha`、`target=alpha-local`、`predecessorAcceptance`、`prodReleaseFacts` 与 `targetBindingRefs` 字段缺席。它必须同时携带且分别验证 `releaseDigest`（Data sample plan 的 `release_identity_digest`）与 `manifestDigest`（immutable payload/Data readiness digest），二者不要求相等，factId 同时包含二者；canonical `environment_promotion.releaseDigest` 语义不变。M1 必须绑定同一 M1 Research `releaseId + releaseDigest + manifestDigest + importRunId + verifyRunId` 的 canonical Data readiness（其中已重验 import、readback 与 activation envelope）及 runner create-once 的 identity-bound `consumer-health.json` exact evidence；该窄 binding 递归绑定并重验原始 stackctl health exact bytes，只要求 bounded consumer 的 `build_ready/runtime_full_ready/release_active/content_exact_queries_ready`，`provider_ready/device_bound/content_live_passed` 不构成 M1 义务。`ReleaseUatSamplePlan` 的 4 entry × 4 carrier 共 16 个 cell 全部 required；`requiredRawResults` 恰好直接绑定这 16 个 fresh API 集成 consumer readback CaseResult refs/exact-byte digests，并逐 slot 读取 `artifactPath` observation，校验无 symlink 的 exact bytes、schema/identity/status、2xx HTTP、response digest 与匹配的 runtimeObjectId。跨 run/release、缺 cell、重复 slot、非 API 集成、App 用户验收结果、health/raw observation 漂移均 `GATE_BLOCK`。
- `m1_api_consumer` 不创建、不引用、不伪造 `TargetUatBinding`、App TargetUatBinding digest、受测 AppArtifact、platform/device、physical-device 或 App raw `ReadinessCaseResult`；它无 promotion authority，不能充当 M100/Alpha promotion、后继环境 predecessor、physical UAT、正式 Green Matrix 或 M1000 start gate。所有 promotion/predecessor consumer 必须显式要求 `acceptanceProfile=environment_promotion`，普通 Alpha/Beta/Gamma/Prod acceptance 语义与 M100/Prod physical 要求完全不放宽。
- 两个 profile 的 `EnvironmentAcceptanceFact` 都是 append-only Ops acceptance fact，并直接绑定本 profile 的全部 required raw refs/exact-byte digests。`m1_api_consumer.sourceFingerprint` 不是调用方 authority，必须由 sample plan、Data readiness、identity-bound consumer health、16 个 raw exact refs/digests 及双摘要/run identity 机械重算；`m1_api_consumer` 只绑定 canonical Data readiness、上述 consumer health binding 与同一 release/import/verify identity 的 16 个 API raw；`activeCas`、`lifecycleExit`、`providerReadiness`、`observabilityReadiness`、`rollbackReadiness`、`resourceFinalization` 及任何 App/target binding 字段必须缺席。`environment_promotion` 才绑定 fresh active CAS/readback、environment lifecycle `Exit`、Provider/observability/rollback readiness、resource finalization，以及 Beta、Gamma、Prod 的前一环境 `environment_promotion` fact exact-byte digest；Data readiness、retired `appUatEnvelopeDigest` field、父 report、bundle digest或 `m1_api_consumer` fact 均不能替代前环境 acceptance 或任一 required raw result。
- 任一 profile required slot 缺失或结果为 `failed/blocked/skipped`、任一 exact-byte digest/readback 漂移均不得创建通过 fact，并返回 `GATE_BLOCK`。仅 `environment_promotion` 额外要求 lifecycle `Exit`、Provider/observability/rollback 与 resource finalization 就绪，并只能按 Alpha→Beta→Gamma→Prod 顺序追加且后继环境 exact-byte 绑定前一环境同 profile fact；任何 legacy aggregate verdict 均无写 authority、无 promotion consumer。
- `lease revoke`、`lock release` 与 `GC protection` 是 `environment_promotion` 的收尾义务，必须分别取证：先停止新使用并 revoke 对应 lease，再 release execution/runtime-use lock，最后确认 raw results、bindings、acceptance facts 及 rollback/replay 证据受 GC protection；`m1_api_consumer` 不创建或伪造这些 promotion-only facts。禁止用含混 `cleanup` 表示删除事实、释放锁或回收 evidence。

<a id="req-007"></a>
### REQ-007 Prod J0/J1/J2 仅为 canonical 发布事实视图

- `J0/J1/J2` 只是 Prod readiness UI/report 的只读视图标签，不新建状态机、ledger、verdict 或可写 promotion authority：`J0` 映射 canonical engineering eligibility，`J1` 映射 durable exact approval，`J2` 映射 canonical canary→5%→20%→50%→100% rollout 与对应 rollback facts。
- 视图必须逐项保留来源对象的 exact identity/digest、时间与 authority；缺步、乱序、审批摘要漂移、canary/比例 rollout 或 rollback fact 缺失时显示 blocked/incomplete，不得通过移动 J 标签、父 report verdict、Data readiness 或 retired `appUatEnvelopeDigest` field 推进。
- Prod acceptance 只有在 production artifact、physical device raw results、production authority、前环境 acceptance exact-byte digest 以及 J0/J1/J2 所映射 canonical facts全部成立时才可创建；撤回审批或 rollback 只追加 canonical durable facts并重算视图，不改写历史 raw result 或 acceptance fact。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。
- `GWT-001` 证据绑定：`local_contract` 覆盖 topology/package/capsule/依赖纯度与只读语义，`api_integration` 覆盖真实 package/up/health/verify、Provider/DNS/TLS/readback，`user_acceptance` 覆盖 production-behavior App artifact 的安装、启动与内容结果。
- `GWT-002` 证据绑定：`local_contract` 覆盖三层 ownership、direct 不获取 lease/transport receipt/不执行 `adb reverse` 且未知设备 fail-closed、外层 managed receipt/lease 的 exact 绑定透传与 owned teardown、`app-dev`/`app-uat` 薄适配边界、managed 字面 `flutter run` dispatcher 的子命令分流/readiness fail-closed 顺序/非 alpha 选择器拒绝与 raw SDK 旁路负例、hermetic dependency bundle stale 的单次有界同步恢复与非交互 fail-closed、`run.sh` 全局 wrapper 与设备选择、PATH 注入投影/回退、attach 键位桥、并发隔离、frozen CocoaPods binding、direct evidence 不可提升、父 report 无 verdict 与 typed blocker；`api_integration` 覆盖真实 stackctl 委托、attempt-1/retry 同 binding、runtime package、CAS/readback、Remote 服务与 lifecycle；`user_acceptance` 覆盖 Android/iOS 的 direct `run.sh` 开发行为，以及 managed/hermetic 受管终端字面 `flutter run`、UAT 启动、Hot Restart、并行双设备、内容 outcome 与恢复动作。
- `GWT-003` 证据绑定：`local_contract` 覆盖有效路径闭集、行为指纹与渠道不可替代性，`api_integration` 覆盖下载对象、签名、包身份、release identity 与 telemetry readback，`user_acceptance` 覆盖各渠道下载、安装、冷启动与覆盖升级行为。
- `GWT-004` 证据绑定：`local_contract` 覆盖二维矩阵、create-once raw slot、父投影只读无 verdict 与 `nonPromotable`，`api_integration` 覆盖 active CAS/readback、empty baseline、rollback/replay 与 previous release identity，`user_acceptance` 覆盖六个模拟器 raw `ReadinessCaseResult`。
- `GWT-005` 证据绑定：`local_contract` 覆盖 rehearsal/promotable profile 与 artifact/device/authority 约束，`api_integration` 覆盖 artifact/runtime/CAS/前环境 acceptance 的 exact binding，`user_acceptance` 覆盖 physical-device raw results。
- `GWT-006` 证据绑定：`local_contract` 覆盖同一 EAF schema/validator 的 `environment_promotion|m1_api_consumer` 条件分支、create-once/append-only、exact-byte refs、空/非空 target binding 约束、M1 promotion-only 字段缺席、非 promotion consumer 拒绝、父投影不可写回与 J 标签纯视图；`api_integration` 分别覆盖 Alpha M1 的 Data readiness、content-consumer health 与同 release/import/verify 的 16 个 API consumer readback slots，以及 `environment_promotion` 的 CAS/readback、Exit、Provider/observability/rollback、resource finalization 与前环境 digest；`user_acceptance` 仅覆盖 `environment_promotion` required App raw results 对正式 acceptance 的直接贡献。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 环境拓扑与打包

- GIVEN 开发、测试或运维角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“环境拓扑与打包”对应的公开行为。
- THEN 各环境 `runtime.yaml` 均声明完整 `edge / media / service / data` 子网与结构化 `urlRoles`。
- AND `stackctl package --env prod --target prod-sim|prod-hosted` 分别生成 target 隔离的 App 包，包内 URL 与 resolver 生成的 `publicBases` 一致，且 `prod-hosted` 仍拒绝本地或测试 host。
- AND immutable package 在开始时复制精确输入闭包到只读 capsule，所有 App/Service/GraphQL/OCI artifact 绑定同一 capsule identity；封存后 live Data/App/Service 修改不使当前构建失败，下一次 capture 才观察这些变化并生成新的 candidate identity。
- AND Alpha/Beta/Gamma `dev-session` 从当前工作树与 topology 实时 render target 隔离的 test-live runtime，不创建 immutable candidate；工作区或配置变化进入告警，严格 health/verify 仍如实失败。
- AND Prod `stackctl package / up / health / verify` 只读取 immutable active candidate，重复 package 只在完整 manifest 和全部 digest 相同的情况下返回原始 receipt，不隐式重建或覆盖候选。
- AND 同一 release train 的组件从同一 source capsule 按 nonprod/prod 信任域构建；Alpha/Beta/Gamma composition 引用相同 nonprod image/App/Web artifact digest，Prod 引用独立 prod digest。交换信任域 artifact/config/binding、篡改 `APP_ENV` 或挂载不兼容环境配置时均在 listener 或业务 Shell 前失败。
- AND `dev-session --all-nonprod` 顺序生成三份 target 隔离的 compile/launch、告警与 health 结果，单个 target 的 runtime health 失败不得抹除其真实编译结果。
- AND Android/iOS 的 production dependency graph、native linker/filelist、SBOM 与最终制品均不含测试插件或 test runner，物理隔离的 UAT test host 枚举全部 canonical 用户验收 case 而不反向进入 production package。
- AND Dart/Pod 跨锁与 CocoaPods executable/version 一致；任一漂移在真实编译前返回 `APP.DEPENDENCY.lock_drift`，且不执行自动 update 或 repo refresh。跨锁范围含物理隔离的 UAT test host：它与生产工程跑同一份 `pubspec.lock` 依赖声明，两侧受版本控制的 `Podfile.lock` 在全部 pubspec 派生插件 pod 上必须同版本，否则验收结果不代表生产行为。test-only pod 与各自独有的 vendored SDK 只存在于一侧，不构成漂移。
- AND bounded content workload 复用健康 full runtime 后，App preflight 仍读取原 full receipt；独立 bounded runtime 的 receipt 不冒充 full readiness。
- AND `stackctl status` 在环境未启动、secret 缺失或 Provider 不可用时只返回诊断失败，不创建 secret、不启动或修复任何组件；consumer/commercial readiness 只有在 canonical Data receipt 与三个 release-bound exact query 均通过时才返回成功。
- AND 公网 DNS 记录只从 `dnsZones` 派生并经供应商中立 provider 写入，每个 canonical target 的全部 topology host 都被覆盖。
- AND 生产地址记录在缺少受保护 edge 地址时保持缺席并显式 pending，既不写占位值也不删除现存记录，非全球可路由或格式非法的注入地址 fail closed。
- AND provisioning 与 ACME challenge 使用两个独立凭据，且 challenge 凭据的可写范围由服务商强制还是仅由凭据隔离保证被如实声明。
- AND 每个 zone 显式选定的 `caaProfiles` 与其 TLS profile 归属一致，不签发公共证书的 zone 发布 `deny-all` 而非继承 apex 允许清单，每个 apex 同时发布 SPF deny 与 `p=reject` 的 `_dmarc` 记录。
- AND 现网核对对 CAA 双向成立：profile 声明的每条记录都在场，且 apex 不存在 profile 之外的 CAA，`deny-all` 的 zone 因此不可能同时挂着允许型 `issue`。
- AND `apexFollowers` 与 apex 共享同一份地址记录、随 apex 一同缺席，受管名字上不出现 CNAME。
- AND 覆盖或删除现存生产 DNS 记录在缺少显式确认时 fail closed 且不产生任何 provider 写入，首次下发生产记录无需确认。
- AND 收敛只拥有计划声明的记录值：地址与 zone 级授权类型由计划完全拥有，同名共享类型上计划外的值（备案、第三方站点校验）既不被占用改写也不被删除，只如实上报。
- AND zone 内不存在未登记记录：收敛后以 provider 的整 zone 列举审计计划面之外的名字，计划外入口逐条上报为 `observedUnmanaged`，服务商自带的 NS/SOA 归入 `observedExempt` 分列，审计只报告、不清理。
- AND 已与计划一致的记录报 `unchanged` 且不产生 provider 写入，期望侧结构化值与现网文本值归一为同一身份。
- AND 公网核对经至少两个与权威服务商相互独立的解析器取证，任一 scope 未被核对时返回 `incomplete` 而非 `ok`，反向解析查询失败与无 PTR 记录分别上报、不折叠为通过。
- AND 有证书声明的每个 target 都在 `verify` 覆盖面内，覆盖面从 `tlsProfiles` 派生而非另立清单。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 Android 与 iOS App 会话遵守三层 ownership

- GIVEN 开发者通过全局可调用的 direct/lightweight `quwoquan_app/run.sh --mode content-live|ui-only --env alpha|beta|gamma [-d <device>]`、默认同属 direct 开发层的 IDE 薄包装入口（`workspace_ide_debug`），或在受管终端执行字面 `flutter run`（launcher `flutter` dispatcher 注入 managed intent，固定 alpha/content-live，launch provenance=`canonical_launcher`）；未显式选择环境时默认 Alpha，并由相应层生成或消费 canonical handoff 与待激活 package。
- WHEN Flutter 构建、运行、正常退出或异常退出，或并行环境任务尝试 down/强制清理。
- AND `make app-dev` 只按默认值或显式 `ENV/DEVICE_ID/MODE` 委托 `stackctl dev-session --launch-app --app-mode`，`make app-uat` 只按显式 `TARGETS/PLATFORM/DEVICE_ID` 无交互委托 `stackctl app-content-uat` 并拒绝 Prod，Make 不持有设备发现、env/target 扩展、交互、状态机、provenance 或 receipt。
- AND 具名激活后，Cursor terminal profiles 与显式 opt-in user-zsh managed block 的新终端自动获得受管 PATH bin 目录与钉定的 Flutter SDK/CocoaPods/Python 身份；`run.sh` 在任意工作目录直接可调用，字面 `flutter run` 命中受管 PATH 上的 launcher `flutter` dispatcher，非 `run` 子命令与其他项目得到与真实 SDK exact 一致的行为；不存在 ZDOTDIR bridge 或 terminal carrier receipt，移除注入并重载即完全回退。
- AND iOS UAT parent 在 attempt-1 前冻结 exact `PATH` 与同一 six-field physical CocoaPods binding，attempt-1/retry 原样消费；任一 attempt 间重发现、ambient identity 依赖、child 反传或 binding 篡改均在 Flutter child 前 typed block。
- THEN direct/lightweight `run.sh` 不调用 `consumer-lease acquire|bind|release`、不执行 `adb reverse`、不生成 managed transport receipt 或 promotable launch receipt；它仍在 executor 前完成 pub 输入处理、exact mobile device 校验与安全 handoff/activation，未知、不可见或不支持设备 fail closed。外层若显式提供有效 receipt/lease/handoff，direct 执行体只 exact 绑定和透传，不接管资源所有权。
- AND managed/hermetic stackctl launcher 在构建前让 Android lease 绑定设备、包名、release handoff 与 topology 端口，准备并验证所需 transport receipt；退出时由 stackctl 控制面拥有 teardown obligation，并可由已验证该 obligation 的受管 `run.sh` cleanup 代执行，释放该 lease且只清理本 invocation owned 的 reverse 映射；异常中断后的 lease 由 App 进程 liveness 判为 stale 并等待显式 GC。
- AND managed/hermetic stackctl launcher 为 iOS Simulator 与已登记 iPhone 获取同一 schema 的 lease，绑定 platform、设备、bundle ID、target 与空 transport ports，并在启动 executor 前将同一 lease 绑定最终 handoff digest；Simulator 通过 user launchd application service 与安装容器 executable 保活，已登记 iPhone 通过 `devicectl` 结构化 App URL 与 process executable 保活。
- AND consumer lease 的只读状态检查不删除 stale lease。
- AND 本地 Alpha 与 Beta/Gamma/Prod 使用同一 production Remote composition；首页、视频与 Creator 由已激活 release 提供，消息和我的主页由真实身份经领域公开 command/event 形成并由真实服务 query 提供，启动器和 UAT 不得隐式切入 Mock、fixture 或残缺 public plane。
- AND target/env 冲突、Prod endpoint/credential 泄露、身份/信任、最小 runtime package、真实编译或 runtime package activation 失败时 App 在进入业务 Shell 前失败；Alpha/Beta/Gamma `test_live` 的两种 App mode 对服务、Provider、内容与观测 readiness 只记录 warning，`content-live` 在启动后以真实 Remote outcome 区分可用、合法空态和 typed unavailable。`immutable_candidate`、内容 UAT 与 Prod readiness 对这些依赖继续严格阻断。
- AND managed/hermetic 与 UAT/evidence 启动回执按 prepared、compiling、compiled、installing、installed、configuring、configured、launching、launched 单向推进；direct/lightweight 不签发该回执。VM attach 只作为 launching 阶段观测。只有同一已安装 `artifactDigest` 的 canonical startup safe terminal 回写 `startupTerminalAttemptId + startupTerminalEvidenceDigest + startupTerminalEvidenceRef` 后才可出现 launched，编译、安装或 activation 失败不得出现 launched，父入口只消费该回执而不自行解释 PID。
- AND 原生 activation 与 runtime config channel 的可见错误码全部来自 `app_launch_manifest.yaml` 的 `runtime_config_error_codes` 闭集。
- AND active receipt 的缺失、读取失败与解码失败分别使用 receipt 语义错误码，不复用 activation request 语义；成功 receipt 必须持久回读已验证的 `launchProvenance` 与 `runtimeConfigSupplyMode`，进程重启后不得硬编码、从环境推断或另建无 schema 状态文件。
- AND 记录 failed receipt 时 active digest 读取失败保持最后已知 CAS 值，以 `runtime_config_activation_rollback_failed` 追加标记状态未知，不覆盖原始失败码。
- AND recovery context 对 active package 缺席与读取失败分流，读取失败携带登记错误码而不吞错为空上下文。
- AND Android/iOS canonical Debug 与 Hot Restart 使用同一 handoff、制品内 trust envelope 和平台私有容器 active package；环境、target、build profile、package digest 与 trust digest 保持一致后才进入安全 Shell，且这些运行时值不进入 Flutter 编译输入。
- AND Android/iOS nonprod AppArtifact 仅构建和签名一次；默认 Alpha 与显式 Alpha/Beta/Gamma 的启动都复用同一完整 APK/`.app` digest，并分别原子激活匹配 target 的签名 runtime config。`alpha → beta → gamma → alpha` 不依赖 clean、重装、共享文件刷新、重试、重编或重签，并发 activation 不互相覆盖 active pointer。
- AND 冷启动和连续 Hot Restart 均先完成 `beginStartupAttempt`，再以 `configurationState=complete` 发送 attempt 事件；Hot Restart 的 `welcomeExitMs` 始终相对本次 attempt 且不超过 6000ms。
- AND 环境无激活内容 release 时 App 只接受 canonical `outcome=empty + emptyReason=no_active_release` 或 typed unavailable，不以普通空列表冒充成功；环境已激活 release 时 App 从 Content API 响应解析 `releaseId + manifestDigest`，UAT 以环境侧期望 release 比对读回身份，App 制品不内嵌内容身份。Prod 发布准出仍绑定 active candidate、commercial readiness 与 rollback/replay 的环境侧证据，任一缺失均阻断准出，但不改变 App 运行时行为。
- AND `stackctl app-content-uat` 只有在 Alpha/Beta/Gamma 的 `environmentArtifact.releaseTrainId` 相同、`packageBaselines[target]` 分别精确等于各自 manifest/sourceCapsule/startup candidate，并且每个 target 由 managed/hermetic 控制面持有并释放 lease/transport、从 active candidate 私有 projection 产生零 warning 的 canonical launch report/attempt 时，才可生成父完整性投影；该投影不得聚合为独立 passed receipt。每个 raw `ReadinessCaseResult` 必须与同一 target、platform、device、immutable source capsule、application ID、runtime package、trust envelope及真实安装 AppArtifact 摘要完全一致，并逐 target 持久化 launch attempt/provenance/artifact/trust/attempt digest、`candidateDigest`、`packageDigest`、`startupTerminalAttemptId`、`startupTerminalEvidenceDigest` 与 `startupTerminalEvidenceRef`。Android 不得绕过 launcher；direct/lightweight 启动日志、截图、VM attach 或 warning/degraded 观测不得提升为 promotable raw result。故障控制只作用于 runtime receipt 绑定的精确容器且始终恢复，任何 target 失败时保留已有 raw evidence、将未执行 required slots 标为 blocked/skipped 原因并停止后续 App 执行。父 report 只读持有 required raw refs、exact-byte digests、coverage 与缺口，不得持有 outcome verdict 或掩盖这些结果。
- AND 受管字面 `flutter run` 依次完成 exact device 解析、alpha full mutable runtime 启动或复用、真实 consumer lease/transport、同一 lease 的 device trust 安装与验证、exact 当前内容绑定（无 latest 猜测）与严格 preflight（TLS、api-edge、user-service、integration-service、SMS Provider/relay identity、真实 OTP journey、含 homepage/Creator 头像/图片/typed video/premium stream/媒体字节的内容预检），写 private managed preparation receipt 后前台 exec canonical `run.sh` 完成 build/install/activation/attach，attempt 记录 `launchProvenance=canonical_launcher`；任一 readiness 不可用在 Flutter build 前输出首个 typed blocker，非 alpha ambient 环境选择器被 typed 拒绝，绕过 dispatcher 的 raw SDK 绝对路径构建在既有 trust gate 以 typed blocker 阻断；managed 启动只要求登录服务可用，真实内容验收仍要求已登记白名单账号登录。`run.sh` 无 `-d` 与受管字面 `flutter run` 均按单设备自动、多设备双 TTY 数字交互、非 TTY typed block 的 canonical 规则选择设备，显式 `-d` 保持 exact。`app_launch_attempt` 的两个 terminal carrier 字段固定为空；launch surface 枚举值与 `app_artifact_manifest.yaml` 的 `launch_provenances` 闭集保持一致，任何启动脚本不得自持第二份枚举副本。
- AND hermetic live worktree 的外层 `run.sh --hermetic` 在创建 private workspace projection 前检出 active dependency bundle 与当前 source identity 漂移时，先输出 canonical stale blocker（detail 只含白名单字段名）；stdin/stderr 双 TTY 的交互会话自动完成一次 canonical 同步并在 active readback 与本次 sync attempt 一致后重试一次 projection 即恢复启动，非交互调用、同步失败、activation ambiguous 或第二次 stale 保持失败且首个 blocker 不被替换，锁定声明不被更新；普通 direct/lightweight 路径只执行自身 pub 输入检查，不进入该 projection/receipt authority。
- AND `run.sh` 前台 TTY 会话的 r/R/q 分别触发同一 attach 会话的 hot reload、hot restart 与停止；两台不同设备的并行 canonical run 互不阻塞并各自到达终态，同设备重复启动即重启既有实例。
- AND 显式但不完整的 handoff、Profile/Release 与超出 nonprod 信任域的 direct 环境选择在安装前失败，用户不得看到由开发配置缺失制造的启动恢复页。
- AND 端到端验收 runner 入口唯一归属主测试树，只承载会话级前置与收尾，不聚合用例也不预启动 App；每个验收场景各自完成一次启动，不存在第二份 runner 入口。

<a id="gwt-003"></a>
### GWT-003 全渠道安装启动行为等价

- GIVEN 同一环境已激活同一内容 release，各路径使用同一 immutable candidate（或 direct Debug 使用同一工作树与 canonical handoff）构建。
- WHEN 分别经 `REQ-004` 声明的有效路径完成安装并点击图标冷启动，包括同包名覆盖升级。
- THEN 各路径 CaseResult 的规范化行为指纹一致，差异只出现在 BuildMode、launch provenance、install channel 与性能观测维度。
- AND 应用市场与官网 APK 渠道各自绑定真实下载/安装回执与安装后 telemetry 回读；官网 APK 的 SHA-256、包名与签名证书摘要与发布事实逐字段一致。
- AND 覆盖升级路径的行为指纹与全新安装一致，本地缓存按 content identity 规则迁移或失效，不存在只有升级用户才遇到的启动死路。
- AND 任一渠道证据缺失时该渠道保持 `GATE_BLOCK/OPEN`，不得以其他渠道回执或 package-only 报告替代。

<a id="gwt-004"></a>
### GWT-004 Alpha/Beta/Gamma rehearsal raw results 保持同一 release

- GIVEN Data 已为同一 immutable release create-once `ReleaseUatSamplePlan`，Alpha、Beta、Gamma 已激活该 release，且 Ops 已为每个 target 的 Android Emulator 与 iOS Simulator required slots create-once `TargetUatBinding`，production Remote composition 可运行。
- WHEN 三个 target 的两端按 `entry × carrier` required cells 依次执行正向内容窗口与 suite 内受控 API Edge 5xx 恢复，并另外在 Alpha 执行独立 empty-baseline drill。
- THEN 三个 target 的两端分别交出绑定同一 release、source capsule、`candidateDigest`、`packageDigest`、真实安装 AppArtifact、launch attempt 与 safe terminal 的 raw `ReadinessCaseResult`。父 report 只读投影 required refs/digests 与缺口，不产生单环境 aggregate、独立 verdict 或 promotion authority，所有 rehearsal 结论均为 `nonPromotable=true`。
- THEN 页面 runner 逐平台验证自动化实际安装并启动的 `testedAppArtifactBinding` 与同 target canonical launch 的六项身份；缺字段、伪造 comparison、非法 provenance 或任一不一致均输出 `APP.UAT.page_artifact_binding_missing` 并停止，不得以 test host 的自身制品或 canonical launch 的复制字段冒充页面已测试 production-behavior AppArtifact。
- THEN Alpha 空态 drill 保存 previous active release identity、应用 empty baseline、取得两端 `no_active_release` raw results 并 same-digest replay previous release；结果不声明 `deleted`。任一中断先恢复，恢复失败即停止。rollback/replay raw results 保留，且 feed/search/recommendation/direct_or_object_route 全部 readback previous release identity。该结果不得替代 Beta/Gamma 正向或 5xx 恢复 CaseResult。
- THEN 每个 target 的受控 Edge 故障都在 `finally` 恢复精确容器并通过 health，同一安装点击唯一重试后重新看到原 release。
- THEN 精选池为空的环境以 `apply` 产出的导入报告为唯一输入完成首次激活，绑定收据记为 `release_import` 且不声明 verify 运行；池中已有条目的环境不接受该路径，其变更只认 consumer 档收据。

<a id="gwt-005"></a>
### GWT-005 physical promotion profile 不复用模拟器结论

- GIVEN `ReleaseUatSamplePlan` 已冻结二维矩阵，Alpha 垂直切片或正式环境 promotion 请求创建 promotable target bindings。
- WHEN Ops 准备 Alpha/Beta/Gamma 正式 profile，或准备 Prod production profile。
- THEN Alpha 垂直切片至少为 Alpha Android physical 与 iOS physical required slots 分别 create-once `TargetUatBinding` 和 raw `ReadinessCaseResult`；正式 promotion 按 plan 补齐相应环境全部 physical slots，且使用与 rehearsal 相同的 canonical raw result schema而非第二套 CaseResult。
- AND Alpha/Beta/Gamma physical slots 逐项绑定已登记物理设备、受测 production-behavior artifact、target runtime/package/config、runner 与 active CAS/readback；任何 Emulator/Simulator raw result 只能保留为 `nonPromotable` rehearsal evidence。
- AND Prod required slots 逐项绑定 production artifact、Android/iOS physical devices 与 production authority；Debug/nonprod artifact、模拟器、人工口头确认或父 report verdict 均返回 `GATE_BLOCK`。
- AND required physical slot 缺失、failed、blocked 或 skipped 时不创建通过 acceptance，既不修改现有 raw result，也不以其他 platform/device/entry/carrier slot 替代。

<a id="gwt-006"></a>
### GWT-006 EnvironmentAcceptanceFact 只从 profile 对应的 canonical authority 链生成

- GIVEN Data 已 create-once `ReleaseUatSamplePlan`，Ops 选择 `acceptanceProfile=environment_promotion|m1_api_consumer`，且所选 profile 的 required raw `ReadinessCaseResult` 已逐 slot 形成。
- WHEN Ops 尝试追加 canonical `EnvironmentAcceptanceFact`。
- THEN 两个 profile 由同一 schema、validator、factId 派生与 append-only store 条件校验；fact 直接列出本 profile 全部 required raw refs/exact-byte digests 与 profile-specific readiness。`m1_api_consumer` 同时列出不同语义且不要求相等的 `releaseDigest` 与 `manifestDigest`，并只列 Data readiness 与 identity-bound consumer health；`environment_promotion` 才列 active CAS/readback、lifecycle `Exit`、Provider/observability/rollback readiness及 resource finalization。retired `appUatEnvelopeDigest` field、Data readiness 或父 report/bundle 不能替代任一 required authority。
- AND `environment_promotion` 必须先有 artifact/device 就绪与 fresh active CAS/readback 后 create-once 的非空 `TargetUatBinding` 集合，再直接绑定全部 required App raw results；Beta/Gamma/Prod 还分别绑定前环境同 profile acceptance exact-byte digest。任一 physical/profile/authority、required slot、digest 或 predecessor 缺失均 `GATE_BLOCK`，M100/Gamma 与 Prod 的 physical-device 要求保持不变。
- AND `m1_api_consumer` 只在 `alpha/alpha-local` 成立，`targetBindingRefs` 字段缺席；它递归重验原始 health exact bytes但只要求 build/runtime/release/exact-query layers，机械重算 sourceFingerprint，并对同一 M1 release/importRunId/verifyRunId 的 16 个 fresh API integration consumer readback CaseResult 与各自 exact HTTP observation 做 4 entry × 4 carrier 精确一一覆盖；raw `objectId` 是 plan source identity，`runtimeObjectId` 仅在 observation；任一 App 用户验收结果、TargetUatBinding/device 字段、跨 identity、重复/缺失 cell 或非 passed result 均 `GATE_BLOCK`。
- AND `m1_api_consumer` fact 被提交给 M100/Alpha promotion、后继环境 predecessor、physical UAT、正式 Green Matrix 或 M1000 start gate consumer 时必须拒绝；不得转换、复制或改标为 `environment_promotion`。
- AND `environment_promotion` 收尾 evidence 分别证明 `lease revoke`、`lock release` 与 raw/binding/acceptance/rollback/replay 的 `GC protection`，不使用 `cleanup completed` 代替三项状态；`m1_api_consumer` 不创建或引用这些收尾 facts。
- AND Prod `J0/J1/J2` 只分别投影 canonical engineering eligibility、durable exact approval、canary→5%→20%→50%→100% rollout/rollback facts；视图无新状态机或 ledger，缺步/乱序/撤回/rollback 时只重算 blocked/incomplete，不改写 canonical facts。

## 6. 依赖

- 前置要求：[`runtime-config`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 环境拓扑与打包 验收证据

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：缺少与修复后 source/candidate identity 一致的 Alpha/Beta/Gamma fresh live 回执。任何旧 `package/up/health`、release 导入或页面回读只作诊断，不作当前通过证据。Prod-sim/Prod 的公网 DNS/TLS 前置由 OPEN-002 独立承接，不反向阻塞 nonprod 本地矩阵。
- 目标：在同一 `releaseTrainId` 下，分别为 Alpha、Beta、Gamma 捕获各自 fresh target-scoped immutable candidate 与唯一 `baselineId`，再按 target 顺序完成 package、up、strict health/verify、同一 immutable release activation/readback、Android/iOS 启动与首页矩阵。三个 target 的环境输入和 baseline 允许且预期不同，不得把 Alpha candidate 或 baseline 复用、复制或回填给 Beta/Gamma。真实登录和 1v1 消息由其所属 Feature OPEN 独立关闭，不由 runtime 复制验收；Prod-sim 只完成打包、纯度、安装启动 readiness，Prod rollout 保持单独授权。
- 完成判定：`GWT-001` 的四环境 App/Service/activation 重建矩阵与 `GWT-002` 的 Android/iOS 会话保护、test-live 告警及 Prod fail-closed 矩阵全部通过，且真实测试以子句级 `spec_ref` 直接绑定 canonical raw `ReadinessCaseResult`；父完整性投影只能证明 Alpha/Beta/Gamma 的 `environmentArtifact.releaseTrainId` 相同，并逐 target 列出各自 fresh candidate manifest、source capsule、`candidateDigest`、`packageDigest`、`packageBaselines[target]` 与 raw refs/digests，不得持有独立 verdict、声称三环境共用一份 candidate 或替代任一 raw result。

<a id="open-002"></a>
### OPEN-002 Prod 公网 DNS 与公共证书 live 准出

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：`quwoquan.com` 注册与 NS 委派已生效，仓内已具备供应商中立的 DNS plan/apply/verify、五个 zone 的完整记录集（含生产 apex 与全部业务子域）、CAA、邮件防护，以及 `prod-sim` 与 `prod-hosted` 两条 DNS-01 证书签发链路，并隔离 provisioning 与 challenge-only 两个凭据。剩余阻断收敛为运行凭据一类：所有者已创建 DNS 权限的 RAM AccessKey 并打通生产 edge 的管理 SSH 通路，但该凭据在会话中暴露过，必须先轮换并收敛为最小授权、再进入受保护变量，期间不能伪造 Prod 接入的 live DNS/TLS 成功证据。边缘可达性已部分就绪：生产 edge 的 443 已从公网可达，80 尚未放行（只影响 HTTP→HTTPS 跳转，不阻塞 DNS-01 证书签发）。该阻断不得反向阻塞 Alpha/Beta/Gamma 的 local-managed 本地闭环，也不得反向阻塞非生产 zone 的公网记录下发。
- 目标：轮换后通过受保护变量提供 `QWQ_DNS_PROVISIONING_API_TOKEN`、`QWQ_ACME_DNS_API_TOKEN` 与 `QWQ_PROD_EDGE_IPV4`，执行五个 zone 的 apply、`prod-sim`/`prod-hosted` 证书签发与公共 CA 验证并保存 receipt。
- 现网前置：服务商控制台当前已存在人工维护的生产 apex 与 `www` 地址记录，第一次 apply 必须把它们收敛进 `dnsZones` 派生的记录集，收敛后控制台不再持有第二份人工记录。生产 edge 主机 443 已从公网可达；80 放行后补 HTTP→HTTPS 跳转探针。
- 完成判定：`GWT-001` 的 Prod `stackctl package / up / health / verify` 子句在真实公网接入下成立——Prod 接入要求的 DNS A/AAAA/CAA/MX/SPF/DMARC、反向解析、证书 SAN/有效期及公开角色 HTTP/WSS 探针全部通过，且证据报告可回读。

<a id="open-003"></a>
### OPEN-003 全渠道安装启动等价矩阵外部证据

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：`GWT-003` 的应用市场渠道（Apple App Store/TestFlight、华为、小米、OPPO、vivo、应用宝）需要外部开发者账号、生产签名、应用记录、审核与真机回读。官网 APK 渠道需要生产 keystore 与公网 CDN。覆盖升级需要历史 version/build 的可安装制品。缺任一项时对应渠道保持阻断，不得以 side-load、package-only 或其他渠道回执冒充。
- 目标：按渠道逐项补齐账号、签名、上传、审核与真机安装回读，形成独立 install receipt 与安装后 telemetry 回读证据。
- 完成判定：`GWT-003` 的全部渠道子句由真实下载/安装/启动回执绑定通过；未就绪渠道在发布准出中保持显式 `GATE_BLOCK/OPEN`，其余渠道不受阻塞。
- 依赖：[`app-release-recovery-routing`](../../../product-ops-growth/product-control-plane-foundation/app-release-recovery-routing/spec.md) `OPEN-001`、各市场开发者账号与审核、生产签名材料。

<a id="open-004"></a>
### OPEN-004 Alpha/Beta/Gamma 双模拟器 target-scoped 内容与恢复证据

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺同一 release train 下 Alpha/Beta/Gamma 各自 Android Emulator 与 iOS Simulator 的正向和受控 5xx 恢复 raw `ReadinessCaseResult`，也缺与这些结果同一执行闭包的 Alpha `no_active_release` lifecycle drill。Alpha 单端、Alpha-only 父 report 或旧 receipt 都不能作为三环境完成证据。
- 尚缺实现：三环境 runner 需按 target/platform/device/entry/carrier create-once slot 执行正向、受控恢复与 Alpha lifecycle drill，并让父 report 只读列举 raw refs/digests。
- 尚缺验收证据：`local_contract` 证明 slot 与父投影约束，`api_integration` 证明 empty/replay 与四入口 previous release identity，`user_acceptance` 交付六个模拟器 raw results。
- 完成判定：`GWT-004` 由二维矩阵、create-once slot 与父投影无 verdict 的 `local_contract`，真实 Alpha empty/replay lifecycle 及四入口 previous release identity readback 的 `api_integration`，以及六个 production Remote `user_acceptance` raw `ReadinessCaseResult` 直接覆盖。每个结果均绑定同一 source/candidate/package/safe-terminal 身份并明确 `nonPromotable=true`，且父 report 只读列举 raw refs/digests，无单环境 aggregate、独立 verdict或 promotion authority。

<a id="open-005"></a>
### OPEN-005 设备相关 launch blocker 的行为断言

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺 `device_unavailable`、`platform_unsupported` 与 `receipt_invalid` 三个 canonical launch blocker 的可观察行为证据；已有枚举集合不能证明真实触发路径。
- 尚缺实现：设备发现与 receipt 校验路径需稳定返回对应 typed blocker，并保持 manifest 闭集、首错与恢复指引语义。
- 尚缺验收证据：`local_contract` 逐项触发三个 blocker，`api_integration` 证明 launcher/设备探测边界与 receipt provenance，`user_acceptance` 证明失败停在业务 Shell 前。
- 完成判定：`GWT-002` 声明的 typed blocker 中这三个码各有一条真实触发的断言——设备类两码由真实设备发现失败（或等价的 canonical 设备探测替身）驱动，`receipt_invalid` 由一次完整 launcher run 产出的非 `app-launch-attempt` 回执驱动；断言与真实四环境启动矩阵同轮交付，不以源码字符串断言替代。

<a id="open-006"></a>
### OPEN-006 prod buildProfile 的 Debug/Profile 配置在 codegen 侧尚未退役

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：当前 `store` distribution class 在 `_shared/app_artifact_manifest.yaml` 只声明 `build_modes: [release]`，prod buildProfile 却仍有 Debug/Profile 配置被物化出来，使「prod 只有 Release」这条 metadata 事实在物理树上不可自证。
- 已达成的部分：`Runner.xcodeproj/project.pbxproj`、`ios/Podfile` 与 `prod.xcscheme` 三处均已不引用 `Debug-prod`/`Profile-prod`，prod scheme 的 `buildForRunning`/`buildForProfiling` 为 `NO`，没有任何构建入口能选中它们。
- 尚缺实现：`quwoquan_service/tools/codegen_app_metadata` 的 App identity codegen 仍按 buildMode × buildProfile 全笛卡尔积产出 `ios/Flutter/Debug-prod.xcconfig` 与 `Profile-prod.xcconfig`，两份文件无人引用却仍登记在 `quwoquan_app/tool/app_identity_codegen/generated_manifest.json`。
- 风险：无引用的生成文件让「prod 只有 Release」这条 metadata 事实在物理树上不可自证，读者需要额外推断哪些配置是死的。
- 尚缺验收证据：`local_contract` 证明 codegen 只生成 distribution class 允许的 build modes，`api_integration` 证明 Xcode project/Podfile/scheme 与生成清单无 Debug-prod/Profile-prod 引用，`user_acceptance` 证明 Prod 安装只消费 Release artifact。
- 完成判定：codegen 按各 buildProfile 的 `distribution_class.build_modes` 求交后产出 xcconfig，`GWT-002` 绑定的 iOS 身份矩阵契约同时断言 project/Podfile/scheme 三处无引用且这两份 xcconfig 不再生成；生成清单随之收敛。
- 依赖：Go codegen 与其 local_contract，属 iOS 构建身份矩阵面。

<a id="open-007"></a>
### OPEN-007 Patrol UAT test host 与生产 runtime config 供给栈尚无双端闭环证据

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚未形成 Android/iOS test host 复用生产原生读取面、trust 嵌入与 host application id activation 编排的双端证据。当前 Patrol CLI 实际运行 `com.quwoquan.testhost.patrol`，只能回读 test host 自身的 `applicationId + artifactDigest`，不能证明生产 AppArtifact 的 `sourceProjectionDigest + runtimeConfigPackageDigest + trustDigest + launchAttemptId`；因此严格页面验收必须返回 `APP.UAT.page_artifact_binding_missing`，不得以 canonical comparison 回填或源码存在冒充完成。
- 尚缺实现：确认 test host 与生产 App 只共享一套生成契约和平台 I/O 实现，没有手写错误码、字段、target 或 launch provenance 副本；从干净受版本控制输入重建双端 host，分别完成 trust 校验、安装后 activation、启动与 release identity readback。
- 尚缺验收证据：`app-content-uat` 在 research 与 consumer 两个相位各产出一次页面 suite 通过回执，其中 `device_bound` 与 `content_live_passed` 均在场且 release identity 与 Data readiness 一致。
- 完成判定：[`GWT-003`](#gwt-003) 的行为指纹一致子句在 test host 启动路径上成立，即同一环境下 test host 与生产 App 的配置完成态、首个安全终态与 release identity 一致且 recovery 不再因缺 package 二次抛错。[`GWT-004`](#gwt-004) 的 Android/iOS 原始 CaseResult 均从实际受测 App 交出六项完整、同 target 且与 canonical launch 相等的 `testedAppArtifactBinding`，不再返回 `APP.UAT.page_artifact_binding_missing`。
- 依赖：生产侧 runtime config 原生供给面与 trust 嵌入脚本，以及 `stackctl app-content-uat` 的 Patrol 编排。

<a id="open-008"></a>
### OPEN-008 ACME challenge 凭据的记录前缀范围无法由服务商强制

- 类型：`risk`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：`acmeChallengeAuthority.requiredNamePrefix` 要求 challenge 凭据只能变更 `_acme-challenge` 记录，但现役 DNS 服务商的授权粒度只到主域名，无法在 IAM 层按记录名前缀收敛。该凭据一旦泄露，实际可写整个 zone 的任意记录，包括生产 apex 与业务子域的地址记录。当前 `providerEnforcement` 已如实标注为 `credential-isolation-only`，隔离价值仅限于两个凭据可独立轮换与吊销。
- 尚缺实现：三条候选路径择一并落为事实——服务商提供记录级授权条件后改标 `provider-enforced-prefix`，或把 `_acme-challenge` 以 CNAME 委派到独立受限 zone 使泄露面不含主 zone，或为 challenge 凭据加短时效签发与使用后即时吊销以把暴露窗口压到单次签发。
- 尚缺验收证据：一个契约测试证明 challenge 凭据在其被授予的范围内无法改写生产地址记录，且该证明来自授权面而非工具链自律。
- 完成判定：`GWT-001` 的「challenge 凭据可写范围如实声明」子句可从 `credential-isolation-only` 升级为 `provider-enforced-prefix`，或委派方案使 challenge 凭据的可写 zone 不含任何生产业务记录。
- 依赖：DNS 服务商授权粒度，或 `_acme-challenge` 委派 zone 的建立。

<a id="open-009"></a>
### OPEN-009 依赖纯度门以命令字面子串断言语义不变量

- 类型：`risk`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：风险在于 `verify_local_dependency_purity.py` 用 `_check_contains` 的字面 needle 断言「离线依赖解析」这类语义不变量，被保护脚本一旦做合法重构就假红。实测现场：`quwoquan_app/run.sh` 把 flutter 可执行体参数化为 `"$QWQ_REAL_FLUTTER" pub get --offline --enforce-lockfile` 后语义完好，但字面 needle `flutter pub get --offline` 不再匹配，门禁 FAIL。假红与真红不可区分，会训练执行者忽略该门，从而让真正的隐式拉取回潮。
- 尚缺实现：该门对命令类不变量的断言方式需一次裁决并统一——按语义要素判定（命令动词加必需 flag 闭集，可执行体允许参数化），或把可执行体解析收敛为受版本控制的单一变量名后断言该变量形态。同一文件内其余命令字面 needle 同批收敛，不逐条特判。
- 尚缺验收证据：一个契约测试证明可执行体被参数化、但离线与 lockfile 强制仍在场时该门通过，且移除 `--offline` 或 `--enforce-lockfile` 时仍阻断。
- 完成判定：[`GWT-001`](#gwt-001) 的依赖纯度子句在被保护脚本参数化可执行体后仍成立，且该门无字面可执行体名耦合。
- 依赖：`quwoquan_app/run.sh` 的 flutter 可执行体解析形态定稿。

<a id="open-010"></a>
### OPEN-010 managed 字面 flutter run 与全局 run.sh 尚未形成真实双端证据

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：required human surfaces 收敛为全局可调用的 direct/lightweight `run.sh`、受控制 IDE Run/Debug 与受管 PATH 中注入 managed intent 的字面 `flutter run`（managed one-command 入口，固定 alpha/content-live）。当前仍缺 managed 字面命令一命令到达 alpha 首页内容的双端现场证据、dispatcher 的 readiness fail-closed 顺序与非 alpha 选择器拒绝、依赖 bundle stale 的单次有界同步恢复、`run.sh` 无 `-d` 交互设备选择、attach 键位桥、并行双设备与同设备重复运行重启的现场证据；facade/carrier 退役后的 PATH 注入等价性、`make app-dev`/`make app-uat` 薄适配与 test_live readiness 也尚未同轮闭环。direct 启动观测不得用来关闭 managed/UAT promotable 证据缺口。
- 尚缺实现：launcher `flutter` dispatcher（`run` 子命令进入 managed stackctl launcher、其余 exact 透传）、managed 路径的固定执行顺序与严格 preflight、private managed preparation receipt、嵌入默认供给与 `native_flutter_run` 消费面的物理退役、`run.sh --hermetic` 外层 bundle stale 检测与单次交互式同步恢复、PATH wrapper 与 TTY 设备选择、attach r/R/q 键位桥、deploy work state 按 run/设备隔离，以及由 managed/hermetic 控制面拥有且只清理 owned mapping 的 `adb reverse` 幂等化。iOS UAT attempt-1/retry 仍复用 parent 预冻结 binding，direct/lightweight `run.sh` 的 test_live warning 不得跳过真实编译、安装、activation 与启动，也不得产生 promotable evidence。
- 尚缺验收证据：`local_contract` 证明两类 Make 薄适配、dispatcher 子命令分流与 readiness fail-closed、raw SDK 旁路负例、bundle stale 单次恢复与非交互 fail-closed、`run.sh` 设备选择、PATH 注入投影可逆、键位桥与并发隔离、blocker 闭集；`api_integration` 证明真实 stackctl 委托、managed preflight 的真实服务/Provider/内容探测、runtime package/CAS readback、physical Pod identity 及 attempt-1/retry 同 binding；`user_acceptance` 证明 Android/iOS 的 `run.sh`、受管终端字面 `flutter run` 一命令首启 alpha 内容、并行双设备、同设备重复运行重启及 raw SDK/非 alpha 选择器负向行为，`make app-uat` 不替代这些 human surfaces。
- 完成判定：[`GWT-002`](#gwt-002) 在全部 required positive surfaces 及负向面逐项成立：从受版本控制输入重建 Cursor/user-zsh PATH 注入后，`run.sh` 任意目录可调用且无 `-d` 时按 canonical 规则选择设备；受管终端字面 `flutter run` 完成固定顺序 preparation、严格 preflight、真实编译、安装与首启 alpha 内容，任一 readiness 不可用在 Flutter build 前输出首个 typed blocker；依赖 bundle stale 在双 TTY 交互会话被一次 canonical 同步恢复且非交互保持 fail-closed；并行双设备互不阻塞、同设备重复运行即重启；raw SDK 绝对路径与非 alpha ambient 选择器仍输出首个 typed blocker。OPEN 保持未关闭，直至上述 fresh 证据全部到位。
- 依赖：本节点启动设计、`app_artifact_manifest.yaml` / `app_launch_manifest.yaml` 与平台 build gate。

<a id="open-011"></a>
### OPEN-011 启动 metadata 消费者仍持有手写协议副本

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺 Swift、Java/Kotlin、Python 与 Shell 启动脚本对 canonical 启动 metadata 的单轨消费，现有手写字段、错误码、target map、状态或 launch provenance 副本可能漂移。
- 尚缺实现：metadata/codegen 需生成跨语言只读协议视图，所有消费者只保留 I/O 与编排并对未知值 fail closed。
- 尚缺验收证据：`local_contract` 证明集合相等、未知值阻断与生成物 freshness，`api_integration` 证明双端 activation/readback 使用同一协议，`user_acceptance` 证明 Android/iOS 可见错误语义一致。
- 完成判定：[`GWT-002`](#gwt-002) 的 metadata 单轨、错误闭集、launch provenance 与双端 activation 子句成立：metadata/codegen 生成跨语言只读协议视图并由所有消费者加载；平台手写代码只保留 I/O 与编排。集合相等、未知值 fail-closed、生成物 freshness 与干净重建测试通过，任一消费者不得自持第二份闭集。
- 依赖：`runtime-config` design、跨服务 metadata compiler 与 App identity codegen。

<a id="open-012"></a>
### OPEN-012 DNS zone 全量对账尚无 fresh 实现与合约证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：尚缺与本次 source/candidate identity 一致的 fresh 实现、contract 与 provider readback 证据。[`GWT-001`](#gwt-001) 已要求 provider 对整个 zone 列举并分列上报 `observedUnmanaged` 与 `observedExempt`；只核对计划声明的名字时，手工新增或历史遗留的计划外业务入口仍可静默通过。
- 尚缺实现：`DnsProvider` 提供 zone-scoped 全量列举能力；`verify` 以 canonical plan 为对账基准，将计划外业务名字逐条归入 `observedUnmanaged`，将服务商管理的 NS/SOA 等具名豁免项归入 `observedExempt`，且该对账只报告、不隐式清理。
- 尚缺验收证据：`local_contract` 用 fake zone 同时注入一条未登记业务记录和一条具名豁免记录，断言两者分别进入 `observedUnmanaged` / `observedExempt` 且不被删除；`api_integration` 再从 fresh provider zone readback 证明同样的分类和完整性。
- 完成判定：只有上述实现与两层证据在同一当前 source fingerprint 下 fresh 重跑并以子句级 `spec_ref` 绑定 [`GWT-001`](#gwt-001) 后，本 OPEN 才能关闭。旧 receipt、只有 plan-scoped 核对或只存在字段/代码的证明均不得冒充完成。
- 依赖：DNS provider adapter 的 zone list 权限与 `stackctl verify` 对账编排。

<a id="open-013"></a>
### OPEN-013 UAT authority 链尚缺 fresh 四环境验收证据

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：`ReleaseUatSamplePlan → TargetUatBinding → raw ReadinessCaseResult → EnvironmentAcceptanceFact` 单向 authority 链、raw slot create-once、acceptance append-only、required raw exact-byte refs、前环境 acceptance digest、lifecycle Exit、Provider/observability/rollback readiness 与父投影禁止写回已由 schema/code/local_contract 落地。当前仍缺同一 current source/candidate fingerprint 下的 fresh `api_integration`/`user_acceptance`、双端物理设备与 Alpha→Beta→Gamma→Prod 顺序 evidence，所以本 OPEN 继续 `GATE_BLOCK`。Data readiness、retired `appUatEnvelopeDigest`、父 report 或所谓 `AppUatResultBundle` 均不能冒充这些 fresh evidence。
- 尚缺实现：无。Data-owned `ReleaseUatSamplePlan`、Ops-owned `TargetUatBinding`/`EnvironmentAcceptanceFact`、canonical raw `ReadinessCaseResult` slot identity、exact-byte evaluator、父 report 只读投影与 J0/J1/J2 纯视图均已落地；不得把本 OPEN 重新表述为 schema/code 缺口。
- 尚缺验收证据：相关 `local_contract` 已证明重复创建、缺 raw、failed/blocked/skipped、父投影写回、J 标签直接推进均 fail closed。仍缺 fresh `api_integration` 证明 active CAS/readback、前环境 acceptance exact-byte digest、Exit 与 Provider/observability/rollback 缺一即阻断，并缺双端物理设备 `user_acceptance` 证明四环境 acceptance 可追溯到每个 required raw result 而非 bundle verdict。
- 完成判定：保持已通过的 `GWT-006` schema/code/local_contract，在同一当前 source/candidate fingerprint 下补齐 fresh `api_integration` 与双端物理设备 `user_acceptance`，并让 Alpha/Beta/Gamma/Prod 的 `EnvironmentAcceptanceFact` 按顺序 exact-byte 绑定前环境 fact；任何 legacy aggregate verdict 无写 authority、无 promotion consumer。

<a id="open-014"></a>
### OPEN-014 promotable physical UAT profile 与生产授权证据尚未闭环

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺 Alpha 垂直切片与正式 promotion 所需的 Android/iOS physical slots。现有 Alpha/Beta/Gamma Android Emulator 与 iOS Simulator evidence 按约保留但全部 `nonPromotable`，Prod 还缺 production artifact、双端 physical devices 与 production authority 共同绑定的 raw evidence。
- 尚缺实现：在不新增 CaseResult 类型的前提下，为 Alpha/Beta/Gamma 和 Prod 声明明确 physical profile、required slot identity、受测 artifact class、device registration、runner 与 authority binding；Ops runner 按 profile 创建 `TargetUatBinding` 并产出同一 canonical raw `ReadinessCaseResult`。
- 尚缺验收证据：`local_contract` 证明模拟器不可升级为 promotable 且两类 profile 共用同一 raw schema；`api_integration` 证明 artifact/device/runtime/CAS/authority exact binding。`user_acceptance` 先交付 Alpha Android+iOS physical vertical slice，再按 release plan 交付其余环境与 Prod physical slots。
- 完成判定：[`GWT-005`](#gwt-005) 的 required physical slots 全部由 fresh raw results 关闭；任何缺失、failed、blocked、skipped 或模拟器替代保持 `GATE_BLOCK`。

<a id="open-015"></a>
### OPEN-015 二维 UAT 与 lifecycle 尚缺 fresh 实证

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：二维 `entry × carrier` schema/code/local_contract 已区分 feed/search/recommendation/direct_or_object_route 与 homepage/article/image/video，并已冻结 required cell、`no_active_release`/empty/deleted 与 rollback/replay identity 语义。当前仍缺 fresh `api_integration`/`user_acceptance`：所有 required cells 尚未在双端物理设备产生 current raw results，四环境 lifecycle drill 也尚未逐 entry 证明回到 previous release identity，所以本 OPEN 继续 `GATE_BLOCK`。
- 尚缺实现：无。Data-owned `ReleaseUatSamplePlan` 已表达二维 cells 与 plan-owned `not_applicable` reason，Ops `TargetUatBinding`/raw slot identity 已同时绑定 entry 与 carrier，lifecycle result 已区分 `no_active_release`、empty、deleted 并承载 previous release identity 与 rollback/replay raw refs。
- 尚缺验收证据：相关 `local_contract` 已对 required/not_applicable 全矩阵、entry/carrier 维度混用与 deleted 误标做负向断言。仍缺 fresh `api_integration` 对四环境 empty baseline、same-digest replay 和四 entry previous identity readback 取证，并缺双端物理设备 `user_acceptance` 对所有 required cells 逐项生成 current raw result。
- 完成判定：保持已落地的二维 schema/code/local_contract，在同一 current source/candidate fingerprint 下由 fresh `api_integration`/双端物理设备 `user_acceptance` 证明 [`GWT-004`](#gwt-004)、[`GWT-005`](#gwt-005) 的 required cells 均可由 raw refs 唯一定位，并完成四环境 lifecycle drill：无 deleted 伪装，四入口 rollback/replay identity 全部一致。
