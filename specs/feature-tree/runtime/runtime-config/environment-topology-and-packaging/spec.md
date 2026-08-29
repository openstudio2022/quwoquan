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
- Android 与 iOS 可执行制品必须由 `stackctl package` 从同一只读 source capsule 按 `buildProfile(nonprod|prod)` 构建，Web 只生成一份共享 bundle；每次组件构建必须显式选择 build product，并在写 manifest 前回读包身份、签名、artifact digest 与生产纯度。AppArtifact 只携带 build-profile 级 trust envelope，不携带 target runtime config package。Alpha/Beta/Gamma 的签名 runtime config package 必须在安装后由 canonical activation 写入同一 nonprod App 的平台私有容器，不得触发重编、重签或改变完整 APK/`.app`/IPA 摘要。
- production App 的 pub/plugin/Pod/registrant/linker/filelist/SBOM 与最终 APK/AAB/IPA 可达图不得含 Patrol、integration_test、PatrolJUnitRunner、XCTest 或其他 test runner；设备 UAT 只能由物理隔离的 test host 单向依赖 production App。
- 日常与 CI 构建只消费已锁定依赖；Dart lock、Flutter plugin podspec、Podfile.lock、Pods/Manifest.lock 与 CocoaPods executable/version 任一漂移时在编译前返回 typed blocker，禁止启动路径自动 update 或联网修复。
- 显式 App 依赖同步每次只在 fresh、attempt-scoped 私有 Gradle home 内联网解析，禁止强制 refresh、跨 attempt seed 或 global cache fallback。
- 同一 invocation 只对可辨识的 TLS/connection EOF、reset、timeout、HTTP 408/429/5xx 与 Gradle wrapper 精确空下载摘要做有总时限的最多三次尝试（含首次）；证书/信任/hostname 错误、404、非空 checksum mismatch 和其他确定性失败立即返回，尝试耗尽保留首次失败。
- 每次依赖子进程必须独占 process group；单进程或总时限到达时按 TERM→短 grace→KILL 回收整个后代树后才可重试或返回。恢复成功的日志只持久化 attempt 序号、closed typed cause、backoff 与结果，不得写环境变量、trust path 或 key material。
- 在线解析成功后必须封存依赖闭包，并在另一 fresh 私有 home 完整离线重放；在线成功不得代替离线可复现性。
- CocoaPods 在线安装同样只能在本 attempt 的私有 `CP_HOME_DIR/CP_CACHE_DIR` 内对上述网络暂态做有界重试并保留已下载字节；Flutter config、确定性 Pod 解析失败与封存后的离线 Pod replay 均不得重试或联网，重试耗尽仍以首次失败为 canonical blocker。
- `prod` 只能读取 `prod` 包；禁止 `prod-gray` 环境、目录或 artifact。
- 同一环境存在多个部署 target 时，每个 target 必须写入独立 package 目录，并从环境 `urlRoles + target urlOverrides + portProfile` 的解析结果投影 App 运行时端点；禁止复制环境默认 target 的 URL 或跨 target 复用可变产物。
- `prod-hosted` artifact 禁止包含 mock/seed/debug/local/test host 与跨环境 URL；`prod-sim` 仍属于 `prod` 环境，但全部公共入口必须使用 `*.sim.quwoquan.com`，不得命中生产 host、增加第五环境或放宽 `prod-hosted` 纯度门。
- 南北向公开入口（URL role、gateway 数据流、公网 DNS、TLS profile、CDN、derived link）与东西向端口块模型由 [`system-topology-and-networking`](../../system-topology-and-networking/spec.md) 拥有；本 Story 只消费 topology resolver 投影完成打包、装配与验收，不复制组网规则。
- local environment matrix 的 `emulator_only` 设备 profile 只要求 iOS Simulator 与 Android Emulator，并且只能签发 `ALPHA_BETA_GAMMA_EMULATOR_ONLY_FUNCTIONAL_GREEN`、`nonPromotable=true` 与 Android 真机 waiver；它不得写入正式 Green Matrix、Provider 140-cell 或 Prod artifact closure。正式 `ALPHA_BETA_GAMMA_LOCAL_GREEN` 继续要求独立 Android 真机回执。
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
- commercial readiness 必须从同一 release 对象闭包投影 canonical `appUatEnvelope`，包含 homepage、article、image、video、Creator、Tag 与 attribution 的验收身份。App 自动验收不得从手工环境变量、fixture 或旧回执重建该信封。

<a id="req-003"></a>
### REQ-003 双端本地运行持有可释放 consumer lease

