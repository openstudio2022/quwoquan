# L3 Story：环境拓扑与打包 (`environment-topology-and-packaging`)

> 所属能力：[`runtime-config`](../spec.md)

> Journey / Scenario：[`JNY-002 / SCN-005`](../../../spec.md#scn-005)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

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

- 受支持环境必须在各自 `runtime.yaml` 声明完整 `edge / media / service / data` 子网与结构化 `urlRoles`。

<a id="req-002"></a>
### REQ-002 各环境 runtime.yaml 声明完整网络与公开入口

- 受支持环境必须在各自 `runtime.yaml` 声明完整 `edge / media / service / data` 子网与结构化 `urlRoles`；`publicBases` 只能由 target resolver 生成。
- `alpha` 与其他环境使用同一 Remote composition/schema/网络平面，只能在容量、endpoint、访问控制、数据 release 和第三方 sandbox 策略上差异化。
- 本地 host 端口必须来自 1000 端口块 + plane + 10 端口槽位模型，canonical 端口以 `0` 结尾。
- App / Service env package 都必须携带 canonical unversioned schema identity、artifact policy 摘要与机器可读报告。
- App 产品支持面固定为 Android、iOS 与 Web；未持有平台工程、包身份、签名和真实安装启动证据的平台不得进入 metadata、schema、CI 或发布矩阵。
- Android、iOS 与 Web 制品必须由 `stackctl package` 从同一只读 source capsule 分环境生成；Android/iOS 每次构建必须显式选择与 environment 同名的 flavor/scheme，并在写 manifest 前回读包身份、签名、effective launch digest 与生产纯度。
- production App 的 pub/plugin/Pod/registrant/linker/filelist/SBOM 与最终 APK/AAB/IPA 可达图不得含 Patrol、integration_test、PatrolJUnitRunner、XCTest 或其他 test runner；设备 UAT 只能由物理隔离的 test host 单向依赖 production App。
- 日常与 CI 构建只消费已锁定依赖；Dart lock、Flutter plugin podspec、Podfile.lock、Pods/Manifest.lock 与 CocoaPods executable/version 任一漂移时在编译前返回 typed blocker，禁止启动路径自动 update 或联网修复。
- `prod` 只能读取 `prod` 包；禁止 `prod-gray` 环境、目录或 artifact。
- 同一环境存在多个部署 target 时，每个 target 必须写入独立 package 目录，并从环境 `urlRoles + target urlOverrides + portProfile` 的解析结果投影 App 运行时端点；禁止复制环境默认 target 的 URL 或跨 target 复用可变产物。
- `prod-hosted` artifact 禁止包含 mock/seed/debug/local/test host 与跨环境 URL；`prod-sim` 仍属于 `prod` 环境，但全部公共入口必须使用 `*.sim.quwoquan.com`，不得命中生产 host、增加第五环境或放宽 `prod-hosted` 纯度门。
- 每个环境的 Web、API、RTC、Ops、CDN 与 Upload 公开入口只由 `environments/<env>/runtime.yaml → stackctl target resolver → launch/artifact manifest` 这一唯一数据流生成，每级绑定上游摘要；本规格只引用 URL role（`publicWeb / api / rtc / ops / cdn / upload`）与 resolver，不复制 host、端口或 URL 字面值，任何第二份拓扑复制均为 `GATE_BLOCK`。浏览器 API 固定走同源 `/api` 反代，禁止按请求头猜测 Web/API。
- 媒体读取按 `/media/avatar|image|video` 分段挂在媒体读取 role 下；App 安装包下载固定为 CDN role 的 `/download` 路径，上传保持独立 upload role。
- `quwoquan_ops/environments/domain_governance.yaml` 登记 public、derived deep-link、OAuth callback、east-west、third-party 与 test-only URL 分类；运行时消费者只能读取 topology resolver 投影，不得再定义公开 authority。
- `domain_governance.yaml` 只拥有 URL role 的身份、分类、owner、exposure 与 consumer；各环境 `runtime.yaml` 只拥有 `scheme / host / portRole / pathBase / tlsProfile`。resolver 只合并互不重叠的字段，任何重复 ownership 必须 `GATE_BLOCK`。
- derived link 的 origin 只来自 `publicWeb` role，path 只来自 `quwoquan_service/contracts/metadata/_shared/link_templates.yaml`；user-service 使用生成的 `linktemplates.UserWebPath`，App/Data/Service 禁止再拼接 `/u/`、`/post/` 等第二份公开业务路径。
- Alpha/Beta/Gamma 本地 target 使用同一个 `local-managed` TLS profile；stackctl 从 topology 解析 SAN，在 target-scoped 仓外部署根生成叶证书、CA 与 resolver handoff，并负责受管 Simulator/Emulator 的信任安装与撤销。App、测试和脚本不得关闭证书校验、使用 `curl -k`、改写 canonical URL 或增加 localhost fallback。
- local environment matrix 的 `emulator_only` 设备 profile 只要求 iOS Simulator 与 Android Emulator，并且只能签发 `ALPHA_BETA_GAMMA_EMULATOR_ONLY_FUNCTIONAL_GREEN`、`nonPromotable=true` 与 Android 真机 waiver；它不得写入正式 Green Matrix、Provider 140-cell 或 Prod artifact closure。正式 `ALPHA_BETA_GAMMA_LOCAL_GREEN` 继续要求独立 Android 真机回执。
- `prod-sim` 仍使用 DNS-01 公共 CA，`prod-hosted` 只接受公共 CA；任何 Prod package 必须拒绝 local-managed CA、信任材料与 resolver handoff。
- 非生产 Web 产物必须 `noindex` 且保持环境访问控制；四环境分别拥有 DNS、证书、配置与发布物，不从 Prod 继承。
- `stackctl status` 是严格只读诊断：只能读取既有进程、package、receipt 与 HTTP 状态，禁止创建或刷新 secret、物化 Provider、启动服务、执行修复或改变环境事实；缺失依赖必须以失败状态返回。
- `stackctl package` 的 immutable candidate 合同用于显式内容验收与 Prod 发布。package plan 必须先派生本次实际读取的 `deploymentInputClosure`，在短 capture 窗口把 staged、unstaged、untracked 精确字节复制到 target-scoped、只读、content-addressed package input capsule，并绑定唯一 `baselineId`；capture 期间闭包变化使该次 capture fail closed 并可重试。
- capsule 不得 hardlink 回 live tree，不得跟随仓库外 symlink，且拒绝 FIFO、device 与 socket。App、Service、Ops、ContractGraph、GraphQL、OCI 与 candidate/rollback release 只能从同一 capsule 构建。长构建结束只复核 capsule manifest/tree digest、各 artifact 的同 capsule provenance 与 candidate CAS，不再比较 live workspace；capsule 封存后的任意工作区变化不影响该 candidate。已存在 candidate 只能在全部 package digest 一致时复用且禁止覆盖。
- 完整候选根 `manifest.json` 必须绑定 canonical unversioned schema identity、source/workspace/package/build input/image/runtime digest、正式规格引用，以及候选和回滚 Data release attestation。
- 每个第一方镜像的 build input 必须覆盖服务 owner 与实际编译消费的共享 runtime、generated ContractGraph binding、platform package 和 module lock，不能只散列 owner 目录。
- 当环境部署输入选择 `service-core` 时，11 个核心 Go 服务的 workload 必须由同一服务自治输入生成一个组合镜像；该镜像同时绑定 module 清单、每个 module 的源码/config/migration digest、OCI SBOM 与 provenance。组合不改变原 hostname、port、route、数据源或服务可观测 identity，Python Recommendation、Realtime、RTC 及两个 Ops 服务继续独立。
- 同一 source release train 必须在候选就绪前为 Alpha/Beta/Gamma/Prod 分别生成不可交换的环境 artifact；每份 artifact 绑定本环境 `service-core` 与五个独立服务镜像、配置、Provider binding、endpoint authority、runtime topology、SBOM/provenance 和 purity attestation。允许共享构建缓存，禁止跨环境复用最终 image digest。
- 单环境 BindingCompiler 与环境配置只从同一只读 capsule 生成 candidate-scoped 派生物，不改源码树或 capsule；封存后 live workspace 漂移不得改变当前候选。运行时 Binding API 不接受 environment 参数。
- 包内 OCI manifest 必须记录实际 image ID；`up` 只能使用该精确 ID，不能使用可漂移 tag。镜像内嵌环境 identity，`APP_ENV`、`CONFIG_VERSION` 等迁移期变量只能做相等断言，错配在 listener 前阻断，不得选择 Adapter、endpoint、数据源或策略。
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
- `dev-session --app-mode content-live|ui-only` 与 canonical launcher 使用同一执行体且默认 `content-live`；只有操作者显式选择 `ui-only` 时，test_live readiness 问题才可记为 warning 后继续真实编译、安装与启动。
- `quwoquan_app/run.sh --mode content-live --env alpha|beta|gamma -d <device>` 是内容联调入口；裸 `flutter run` 与 IDE 直接 Flutter Debug 默认选择 metadata 声明的 `alpha-local`，显式环境统一通过 `--flavor alpha|beta|gamma` 选择对应 canonical local target，禁止选择 Prod 或直接覆盖 URL、密钥、target、manifest 与 release。`QWQ_ENVIRONMENT` 只允许由 canonical wrapper 转译为同名 flavor，`APP_RUNTIME_ENV` 只校验实际 flavor 投影，不得反向选择原生包身份。
- direct Debug 必须把当前 topology 派生的 test-live runtime config 与 native manifest 交给 Dart 冷启动和 Hot Restart，不得在 App 代码中复制 Alpha endpoint。该配置记录可变摘要供诊断，但摘要变化不得阻止测试编译；实际 environment、application/bundle ID 与显示名必须在 Gradle/Xcode 解析构建图之前由静态 flavor/scheme configuration 确定。
- App 构建不得读取或改写共享的“当前环境”文件。任意前序环境后，默认 Alpha 或显式 Alpha/Beta/Gamma 的第一条构建命令必须成功；`alpha → beta → gamma → alpha` 顺序切换不得要求 clean 或重试，并发构建不得共享可写 identity 输入或输出。
- `app_effective_launch_manifest` 只拥有 environment、target、endpoints 与 launch provenance，不携带任何内容 release 身份或 `contentBindingState`。内容激活是服务端运行时事实：App 冷启动后从 Content API 响应携带的 canonical release identity（`releaseId + manifestDigest`）解析当前内容身份，不得伪造 releaseId 或 receipt。`content-live` 模式与环境验收的期望 release 只写入 UAT evidence 与环境侧 readiness 回执，不烘焙进 App 制品；内容发布与回滚不要求重新打包或重新审核 App。
- direct Debug 只允许在未显式提供 target、launch mode 或任一 digest 时，把 `APP_RUNTIME_ENV`/`QWQ_ENVIRONMENT` 当作三环境选择器并生成完整 handoff；两个选择器冲突、Prod、任意 target override、过期/缺失 manifest 或摘要不一致均 fail-closed。Profile、Release 与 Prod direct build 禁止隐式推断。
- Android 从 topology 推导包名、设备与全部 `adb reverse` 端口，在 Flutter 构建前获取 release-bound lease；canonical launcher 通过 `trap` 在退出时释放，裸 Debug 的 provisional lease 在 App 停止后由 liveness 判为 stale 并等待显式 GC。
- iOS Simulator 同源准备环境包、系统公共 CA 预检、native runtime manifest 与 provisional lease。iOS lease 绑定 platform、Simulator UDID、bundle ID、target、启动宽限期与 handoff digest；宽限期后必须结合 `simctl get_app_container`、Simulator `user/<uid>` launchd 域中的 `UIKitApplication:<bundleId>` service 与 executable path 判定前台、后台或挂起进程。
- 已验证存活的 App lease 不受 12 小时 provisional 上限影响；`consumer-lease status` 和 down/package/roll 前检查必须严格只读，不得删除 stale 文件。只有显式 `release`/GC 可以清理 lease。
- canonical launcher 固定编译 production `lib/main_prod.dart`，裸 Debug 的默认 `lib/main.dart` 只能薄委托同一入口。
- 两者都连接完整 Remote topology，并消费同一 handoff 的 runtime package，禁止 alpha runner、fixture override 或只提供 mock/public-plane 子集的本地进程。
- Gradle/Xcode 对 canonical launcher 验证其完整 runtime package、制品摘要与设备证明；对 direct Debug 只允许从 metadata/topology 构建所选 canonical handoff并获取本平台 consumer lease，不得启动或修复环境、推断 URL、复制配置或吞掉准备脚本失败。原生 build phase 只能验证已选 flavor/scheme 与 handoff 一致并写入产物内 runtime package，不得改写影响本次或下次 application/bundle identity 的源码树状态。
- iOS Profile/Release、显式非 Alpha 环境与 Beta/Gamma/Prod 均必须携带 canonical launcher 的 target、Dart defines digest、runtime config digest 与 immutable effective manifest digest，缺一即在安装前 `GATE_BLOCK`。
- Alpha/Beta/Gamma 的 `ui-only` 或裸 direct Debug 中，runtime/Provider/content 不健康、startup receipt 缺失、active candidate 过期以及 source/config/generated digest 漂移只形成结构化告警，不得使 Xcode/Gradle build phase 失败。其 Remote 内容请求必须停在 canonical `no_active_release` 或 typed unavailable，不得持续请求已知不可达服务。`content-live` 必须在构建前验证 runtime running、环境侧已激活 release 的 readiness 回执、API/Media/Search/Recommendation 可用性，任一缺失均以 typed blocker 停止。该验证只形成环境侧证据，不向 App 制品注入内容身份。依赖解析、真实编译、设备选择、target 冲突、无法生成最小 handoff、Prod endpoint/credential 泄露与不安全 secret 在两种 mode 下均须硬阻断。
- `app-debug-preflight` 必须显式选择 `test_live` 或 `immutable_candidate`，不得以默认 mode 替调用方决定严格度。receipt 的 `details` 只记录安全编译/启动 blocker，`warnings` 只记录 test-live readiness 诊断；`gate_block` 对应非零退出，`warning|passed` 对应零退出，平台启动器不得重新解释同一事实的严重级别。
- test-live 中缺失、停止、过期或漂移的 runtime/startup/service/Provider/TLS/trust/transport lease/content readiness 必须保留完整脱敏诊断并继续构建。非法环境/target、环境命名空间逃逸、显式 handoff 冲突或不完整、无法生成 canonical runtime package/native manifest、工具链/真实编译失败与不可用设备仍阻断。`immutable_candidate`、严格 health/verify、内容 UAT 与 Prod 不复用该降级。
- App launcher 不拥有环境生命周期，默认不得隐式执行 `stackctl up/down/repair`，只可调用只读 `stackctl app-debug-preflight/status`。
- 只有操作者显式传入 `--ensure-runtime` 时，`content-live` 才可委托 `stackctl` 启动当前已选 immutable candidate，且不得执行 package、repair 或重选 release。
- `ui-only` 预检以 `warning` + exit 0 报告服务、Provider、内容与漂移问题；`content-live` 必须消费严格 delivery 结果，不得把 warning 重新解释为内容可用。
- direct Debug 与 canonical launcher 在安装前必须调用 `stackctl app-debug-preflight`。Alpha/Beta/Gamma test-live 只校验安全环境选择与最小 handoff并收集运行时诊断，不委托商业 `app-content-preflight`；Prod release 启动继续验证 immutable candidate、必要服务/Provider，并委托 `app-content-preflight` 绑定 commercial readiness、rollback/replay、首页/视频书、Creator 与媒体证据。
- 所有启动入口必须写同一 `app-launch-attempt` receipt，并等待最长 15 分钟直到真实达到 `launched` 或产生首个 typed failure；PID 存活、进程已创建或 1.5 秒未退出均不是成功。编译、安装、启动失败分别使用 `APP.LAUNCH.compile_failed`、`APP.LAUNCH.install_failed`、`APP.LAUNCH.launch_failed`，已启动后的运行时不可用记为 `runtime_degraded` warning，正常 Ctrl-C 记为 `stopped`。
- Android `prod-sim` 只安装并启动 exact Release artifact；Flutter 不支持 iOS AOT Release/Profile simulator，故 iOS Release 基础编译生成 unsigned iphoneos `.app`，Simulator 只允许 non-promotable Debug 启动且不得冒充 Release/Prod 证据。`prod-hosted` 只消费已签名 artifact、manifest、安装回执和严格 readiness，禁止 `flutter run`、Debug 或未经授权的真实 rollout。
- 每次 Dart isolate 启动必须先生成新 `attemptId`，再调用原生 `beginStartupAttempt(attemptId)`。原生返回 `attemptKind=cold|hotRestart`、`processElapsedMs`、`attemptElapsedMs` 与 `deadlineOrigin=nativeProcess|dartHotRestart`。
- `startup_attempt_started` 只能在 native runtime package 已水合且 `configurationState=complete` 后发送；Cold Start 的 6 秒预算可使用进程时钟，Hot Restart 只能使用本次 attempt 时钟。进程总存活时间只作诊断，不得写入 `welcomeExitMs` 或消耗 Hot Restart 预算。
- `stackctl app-content-uat` 必须在唯一 environment operation owner 已完成同一 baseline/release activation 后，顺序对 Alpha、Beta、Gamma 执行上述预检、字面 `flutter run`、首页 Feed、`environment_app_core_readback` 与视频播放 Patrol。
- 自动验收在整个执行窗口持有 runtime-use lock；任一 target 失败即停止并输出首个 typed blocker 和可机读 receipt。禁止以 dry-run、旧 receipt 或单环境成功替代三环境结论。
- 自动验收必须在每个 target 的正向内容读回之后执行受控 API Edge 故障窗口：故障控制器只可操作当前 runtime receipt 绑定的 Compose project 与精确容器，App 必须在同一次安装中呈现与已确认原因匹配的唯一用户恢复动作；控制器恢复原容器并重新通过健康检查后，App 点击该动作必须无需重装即可恢复 release-bound 首页内容。任一步骤异常都必须在 `finally` 恢复环境并使验收失败，禁止遗留人为故障或以本地 double 替代。
- 活跃 lease 存在时，`stackctl down`、环境矩阵强制清理和端口强制回收必须 `GATE_BLOCK`。

<a id="req-004"></a>
### REQ-004 所有有效构建、安装与启动路径行为等价

- 有效路径集合固定为：裸 `flutter run`（Debug，canonical Alpha/Beta/Gamma local target）、canonical launcher `run.sh`（content-live/ui-only）、`stackctl package` 产物 Debug 安装到 Simulator/Emulator/登记设备后点击图标、Android `prod-sim` exact Release、Android/iOS `prod-hosted` Release、应用市场 Release 安装（Apple App Store/TestFlight、华为、小米、OPPO、vivo、应用宝）、官网签名 APK 安装，以及上述任一渠道的同包名覆盖升级。iOS Simulator 只允许 non-promotable Debug，不属于 Release 安装路径。
- 等价定义：同一环境与同一服务端状态下，各路径的规范化行为指纹一致——配置完成态、首个安全终态、路由/登录态、内容 outcome 与 release identity、恢复动作均相同，且无 fatal recovery 差异。BuildMode、launch provenance 与 install channel 只允许作为观测事实记录，不得参与业务分支。
- 每类安装渠道产出独立、按 store/device/build 追加的 install receipt。应用市场渠道的准出证据必须来自真实市场客户端下载安装与安装后冷启动 telemetry 回读，官网 APK 渠道必须来自官网下载对象的 SHA-256/签名/包名比对与安装后启动回读。package-only 编译、side-load 或另一渠道回执不得互相替代。
- Debug 签名制品仅限开发者本机、Simulator/Emulator 与已登记设备，不进入 TestFlight、任何应用市场或官网公开下载；市场与官网只接受 Release 签名制品。
- 每个渠道的验收 CaseResult 声明自动化分级：CI 全自动、设备实验室定期自动、或人工执行加机器回执；人工动作缺机器回执时按失败处理。

<a id="req-005"></a>
### REQ-005 Alpha 双模拟器只交 target-scoped 原始 CaseResult

- Alpha 内容验收的正向窗口必须让 Android Emulator 与 iOS Simulator 对同一 `releaseId + manifestDigest + sourceIdentitySetDigest` 分别生成原始 CaseResult，并覆盖 [`AppRoot UAT-001`](../../../spec.md#uat-001) 的内容、Creator、搜索和可恢复终态，以及 [`UAT-003`](../../../spec.md#uat-003) 的同状态、同内容 identity 与同恢复动作。
- `stackctl app-content-uat --targets alpha-local` 只可编排 Alpha target；它不得生成 Alpha-only aggregate、canonical matrix passed 或 promotion 事实。两个原始结果及其父 report 都必须声明 `nonPromotable=true`。
- `no_active_release` 必须在 active-release suite 外的独立窗口验证：保存原 active release 与 readback、通过正式环境命令应用已核验 empty baseline、依次取得两端 `outcome=empty + emptyReason=no_active_release` CaseResult、same-digest replay 原 release 并复核 lifecycle/readback。任一步中断都必须先恢复原 release；恢复失败保留首个 typed blocker 并停止。
- `CONTROLLED_EDGE_RECOVERY_UAT_TEST_TARGET` 必须进入 Alpha suite。故障控制只操作 runtime receipt 绑定的精确 API Edge 容器，App 显示唯一重试动作；`finally` 恢复容器并通过 health 后，同一安装点击重试必须重新读取原 release。
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
- AND 同一 release train 的 Alpha/Beta/Gamma/Prod environment artifact 从同一 source capsule 派生但最终镜像 digest 互不复用；交换 image/config/binding、篡改 `APP_ENV` 或在运行时选择其他环境时均在 listener 前失败。
- AND `dev-session --all-nonprod` 顺序生成三份 target 隔离的 compile/launch、告警与 health 结果，单个 target 的 runtime health 失败不得抹除其真实编译结果。
- AND Android/iOS 的 production dependency graph、native linker/filelist、SBOM 与最终制品均不含测试插件或 test runner，物理隔离的 UAT test host 枚举全部 canonical 用户验收 case 而不反向进入 production package。
- AND Dart/Pod 跨锁与 CocoaPods executable/version 一致；任一漂移在真实编译前返回 `APP.DEPENDENCY.lock_drift`，且不执行自动 update 或 repo refresh。
- AND bounded content workload 复用健康 full runtime 后，App preflight 仍读取原 full receipt；独立 bounded runtime 的 receipt 不冒充 full readiness。
- AND `stackctl status` 在环境未启动、secret 缺失或 Provider 不可用时只返回诊断失败，不创建 secret、不启动或修复任何组件；consumer/commercial readiness 只有在 canonical Data receipt 与三个 release-bound exact query 均通过时才返回成功。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 Android 与 iOS App 会话保护本地运行时

- GIVEN 开发者通过 `quwoquan_app/run.sh --mode content-live|ui-only --env alpha|beta|gamma -d <device>`，或在没有显式 handoff identity 时通过裸 `flutter run`，默认选择 Alpha App，或以 `APP_RUNTIME_ENV`/`QWQ_ENVIRONMENT` 显式选择对应环境。
- WHEN Flutter 构建、运行、正常退出或异常退出，或并行环境任务尝试 down/强制清理。
- THEN Android lease 在构建前绑定设备、包名、release handoff 与 topology 端口。
- AND canonical launcher 退出时由 trap 释放 Android lease，裸 Debug 在 App 停止后由 liveness 判为 stale。
- AND iOS Simulator lease 在构建前绑定设备、bundle ID、target 与 handoff digest，并通过 user launchd application service 与安装容器 executable 保活。
- AND consumer lease 的只读状态检查不删除 stale lease。
- AND 本地 Alpha 与 Beta/Gamma/Prod 使用同一 production Remote composition；首页、视频与 Creator 由已激活 release 提供，消息和我的主页由真实身份经领域公开 command/event 形成并由真实服务 query 提供，启动器和 UAT 不得隐式切入 Mock、fixture 或残缺 public plane。
- AND target/env 冲突、Prod endpoint/credential 泄露、依赖或真实编译失败时 App 在安装前失败；`ui-only` 对 runtime、系统信任、transport、API 与内容不可用记录告警并进入非晋级安全 Shell，`content-live` 对 runtime、release binding、API、Media、Search、Recommendation 或 readiness 不可用在 Flutter 安装前返回 typed blocker。
- AND 启动回执按 prepared、compiling、compiled、installing、installed、launching、launched 单向推进；子进程在 1.5 秒后编译失败不得出现 launched，父入口只消费该回执而不自行解释 PID。
- AND 裸 Android/iOS Debug `flutter run` 使用 `direct_flutter_run` canonical Alpha/Beta/Gamma handoff，冷启动与 Hot Restart 后环境、target 与 digest 保持一致并进入安全 Shell。
- AND 任意前序环境后，默认 Alpha 与显式 Alpha/Beta/Gamma flavor 的第一条 `flutter run/build` 或 Xcode Run/Profile/Archive 命令即使用本次 environment × BuildMode 身份成功构建；`alpha → beta → gamma → alpha` 不依赖 clean、共享文件刷新或重试，并发构建不互相覆盖 identity 输入或产物。
- AND 冷启动和连续 Hot Restart 均先完成 `beginStartupAttempt`，再以 `configurationState=complete` 发送 attempt 事件；Hot Restart 的 `welcomeExitMs` 始终相对本次 attempt 且不超过 6000ms。
- AND 环境无激活内容 release 时 App 只接受 canonical `outcome=empty + emptyReason=no_active_release` 或 typed unavailable，不以普通空列表冒充成功；环境已激活 release 时 App 从 Content API 响应解析 `releaseId + manifestDigest`，UAT 以环境侧期望 release 比对读回身份，App 制品不内嵌内容身份。Prod 发布准出仍绑定 active candidate、commercial readiness 与 rollback/replay 的环境侧证据，任一缺失均阻断准出，但不改变 App 运行时行为。
- AND `stackctl app-content-uat` 只有在 Alpha/Beta/Gamma 同 baseline、releaseId、manifest digest 与 `appUatEnvelope` 的预检、字面 `flutter run`、首页 Feed、核心 readback、视频播放，以及受控 API Edge 故障下的错误文案与同安装恢复均通过时生成 passed receipt；故障控制只作用于 runtime receipt 绑定的精确容器且始终恢复，任何 target 失败时保留已有证据并停止后续 App 执行。
- AND 显式但不完整的 handoff、Profile/Release 与非 Alpha direct build 在安装前失败，用户不得看到由开发配置缺失制造的启动恢复页。

<a id="gwt-003"></a>
### GWT-003 全渠道安装启动行为等价

- GIVEN 同一环境已激活同一内容 release，各路径使用同一 immutable candidate（或 direct Debug 使用同一工作树与 canonical handoff）构建。
- WHEN 分别经 `REQ-004` 声明的有效路径完成安装并点击图标冷启动，包括同包名覆盖升级。
- THEN 各路径 CaseResult 的规范化行为指纹一致，差异只出现在 BuildMode、launch provenance、install channel 与性能观测维度。
- AND 应用市场与官网 APK 渠道各自绑定真实下载/安装回执与安装后 telemetry 回读；官网 APK 的 SHA-256、包名与签名证书摘要与发布事实逐字段一致。
- AND 覆盖升级路径的行为指纹与全新安装一致，本地缓存按 content identity 规则迁移或失效，不存在只有升级用户才遇到的启动死路。
- AND 任一渠道证据缺失时该渠道保持 `GATE_BLOCK/OPEN`，不得以其他渠道回执或 package-only 报告替代。

<a id="gwt-004"></a>
### GWT-004 Alpha 双模拟器正向、空态与受控恢复保持同一 release

- GIVEN Alpha 已激活一份可形成完整 `appUatEnvelope` 的 immutable release，Android Emulator 与 iOS Simulator 均可运行 production Remote composition。
- WHEN 两端依次执行正向内容窗口、独立 empty-baseline 空态窗口与 suite 内受控 API Edge 5xx 恢复。
- THEN 两端分别交出绑定同一 release、App SHA、package identity 与 startup attempt 的 target-scoped 原始 CaseResult，父 report 不产生 Alpha-only aggregate 或 promotion passed，所有结论均为 `nonPromotable=true`。
- THEN 空态窗口保存原 active release、应用 empty baseline、取得两端 `no_active_release` 结果并 same-digest replay 原 release；任一中断先恢复，恢复失败即停止且不执行后续窗口。
- THEN 受控 Edge target 始终在 `finally` 恢复精确容器并通过 health，同一安装点击唯一重试后重新看到原 release。

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
- 影响或价值：尚缺 Alpha/Beta/Gamma/Prod-sim live runtime，因而 live health、release activation 和三个 release-bound exact query 仍无通过证据；Alpha/Beta/Gamma 的 local-managed TLS/resolver 不依赖公网 DNS/ACME，Prod-sim 与 Prod 的公共 DNS/TLS 前置由 OPEN-002 保留。
  - 一号阻塞（已解除机制并固化工具）：同一 local target 的 mutable test_live 栈与 immutable candidate 栈共享同一 canonical 端口段（如 alpha mongodb 17410），test_live receipt 非 `stopped` 时 candidate `up` 必然以 Compose "port is already allocated" 失败。`stackctl up` 已内建启动前互斥 fail-fast（`assert_no_running_mutable_runtime`，合约 `quwoquan_ops/tests/local_contract/stackctl/test_local_runtime_mutual_exclusion__local_contract_test.py`）；test_live 栈已由使用方释放。
  - 二号阻塞（当前现行）：candidate 栈的 `service-core` 容器启动即退（exit 1，依赖服务全部无法启动，栈自动回滚），alpha/gamma 同因；修复由 service-core composition owner 会话经 gamma `up` 迭代进行中，全局 local stack 操作锁在其迭代期间基本被持有。
- 目标：依次启动 Alpha/Beta/Gamma Remote topology，补齐 release activation、live health 与 consumer/commercial exact-query 矩阵；Prod-sim/Prod 继续等待其公网前置。
- 完成判定：`GWT-001` 的四环境 App/Service/activation 重建矩阵与 `GWT-002` 的 Android/iOS 会话保护、test-live 告警及 Prod fail-closed 矩阵全部通过，且真实测试以子句级 `spec_ref` 绑定同一候选 ResultBundle。

<a id="open-002"></a>
### OPEN-002 Prod 公网 DNS 与公共证书 live 准出

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：仓库具备公网 DNS plan/apply/verify、CAA、邮件防护与 DNS-01 证书签发链路，并隔离 DNS provisioning token 与 challenge-only token；但当前未提供 Cloudflare token/zone id 与 ACME account email，不能伪造 Prod 接入的 live DNS/TLS 成功证据。该阻断不得反向阻塞 Alpha/Beta/Gamma 的 local-managed 本地闭环。
- 目标：通过受保护变量提供 `QWQ_DNS_PROVISIONING_API_TOKEN`、`QWQ_ACME_DNS_API_TOKEN`、`QWQ_DNS_ZONE_ID`、`QWQ_ACME_ACCOUNT_EMAIL`，执行 Prod 接入所需的 apply、证书签发与公共 CA 验证并保存 receipt。
- 完成判定：`GWT-001` 的 Prod `stackctl package / up / health / verify` 子句在真实公网接入下成立——Prod 接入要求的 DNS A/AAAA/CAA/MX/SPF、反向解析、证书 SAN/有效期及公开角色 HTTP/WSS 探针全部通过，且证据报告可回读。

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
### OPEN-004 Alpha 双模拟器 target-scoped 内容与恢复证据

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前 suite 尚未消费受控 Edge recovery target，也没有同一 Alpha release 下 Android Emulator 与 iOS Simulator 的正向、独立 `no_active_release` 空态和 5xx 恢复原始 CaseResult；单端或父 report 不能作为 promotion 证据。
- 完成判定：`GWT-004` 由 suite plan/result 的 `local_contract`、真实 Alpha release lifecycle/readback 的 `api_integration` 与两端 production Remote `user_acceptance` 直接覆盖，结果明确 `nonPromotable=true` 且无 Alpha-only aggregate。
