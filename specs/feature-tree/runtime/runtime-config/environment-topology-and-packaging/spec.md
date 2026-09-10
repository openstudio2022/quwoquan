# L3 Story：环境拓扑与打包 (`environment-topology-and-packaging`)

> 所属能力：[`runtime-config`](../spec.md)

> Journey / Scenario：[`JNY-002 / SCN-005`](../../../spec.md#scn-005)

> 设计归属：[L2 DEC-001](../design.md#dec-001)、[L2 DEC-002](../design.md#dec-002)、[L2 DEC-003](../design.md#dec-003)、[L2 DEC-004](../design.md#dec-004)、[L2 DEC-006](../design.md#dec-006)

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
- 云侧四环境保持同构 schema/网络平面（归 [`system-topology-and-networking` REQ-002](../../system-topology-and-networking/spec.md#req-002)）；App 只在组合根选择 Alpha canonical 离线快照或 Beta/Gamma/Prod Remote，详见 [`REQ-008`](#req-008)。其余环境差异限于容量、endpoint、访问控制、内容版本和第三方 sandbox 策略，不形成不同业务页面。
- App / Service env package 都必须携带 canonical unversioned schema identity、artifact policy 摘要与机器可读报告。
- App 产品支持面固定为 Android、iOS 与 Web；未持有平台工程、包身份、签名和真实安装启动证据的平台不得进入 metadata、schema、CI 或发布矩阵。
- Android 与 iOS 可执行制品必须由 `stackctl package` 从同一只读 source capsule 按 `buildProfile(nonprod|prod)` 构建，Web 只生成一份共享 bundle；每次组件构建必须显式选择 build product，并在写 manifest 前回读包身份、签名、artifact digest 与生产纯度。AppArtifact 以 build-profile 级 trust envelope 隔离 nonprod/prod；nonprod 可携带 REQ-008 的完整 Alpha 离线快照及同源启动材料，其完整性验证不是在线 endpoint 签名包的双读 fallback。Beta/Gamma 在线签名配置在安装后经 canonical activation 写入同一 nonprod App 私有容器，切环境不触发重编、重签或改变制品摘要；Prod 不携带非生产离线资产。
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
- local environment matrix 的 `emulator_only` rehearsal 运行模式只要求 iOS Simulator 与 Android Emulator，并保留原始 canonical `ReadinessCaseResult`。这些结果及其 Alpha/Beta/Gamma `EnvironmentAcceptanceFact` 必须保持 `nonPromotable=true`，不得进入最终签名包的物理接受、RC `QualificationFact`、正式 Green Matrix 或 Prod 激活 authority；不得把模拟器结果改标、复制或聚合为物理设备证据。最终签名包的 Android/iOS 物理接受由 RC qualification 独立绑定，不回写环境 rehearsal。
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
- 云侧多 target 可按 [`multi-environment-instance-isolation`](../../deliver-deploy-prod-pipeline/multi-environment-instance-isolation/spec.md) 的 host-target 单实例规则并行；资格前驱和有限设备 slot 排队不要求停止其他环境。Alpha 离线 App 不触发云栈启动。
- 在线 App 会话以 full runtime 为 baseline；Alpha 离线无云侧 baseline。bounded 内容任务只复用健康 full 能力，不覆盖 baseline receipt；独立 bounded runtime 占同一 host-target slot，不得与另一 full/test-live/candidate 栈并存，退出仅恢复自己有权管理的进入前状态。
- 在线环境及独立 Alpha API gate 使用同一 canonical 发布、激活与就绪链，不选择内容类别；readiness 绑定 exact immutable release，分别验证首页推荐 Post items、普通 video 查询和视频书 premium/premium_stream 的真实结果。普通 video 非空不代替 premium ready，缺正式 receipt 或 required query 为空不产生通过事实。Alpha 离线装配按 REQ-008 验证快照闭包，不复用服务 activation authority。
- `ReleaseUatSamplePlan` 是环境消费侧从 immutable release exact bytes（`payload/release.json`、`payload/desired_state.json`、`payload/objects/**`）确定性派生的下游 artifact：每载体按 identity 升序取首个对象，二维 cells 全部 `required`，`milestone` 恒为 `null`；落点固定为 `<releaseRoot>/uat/sample_plan.json`（`payload/` 之外，payload digest 不受影响），派生回执把 plan digest 绑到 `releaseId + manifestDigest`。producer handoff 与 release header 不携带、不引用该 plan；Ops 只通过 exact-byte `TargetUatBinding` 将派生 plan 绑定到 target/runtime/package/config/platform/device/runner slot。App 自动验收不得从手工环境变量、fixture、旧回执或任何 retired envelope 重建计划或 target binding。
- 应用消费验收必须建模为二维矩阵：`entry ∈ {feed, search, recommendation, direct_or_object_route}`，`carrier ∈ {homepage, article, image, video}`；每个 cell 只能声明 `required` 或 `not_applicable`，后者必须携带 plan-owned reason。entry 是到达内容的入口，carrier 是被消费的内容载体，禁止把二者混称为同一组“四 surface”、以一维列表替代矩阵，或以一个通过 cell 覆盖另一个 required cell。

<a id="req-003"></a>
### REQ-003 双端本地运行按三层 ownership 隔离 direct、managed 与 UAT 证据

- 启动 ownership 唯一分为三层，且不得跨层提升 authority：direct/lightweight `run.sh` 只拥有当前工作树的开发启动；managed/hermetic stackctl launcher 由控制面拥有 runtime preparation、transport receipt 与 consumer lease；UAT/evidence 层只能消费 managed/hermetic 启动链形成 promotable evidence。`content-live` 是未指定 mode 时的默认；`ui-only` 仅用于调试安全 Shell 与页面布局，所有结果必须显式 `nonPromotable=true`。
- `quwoquan_app/run.sh --mode content-live|ui-only --env alpha|beta|gamma [-d <device>]` 在普通调用下是 direct/lightweight 路径：它必须经既有 stackctl lease 边界取得/绑定并 exact 释放本 invocation 的安全使用租约（Alpha 离线仅设备绑定），但不得创建 managed runtime transport、执行 `adb reverse` 或签发 transport/readiness receipt，安全租约缺失不得伪装为已保护；但若 stackctl 外层已交付经 exact readback 验证的 receipt/lease/handoff 与 cleanup obligation，则它必须按同一身份正确绑定和透传给 build/install/activation/attach，并只履行外层明确委托的本 invocation teardown，不得重获、改写、释放或清理不属于该 invocation 的资源。direct 仍拥有自身直接执行所必需的真实 SDK 解析、pub 输入检查与 `pub get`、设备发现/校验、签名 handoff/trust、真实 build/install/activation/attach；显式或自动选择的未知、不可见、非移动或不受支持设备必须在 executor 前 fail closed。direct 的任何输出只属于开发观测，不构成 managed preparation receipt、`app-launch-attempt`/test-live report 或 promotable UAT evidence。
- `dev-session --app-mode content-live|ui-only` 默认 `content-live`。Alpha/Beta/Gamma 的 direct `test_live` 是开发启动严格度：两种 App mode 都不得因服务、Provider、内容或观测 readiness 不可用而跳过真实编译、安装、activation 与启动；`ui-only` 始终标记 `nonPromotable=true`，`content-live` 必须读取 REQ-008 所选的 canonical source 并如实呈现成功、合法空态或 typed unavailable；Alpha 不为此请求 Remote。direct/lightweight 的 warning+degraded 结果无论 mode 都不得进入 promotion authority 链。
- `make app-dev ENV=alpha|beta|gamma [DEVICE_ID=<id>] [MODE=content-live|ui-only]` 是面向人类的公开一键入口，仅作为 `stackctl dev-session --launch-app --app-mode` 的薄 adapter；`ENV` 默认 `alpha`，`MODE` 默认 `content-live`。设备选择只委托 canonical device authority：唯一设备自动选择，多设备必须显式 `DEVICE_ID`。Make 不拥有设备发现、env/target 扩展、交互、状态机、provenance 或 receipt。
- `make app-uat TARGETS=... PLATFORM=... DEVICE_ID=...` 是面向 AI/自动化的无交互公开入口，只委托 `stackctl app-content-uat`；`TARGETS` 仅允许 `alpha-local`、`beta-local`、`gamma-local` 的非空子集，禁止 Prod。它只编排自动验收，不替代受管字面 `flutter run` 或 IDE surface 的用户验收。
- `quwoquan_app/run.sh --mode content-live --env alpha|beta|gamma -d <device>` 是内容联调与 Hot Restart 的 canonical direct 开发启动执行体，不是完整或 promotable 启动证据链；具名激活入口把受管 bin 目录注入 PATH 后，`run.sh` 在任意工作目录全局可调用，PATH wrapper 只 `exec` 仓库内同一脚本，不复制参数、状态或第二套逻辑。受控制的 IDE Run/Debug（`workspace_ide_debug`）可以薄包装该 direct 执行体，但除非由 stackctl UAT/evidence 控制面显式提供 managed/hermetic launch control，否则同样只有 non-promotable 开发观测 authority。
- managed/hermetic 控制面拥有其 runtime preparation 与证据：默认字面 `flutter run` 固定 Alpha/content-live，按 REQ-008 验证离线快照和设备绑定，不启动云栈、不要求 DNS/TLS/登录服务或云侧 consumer lease。Beta/Gamma/UAT 的 Remote 路径由控制面先解析 exact device、启动或复用同 target full runtime、取得独立使用租约和必要 transport/trust、绑定 exact 内容并执行严格 preflight；只清理本 invocation owned 资源，不能提升 direct 安全租约为 managed readiness。其他 Flutter 子命令/项目 exact 透传，非法选择器 typed 拒绝；raw SDK 和 IDE 默认 Alpha 使用同一 canonical 离线读取与完整性校验，不依赖 PATH 注入。
- 默认 Alpha 构建期供给只依赖仓库与 SDK，从当前受版本控制源码派生 nonprod trust、完整离线快照及独立 signed offline bootstrap document，并经同一 activation/CAS/read chain 消费，不依赖用户 shell、PATH 或特定 worktree 绝对路径。供给失败 typed 阻断，不生成假配置/内容成功。已显式激活的在线目标不因默认供给被静默替换；显式切回 Alpha 才采用该制品的快照。离线包完整性与在线配置时间窗分离，相关 schema 只由 canonical launch metadata 拥有；provenance 仍是观测，不恢复退役 terminal carrier 或第二启动协议。
- 设备选择：`run.sh` 未给 `-d` 时委托 canonical device authority——唯一可用移动设备自动选择，多台且 stdin/stderr 均为 TTY 时显示 canonical 数字列表并接受一次交互选择，任一流非 TTY 时以 typed blocker 要求显式 `-d`，不得按最近使用猜测设备；显式 `-d` 必须按 exact device identity 保留并校验。`workspace_ide_debug` 由 profile 的显式设备选择或同一 canonical authority 解析；受管字面 `flutter run` 的设备选择同样由 canonical device authority 裁决——单设备自动、多设备双 TTY 数字选择、非 TTY typed block、显式 `-d` 按 exact device identity 校验。
- 终端注入必须可凭受版本控制真相源重建且可逆：具名激活入口向 Cursor terminal profiles 与显式 opt-in 的 user-zsh managed source block 注入同一受管 PATH bin 目录（含 launcher `flutter` dispatcher）与钉定的 Flutter SDK/CocoaPods/Python 身份，不改 ZDOTDIR、不生成 terminal receipt；dispatcher 只对本 App 工作区的 `run` 子命令进入 managed 入口，其余子命令与其他项目 exact 透传真实 SDK。新终端自动生效，既有 shell 只能通过显式 source 刷新接入；移除注入并重载、或移除 user-zsh managed block 即完全回退，不得要求修改 Flutter 安装或遗留第二 launcher。
- `run.sh` 前台会话与并发语义：TTY 下 r/R/q 分别桥接为同一 attach 会话的 hot reload、hot restart 与停止，非 TTY 保持无键盘面。跨设备并行 canonical run 互不阻塞——deploy work state 按 run/设备隔离；direct/lightweight 不执行 `adb reverse`，managed/hermetic 控制面的 Android `adb reverse` 必须幂等且只清理本 invocation 新建的映射，不清理预存或他会话映射；同设备重复启动复用同一受控绑定；显式跨环境切换先结束旧会话并冷启动或重建完整 ProviderScope，旧 lease 不得解绑新会话。
- canonical launcher 固定选择 nonprod build profile，默认 Alpha 离线，显式 Beta/Gamma 只选择各自在线签名配置；它禁止选择 Prod 或直接覆盖 URL、密钥、target、manifest 与 release。
- 环境选择器只选择 nonprod 内的 canonical source/运行配置，不选择原生包身份、不进入 Flutter 编译输入、不直接决定页面行为。
- `workspace_ide_debug` surface 没有自建的 mode 协议；run mode 与环境同构，经 `QWQ_RUN_MODE`（`content-live|ui-only`，默认 `content-live`）选择并交同一 canonical 执行体校验，IDE profile 只投影同一输入，非法值 fail closed。受管字面 `flutter run` 不参与 mode 选择协议：managed 入口固定 alpha/content-live，任何非 alpha 的 ambient 环境或 mode 选择器对字面命令 typed 拒绝。
- canonical Debug 安装或复用同一 nonprod AppArtifact；默认 Alpha 的独立 signed offline document 与在线目标签名配置均经同一原生 coordinator 验证、CAS 激活与 read chain，再按文档类型读取 source。冷启动与 Hot Restart 都只消费该 canonical 解析结果，Dart 不读取 endpoint define、环境变量或第二 keyring；配置变化不重编/重签，实际环境在握手后成立，换环境前结束旧会话并重建 scope。
- App 构建不得读取或改写共享的“当前环境”文件，nonprod 组件只编译一次。
- 同包 Alpha→Beta→Gamma→Alpha 显式切换只改变已验证 source/配置绑定并重建完整运行上下文，不要求 clean、重编、重签或重装；不得只移动 pointer 而继续使用旧 client。
- 并发 activation 必须以 expected active digest 条件更新，不能共享可写 handoff 或相互覆盖。AppArtifact digest 与签名必须保持不变。
- effective launch 配置不拥有内容激活事实。在线 App 只从 Content API 的 canonical typed identity 确认 server active release，环境期望仅用于 evidence 比对；Alpha 的制品快照携带独立 source/version/digest，不写服务端 activation receipt。在线发布/回滚不重打 App，Alpha 快照升级随 nonprod 制品更新并在验证失败时保留旧完整快照。
- canonical Debug 仅在操作者未选择环境时默认 Alpha；两个环境选择器冲突、Prod、任意 target override、在线 package 过期/缺失、所选 source 的 trust envelope 缺失、摘要不一致或 activation readback 失败均 fail-closed。Profile、Release 与 Prod 启动禁止隐式推断。
- 在线 source 的 Android managed/hermetic 控制面从 topology 推导包名、设备与所需 `adb reverse` 端口，在 Flutter 构建前获取 release-bound lease 并准备可验证 transport receipt；其 teardown 在退出时释放本次创建的 lease 并仅移除本次 owned reverse 映射。direct/lightweight 不创建 transport/readiness receipt，但仍取得自己的安全使用租约；外层已委托同 invocation lease 时只消费该 exact 绑定，不重复 acquire。异常中断后的 managed provisional lease 由 App 进程 liveness 判为 stale 并等待显式 GC。
- 在线 source 的 iOS managed/hermetic 控制面为 Simulator 与已登记 iPhone 同源准备签名 runtime package、安装后 activation 与同一 `consumer-lease` 对象，Simulator 额外执行系统公共 CA 预检；direct/lightweight 也持同一安全 lease 协议但不签 managed preparation，Alpha 离线只持设备绑定。
- iOS lease 绑定 platform、设备标识、bundle ID、target、active package digest、启动宽限期与 handoff digest，且不携带 transport ports。
- 宽限期后，Simulator 必须结合 `simctl get_app_container`、`user/<uid>` launchd 域中的 `UIKitApplication:<bundleId>` service 与 executable path 判定存活。已登记 iPhone 必须结合 `devicectl device info apps/processes` 的结构化 App URL 与 process executable 判定存活。
- 结构化状态读取失败只能保留 `active_unverified` 证据，不得代偿为已停止或已存活。
- 已验证存活的 App lease 不受 12 小时 provisional 上限影响；`consumer-lease status` 和 down/package/roll 前检查必须严格只读，不得删除 stale 文件。只有显式 `release`/GC 可以清理 lease。
- canonical launcher 固定编译 production `lib/main_prod.dart`；`lib/main.dart` 只能薄委托同一入口，不能建立裸 Flutter 启动协议。
- 所有受支持入口都由同一启动解析边界选择 REQ-008 的 typed source：Alpha 只读制品快照，其他环境只读 Remote；禁止 alpha test runner、fixture override、假服务或 Remote 失败后切本地。在线 source 继续通过 canonical activation/native reader/resolver 验证目标签名包。
- Gradle/Xcode 只验证所选 `nonprod/prod` profile、build-profile trust envelope、build product 摘要与设备证明；target runtime package 不进入 build phase、bundle resource 或 assets。
- 在线 source 的 canonical Debug 只允许从 metadata/topology 构建所选 handoff 并在安装后 activation；Alpha 离线按 REQ-008 验证 canonical 制品材料；本平台 transport/readiness 仅由 managed/hermetic 外层准备；direct 安全使用租约经同一控制面取得，不得伪造或提升 authority。两层均不得推断 URL、复制配置到源码/构建树或吞掉 activation 失败；只有显式 managed/hermetic 控制面可按其合同启动或复用 runtime。
- Android/iOS 的 target package activation 必须验证 runtime package、制品内独立 trust envelope、build profile、target 与 effective manifest digest，并以 expected active digest 原子更新私有容器。缺一或 readback 不一致即在进入业务 Shell 前 `GATE_BLOCK`，失败时保留上一 active digest；endpoint、environment 和 runtime config 摘要不得进入 `DART_DEFINES`。
- 已激活旧 package 的时间窗（`expiresAt`）过期只使消费读取 fail-closed，不得阻断以其身份为 expected active digest 的下一次替换激活：activation 流程读取 CAS 前值时仍必须验证 trust envelope、签名与结构完整性，仅豁免时间窗判定；该豁免不得扩展到冷启动/Hot Restart 的 native reader 消费路径，也不得放松对新 package 自身的 freshness 校验。过期即死锁、要求删除重装才能恢复的实现是违约。
- active receipt schema 新增必填观测字段时，不得让已安装旧 App 永久死锁或要求卸载/清数据。当前迁移只允许在下一次 activation 的 CAS 前值读取阶段接受“精确等于当前 receipt 字段集减去 `launchProvenance`、`runtimeConfigSupplyMode`”的上一版 canonical receipt。它必须是 `activated`、摘要字段合法、`activePackageDigest=packageDigest`、环境/target/buildProfile 自洽且无 error/validation issue，且唯一输出是 `expectedActiveDigest`。同字段集的上一版 launch receipt 只允许作为等待原生用当前 schema 原子替换的 stale 文件被忽略，绝不构成本次 request 的成功证据。上一版 receipt 不得进入 cold start、Hot Restart、Dart/runtime readback 或成功证据。新 activation 仍须完整验证新 package 并由原生以当前 schema 原子覆盖 active receipt。任意额外缺字段、额外字段、非 canonical JSON 或身份/摘要不自洽都 fail-closed。不存在仍可生成上一版 receipt 的受支持 artifact 且设备基线证明迁移完成后必须删除该单代迁移读口。
- Alpha/Beta/Gamma 的 `test_live` 中，无论选择 `ui-only` 还是 `content-live`，runtime/startup/service/Provider/TLS/transport/content readiness 不健康、startup receipt 缺失、active candidate 过期及 source/config/generated digest 漂移都只形成结构化 warning，不得使 Xcode/Gradle build phase 失败或跳过真实编译、安装、activation 与启动。任一 warning 必须使最终 launch report 和 runtime health 保持 `degraded`，不得提升为 `healthy`。`content-live` 启动后读取 REQ-008 的 canonical source；在线依赖不可用只能到达 canonical 空态或 typed unavailable/degraded，Alpha 不以无云侧 readiness 推断离线失败，也不伪造 Remote 成功。依赖解析、身份/信任、最小 handoff/runtime package 生成、真实编译、设备选择、target 冲突、命名空间逃逸、Prod endpoint/credential 泄露与不安全 secret 始终硬阻断。
- `app-debug-preflight` 必须显式选择 `test_live` 或 `immutable_candidate`，不得以默认 mode 替调用方决定严格度。receipt 的 `details` 只记录安全编译/启动 blocker，`warnings` 只记录 test-live readiness 诊断。`gate_block` 对应非零退出，`warning|passed` 对应零退出；preflight 的零退出只允许继续构建，不等于 runtime healthy 或 UAT passed，平台启动器不得重新解释同一事实的严重级别。
- `test_live` 中缺失、停止、过期或漂移的 runtime/startup/service/Provider/TLS/transport lease/content readiness 与本地容量诊断必须保留完整脱敏 warning 并继续构建；它们不得被重新分类为 identity/security blocker。非法环境/target、环境命名空间逃逸、显式 handoff 冲突或不完整、无法生成 canonical runtime package/native manifest、build-profile trust 缺失或不一致、工具链/真实编译失败与不可用设备仍阻断。`immutable_candidate`、严格 health/verify、内容 UAT 与 Prod 不复用该降级。
- direct/lightweight 不拥有环境生命周期，不隐式 up/down/repair；除只读诊断外仅经既有控制面操作自身安全使用租约或设备绑定。managed/hermetic 只对在线 source 按显式合同启动/复用 full runtime，Alpha 离线不要求它。
- `--ensure-runtime` 不得让 direct/lightweight 路径接管环境生命周期；只有 managed/hermetic 控制面持有显式 frozen candidate identity 时，`content-live` 才可委托 `stackctl` 启动该 exact candidate，且不得执行 package、repair 或重选 release。
- `ui-only` 与 `content-live` 的 `test_live` 预检都以 `warning` + exit 0 报告服务、Provider、内容、观测、容量与漂移问题。`content-live` 不得把 warning 重新解释为内容可用，而是在真实启动后的 canonical source 读取中产生可观察 outcome；warning 运行的最终健康度只能是 `degraded`。只有零 warning 的 `immutable_candidate`、内容 UAT 与 Prod readiness 才能消费严格 delivery 结果。
- direct/lightweight Debug 在设备执行前必须调用 `stackctl app-debug-preflight`，但该只读诊断不转移 lease/transport ownership；managed/hermetic launcher 在 Flutter build 前消费由控制面签发并 exact readback 的严格 preflight/receipt。Alpha/Beta/Gamma direct test-live 只校验安全环境选择与最小 handoff并收集运行时诊断，不委托严格 `app-content-preflight`；Prod release 与 UAT/evidence 启动继续验证 immutable candidate、必要服务/Provider，并委托 `app-content-preflight` 绑定内容 readiness、首页/视频书、Creator 与媒体证据。完整 integration/release 验证独立要求 lifecycle Exit，不把它变成普通 managed/content-live 启动或首次激活的前置。
- 只有 managed/hermetic 与 UAT/evidence 启动入口必须写 canonical `app-launch-attempt` receipt，并等待最长 15 分钟直到真实达到 `launched`、`runtime_degraded` 或产生首个 typed failure；direct/lightweight 只输出开发阶段观测，不得签发该 receipt 或据此宣称通过。PID 存活、进程已创建、1.5 秒未退出与 Flutter VM attach 都不是成功。只有本次已安装 `artifactDigest` 发出的 canonical `startup_safe_terminal` 与同一 managed launch attempt 关联，且回执持久化非空 `startupTerminalAttemptId + startupTerminalEvidenceDigest + startupTerminalEvidenceRef` 后才能标记 `launched`；任一 warning 只能到达 `runtime_degraded`。编译、安装或启动失败分别使用 canonical typed blocker，正常 Ctrl-C 记为 `stopped`。
- Android `prod-sim` 只安装并启动 exact Release artifact；Flutter 不支持 iOS AOT Release/Profile simulator，故 iOS Release 基础编译生成 unsigned iphoneos `.app`，Simulator 只允许 non-promotable Debug 启动且不得冒充 Release/Prod 证据。`prod-hosted` 只消费已签名 artifact、manifest、安装回执和严格 readiness，禁止 `flutter run`、Debug 或未经授权的真实 rollout。
- 每次 Dart isolate 启动必须先生成新 `attemptId`，再调用原生 `beginStartupAttempt(attemptId)`。原生返回 `attemptKind=cold|hotRestart`、`processElapsedMs`、`attemptElapsedMs` 与 `deadlineOrigin=nativeProcess|dartHotRestart`。
- `startup_attempt_started` 只能在所选 canonical source 已验证并完成配置后发送，在线 source 必须先水合有效 native package，Alpha 离线不能伪造在线 package；Cold Start 的 6 秒预算可使用进程时钟，Hot Restart 只能使用本次 attempt 时钟。进程总存活时间只作诊断，不得写入 `welcomeExitMs` 或消耗 Hot Restart 预算。
- 自动页面 suite 以同一 source train/cohort 和逐 target 精确制品/来源绑定执行：首页 items、真实 premium 与播放器分别回读。Alpha 离线绑定完整快照，Beta/Gamma 绑定服务 active release；严格预检只检查所选 source 的必要能力，不为 Alpha 请求云侧 readiness。设备 slot 可串行，云栈不因此串行或停止；required warning 阻断本 slot 并如实保留。
- iOS UAT parent 必须在 attempt-1 前一次性解析并冻结 exact `PATH` 与同一 six-field physical CocoaPods binding，attempt-1 与 retry 原样复用；不得依赖 parent shell ambient identity、在 attempt 间重新发现，或由 Flutter child/其他子进程反向传回 binding。binding 被篡改或不能保持一致时，必须在启动 Flutter child 前返回 typed blocker。
- 每个 target 的页面 suite 前必须解析 fresh active candidate，并校验 manifest 的 `candidateDigest`、`packageDigest` 与只读 input capsule。runner 只能把该 capsule 复制到 attempt-scoped 私有 writable projection 后从 projection build/launch，不得从 live `APP_DIR` 取源码；复制前后 tree digest 漂移即返回首个 typed blocker。
- 每个页面 suite 必须消费紧邻且绑定同 target/platform/device/immutable source/真实安装 AppArtifact 的 canonical launch evidence；在线配置与离线 source 各自按现役 metadata 证明，不伪造缺失字段。raw SDK 默认 Alpha 的开发观测不自行签发 UAT authority，受控 runner 的真实结果不可由启动日志替代。
- 只有 attempt 真实完成 compiled、installed、configured，并由本次已安装 APK/`.app` 的同一 `artifactDigest` 产生关联 startup safe terminal 后才可进入页面 suite。VM attach 只记观测，不得替代 safe terminal；回执必须含非空 `startupTerminalAttemptId + startupTerminalEvidenceDigest + startupTerminalEvidenceRef`。
- 页面 suite 必须从实际安装启动的 App 回读 canonical tested-artifact binding，与同 target launch 的真实制品、source、trust 和 attempt 精确一致；字段只由 metadata 拥有。test host 自身 identity、复制 comparison 或无安装/启动 provenance 不能证明受测 App。若现役 schema 无法表达 Alpha 离线 source 则保持 typed blocker/OPEN-019，先由 metadata owner 修正，不用假的在线 package digest 补齐。
- 聚合回执必须逐 target 写入 `launchAttemptId`、launch provenance、artifact/trust/attempt digest、`candidateDigest`、`packageDigest`、`startupTerminalAttemptId`、`startupTerminalEvidenceDigest` 与 `startupTerminalEvidenceRef`，并写入非空 `releaseTrainId` 与 `packageBaselines[target]`。每个 UAT runtime binding 的 `candidateDigest` 必须等于对应 startup receipt 和 target baseline，launch source 必须等于该 binding 的 immutable source capsule。回执不得保留空 scalar、从 Alpha 取值代替其他 target，或接受上一代 UAT。
- UAT/evidence 层必须经 `stackctl app-content-uat` 或等价受控入口使用 managed/hermetic ownership：在线窗口持 target-scoped runtime-use lease，Alpha 离线窗口只持设备绑定；各自只释放本 invocation owned 资源，逐 target 绑定 immutable source capsule、strict zero-warning preflight、canonical launch receipt、safe terminal 与 raw `ReadinessCaseResult`。任一 target 失败即停止并输出首个 typed blocker 和可机读 receipt。禁止消费、复制、改标或聚合 direct/lightweight 的 warning/degraded 输出、截图、VM attach、启动日志或无 receipt 运行作为 promotable evidence；禁止以 dry-run、旧 receipt 或单环境成功替代三环境结论。
- 云侧运行权威与使用租约由既有部署控制面按 host-target 统一跨 worktree/共享 daemon 发现，不按 lane 创建第二栈；受管根不能由调用者任意改写。每个 target 独立 lifecycle fence，运行 generation 与 package candidate pointer 分离；worktree 只持来源和报告引用，不凭本地 receipt 缺席推导服务停止。详见 [`multi-environment-instance-isolation` REQ-001/004](../../deliver-deploy-prod-pipeline/multi-environment-instance-isolation/spec.md#req-001)。
- 受控 API Edge 故障只作用于 Remote source 与独立 Alpha API gate，并遵循 REQ-005 的精确 target 维护租约与恢复边界；Beta/Gamma 在同次安装重试恢复，Alpha 离线证明不受影响。异常必须恢复本次 owned 故障并保留首错，不遗留故障、不以 double 替代。
- 活跃 lease 未协调时 down/restart/repair 必须阻断；矩阵禁止跨 target 预清理或端口强制回收，即使没有本 worktree receipt 也不能认定资源无 owner。

<a id="req-004"></a>
### REQ-004 所有有效构建、安装与启动路径行为等价

- 有效路径集合固定为：canonical launcher `run.sh`（content-live/ui-only/Hot Restart，launch provenance=`canonical_launcher`）、受控制 IDE profile（`workspace_ide_debug`）、受管 PATH 中经 launcher `flutter` dispatcher 进入 canonical launcher 的字面 `flutter run`（managed one-command 入口，launch provenance=`canonical_launcher`，固定 alpha/content-live）、`stackctl package` 产物 Debug 安装到 Simulator/Emulator/登记设备并由 canonical activation 后点击图标、Android `prod-sim` exact Release、Android/iOS `prod-hosted` Release、应用市场 Release 安装（Apple App Store/TestFlight、华为、小米、OPPO、vivo、应用宝）、官网签名 APK 安装，以及上述任一渠道的同包名覆盖升级。raw SDK/原始平台构建的默认 Alpha 路径同样有效且必须消费 canonical 离线供给，非 Alpha 在线路径缺合法 handoff 仍阻断；iOS Simulator 只允许 non-promotable Debug，不属于 Release 安装路径。
- 等价定义：同一环境与同一已验证内容来源状态下，各路径的规范化行为指纹一致——配置完成态、首个安全终态、路由/登录态、内容 outcome 与 release identity、恢复动作均相同，且无 fatal recovery 差异。BuildMode、launch provenance 与 install channel 只允许作为观测事实记录，不得参与业务分支。本条与上条是有效路径集合与等价指纹定义的唯一 owner，AppRoot 与其他节点只引用不复制。
- 每类安装渠道产出独立、按 store/device/build 追加的 install receipt。应用市场渠道的准出证据必须来自真实市场客户端下载安装与安装后冷启动 telemetry 回读，官网 APK 渠道必须来自官网下载对象的 SHA-256/签名/包名比对与安装后启动回读。package-only 编译、side-load 或另一渠道回执不得互相替代。
- Debug 签名制品仅限开发者本机、Simulator/Emulator 与已登记设备，不进入 TestFlight、任何应用市场或官网公开下载；市场与官网只接受 Release 签名制品。
- 每个渠道的验收 CaseResult 声明自动化分级：CI 全自动、设备实验室定期自动、或人工执行加机器回执；人工动作缺机器回执时按失败处理。

<a id="req-005"></a>
### REQ-005 canonical raw ReadinessCaseResult 是唯一 UAT 结果事实

- canonical raw `ReadinessCaseResult` 是唯一可承载 UAT outcome、verdict 与 failure/blocked/skipped 原因的结果事实。每个 `required target × platform × device × entry × carrier` slot 必须 create-once；`not_applicable` cell 由 plan 声明且不生成伪通过结果。required slot 缺失、`failed`、`blocked` 或 `skipped` 均保持原状并阻断相应 acceptance，不得被父 report、所谓 `AppUatResultBundle`、summary、重跑或其他 slot 掩盖。
- 父 report/所谓 `AppUatResultBundle` 只能是对 required raw refs、exact-byte digests、矩阵覆盖率与缺口的只读完整性投影：无独立 verdict、无 promotion authority、不可写回 raw result 或 acceptance fact，也不得另造第二套 CaseResult。任何聚合层出现独立 `passed`、丢弃非通过结果或把模拟器 evidence 提升为 promotable 时必须 `GATE_BLOCK`。
- Alpha、Beta、Gamma rehearsal 内容验收继续让 Android Emulator 与 iOS Simulator 对同一 `releaseId + manifestDigest + sourceIdentitySetDigest` 分别生成 canonical raw `ReadinessCaseResult`，覆盖 [`AppRoot UAT-001`](../../../spec.md#uat-001) 的内容、Creator、搜索和可恢复终态，以及 [`UAT-003`](../../../spec.md#uat-003) 的同状态、同内容 identity 与同恢复动作；这些 slot 全部明确 `nonPromotable=true`。
- 多 target App UAT 按冻结 required slots 与可用设备独占编排，不因设备顺序停止并行云栈；Alpha 离线 slot 与服务 gate 分离。rehearsal 父 report 只读投影完整性并声明 `nonPromotable=true`；不得生成单环境 aggregate、canonical matrix passed 或 promotion 事实。
- Alpha/Beta/Gamma 的环境执行只使用 `EnvironmentAcceptanceFact` v2 的 `smoke|integration|release` profile；其中 `release` profile 的 `caseResultRefs` 必须引用 canonical App UAT 层的 `ReadinessCaseResult`。Simulator/Emulator 结果可以证明 rehearsal 与本地集成，但相应事实必须保持 `nonPromotable=true`。最终签名包的 Android/iOS 物理设备结果仍使用同一 canonical raw result 语义，却只进入 RC package acceptance 与 `QualificationFact`，不得被环境事实或 Prod rollout 重复解释为第二种 outcome。
- Data M1 API consumer 的读回可以作为普通 canonical `ReadinessCaseResult` 或与角色匹配的 named evidence 输入；raw 的 `objectId` 始终保留 plan source identity，导入后的 `runtimeObjectId` 只存在于 `artifactPath` 指向的 exact observation，不得向 canonical raw 添加 `observedObjectId` 或用 runtime identity 改写 source identity。它不携带 App UAT、物理设备或 promotion authority；只有满足某个现役 EAF v2 profile 的完整 candidate、ImpactPlan、结果与全部 named evidence 闭包时才能进入该事实，否则 Data ship 保持 `GATE_BLOCK/OPEN`，不得恢复已删除的专用 builder。
- `no_active_release` 只作为独立 Alpha API gate 的 lifecycle drill，不改变 Alpha 离线 App：在服务 active-release suite 外保存 previous release identity 与 readback，通过正式环境命令应用已核验 empty baseline，取得真实 API no_active_release 结果，再 same-digest replay previous release 并逐 entry 复核生命周期。`no_active_release` 或 empty baseline 绝不等同 `deleted`；rollback/replay 的 raw 结果 append-only 保留，且 `feed/search/recommendation/direct_or_object_route` 均须回到 previous release identity。任一步中断都必须先恢复原 release。该 drill 不代替 Beta/Gamma 正向与恢复结果，也不能单独关闭矩阵。
- 受控 Edge 恢复分别验证 Beta/Gamma Remote App 与独立 Alpha API gate，不能要求 Alpha 离线 App 因 Edge 故障失败。故障控制只操作该 target 维护租约与 receipt 绑定的精确容器，退出必须恢复并健康回读；Remote App 在同一安装重试读取原 release，Alpha 离线浏览不受该故障影响。
- 网络不可用显示 typed unavailable 与唯一重试，恢复网络后在原页续接同一 release；白名单或身份权限拒绝只提供重新登录或返回安全 Shell，登录成功沿用 canonical AuthContinuation，取消不循环。
- 新账号或无历史用户不形成第二套 feed：有 active release 时读取同一内容 projection，无 active release 时进入同一 canonical 空态。相机与 RTC 不参与本验收。

<a id="req-006"></a>
### REQ-006 Release UAT 输入与 EnvironmentAcceptanceFact v2 单轨派生

- `ReleaseUatSamplePlan` 由环境消费侧在 release 层 create-once 派生（唯一实现 `quwoquan_ops/cli/lib/release_uat_sample_plan_derivation.py`），环境无关，只依赖 immutable payload 字节；它冻结 release identity、source identity、二维 `entry × carrier` cell 的 `required/not_applicable`、sample identity 与 raw case expectation。同字节重放幂等，已落盘字节漂移、派生回执与 `releaseId + manifestDigest` 不符、release root 不在 `data/releases/<releaseId>` canonical 位置均 fail closed；Ops、App runner 与环境不得手写、补写或按 target 分叉该 plan，producer 不得重新把它封进 payload 或 header。
- `TargetUatBinding` 仍逐 target/runtime/package/config/platform/device/runner slot create-once，并与 plan 一起约束 raw `ReadinessCaseResult` 的来源；它们不是 EAF v2 字段。父 report 只能只读投影 raw refs、exact-byte digests、coverage 与缺口，不能回写 raw result 或环境事实。
- canonical `EnvironmentAcceptanceFact` v2 只覆盖 `environment=alpha|beta|gamma` 与 `profile=smoke|integration|release`，由同一 scheduler、schema、validator 和 append-only store 处理。事实必须绑定 `candidate`、`impactPlanDigest`、非空且去重的 `caseResultRefs`、`runtimeIdentity`、`dataLifecycle`、`providerReadiness`、`observabilityReadiness`、`inspectEvidence`、`doctorEvidence`、`cleanupEvidence`、`leaseClosureEvidence`、`predecessor`、`expiresAt`、`nonPromotable`、`issuedAt` 与 DSSE `signer`；`factId` 必须由签名后的 exact fact 机械派生。
- 每个 `caseResultRefs` 与 named evidence 都必须是不可变 relative ref 加 exact-byte digest，且各 evidence role 引用不同对象。raw result 必须为 canonical `ReadinessCaseResult`、`status=passed`，并与环境、`<environment>-local` target、candidate commit 和 candidate identity 一致；`release` profile 还必须逐项证明 canonical App UAT producer 与 layer identity。任一 required raw slot 缺失、`failed/blocked/skipped`、跨 candidate 或 digest 漂移均不得创建通过事实。
- Alpha 的 `predecessor` 必须为 `null`；Beta 与 Gamma 分别 exact-byte 绑定 Alpha 与 Beta 的同 profile、同 candidate、同 `impactPlanDigest`、同 `nonPromotable` 前驱。Beta 仅可以闭集原因码写 typed `not_required`（`IMPACT_PLAN.NO_LIVE_ENVIRONMENT_REQUIRED`：ImpactPlan 明确无需 live environment；`ACCEPTANCE.BETA_OPTIONAL_BY_POLICY`：lane 验收未显式 opt-in Beta），其余通过事实均为 `status=passed`；Prod 不在该 predecessor 链中。
- named evidence 必须分别证明 runtime identity、Data lifecycle、Provider readiness、observability readiness、inspect、doctor、cleanup 与 lease closure，并与本 fact 的 environment/profile/candidate/ImpactPlan 一致。`cleanupEvidence` 不得掩盖 lease closure，`leaseClosureEvidence` 必须独立证明资源已释放。
- Data M1 API consumer 不获得专用 EAF profile、字段集、validator 或 writer。其 API `CaseResult` 与 health/readback 可以作为普通 `caseResultRefs` 或匹配角色的 named evidence，但只有在同一 Alpha candidate 上满足选定现役 profile 的全部 v2 闭包后才能签发 EAF；当前调用链若无法提供完整闭包，Data ship 必须保持 blocked 并由 [`OPEN-016`](#open-016) 跟踪，不能恢复旧 builder 或另造 schema。

<a id="req-007"></a>
### REQ-007 Prod J0/J1/J2 仅为 canonical 发布事实视图

- `J0/J1/J2` 只是 Prod readiness UI/report 的只读视图标签，不新建状态机、ledger、verdict 或可写 promotion authority：`J0 = QualificationFact + stable ReleaseTagAdmissionFact`，`J1 = ProdActivationAdmissionFact`，`J2 = ordered ProdStageAttemptFact → ProdReleasedFact|ProdRollbackFact → read-only PostReleaseSoakFact`；其中 soak 只适用于 released 分支。
- EAF v2 的 environment 与 predecessor 闭集在 Gamma 结束。最终签名包、Provider、UAT 与 Android/iOS 物理设备接受属于 RC qualification；只有同一 qualified RC 的 stable tag admission 才能进入 Prod activation admission，Gamma 前驱、Alpha/Beta/Gamma rehearsal、Data readiness 或任何 EAF 均不能充当 Prod admission。
- `J2` 只按同一 activation admission 的 exact predecessor 链读取 `canary → 5 → 20 → 50 → 100` 的 `ProdStageAttemptFact`。最后一个 `stage=100,status=passed` attempt 才能派生 `ProdReleasedFact` terminal；任一 stage 失败且 hosted rollback 成功时只能派生 `ProdRollbackFact` terminal。缺步、乱序、跨 activation、摘要漂移或并存冲突 terminal 均显示 blocked/incomplete。
- `ProdReleasedFact` 是 stage 100 的 release terminal，和 soak 完全分离；release terminal 一经形成，不等待也不吸收后续 soak verdict。`PostReleaseSoakFact` 只能作为 exact 引用该 `ProdReleasedFact`、并由其追溯同一 activation admission 的只读后置视图，不修改 tag、qualification、activation、terminal 或 release identity。
- `ProdRollbackFact` 必须 exact 引用同一 `ProdActivationAdmissionFact`、失败的 terminal `ProdStageAttemptFact` 与作为 rollback target 的上一 `ProdReleasedFact`；rollback 与 soak 均不得生成 Prod `EnvironmentAcceptanceFact` 或 terminal `ReleaseEvidenceManifest`。任何 `ReleaseEvidenceManifest` 只允许作为显式标记的 legacy historical/non-promotable diagnostic snapshot，以历史或 rehearsal 诊断用途只读保留；formal J0/J1/J2、`ProdActivationAdmissionFact` admission 与 rollout materialization 均必须拒绝，且不得称其为候选或正式发布输入。
- 任何 legacy snapshot、aggregate verdict、旧 receipt 或字段值等价的复制对象都不能满足 J0、J1、J2 的任一子视图，也不能满足 `ProdActivationAdmissionFact` admission；视图只接受上述 canonical fact 的 exact ref/digest、时间与 authority。撤回审批、rollback 或 soak 只追加 canonical durable facts并重算视图，不改写历史事实。

<a id="req-008"></a>
### REQ-008 canonical 离线与在线读取行为等价、权威分离

- 未显式选择环境时，raw SDK、受管 `flutter run`、IDE 与 `run.sh` 均默认 Alpha 包内快照；首装断网且无后端/预热缓存仍可浏览首页推荐 Post 与视频书 premium、详情、头像/图片/封面和完整视频。快照从 canonical 出库按 exact release/cohort 确定性派生，包含完整引用与媒体字节及许可，不手写演示内容、不导入 test doubles、不做 Remote fallback。
- Beta/Gamma/Prod 仍只走 Remote，四环境共用页面与 typed ports；只有组合根读取 source/profile 选择 adapter。成功/空/失败、稳定对象身份、详情引用、过滤、分页终止/去重/取消/重试及媒体播放/seek 的可观察合同相同；同 canonical cohort 参数化验证，在线个性化排序、账号权限和新鲜度属于明确能力差异，不要求在线各环境永久同量同序。
- 首页消费推荐 Post items，视频书消费 canonical premium 精选；离线快照封存选择与频道清单，不把普通 video 等同 premium、不复制在线推荐引擎。未支持登录、写入和私有访问返回 typed capability unavailable，不假写成功、不跨环境回放。
- 离线快照身份证明制品绑定的 source/version/digest，不证明服务端 active release、账号授权或 activation receipt。只收录具有公开离线再分发许可的内容，永久离线不承诺即时撤权；需要即时撤权的内容不得进入快照。Alpha API gate 可独立运行，但不能要求 Alpha App 走 Remote，也不能用离线 App 结果签服务环境或晋级资格。
- Alpha bootstrap 使用独立 signed offline document 绑定 bundle 完整性与许可，和在线 endpoint 配置共用同一 activation/CAS/receipt/read chain，不直接绕过 active pointer 读 bundle，不伪造 HTTPS。离线文档不继承在线配置 24 小时有效期；不能通过忽略在线 expiry 实现离线，Beta/Gamma/Prod 的签名、有效期和信任域完整保留。source 类型及映射由 canonical launch metadata 冻结，组合根消费 AppContentSource typed 值，不自持 wire 副本。在线配置提前刷新验证后原子激活，失败保留尚有效旧配置，到期 fail closed。
- nonprod 仍是一套包身份；离线资产仅进入 nonprod、Beta/Gamma 不消费、Prod 制品不包含该内容或替身装配。跨环境显式切换重建进程或完整 ProviderScope，不在旧 client 动态换 endpoint；缓存与认证隔离消费 [`local-cache-architecture` REQ-004](../../runtime-client-foundation/local-cache-architecture/spec.md#req-004)。
- 在线内容更新须在完整媒体、四域 candidate 与首页/premium/必要详情查询闭包全部 ready 后，按 [`runtime-data-engineering` DEC-003](../../runtime-data-engineering/design.md#dec-003) 单 CAS 可见；失败保旧，结果不明先回读 exact pointer，再按现役授权显式 rollback，不用客户端旧缓存或第二 active flag 伪造更新成功。
- 可用性分别报告离线启动/浏览、在线推荐/premium、头像/图片、视频首帧/持续播放/seek、stale 比例及恢复时长。沿用前台读取与媒体准备 6 秒总预算、在线 operation 的 timeout/retry 合同，以及 CAS 后 60 秒回读与显式 rollback 后 5 分钟恢复目标；这些是合同目标，未有 fresh 证据不得声明已达成。库存未知不得填 0，首屏、推荐窗口、声明对象数、激活闭包、详情可读和媒体可播放分别计数并说明遍历边界。
- 在线 Feed SLO 必须由 Content owner 统一 canonical operation 与 observability 的指标范围、分母、窗口及告警派生；目前 99.9%/500ms 与 99.5%/200ms 的冲突不能择宽判绿，首刷/续页与端到端媒体不混算。生产跨故障域可用性不由本地单实例结果证明。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。
- `GWT-001` 证据绑定：`local_contract` 覆盖 topology/package/capsule/依赖纯度与只读语义，`api_integration` 覆盖真实 package/up/health/verify、Provider/DNS/TLS/readback，`user_acceptance` 覆盖 production-behavior App artifact 的安装、启动与内容结果。
- `GWT-002` 证据绑定：`local_contract` 覆盖三层 ownership、direct 持安全使用租约但不获取 managed transport/readiness authority、不执行 `adb reverse`，未知设备 fail-closed、外层 managed receipt/lease 的 exact 绑定透传与 owned teardown、`app-dev`/`app-uat` 薄适配边界、managed 字面 `flutter run` dispatcher 的子命令分流/readiness fail-closed 顺序/非 alpha 选择器拒绝与 raw SDK 默认 Alpha 等价与非法在线 handoff 负例、hermetic dependency bundle stale 的单次有界同步恢复与非交互 fail-closed、`run.sh` 全局 wrapper 与设备选择、PATH 注入投影/回退、attach 键位桥、并发隔离、frozen CocoaPods binding、direct evidence 不可提升、父 report 无 verdict 与 typed blocker；`api_integration` 覆盖真实 stackctl 委托、attempt-1/retry 同 binding、runtime package、CAS/readback、Remote 服务与 lifecycle；`user_acceptance` 覆盖 Android/iOS 的 direct `run.sh` 开发行为，以及 managed/hermetic 受管终端字面 `flutter run`、UAT 启动、Hot Restart、并行双设备、内容 outcome 与恢复动作。
- `GWT-003` 证据绑定：`local_contract` 覆盖有效路径闭集、行为指纹与渠道不可替代性，`api_integration` 覆盖下载对象、签名、包身份、release identity 与 telemetry readback，`user_acceptance` 覆盖各渠道下载、安装、冷启动与覆盖升级行为。
- `GWT-004` 证据绑定：`local_contract` 覆盖二维矩阵、create-once raw slot、父投影只读无 verdict 与 `nonPromotable`，`api_integration` 覆盖 active CAS/readback、empty baseline、rollback/replay 与 previous release identity，`user_acceptance` 覆盖六个模拟器 raw `ReadinessCaseResult`。
- `GWT-005` 证据绑定：`local_contract` 覆盖 rehearsal 的 `nonPromotable` 约束、EAF v2 与 RC qualification 的 authority 隔离及 raw result 单轨；`api_integration` 覆盖 RC final material 与 package acceptance/QualificationFact 的 exact binding；`user_acceptance` 覆盖最终签名包的 Android/iOS physical-device raw results。
- `GWT-006` 证据绑定：`local_contract` 覆盖 EAF v2 的 Alpha/Beta/Gamma 环境闭集、`smoke|integration|release` profile、candidate/ImpactPlan、`caseResultRefs`、八类 named evidence、predecessor、`nonPromotable`、DSSE signer、Beta typed `not_required`、append-only 与父投影不可写回；同时覆盖 J0/J1/J2 projector 的 canonical 类型闭集、exact ref/digest、stage 顺序、stage 100 terminal、released/rollback terminal 排他、terminal/soak 分离、rollback/soak 不生成 Prod EAF 或 terminal `ReleaseEvidenceManifest`，任何 `ReleaseEvidenceManifest` 仅能作为显式 legacy historical/non-promotable history/rehearsal diagnostic snapshot 只读保留，以及 formal J0/J1/J2、Prod activation admission、rollout materialization 对它和其他 legacy snapshot/aggregate/旧 receipt 的拒绝。`api_integration` 覆盖 Alpha→Beta→Gamma predecessor、M1 窄 evidence fail closed，并从 hosted readback 证明同一 activation 下 `ProdStageAttemptFact → ProdReleasedFact|ProdRollbackFact` 与 released 后只读 `PostReleaseSoakFact` 的 exact 引用；`user_acceptance` 只覆盖 EAF `release` profile 的 App raw results，不代替 Prod canonical facts。

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
- AND 多 target 会话可并行生成各自隔离的 compile/launch、告警与 health 结果，不预清理其他 target；单个 runtime health 失败不抹除真实编译结果，也不自动 down 已复用服务。
- AND Android/iOS 的 production dependency graph、native linker/filelist、SBOM 与最终制品均不含测试插件或 test runner，物理隔离的 UAT test host 枚举全部 canonical 用户验收 case 而不反向进入 production package。
- AND Dart/Pod 跨锁与 CocoaPods executable/version 一致；任一漂移在真实编译前返回 `APP.DEPENDENCY.lock_drift`，且不执行自动 update 或 repo refresh。跨锁范围含物理隔离的 UAT test host：它与生产工程跑同一份 `pubspec.lock` 依赖声明，两侧受版本控制的 `Podfile.lock` 在全部 pubspec 派生插件 pod 上必须同版本，否则验收结果不代表生产行为。test-only pod 与各自独有的 vendored SDK 只存在于一侧，不构成漂移。
- AND bounded content workload 复用健康 full runtime 后，App preflight 仍读取原 full receipt；独立 bounded runtime 的 receipt 不冒充 full readiness。
- AND `stackctl status` 在环境未启动、secret 缺失或 Provider 不可用时只返回诊断失败，不创建 secret、不启动或修复任何组件；内容 readiness 只有在 canonical Data receipt 与三个 release-bound exact query 均通过时才返回成功。
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
- THEN direct/lightweight `run.sh` 持自己的 exact 安全使用租约（Alpha 离线仅设备绑定），不执行 `adb reverse`、不生成 managed transport receipt 或 promotable launch receipt；它仍在 executor 前完成 pub 输入处理、exact mobile device 校验与安全 handoff/activation，未知、不可见或不支持设备 fail closed。外层若显式提供有效 receipt/lease/handoff，direct 执行体只 exact 绑定和透传，不接管资源所有权。
- AND managed/hermetic stackctl launcher 在构建前让 Android lease 绑定设备、包名、release handoff 与 topology 端口，准备并验证所需 transport receipt；退出时由 stackctl 控制面拥有 teardown obligation，并可由已验证该 obligation 的受管 `run.sh` cleanup 代执行，释放该 lease且只清理本 invocation owned 的 reverse 映射；异常中断后的 lease 由 App 进程 liveness 判为 stale 并等待显式 GC。
- AND managed/hermetic stackctl launcher 为 iOS Simulator 与已登记 iPhone 获取同一 schema 的 lease，绑定 platform、设备、bundle ID、target 与空 transport ports，并在启动 executor 前将同一 lease 绑定最终 handoff digest；Simulator 通过 user launchd application service 与安装容器 executable 保活，已登记 iPhone 通过 `devicectl` 结构化 App URL 与 process executable 保活。
- AND consumer lease 的只读状态检查不删除 stale lease。
- AND Alpha 离线与 Beta/Gamma/Prod Remote 只在组合根选择同一 typed ports，读取身份和能力按 REQ-008 区分；在线消息与个人数据仍只经真实 command/query，离线未支持能力明确不可用，不假成功、不切 Mock/fixture。
- AND target/env 冲突、Prod endpoint/credential 泄露、身份/信任、最小 runtime package、真实编译或 runtime package activation 失败时 App 在进入业务 Shell 前失败；Alpha/Beta/Gamma `test_live` 的两种 App mode 对服务、Provider、内容与观测 readiness 只记录 warning，`content-live` 在启动后以 canonical source outcome 区分可用、合法空态和 typed unavailable。`immutable_candidate`、内容 UAT 与 Prod readiness 对这些依赖继续严格阻断。
- AND managed/hermetic 与 UAT/evidence 启动回执按 prepared、compiling、compiled、installing、installed、configuring、configured、launching、launched 单向推进；direct/lightweight 不签发该回执。VM attach 只作为 launching 阶段观测。只有同一已安装 `artifactDigest` 的 canonical startup safe terminal 回写 `startupTerminalAttemptId + startupTerminalEvidenceDigest + startupTerminalEvidenceRef` 后才可出现 launched，编译、安装或 activation 失败不得出现 launched，父入口只消费该回执而不自行解释 PID。
- AND 原生 activation 与 runtime config channel 的可见错误码全部来自 `app_launch_manifest.yaml` 的 `runtime_config_error_codes` 闭集。
- AND active receipt 的缺失、读取失败与解码失败分别使用 receipt 语义错误码，不复用 activation request 语义；成功 receipt 必须持久回读已验证的 `launchProvenance` 与 `runtimeConfigSupplyMode`，进程重启后不得硬编码、从环境推断或另建无 schema 状态文件。
- AND 记录 failed receipt 时 active digest 读取失败保持最后已知 CAS 值，以 `runtime_config_activation_rollback_failed` 追加标记状态未知，不覆盖原始失败码。
- AND recovery context 对 active package 缺席与读取失败分流，读取失败携带登记错误码而不吞错为空上下文。
- AND Android/iOS Debug 与 Hot Restart 消费同一 canonical source 解析：在线核对 handoff/trust/active package，Alpha 核对制品快照与其完整性；目标与信任一致后进入同一安全 Shell，不把 endpoint 写入 Flutter 编译输入。
- AND Android/iOS nonprod AppArtifact 仅构建签名一次；默认 Alpha 与显式 Alpha/Beta/Gamma 共用完整制品摘要，Alpha 验证离线快照，Beta/Gamma 激活匹配 target 的在线配置。同包显式切换先结束旧会话并重建 scope，不 clean/重装/重编/重签，并发 activation 不互相覆盖。
- AND 冷启动和连续 Hot Restart 均先完成 `beginStartupAttempt`，再以 `configurationState=complete` 发送 attempt 事件；Hot Restart 的 `welcomeExitMs` 始终相对本次 attempt 且不超过 6000ms。
- AND 在线 source 无 active release 时只接受 canonical no_active_release 或 typed unavailable，不以普通空列表冒充成功；有 active release 时只从 Content API 验证身份。Alpha 快照身份独立且不伪造 server activation；Prod readiness/rollback 准出证据缺失仍阻断，不由离线包或 UAT 期望值补造。
- AND `stackctl app-content-uat` 只有在 Alpha/Beta/Gamma 的 `environmentArtifact.releaseTrainId` 相同、`packageBaselines[target]` 分别精确等于各自 manifest/sourceCapsule/startup candidate，并且每个 source 由 managed/hermetic 控制面持其必要的设备/target lease、从 immutable 私有 projection 产生同源零 warning canonical launch evidence 时，才可生成父完整性投影；该投影不得聚合为独立 passed receipt。每个 raw `ReadinessCaseResult` 必须与同一 target/platform/device、immutable source capsule、真实安装 AppArtifact 和 source 所需配置/trust 的 canonical binding 完全一致（Alpha 不伪造在线 package），并逐 target 持久化 launch attempt/provenance/artifact/trust/attempt digest、`candidateDigest`、`packageDigest`、`startupTerminalAttemptId`、`startupTerminalEvidenceDigest` 与 `startupTerminalEvidenceRef`。Android 不得绕过 launcher；direct/lightweight 启动日志、截图、VM attach 或 warning/degraded 观测不得提升为 promotable raw result。故障控制只作用于 runtime receipt 绑定的精确容器且始终恢复，任何 target 失败时保留已有 raw evidence、将未执行 required slots 标为 blocked/skipped 原因并停止后续 App 执行。父 report 只读持有 required raw refs、exact-byte digests、coverage 与缺口，不得持有 outcome verdict 或掩盖这些结果。
- AND 默认 Alpha 的受管字面命令、raw SDK、IDE 与 run.sh 在相同制品上读取同一离线快照，不请求云侧 runtime/lease/DNS/TLS/登录 readiness；缺完整快照或签名信任时 typed 阻断。设备选择保持单设备自动、多设备双 TTY 选择、非 TTY 明确设备，非 Alpha 非法选择器仍拒绝；provenance 与错误只消费 canonical metadata，不自持枚举。
- AND hermetic live worktree 的外层 `run.sh --hermetic` 在创建 private workspace projection 前检出 active dependency bundle 与当前 source identity 漂移时，先输出 canonical stale blocker（detail 只含白名单字段名）；stdin/stderr 双 TTY 的交互会话自动完成一次 canonical 同步并在 active readback 与本次 sync attempt 一致后重试一次 projection 即恢复启动，非交互调用、同步失败、activation ambiguous 或第二次 stale 保持失败且首个 blocker 不被替换，锁定声明不被更新；普通 direct/lightweight 路径只执行自身 pub 输入检查，不进入该 projection/receipt authority。
- AND `run.sh` 前台 TTY 会话的 r/R/q 分别触发同一 attach 会话的 hot reload、hot restart 与停止；两台不同设备的并行 canonical run 互不阻塞并各自到达终态，同设备重复启动复用同一受控绑定；显式跨环境切换先结束旧会话并冷启动或重建完整 ProviderScope，旧 lease 不得解绑新会话。
- AND 显式但不完整的 handoff、Profile/Release 与超出 nonprod 信任域的 direct 环境选择在安装前失败，用户不得看到由开发配置缺失制造的启动恢复页。
- AND 端到端验收 runner 入口唯一归属主测试树，只承载会话级前置与收尾，不聚合用例也不预启动 App；每个验收场景各自完成一次启动，不存在第二份 runner 入口。

<a id="gwt-003"></a>
### GWT-003 全渠道安装启动行为等价

- GIVEN 同一环境具有同一已验证 source（Alpha 制品快照或在线 active release），各适用路径使用同一 immutable candidate（或 direct Debug 同一工作树与 canonical source）构建。
- WHEN 分别经 `REQ-004` 声明的有效路径完成安装并点击图标冷启动，包括同包名覆盖升级。
- THEN 各路径 CaseResult 的规范化行为指纹一致，差异只出现在 BuildMode、launch provenance、install channel 与性能观测维度。
- AND 应用市场与官网 APK 渠道各自绑定真实下载/安装回执与安装后 telemetry 回读；官网 APK 的 SHA-256、包名与签名证书摘要与发布事实逐字段一致。
- AND 覆盖升级路径的行为指纹与全新安装一致，本地缓存按 content identity 规则迁移或失效，不存在只有升级用户才遇到的启动死路。
- AND 任一渠道证据缺失时该渠道保持 `GATE_BLOCK/OPEN`，不得以其他渠道回执或 package-only 报告替代。

<a id="gwt-004"></a>
### GWT-004 Alpha/Beta/Gamma rehearsal raw results 保持同一 release

- GIVEN 环境消费侧已从同一 immutable release 派生 canonical sample plan，Alpha 离线快照和 Beta/Gamma Remote 的各平台 required slots 已绑定各自真实制品与 source identity，独立 Alpha API gate 已激活该 release。
- WHEN 两端按 required cells 验证可用内容，Beta/Gamma 执行受控 Edge 恢复，独立 Alpha API gate 执行 empty/replay 与服务故障 drill。
- THEN 三个 target 的两端分别交出绑定同一 release、source capsule、`candidateDigest`、`packageDigest`、真实安装 AppArtifact、launch attempt 与 safe terminal 的 raw `ReadinessCaseResult`。父 report 只读投影 required refs/digests 与缺口，不产生单环境 aggregate、独立 verdict 或 promotion authority，所有 rehearsal 结论均为 `nonPromotable=true`。
- THEN 页面 runner 逐平台验证实际安装启动 App 的 canonical artifact/source binding 与同 target launch 完全一致；缺适用字段、伪造 comparison、非法 provenance 或不一致均 typed 阻断。Alpha schema 未能表达离线 source 前保持 OPEN，不造在线 package 字段，也不以 test host 或复制比较值冒充受测制品。
- THEN Alpha API 空态 drill 保存 previous active release identity、应用 empty baseline、取得服务 no_active_release 结果并 same-digest replay previous release；Alpha 离线 App 继续读取自己的快照，服务结果不声明 deleted 或代填 App raw result。任一中断先恢复，恢复失败即停止。rollback/replay raw results 保留，且 feed/search/recommendation/direct_or_object_route 全部 readback previous release identity。该结果不得替代 Beta/Gamma 正向或 5xx 恢复 CaseResult。
- THEN 每个服务 target 的受控 Edge 故障都恢复精确容器并通过 health；Beta/Gamma App 同一安装重试看到原 release，Alpha 离线 App 不被云侧故障阻断。
- THEN 精选池为空的环境以 `apply` 产出的导入报告为唯一输入完成首次激活，绑定收据记为 `release_import` 且不声明 verify 运行；池中已有条目的环境不接受该路径，其变更只认精确绑定的内容 readiness 收据。
- THEN `stackctl matrix` 只消费显式 candidate/rollback 准入引用，内容 release 使用 `handoff-ref-v1`、empty baseline 使用 system attestation，二者都精确绑定输入 release 身份。original 与 replay 均按 `apply → activate → verify` 推进，不选择类别或命名就绪轨道；rollback 先准备目标，再以 Content active pointer 的 exact release/digest/revision 三元组执行并 verify。Exit 的 original/replay run 引用必须指向成功 `activate`，由该结果的前驱引用继续重验 prepared apply 与导入报告，不能用 apply 的 prepared 结果冒充可见性成功。
- THEN lifecycle Exit 对 original、rollback、replay 三段分别重验同环境、同 release/digest、不同 run IDs 与 canonical result refs，same-digest replay 必须恢复 original；错用 apply、错绑前驱、跨环境、verify 引用漂移或任一阶段失败均不签发 passed。真实 matrix raw results 才证明环境闭环。

<a id="gwt-005"></a>
### GWT-005 本地 rehearsal 不替代 RC 物理包接受

- GIVEN Alpha/Beta/Gamma 已产生与 exact candidate、target 和 release 绑定的 canonical raw `ReadinessCaseResult`，且某个 RC 已封存最终签名 App material。
- WHEN Environment Ops 追加 EAF v2，或 Release Ops 尝试创建 RC `QualificationFact`。
- THEN Simulator/Emulator raw results 及消费它们的环境事实必须保持 `nonPromotable=true`；不得复制、改标或聚合为最终包、physical-device 或 Prod authority。
- AND EAF v2 只覆盖 Alpha/Beta/Gamma 的 `smoke|integration|release` 环境执行；其中 `release` profile 直接引用 canonical App UAT raw results，但不因此取得 RC 最终包接受 authority。
- AND 最终签名包的 Android 与 iOS physical-device outcome 仍由 canonical raw `ReadinessCaseResult` 表达，并由同一 RC material 的 package acceptance/UAT facts exact 绑定后进入 `QualificationFact`；缺任一平台、artifact identity、device registration、failed/blocked/skipped raw result 或 exact digest 时保持 `GATE_BLOCK`。
- AND stable tag 与 Prod 激活只消费已 qualified RC 的 exact material 和 admission facts，不把 production 纳入 EAF v2 environment 闭集，也不重跑或回写 Alpha/Beta/Gamma 业务矩阵。

<a id="gwt-006"></a>
### GWT-006 EnvironmentAcceptanceFact v2 只从完整 canonical 闭包生成

- GIVEN Environment Ops 持有 Alpha/Beta/Gamma exact candidate、`impactPlanDigest`、选定的 `profile=smoke|integration|release`、fresh `caseResultRefs` 与全部 named evidence；Prod projector 持有待显示对象的 canonical exact refs/digests。
- WHEN canonical scheduler 尝试追加 `EnvironmentAcceptanceFact` v2，或 Prod readiness projector 计算 J0/J1/J2。
- THEN 同一 EAF schema、validator、factId 派生与 append-only store 校验完整字段闭包；所有 refs 均以不可变 relative ref + exact-byte digest 绑定，DSSE payload exact 覆盖 unsigned fact，签名或任一 identity/digest 漂移均 `GATE_BLOCK`。
- AND `caseResultRefs` 非空、去重且逐项为同 environment/target/candidate 的 passed canonical `ReadinessCaseResult`；`release` profile 只接受 canonical App UAT 结果。raw failure、缺 slot、父 report verdict、bundle/count 或旧 receipt 均不能代填。
- AND `runtimeIdentity`、`dataLifecycle`、`providerReadiness`、`observabilityReadiness`、`inspectEvidence`、`doctorEvidence`、`cleanupEvidence` 与 `leaseClosureEvidence` 分别匹配自己的 role/status，并与 environment/profile/candidate/ImpactPlan 一致；cleanup 与 lease closure 不得合并成一个含混状态。
- AND Alpha predecessor 为 null，Beta/Gamma 分别 exact-byte 绑定前一环境的同 profile、candidate、ImpactPlan 与 `nonPromotable` fact；只有 Beta 可以 `not_required` 且原因码限于 typed no-live 或 policy-optional 闭集。EAF v2 链在 Gamma 结束，任何 Prod EAF、Prod predecessor 或以 Gamma fact 充当 Prod admission 的请求都 `GATE_BLOCK`。
- AND Data M1 API consumer 的 fresh API `CaseResult`、health 与 readback 只有作为普通结果或匹配角色的 named evidence并满足上述完整闭包时才可进入现役 EAF；专用 writer 缺失时保持 Data ship blocked/OPEN，不得用窄化 readiness、缺失 evidence 或第二 schema 绕过。
- AND J0 仅在同一 RC material 的 passed `QualificationFact` 与 admitted stable `ReleaseTagAdmissionFact` 均可 exact 回读时完整；J1 仅在 `ProdActivationAdmissionFact` exact 引用该 J0 tag/qualification 并在 canary 前成立时完整，缺任一对象或 identity/digest 不一致均显示 blocked/incomplete。
- AND J2 仅按同一 `ProdActivationAdmissionFact` 的 exact predecessor 顺序接受 `canary → 5 → 20 → 50 → 100` `ProdStageAttemptFact`；最后一个 `stage=100,status=passed` attempt 只能形成一个 `ProdReleasedFact` terminal，任一失败 attempt 只能在 successful hosted rollback 后形成一个 `ProdRollbackFact` terminal，缺步、乱序、跨 activation 或冲突 terminal 均显示 blocked/incomplete。
- AND `ProdReleasedFact` 的 terminal 完整性不以 soak 为前置且不被 soak 改写；released 分支的 `PostReleaseSoakFact` 必须 `readOnly=true`、exact 引用该 terminal 并可追溯同一 activation。rollback 分支的 `ProdRollbackFact` 必须 exact 引用同一 activation、失败 attempt 与上一 `ProdReleasedFact` rollback target。
- AND rollback 或 soak 不创建、不提升也不代填 Prod `EnvironmentAcceptanceFact`，也不生成 terminal `ReleaseEvidenceManifest`；任何 `ReleaseEvidenceManifest` 只允许作为显式 legacy historical/non-promotable history/rehearsal diagnostic snapshot 只读保留，formal J0/J1/J2、`ProdActivationAdmissionFact` admission 与 rollout materialization 均必须拒绝，且不能称为候选或正式发布输入。
- AND legacy snapshot、aggregate verdict、旧 receipt、latest 查询或值等价复制对象提交给 J0/J1/J2 projector 或 `ProdActivationAdmissionFact` admission 时均被拒绝；只有 canonical fact exact bytes 可以满足对应视图。

<a id="gwt-007"></a>
### GWT-007 Alpha 离线可用与在线完整切换不混权威

- GIVEN 同一 canonical cohort 有许可完备、含完整媒体的制品绑定快照和在线 candidate，四环境使用同一 typed ports 与页面。
- WHEN Alpha 在无后端、断网、无缓存首装后经各默认入口浏览，或在线环境准备、切换、回读与回滚内容。
- THEN Alpha 各入口通过独立 signed offline document 的同一 activation/CAS/read chain 读取同一快照，在在线配置 24 小时到期前、恰到期及之后仍可浏览推荐 items、premium、详情和播放/seek；坏签名/摘要或缺媒体阻断制品/激活并保留已验证旧快照，不忽略在线 expiry、不造 HTTPS 或 server active identity。
- THEN 同 cohort 的离线/Remote 参数化合同证明身份、过滤、详情、空态和分页边界等价；Beta/Gamma/Prod 不消费离线快照且在线签名过期仍阻断，页面不按 source/profile 分支，nonprod 同包切环境重建上下文。
- THEN 在线缺媒体、精选/必要查询未 ready 或 CAS race 保持旧版本；CAS 结果未知与 60 秒回读失败先查权威 pointer，再显式 rollback，5 分钟内恢复或明确阻断，首次无 previous 不猜旧版本；读会话和媒体不混版本。
- THEN 报告将声明库存、激活闭包、详情、推荐窗口、premium 和媒体成功分开，不可达为未知；服务 SLO 口径冲突及未测设备/生产故障域保持 OPEN，不以离线成功、首屏数量或旧 receipt 计为 Remote 健康。

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
- 目标：同一 release train 下逐 target 捕获 fresh immutable candidate/baseline，分别完成其 package、strict runtime/activation/readback 与设备证据；不同云侧 target 可并行，设备 slot 可排队。Alpha App 另按完整离线 source 验证，不能消费 Alpha API gate 的成功作为自身结果。三个 target 的环境输入和 baseline 允许且预期不同，不得把 Alpha candidate 或 baseline 复用、复制或回填给 Beta/Gamma。真实登录和 1v1 消息由其所属 Feature OPEN 独立关闭，不由 runtime 复制验收；Prod-sim 只完成打包、纯度、安装启动 readiness，Prod rollout 保持单独授权。
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
- 影响或价值：尚缺同一 canonical cohort 的 Alpha 离线与 Beta/Gamma Remote 双模拟器正向证据，以及 Beta/Gamma Remote 恢复和独立 Alpha API empty/replay 证据；离线结果不能补服务激活，单端、父 report 或旧 receipt 不能证明矩阵。
- 尚缺实现：三环境 runner 需按 target/platform/device/entry/carrier create-once slot 执行正向、受控恢复与 Alpha lifecycle drill，并让父 report 只读列举 raw refs/digests。
- 尚缺验收证据：`local_contract` 证明 slot 与父投影约束，`api_integration` 证明 empty/replay 与四入口 previous release identity，`user_acceptance` 交付六个模拟器 raw results。
- 完成判定：`GWT-004` 由二维矩阵、create-once slot 与父投影无 verdict 的 `local_contract`，真实 Alpha empty/replay lifecycle 及四入口 previous release identity readback 的 `api_integration`，以及 Alpha 离线及 Beta/Gamma Remote 六个 `user_acceptance` raw `ReadinessCaseResult` 直接覆盖。每个结果均绑定同一 source/candidate/package/safe-terminal 身份并明确 `nonPromotable=true`，且父 report 只读列举 raw refs/digests，无单环境 aggregate、独立 verdict或 promotion authority。

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
- 尚缺验收证据：`app-content-uat` 沿默认内容链产生页面 suite 的真实结果，不选择命名相位；`device_bound` 与 `content_live_passed` 均在场且 release identity 与 Data readiness 一致，环境差异只消费对应运行配置。
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
- 影响或价值：raw SDK、受管字面 flutter run、IDE 和 run.sh 的默认 Alpha 离线首装、重复冷启动与播放器尚缺同轮双端现场证据；设备选择、same-device 安全绑定、跨设备并行、PATH 可逆投影及依赖有界恢复也不能由静态 launcher 测试替代。direct 安全 lease 不提升 managed/UAT authority，离线成功不替代 Remote readiness。
- 尚缺实现：各入口统一 Alpha canonical 离线供给与完整性判定、在线严格 preflight、设备/安全 lease 独占、私有构建投影和有界依赖 stale 恢复；PATH wrapper 只薄透传，不能使 raw SDK 默认走另一 source。direct 不提升证据，managed 只清理 owned mapping，UAT retry 复用预冻结工具链。
- 尚缺验收证据：local_contract 证明入口薄适配、Alpha 离线完整性、在线 handoff 负例、依赖有界恢复、设备/租约并发；api_integration 证明真实制品安装/online activation 与一致工具链；user_acceptance 在 Android/iOS 的 raw SDK、受管字面命令、IDE 与 run.sh 无后端首装验证首页/premium/媒体及同包切环境。非法在线选择器失败，raw SDK 默认 Alpha 不应失败；自动化结果不替代 required human surfaces。
- 完成判定：[`GWT-002`](#gwt-002)、[`GWT-007`](#gwt-007) 在 raw SDK、受管字面命令、IDE 与 run.sh 默认 Alpha 上读取同一完整快照，断网/无后端首装与再次冷启动成立；设备选择、双端并行、同设备安全切换与依赖 stale 有界恢复有 fresh 证据。非法在线 handoff/选择器仍阻断，direct 安全 lease 不提升 managed/UAT authority；未测 surface 保持 OPEN。
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
### OPEN-013 EnvironmentAcceptanceFact v2 尚缺 fresh Alpha/Beta/Gamma 验收闭环

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：现役 schema/validator/scheduler 已定义 EAF v2 的 Alpha/Beta/Gamma、`smoke|integration|release`、candidate/ImpactPlan、`caseResultRefs`、八类 named evidence、predecessor、DSSE signer 与 `nonPromotable` 约束，但代码存在不等于当前 candidate 已完成验收。当前仍缺同一 source/candidate fingerprint 下逐环境 fresh `api_integration`/必要 `user_acceptance` 与完整 named evidence，因此不能把局部 contract PASS、Data readiness、父 report 或旧 receipt 当成环境准出。
- 尚缺实现：各 Alpha/Beta/Gamma execution producer 必须按 selected profile 生成 role 正确且 identity 一致的 `runtimeIdentity`、`dataLifecycle`、`providerReadiness`、`observabilityReadiness`、`inspectEvidence`、`doctorEvidence`、`cleanupEvidence` 与 `leaseClosureEvidence`，并只调用 canonical scheduler；仍提交退役 payload 的调用点必须迁移，不能由规格假定已完成。
- 尚缺验收证据：`local_contract` 需持续证明字段闭集、Beta typed no-live、release App UAT 约束、predecessor/DSSE/digest fail-closed；`api_integration` 需证明 active candidate/readback、各 named role 与 cleanup/lease 独立闭合；受影响 `release` profile 还需 fresh App `user_acceptance` raw results。
- 完成判定：[`GWT-006.t1`](#gwt-006) 至 [`GWT-006.t12`](#gwt-006) 逐条由职责匹配的 current local_contract/api_integration 或必要 user_acceptance 绑定并实际通过；同一 exact candidate 的 Alpha EAF 以 null predecessor 创建，Beta（或 typed no-live）与 Gamma 分别 exact-byte 绑定前一环境同 profile/candidate/ImpactPlan/`nonPromotable` fact，全部 refs 可重验且 Gamma 被 `IntegrationQualificationFact` 消费。Production release facts 不属于此 OPEN，也不得代填 Alpha/Beta/Gamma 环境事实。

<a id="open-014"></a>
### OPEN-014 RC 最终包物理接受与生产授权证据尚未闭环

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前尚缺 RC 最终签名包的双物理平台接受证据。Alpha/Beta/Gamma Simulator/Emulator evidence 只能证明本地 rehearsal 并保持 `nonPromotable`；它不能证明 RC 最终签名 App package 已在 Android physical device 与 iPhone 上安装、启动和完成 required UAT。该物理接受属于 RC `QualificationFact`，不属于环境 EAF 或 Prod stage。
- 尚缺实现：RC qualification 执行面需从同一 build-once final material create-once 产出 package acceptance 与 UAT facts，逐项绑定最终 artifact digest、签名、platform、registered device 与 canonical raw `ReadinessCaseResult`，再由 `QualificationFact` exact 引用；不得新增 EAF profile或第二种 CaseResult。
- 尚缺验收证据：`local_contract` 证明模拟器不可升级、两类执行共用 canonical raw outcome 且 qualification 缺任一 physical platform 时 fail closed；`api_integration` 证明 request/material/package acceptance/UAT/supply-chain exact binding；`user_acceptance` 交付同一 RC 最终签名包的 Android+iOS physical-device fresh raw results。
- 完成判定：[`GWT-005.t1`](#gwt-005) 至 [`GWT-005.t8`](#gwt-005) 逐条由职责匹配的 current local_contract/api_integration/user_acceptance 绑定并实际通过；RC `QualificationFact` 对同一 material exact 绑定 passed package acceptance、Provider、UAT 与 supply-chain facts，package acceptance 明确覆盖 Android/iOS 两个 physical platforms；随后 stable `ReleaseTagAdmissionFact` 与 `ProdActivationAdmissionFact` 复用相同 build number/digests。任何缺失、failed、blocked、skipped 或模拟器替代均保持 `GATE_BLOCK`，不向 EAF v2 追加 production environment。

<a id="open-015"></a>
### OPEN-015 二维 UAT 与 lifecycle 尚缺 fresh Alpha/Beta/Gamma 实证

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：二维 `entry × carrier` 语义已区分 feed/search/recommendation/direct_or_object_route 与 homepage/article/image/video，并冻结 required cell、`no_active_release`/empty/deleted 与 rollback/replay identity 边界；但当前仍缺与现役 EAF v2 candidate/profile 对齐的 fresh `api_integration`/`user_acceptance`。required cells 未全部形成 current raw results，Alpha lifecycle drill 也未逐 entry 证明回到 previous release identity，因此本 OPEN 继续 `GATE_BLOCK`。
- 尚缺实现：Alpha/Beta/Gamma runner 需让每个 required slot 以 canonical `ReadinessCaseResult` create-once 落盘，并把 selected profile 所需结果作为 EAF v2 `caseResultRefs`；父投影只列 refs/digests/coverage/gap。Alpha `no_active_release` drill 必须与正常 active-release suite 隔离并在 `finally` 恢复 previous release。
- 尚缺验收证据：`local_contract` 需持续覆盖 required/not_applicable 全矩阵、entry/carrier 混用与 deleted 误标；`api_integration` 需对 Alpha empty baseline、same-digest replay 和四 entry previous identity readback 取证；`user_acceptance` 需按受影响 profile 为 Alpha/Beta/Gamma required cells 逐项生成 fresh raw result。Simulator/Emulator 结论保持 `nonPromotable`，RC physical package acceptance 由 [`OPEN-014`](#open-014) 独立承接。
- 完成判定：[`GWT-004`](#gwt-004) 的 rehearsal required cells 可由 raw refs 唯一定位，Alpha lifecycle drill 无 deleted 伪装且四入口 rollback/replay identity 一致；相应 EAF v2 只在 `caseResultRefs` 与全部 named evidence 同时闭合后生成。Prod rollout 不重跑本矩阵，也不向 EAF v2 追加 production environment。

<a id="open-016"></a>
### OPEN-016 Data M1 API consumer 尚未接入完整 EAF v2 闭包

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：旧 Data M1 专用 EAF writer 已不存在，这是单轨切换结果而非可恢复兼容面。当前 M1 API consumer raw results、consumer health 与 Data readiness 即使各自有效，也不能在缺少 candidate、`impactPlanDigest`、完整 named runtime/data/provider/observability/inspect/doctor/cleanup/lease evidence、predecessor 与 DSSE signer 时宣称 EAF v2 或 Data ship 通过。
- 尚缺实现：Data/Ops owner 需裁决 M1 ship 是否消费现役 EAF；若消费，只能把 API `CaseResult` 与匹配 role 的 evidence 接入 canonical scheduler，并按真实用途选择 `smoke|integration|release` 中已有 profile、补齐 v2 全部闭包。若业务无需 EAF，则由 Data owner 改为消费其自身 canonical ship authority；两种路径都不得新增 M1 profile/schema、恢复旧 builder 或保留双写。
- 尚缺验收证据：负向 `local_contract` 证明旧 writer/profile 不可用且窄 evidence 不能签发 EAF；选择 EAF 路径时，`api_integration` 需用同一 Alpha candidate 的 fresh API results 与全部 named evidence 形成可递归重验的 v2 fact，并证明缺任一 role、predecessor/signature/digest 漂移均 fail closed。
- 完成判定：[`GWT-006.t9`](#gwt-006) 与 [`GWT-006.t10`](#gwt-006) 由职责匹配的 current local_contract/api_integration 直接绑定并实际通过；Data ship consumer 只接受其已裁决的单一 canonical authority。若该 authority 为 EAF v2，则由 canonical scheduler 生成完整且可验签的 Alpha fact；若不是，则 Data owner 的 current spec 与 consumer 均不再要求 EAF。裁决和 fresh evidence 完成前保持 `GATE_BLOCK/OPEN`。

<a id="open-017"></a>
### OPEN-017 Prod 内容落地通道缺 hosted 数据面输入与媒体根

- 类型：`external_blocker`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：Alpha/Beta/Gamma 三条 `local-import` 通道同构且共享同一条 Data `ship apply → activate → verify` 链；`prod` 的 `dataReleaseTarget=prod-hosted` 声明 `hosted-import`，但四个 secret 输入 `QWQ_PROD_DATA_RELEASE_MONGO_URI` / `QWQ_PROD_DATA_RELEASE_REDIS_ADDR` / `QWQ_PROD_DATA_RELEASE_USER_POSTGRES_DSN` / `QWQ_PROD_DATA_RELEASE_MEDIA_ROOT` 在仓内没有任何供给来源（workflow、runbook、access-isolation 或受保护变量清单均未登记），hosted 侧也没有与 `start_local_gamma_mirror.sh` `prepare_media_root` 等价的公开切片媒体根准备；`quwoquan_service/services/content-service/resources/policies/content/release_readiness.yaml` 的 `phases.import` 只声明 alpha/beta/gamma，`ship apply --env prod --import` 在 `environment_readiness` 阶段即 `GATE_BLOCK`；输入齐备后 Data ship 仍会在非 dry-run 下以 `missing secret inputs` typed 拒绝。`prod-sim` 现已声明与本地三环境同形的 `local-import` 数据面，但 Data ship 只按 `dataReleaseTarget` 解析目标，`prod` 环境仍只能指向 `prod-hosted`，prod-sim 尚不能作为 prod 内容彩排目标。
- 尚缺实现：`release_readiness.yaml` 的 `phases.import` 补 `prod: {target: prod-hosted, workload: full, healthScope: content-import}`；`lane/ops` 在 `access-isolation.yaml` 或受保护变量清单登记四个 hosted 输入的供给来源与最小权限，并为 prod-hosted 提供公开切片媒体根准备与只读挂载；Data ship 若要支持 prod-sim 彩排，需在 `--env prod` 下显式选择 target 而不是隐式取 `dataReleaseTarget`。
- 尚缺验收证据：`ship apply --env prod --import --full-sync --confirm-prod-apply` 在 hosted 输入齐备时到达 `prepared`，`activate` 完成 Content CAS，`content-readiness --env prod` 通过；prod-sim 彩排以同一 immutable release 取得 `release-readiness.json`。
- 完成判定：[`GWT-001`](#gwt-001) 的 prod 打包子句与 [`GWT-004`](#gwt-004) 的同 release 语义对 prod-hosted 成立，且不得以 alpha/beta/gamma 证据或 dry-run 结果冒充 prod 内容落地。
- 依赖：hosted 凭据与媒体根由所有者提供；Prod 激活仍受 `ReleaseTagAdmissionFact` / `ProdActivationAdmissionFact` 约束，本 OPEN 不改变 promotion 边。

<a id="open-018"></a>
### OPEN-018 `stackctl matrix` 的 Data 生命周期编排与现役 ship CLI 漂移

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：`quwoquan_ops/cli/lib/local_env_gate_matrix/orchestrator.py` 的 Data 生命周期尚缺默认无类别链路的实现闭环与当前真实矩阵证据。显式准入、prepared apply、activate、verify 与 rollback CAS 前驱必须按现役 Data 契约连续绑定，不能沿用 release-id 旁路、命名 readiness 相位或以 prepared 冒充 activated 的结果。
- 尚缺实现：candidate/rollback 分别消费显式 handoff ref 或 empty-baseline system attestation；Data 阶段统一为 `apply → activate → verify`，删除命名消费轨道参数和结果字段；rollback 前从 Content active pointer 精确读取 release/digest/revision 三元组。Exit 按成功 activation/rollback 与 exact verify 对闭合，普通内容启动不强制此演练；对应 local_contract 通过现役 CLI parser 校验实际 argv。
- 尚缺验收证据：`stackctl matrix --targets alpha-local,beta-local,gamma-local` 对同一无类别 release 取得三个 target 的 `release-readiness.json` 与 `release_active` 通过，环境差异只按配置执行，rollback/replay 回到同一 release identity。
- 完成判定：[`GWT-004`](#gwt-004) 由矩阵真实运行的 raw results 绑定，而不是手工逐环境重放；不得放宽 Data CLI 准入或恢复 `--release-id` 隐式选择。
- 依赖：Data 无类别发布契约与 ship 生命周期、Ops matrix 及 readiness 消费者同步迁移（内容 owner `DEC-041` 与 runtime-config `DEC-005`）。

<a id="open-019"></a>
### OPEN-019 离线装配与无中断查询准入尚缺闭环

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：Alpha canonical 快照派生/公开离线许可/完整资产、typed adapter、四入口冷启动/媒体及在线 candidate-scoped 推荐/精选/必要查询预物化尚缺 fresh 闭环。CAS 后异步追平会 fail closed，不能写成已实现无中断切换；首次无 previous、结果未知、显式 rollback 与 exact pointer readback 必须故障注入验证。
- 完成判定：`GWT-007` 由 canonical cohort 参数化 local_contract、真实媒体/四域/query barrier/CAS/recovery api_integration 和 Android/iOS 首装离线及在线页面/播放器 user_acceptance 直接绑定；源码或局部测试不替代完整证据。
- 依赖：canonical Data producer、Content/Recommendation/Search candidate owner、App 组合根与启动 metadata；规格不新增 wire 字段，未具备 typed 契约前对应实现仍阻断。

<a id="open-020"></a>
### OPEN-020 Feed SLO 与可用性统计口径尚未收敛

- 类型：`risk`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：Content operation 的 99.9%/p95 500ms 与 recommendation observability 的 99.5%/p95 200ms 尚未由 owner 证明范围、分母、窗口及告警映射一致；不能分别挑较宽项组成绿灯。离线命中、stale、合法空、请求错误和媒体成功也不能混计。
- 完成判定：`GWT-007` 的统计结果由 Content owner 冻结唯一 canonical 指标口径，并使同范围 SLO/告警单轨派生；首刷/续页、端侧 6 秒终态与视频播放分开验收，未测目标保持未证实。
- 依赖：[`Content operations`](../../../../../quwoquan_service/services/content-service/contracts/content/post/operations.yaml) 与 [`recommendation SLO`](../../../../../quwoquan_service/services/content-service/observability/slo/recommendation_slo.yaml) 的 owner 裁决；本节点不自行放宽阈值。