- `quwoquan_app/run.sh --mode content-live -d <device>` 是显式选择设备、持有 consumer lease、准备平台 transport 并验证真实首页/视频书内容的 canonical launcher，也是未指定 mode 时的默认；`--mode ui-only` 只允许调试安全 Shell 与页面布局且生成 `nonPromotable=true` 证据。IDE launch profile 可以薄包装该入口。
- `dev-session --app-mode content-live|ui-only` 与 canonical launcher 使用同一执行体且默认 `content-live`。Alpha/Beta/Gamma 的 `test_live` 是开发启动严格度：两种 App mode 都不得因服务、Provider、内容或观测 readiness 不可用而跳过真实编译、安装、activation 与启动；`ui-only` 始终标记 `nonPromotable=true`，`content-live` 还必须在启动后真实请求 Remote 内容并如实呈现成功、合法空态或 typed unavailable。
- `quwoquan_app/run.sh --mode content-live --env alpha|beta|gamma -d <device>` 是内容联调与 Hot Restart 的唯一开发启动执行体。字面 `flutter run` 与受控制的 IDE Run/Debug 是两个独立受支持的 thin command surface，必须分别薄包装并归一化进入同一执行体；工作区 `flutter` facade 只拦截本 App 的 `run` 子命令（launch provenance=`workspace_flutter_run`），IDE 薄包装使用 `workspace_ide_debug`，其余子命令与其他项目全部透传真实 Flutter SDK。未经任一 canonical handoff 的原始 Xcode/Gradle backend 不具备安装后 target config activation 能力，必须继续 fail-closed，且 typed blocker 必须只指引 `run.sh`、工作区 facade 激活入口或受控制的 IDE profile。
- 设备选择按 launch surface 分层：直接调用 `run.sh` 必须显式 `-d <device>`；`workspace_flutter_run` surface 在设备清单恰有一台可用移动设备时允许自动选择该设备，多设备时列出 canonical inventory 并要求 `-d`，不得按最近使用猜测设备。`workspace_ide_debug` 必须由 profile 的显式设备选择或同一 inventory 规则解析，不能读取 IDE 最近设备作为事实。
- 工作区 facade 与 IDE profile 必须可凭受版本控制真相源重建。首次使用只执行仓库内具名激活入口，本地编辑器配置只是可删除投影。激活后重载编辑器窗口，新建工作区终端的 `command -v flutter` 必须解析到 facade，IDE Run/Debug 必须显示并调用 canonical profile。旧终端、仓库外终端、绝对 SDK 命令与原始 Xcode/Gradle 不属于受支持正向面。未激活时唯一恢复动作是执行具名激活入口并重载窗口，不得要求修改全局 PATH、Flutter 安装或关闭 trust gate。移除投影并重载即完全回退。
- canonical launcher 固定选择 metadata 声明的 `nonprod` build profile，默认 target 为 `alpha-local`，显式环境只选择对应签名 runtime config package。它禁止选择 Prod 或直接覆盖 URL、密钥、target、manifest 与 release。
- `QWQ_ENVIRONMENT` 只允许选择 nonprod 信任域内的 runtime package，不得反向选择原生包身份或进入 Flutter 编译输入。
- `workspace_flutter_run` 与 `workspace_ide_debug` surface 没有自建的 mode 协议；run mode 与环境同构，经 `QWQ_RUN_MODE`（`content-live|ui-only`，默认 `content-live`）选择并交同一 canonical 执行体校验，IDE profile 只投影同一输入，非法值 fail closed。
- canonical Debug 必须先安装或复用同一 nonprod AppArtifact，再由 executor 写入完整 activation request、经冷启动原生 activation coordinator 把当前 topology 派生的 test-live package 原子激活到 App 私有容器，最后启动或 attach Flutter。冷启动和 Hot Restart 由原生 reader 返回 active package 与制品内 profile trust envelope，Dart 不得读取 endpoint define、环境变量或第二份 keyring。配置变化只要求重新签发和 activation，不触发 Flutter/原生重编或 AppArtifact 重签；实际 environment 只在启动握手后成立。
- App 构建不得读取或改写共享的“当前环境”文件，nonprod 组件只编译一次。
- `alpha → beta → gamma → alpha` 顺序切换只推进 target-scoped activation pointer，不得要求 clean、重试、重编或重装同一制品。
- 并发 activation 必须以 expected active digest 条件更新，不能共享可写 handoff 或相互覆盖。AppArtifact digest 与签名必须保持不变。
- `app_effective_launch_manifest` 只拥有 environment、target、endpoints 与 launch provenance，不携带任何内容 release 身份或 `contentBindingState`。内容激活是服务端运行时事实：App 冷启动后从 Content API 响应携带的 canonical release identity（`releaseId + manifestDigest`）解析当前内容身份，不得伪造 releaseId 或 receipt。`content-live` 模式与环境验收的期望 release 只写入 UAT evidence 与环境侧 readiness 回执，不烘焙进 App 制品；内容发布与回滚不要求重新打包或重新审核 App。
- canonical Debug 仅在操作者未选择环境时默认 Alpha；两个环境选择器冲突、Prod、任意 target override、过期/缺失 package、trust envelope 缺失、摘要不一致或 activation readback 失败均 fail-closed。Profile、Release 与 Prod 启动禁止隐式推断。
- Android 从 topology 推导包名、设备与全部 `adb reverse` 端口，在 Flutter 构建前获取 release-bound lease；canonical launcher 通过 `trap` 在退出时释放，裸 Debug 的 provisional lease 在 App 停止后由 liveness 判为 stale 并等待显式 GC。
- iOS Simulator 与已登记 iPhone 同源准备签名 runtime package、安装后 activation 与同一 `consumer-lease` 对象，Simulator 额外执行系统公共 CA 预检。
- iOS lease 绑定 platform、设备标识、bundle ID、target、active package digest、启动宽限期与 handoff digest，且不携带 transport ports。
- 宽限期后，Simulator 必须结合 `simctl get_app_container`、`user/<uid>` launchd 域中的 `UIKitApplication:<bundleId>` service 与 executable path 判定存活。已登记 iPhone 必须结合 `devicectl device info apps/processes` 的结构化 App URL 与 process executable 判定存活。
- 结构化状态读取失败只能保留 `active_unverified` 证据，不得代偿为已停止或已存活。
- 已验证存活的 App lease 不受 12 小时 provisional 上限影响；`consumer-lease status` 和 down/package/roll 前检查必须严格只读，不得删除 stale 文件。只有显式 `release`/GC 可以清理 lease。
- canonical launcher 固定编译 production `lib/main_prod.dart`；`lib/main.dart` 只能薄委托同一入口，不能建立裸 Flutter 启动协议。
- 所有受支持路径都连接完整 Remote topology，并由同一 activation command、native reader 与 Dart resolver 消费 active runtime package，禁止 alpha runner、fixture override 或只提供 mock/public-plane 子集的本地进程。
- Gradle/Xcode 只验证所选 `nonprod/prod` profile、build-profile trust envelope、build product 摘要与设备证明；target runtime package 不进入 build phase、bundle resource 或 assets。
- canonical Debug 只允许从 metadata/topology 构建所选 handoff、获取本平台 consumer lease并在安装后执行 activation；不得启动或修复环境、推断 URL、复制配置到源码/构建树或吞掉 activation 失败。
- Android/iOS 的 target package activation 必须验证 runtime package、制品内独立 trust envelope、build profile、target 与 effective manifest digest，并以 expected active digest 原子更新私有容器。缺一或 readback 不一致即在进入业务 Shell 前 `GATE_BLOCK`，失败时保留上一 active digest；endpoint、environment 和 runtime config 摘要不得进入 `DART_DEFINES`。
- 已激活旧 package 的时间窗（`expiresAt`）过期只使消费读取 fail-closed，不得阻断以其身份为 expected active digest 的下一次替换激活：activation 流程读取 CAS 前值时仍必须验证 trust envelope、签名与结构完整性，仅豁免时间窗判定；该豁免不得扩展到冷启动/Hot Restart 的 native reader 消费路径，也不得放松对新 package 自身的 freshness 校验。过期即死锁、要求删除重装才能恢复的实现是违约。
- active receipt schema 新增必填观测字段时，不得让已安装旧 App 永久死锁或要求卸载/清数据。当前迁移只允许在下一次 activation 的 CAS 前值读取阶段接受“精确等于当前 receipt 字段集减去 `launchProvenance`、`runtimeConfigSupplyMode`”的上一版 canonical receipt。它必须是 `activated`、摘要字段合法、`activePackageDigest=packageDigest`、环境/target/buildProfile 自洽且无 error/validation issue，且唯一输出是 `expectedActiveDigest`。同字段集的上一版 launch receipt 只允许作为等待原生用当前 schema 原子替换的 stale 文件被忽略，绝不构成本次 request 的成功证据。上一版 receipt 不得进入 cold start、Hot Restart、Dart/runtime readback 或成功证据。新 activation 仍须完整验证新 package 并由原生以当前 schema 原子覆盖 active receipt。任意额外缺字段、额外字段、非 canonical JSON 或身份/摘要不自洽都 fail-closed。不存在仍可生成上一版 receipt 的受支持 artifact 且设备基线证明迁移完成后必须删除该单代迁移读口。
- Alpha/Beta/Gamma 的 `test_live` 中，无论选择 `ui-only` 还是 `content-live`，runtime/startup/service/Provider/TLS/transport/content readiness 不健康、startup receipt 缺失、active candidate 过期及 source/config/generated digest 漂移都只形成结构化 warning，不得使 Xcode/Gradle build phase 失败或跳过真实编译、安装、activation 与启动。任一 warning 必须使最终 launch report 和 runtime health 保持 `degraded`，不得提升为 `healthy`。`content-live` 启动后必须真实请求 Remote 内容；依赖不可用时只能到达 canonical `no_active_release`、typed unavailable 或 `runtime_degraded`，不得伪造首页成功。依赖解析、身份/信任、最小 handoff/runtime package 生成、真实编译、设备选择、target 冲突、命名空间逃逸、Prod endpoint/credential 泄露与不安全 secret 始终硬阻断。
- `app-debug-preflight` 必须显式选择 `test_live` 或 `immutable_candidate`，不得以默认 mode 替调用方决定严格度。receipt 的 `details` 只记录安全编译/启动 blocker，`warnings` 只记录 test-live readiness 诊断。`gate_block` 对应非零退出，`warning|passed` 对应零退出；preflight 的零退出只允许继续构建，不等于 runtime healthy 或 UAT passed，平台启动器不得重新解释同一事实的严重级别。
- `test_live` 中缺失、停止、过期或漂移的 runtime/startup/service/Provider/TLS/transport lease/content readiness 与本地容量诊断必须保留完整脱敏 warning 并继续构建；它们不得被重新分类为 identity/security blocker。非法环境/target、环境命名空间逃逸、显式 handoff 冲突或不完整、无法生成 canonical runtime package/native manifest、build-profile trust 缺失或不一致、工具链/真实编译失败与不可用设备仍阻断。`immutable_candidate`、严格 health/verify、内容 UAT 与 Prod 不复用该降级。
- App launcher 不拥有环境生命周期，默认不得隐式执行 `stackctl up/down/repair`，只可调用只读 `stackctl app-debug-preflight/status`。
- 只有操作者显式传入 `--ensure-runtime` 时，`content-live` 才可委托 `stackctl` 启动当前已选 immutable candidate，且不得执行 package、repair 或重选 release。
- `ui-only` 与 `content-live` 的 `test_live` 预检都以 `warning` + exit 0 报告服务、Provider、内容、观测、容量与漂移问题。`content-live` 不得把 warning 重新解释为内容可用，而是在真实启动后的 Remote 请求中产生可观察 outcome；warning 运行的最终健康度只能是 `degraded`。只有零 warning 的 `immutable_candidate`、内容 UAT 与 Prod readiness 才能消费严格 delivery 结果。
- direct Debug 与 canonical launcher 在安装前必须调用 `stackctl app-debug-preflight`。Alpha/Beta/Gamma test-live 只校验安全环境选择与最小 handoff并收集运行时诊断，不委托商业 `app-content-preflight`；Prod release 启动继续验证 immutable candidate、必要服务/Provider，并委托 `app-content-preflight` 绑定 commercial readiness、rollback/replay、首页/视频书、Creator 与媒体证据。
- 所有启动入口必须写同一 `app-launch-attempt` receipt，并等待最长 15 分钟直到真实达到 `launched`、`runtime_degraded` 或产生首个 typed failure。PID 存活、进程已创建、1.5 秒未退出与 Flutter VM attach 都不是成功。只有本次已安装 `artifactDigest` 发出的 canonical `startup_safe_terminal` 与本次 launch attempt 关联，且回执持久化非空 `startupTerminalAttemptId + startupTerminalEvidenceDigest + startupTerminalEvidenceRef` 后才能标记 `launched`；任一 warning 只能到达 `runtime_degraded`。编译、安装或启动失败分别使用 canonical typed blocker，正常 Ctrl-C 记为 `stopped`。
- Android `prod-sim` 只安装并启动 exact Release artifact；Flutter 不支持 iOS AOT Release/Profile simulator，故 iOS Release 基础编译生成 unsigned iphoneos `.app`，Simulator 只允许 non-promotable Debug 启动且不得冒充 Release/Prod 证据。`prod-hosted` 只消费已签名 artifact、manifest、安装回执和严格 readiness，禁止 `flutter run`、Debug 或未经授权的真实 rollout。
- 每次 Dart isolate 启动必须先生成新 `attemptId`，再调用原生 `beginStartupAttempt(attemptId)`。原生返回 `attemptKind=cold|hotRestart`、`processElapsedMs`、`attemptElapsedMs` 与 `deadlineOrigin=nativeProcess|dartHotRestart`。
- `startup_attempt_started` 只能在 native runtime package 已水合且 `configurationState=complete` 后发送；Cold Start 的 6 秒预算可使用进程时钟，Hot Restart 只能使用本次 attempt 时钟。进程总存活时间只作诊断，不得写入 `welcomeExitMs` 或消耗 Hot Restart 预算。
- `stackctl app-content-uat` 必须在唯一 environment operation owner 已完成同一 `releaseTrainId`、逐 target 精确 baseline 与同一 release activation 后，顺序对 Alpha、Beta、Gamma 执行上述严格预检、canonical `run.sh`/工作区 facade 启动、首页 Feed、`environment_app_core_readback` 与视频播放 Patrol。严格预检和 launch report 都必须零 warning，任一 warning 立即阻断本 target 页面 suite。
- 每个 target 的页面 suite 前必须解析 fresh active candidate，并校验 manifest 的 `candidateDigest`、`packageDigest` 与只读 input capsule。runner 只能把该 capsule 复制到 attempt-scoped 私有 writable projection 后从 projection build/launch，不得从 live `APP_DIR` 取源码；复制前后 tree digest 漂移即返回首个 typed blocker。
- 每个 target 的页面 suite 必须新建并消费紧邻的同 target、platform、device、immutable source capsule、application ID、runtime package 与 trust envelope 的 canonical launch report 和 `app-launch-attempt`。Android 不得跳过 canonical launcher，iOS 工作区字面 `flutter run` 必须由 facade 进入同一执行体。
- 只有 attempt 真实完成 compiled、installed、configured，并由本次已安装 APK/`.app` 的同一 `artifactDigest` 产生关联 startup safe terminal 后才可进入页面 suite。VM attach 只记观测，不得替代 safe terminal；回执必须含非空 `startupTerminalAttemptId + startupTerminalEvidenceDigest + startupTerminalEvidenceRef`。
- 页面 suite 必须从自动化实际安装并启动的 App 读取 `testedAppArtifactBinding`，并把其 `applicationId`、`artifactDigest`、`sourceProjectionDigest`、`runtimeConfigPackageDigest`、`trustDigest` 与 `launchAttemptId` 逐字段绑定到同 target canonical launch。test host 自身的包名或制品摘要、从 canonical report 复制的 comparison 字段以及缺少安装/启动 readback provenance 的报告都不能证明实际受测 AppArtifact；任一字段缺失、来源非法或不一致时必须以 canonical `APP.UAT.page_artifact_binding_missing` 作为首个 blocker，停止该 target 页面 suite 且不得生成页面通过结果。
- 聚合回执必须逐 target 写入 `launchAttemptId`、launch provenance、artifact/trust/attempt digest、`candidateDigest`、`packageDigest`、`startupTerminalAttemptId`、`startupTerminalEvidenceDigest` 与 `startupTerminalEvidenceRef`，并写入非空 `releaseTrainId` 与 `packageBaselines[target]`。每个 UAT runtime binding 的 `candidateDigest` 必须等于对应 startup receipt 和 target baseline，launch source 必须等于该 binding 的 immutable source capsule。回执不得保留空 scalar、从 Alpha 取值代替其他 target，或接受上一代 UAT。
- 自动验收在整个执行窗口持有 runtime-use lock；任一 target 失败即停止并输出首个 typed blocker 和可机读 receipt。禁止以 dry-run、旧 receipt 或单环境成功替代三环境结论。
- 自动验收必须在每个 target 的正向内容读回之后执行受控 API Edge 故障窗口：故障控制器只可操作当前 runtime receipt 绑定的 Compose project 与精确容器，App 必须在同一次安装中呈现与已确认原因匹配的唯一用户恢复动作；控制器恢复原容器并重新通过健康检查后，App 点击该动作必须无需重装即可恢复 release-bound 首页内容。任一步骤异常都必须在 `finally` 恢复环境并使验收失败，禁止遗留人为故障或以本地 double 替代。
- 活跃 lease 存在时，`stackctl down`、环境矩阵强制清理和端口强制回收必须 `GATE_BLOCK`。

<a id="req-004"></a>
### REQ-004 所有有效构建、安装与启动路径行为等价

- 有效路径集合固定为：canonical launcher `run.sh`（content-live/ui-only/Hot Restart，launch provenance=`canonical_launcher`）、受控制 IDE profile（`workspace_ide_debug`）、经工作区 facade 归一化进入同一执行体的字面 `flutter run`（`workspace_flutter_run`）、`stackctl package` 产物 Debug 安装到 Simulator/Emulator/登记设备并由 canonical activation 后点击图标、Android `prod-sim` exact Release、Android/iOS `prod-hosted` Release、应用市场 Release 安装（Apple App Store/TestFlight、华为、小米、OPPO、vivo、应用宝）、官网签名 APK 安装，以及上述任一渠道的同包名覆盖升级。未经 facade/canonical handoff 的原始 Xcode/Gradle backend 调用不属于有效路径；iOS Simulator 只允许 non-promotable Debug，不属于 Release 安装路径。
- 等价定义：同一环境与同一服务端状态下，各路径的规范化行为指纹一致——配置完成态、首个安全终态、路由/登录态、内容 outcome 与 release identity、恢复动作均相同，且无 fatal recovery 差异。BuildMode、launch provenance 与 install channel 只允许作为观测事实记录，不得参与业务分支。本条与上条是有效路径集合与等价指纹定义的唯一 owner，AppRoot 与其他节点只引用不复制。
- 每类安装渠道产出独立、按 store/device/build 追加的 install receipt。应用市场渠道的准出证据必须来自真实市场客户端下载安装与安装后冷启动 telemetry 回读，官网 APK 渠道必须来自官网下载对象的 SHA-256/签名/包名比对与安装后启动回读。package-only 编译、side-load 或另一渠道回执不得互相替代。
- Debug 签名制品仅限开发者本机、Simulator/Emulator 与已登记设备，不进入 TestFlight、任何应用市场或官网公开下载；市场与官网只接受 Release 签名制品。
- 每个渠道的验收 CaseResult 声明自动化分级：CI 全自动、设备实验室定期自动、或人工执行加机器回执；人工动作缺机器回执时按失败处理。

<a id="req-005"></a>
### REQ-005 Alpha/Beta/Gamma 双模拟器只交 target-scoped 原始 CaseResult

- Alpha、Beta、Gamma 内容验收的正向窗口必须让 Android Emulator 与 iOS Simulator 对同一 `releaseId + manifestDigest + sourceIdentitySetDigest` 分别生成原始 CaseResult，并覆盖 [`AppRoot UAT-001`](../../../spec.md#uat-001) 的内容、Creator、搜索和可恢复终态，以及 [`UAT-003`](../../../spec.md#uat-003) 的同状态、同内容 identity 与同恢复动作。
- `stackctl app-content-uat --targets alpha-local,beta-local,gamma-local` 按冻结顺序编排三个 target。每个平台结果和父 report 都必须声明 `nonPromotable=true`；父 report 不得生成单环境 aggregate、canonical matrix passed 或 promotion 事实。
- `no_active_release` 只作为 Alpha 独有的独立 lifecycle drill：在 active-release suite 外保存原 active release 与 readback，通过正式环境命令应用已核验 empty baseline，依次取得两端 `outcome=empty + emptyReason=no_active_release` CaseResult，再 same-digest replay 原 release并复核 lifecycle/readback。任一步中断都必须先恢复原 release；该 drill 不代替 Beta/Gamma 正向与恢复结果，也不能单独关闭三环境矩阵。
- `CONTROLLED_EDGE_RECOVERY_UAT_TEST_TARGET` 必须分别进入 Alpha、Beta、Gamma suite。每次故障控制只操作当前 target runtime receipt 绑定的精确 API Edge 容器，App 显示唯一重试动作；`finally` 恢复容器并通过 health 后，同一安装点击重试必须重新读取原 release。
- 网络不可用显示 typed unavailable 与唯一重试，恢复网络后在原页续接同一 release；白名单或身份权限拒绝只提供重新登录或返回安全 Shell，登录成功沿用 canonical AuthContinuation，取消不循环。
- 新账号或无历史用户不形成第二套 feed：有 active release 时读取同一 public/research projection，无 active release 时进入同一 canonical 空态。相机与 RTC 不参与本验收。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

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
### GWT-002 Android 与 iOS App 会话保护本地运行时

- GIVEN 开发者通过 `quwoquan_app/run.sh --mode content-live|ui-only --env alpha|beta|gamma -d <device>`、受版本控制的 IDE 薄包装入口（`workspace_ide_debug`），或在完成具名激活并重载后的新工作区终端执行字面 `flutter run`（facade 归一化为同一执行体，launch provenance=`workspace_flutter_run`，`QWQ_ENVIRONMENT=beta|gamma` 显式选择环境），在未显式选择环境时默认 Alpha，并由 launcher 生成 canonical handoff 与待激活 package。
- WHEN Flutter 构建、运行、正常退出或异常退出，或并行环境任务尝试 down/强制清理。
- THEN Android lease 在构建前绑定设备、包名、release handoff 与 topology 端口。
- AND canonical launcher 退出时由 trap 释放 Android lease；异常中断后的 lease 由 App 进程 liveness 判为 stale 并等待显式 GC。
- AND iOS Simulator 与已登记 iPhone 在构建前获取同一 schema 的 lease，绑定 platform、设备、bundle ID、target 与空 transport ports，并在启动 executor 前将同一 lease 绑定最终 handoff digest；Simulator 通过 user launchd application service 与安装容器 executable 保活，已登记 iPhone 通过 `devicectl` 结构化 App URL 与 process executable 保活。
- AND consumer lease 的只读状态检查不删除 stale lease。
- AND 本地 Alpha 与 Beta/Gamma/Prod 使用同一 production Remote composition；首页、视频与 Creator 由已激活 release 提供，消息和我的主页由真实身份经领域公开 command/event 形成并由真实服务 query 提供，启动器和 UAT 不得隐式切入 Mock、fixture 或残缺 public plane。
- AND target/env 冲突、Prod endpoint/credential 泄露、身份/信任、最小 runtime package、真实编译或 runtime package activation 失败时 App 在进入业务 Shell 前失败；Alpha/Beta/Gamma `test_live` 的两种 App mode 对服务、Provider、内容与观测 readiness 只记录 warning，`content-live` 在启动后以真实 Remote outcome 区分可用、合法空态和 typed unavailable。`immutable_candidate`、内容 UAT 与 Prod readiness 对这些依赖继续严格阻断。
- AND 启动回执按 prepared、compiling、compiled、installing、installed、configuring、configured、launching、launched 单向推进；VM attach 只作为 launching 阶段观测。只有同一已安装 `artifactDigest` 的 canonical startup safe terminal 回写 `startupTerminalAttemptId + startupTerminalEvidenceDigest + startupTerminalEvidenceRef` 后才可出现 launched，编译、安装或 activation 失败不得出现 launched，父入口只消费该回执而不自行解释 PID。
- AND 原生 activation 与 runtime config channel 的可见错误码全部来自 `app_launch_manifest.yaml` 的 `runtime_config_error_codes` 闭集。
- AND active receipt 的缺失、读取失败与解码失败分别使用 receipt 语义错误码，不复用 activation request 语义；成功 receipt 必须持久回读已验证的 `launchProvenance` 与 `runtimeConfigSupplyMode`，进程重启后不得硬编码、从环境推断或另建无 schema 状态文件。
- AND 记录 failed receipt 时 active digest 读取失败保持最后已知 CAS 值，以 `runtime_config_activation_rollback_failed` 追加标记状态未知，不覆盖原始失败码。
- AND recovery context 对 active package 缺席与读取失败分流，读取失败携带登记错误码而不吞错为空上下文。
- AND Android/iOS canonical Debug 与 Hot Restart 使用同一 handoff、制品内 trust envelope 和平台私有容器 active package；环境、target、build profile、package digest 与 trust digest 保持一致后才进入安全 Shell，且这些运行时值不进入 Flutter 编译输入。
- AND Android/iOS nonprod AppArtifact 仅构建和签名一次；默认 Alpha 与显式 Alpha/Beta/Gamma 的启动都复用同一完整 APK/`.app` digest，并分别原子激活匹配 target 的签名 runtime config。`alpha → beta → gamma → alpha` 不依赖 clean、重装、共享文件刷新、重试、重编或重签，并发 activation 不互相覆盖 active pointer。
- AND 冷启动和连续 Hot Restart 均先完成 `beginStartupAttempt`，再以 `configurationState=complete` 发送 attempt 事件；Hot Restart 的 `welcomeExitMs` 始终相对本次 attempt 且不超过 6000ms。
- AND 环境无激活内容 release 时 App 只接受 canonical `outcome=empty + emptyReason=no_active_release` 或 typed unavailable，不以普通空列表冒充成功；环境已激活 release 时 App 从 Content API 响应解析 `releaseId + manifestDigest`，UAT 以环境侧期望 release 比对读回身份，App 制品不内嵌内容身份。Prod 发布准出仍绑定 active candidate、commercial readiness 与 rollback/replay 的环境侧证据，任一缺失均阻断准出，但不改变 App 运行时行为。
- AND `stackctl app-content-uat` 只有在 Alpha/Beta/Gamma 的 `environmentArtifact.releaseTrainId` 相同、`packageBaselines[target]` 分别精确等于各自 manifest/sourceCapsule/startup candidate，并且每个 target 从 active candidate 私有 projection 产生零 warning 的 canonical launch report/attempt 时，才可聚合为 passed receipt。该回执必须与同一 target、platform、device、immutable source capsule、application ID、runtime package、trust envelope及真实安装 AppArtifact 摘要完全一致，并逐 target 持久化 launch attempt/provenance/artifact/trust/attempt digest、`candidateDigest`、`packageDigest`、`startupTerminalAttemptId`、`startupTerminalEvidenceDigest` 与 `startupTerminalEvidenceRef`。Android 不得绕过 launcher，故障控制只作用于 runtime receipt 绑定的精确容器且始终恢复，任何 target 失败时保留已有证据并停止后续 App 执行。
- AND 字面 `flutter run` 经 facade 单轨解析仓库钉定的真实 Flutter SDK（拒绝 facade 自递归、错误 SDK 版本与 PATH 漂移），非 `run` 子命令与其他 Flutter 项目全部透传；launch surface 枚举值与 `app_artifact_manifest.yaml` 的 `launch_provenances` 闭集保持一致，任何启动脚本不得自持第二份枚举副本。
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
### GWT-004 Alpha/Beta/Gamma 双模拟器正向与受控恢复保持同一 release

- GIVEN Alpha、Beta、Gamma 已激活同一份可形成完整 `appUatEnvelope` 的 immutable release，每个 target 的 Android Emulator 与 iOS Simulator 均可运行 production Remote composition。
- WHEN 三个 target 的两端依次执行正向内容窗口与 suite 内受控 API Edge 5xx 恢复，并另外在 Alpha 执行独立 empty-baseline drill。
- THEN 三个 target 的两端分别交出绑定同一 release、source capsule、`candidateDigest`、`packageDigest`、真实安装 AppArtifact、launch attempt 与 safe terminal 的原始 CaseResult。父 report 不产生单环境 aggregate 或 promotion passed，所有结论均为 `nonPromotable=true`。
- THEN 页面 runner 逐平台验证自动化实际安装并启动的 `testedAppArtifactBinding` 与同 target canonical launch 的六项身份；缺字段、伪造 comparison、非法 provenance 或任一不一致均输出 `APP.UAT.page_artifact_binding_missing` 并停止，不得以 test host 的自身制品或 canonical launch 的复制字段冒充页面已测试生产 AppArtifact。
- THEN Alpha 空态 drill 保存原 active release、应用 empty baseline、取得两端 `no_active_release` 结果并 same-digest replay 原 release。任一中断先恢复，恢复失败即停止；该结果不得替代 Beta/Gamma 正向或 5xx 恢复 CaseResult。
- THEN 每个 target 的受控 Edge 故障都在 `finally` 恢复精确容器并通过 health，同一安装点击唯一重试后重新看到原 release。
- THEN 精选池为空的环境以 `apply` 产出的导入报告为唯一输入完成首次激活，绑定收据记为 `release_import` 且不声明 verify 运行；池中已有条目的环境不接受该路径，其变更只认 consumer 档收据。

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
- 完成判定：`GWT-001` 的四环境 App/Service/activation 重建矩阵与 `GWT-002` 的 Android/iOS 会话保护、test-live 告警及 Prod fail-closed 矩阵全部通过，且真实测试以子句级 `spec_ref` 绑定一份聚合 ResultBundle；该 ResultBundle 必须证明 Alpha/Beta/Gamma 的 `environmentArtifact.releaseTrainId` 相同，并逐 target 绑定各自 fresh candidate manifest、source capsule、`candidateDigest`、`packageDigest` 与 `packageBaselines[target]`，不得声称三环境共用一份 candidate。

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
- 影响或价值：当前尚无同一 release train 下 Alpha/Beta/Gamma 各自 Android Emulator 与 iOS Simulator 的正向和受控 5xx 恢复原始 CaseResult，也没有与这些结果同轮的 Alpha `no_active_release` lifecycle drill。Alpha 单端、Alpha-only 父 report或旧 receipt 都不能作为三环境完成证据。
- 完成判定：`GWT-004` 由三环境 suite plan/result 的 `local_contract`、真实 Alpha empty/replay lifecycle readback 的 `api_integration` 与六个 production Remote `user_acceptance` 原始 CaseResult 直接覆盖。每个结果均绑定同一 source/candidate/package/safe-terminal 身份并明确 `nonPromotable=true`，且父 report 无单环境 aggregate 或 promotion passed。

<a id="open-005"></a>
### OPEN-005 设备相关 launch blocker 的行为断言

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：当前 `app_launch_manifest` 已登记全部 launch blocker，`APP.LAUNCH.compile_failed`、`install_failed`、`launch_failed`、`prod_debug_forbidden`、`prod_artifact_required`、`prod_artifact_invalid`、`prod_hosted_flutter_forbidden`、`receipt_timeout` 已有行为断言；`device_unavailable`、`platform_unsupported` 只在 `run_app_instance.sh` 的设备发现路径抛出，`receipt_invalid` 只在 launcher 完整跑完一次后由 test_live 报告段抛出，三者当前只有枚举集合断言，没有行为断言。
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
- 完成判定：codegen 按各 buildProfile 的 `distribution_class.build_modes` 求交后产出 xcconfig，`GWT-002` 绑定的 iOS 身份矩阵契约同时断言 project/Podfile/scheme 三处无引用且这两份 xcconfig 不再生成；生成清单随之收敛。
- 依赖：Go codegen 与其 local_contract，属 iOS 构建身份矩阵面。

<a id="open-007"></a>
### OPEN-007 Patrol UAT test host 与生产 runtime config 供给栈尚无双端闭环证据

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚未形成 Android/iOS test host 复用生产原生读取面、trust 嵌入与 host application id activation 编排的双端证据。当前 Patrol CLI 实际运行 `com.quwoquan.testhost.patrol`，只能回读 test host 自身的 `applicationId + artifactDigest`，不能证明生产 AppArtifact 的 `sourceProjectionDigest + runtimeConfigPackageDigest + trustDigest + launchAttemptId`；因此严格页面验收必须返回 `APP.UAT.page_artifact_binding_missing`，不得以 canonical comparison 回填或源码存在冒充完成。
- 尚缺闭环：确认 test host 与生产 App 只共享一套生成契约和平台 I/O 实现，没有手写错误码、字段、target 或 launch provenance 副本；从干净受版本控制输入重建双端 host，分别完成 trust 校验、安装后 activation、启动与 release identity readback。
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
### OPEN-010 三类开发启动面与 test_live 严格度尚未形成真实双端证据

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚未形成 `run.sh`、新工作区终端字面 `flutter run` 与受控制 IDE Run/Debug 三个独立正向面的双端证据。IDE profile 不存在，未激活终端仍解析到真实 SDK，Android 原始 Gradle 缺 trust 还可能产出制品；test_live 旧实现又会因内容 readiness 在真实编译前退出，导致局部契约通过但用户仍无法启动。
- 完成判定：[`GWT-002`](#gwt-002) 在三个开发启动面及 raw backend 负向面逐项成立：从受版本控制输入重建激活投影后，三个正向面在 Android/iOS 各完成同 attempt 的 compile、install、activation、launch/attach；服务、Provider、内容或观测不可用只产生 warning 和真实 runtime outcome。绝对 SDK、原始 Xcode 与原始 Gradle 缺 trust 均在构建期输出首个 typed blocker，且 blocker 指向唯一恢复动作。
- 依赖：本节点启动设计、`app_artifact_manifest.yaml` / `app_launch_manifest.yaml` 与平台 build gate。

<a id="open-011"></a>
### OPEN-011 启动 metadata 消费者仍持有手写协议副本

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：仍存在 Swift、Java/Kotlin、Python、Shell 与 facade 各自复制启动字段、错误码、target map、状态或 launch provenance 的缺口，且 iOS 错误分支已少于 canonical metadata。继续逐文件修补会让同类启动问题反复出现。
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
