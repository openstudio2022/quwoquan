# L3 Story：环境拓扑与打包 (`environment-topology-and-packaging`)

> 所属能力：[`runtime-config`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L1 DEC-001](../../design.md#dec-001)

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
- `prod` 只能读取 `prod` 包；禁止 `prod-gray` 环境、目录或 artifact。
- 同一环境存在多个部署 target 时，每个 target 必须写入独立 package 目录，并从环境 `urlRoles + target urlOverrides + portProfile` 的解析结果投影 App 运行时端点；禁止复制环境默认 target 的 URL 或跨 target 复用可变产物。
- `prod-hosted` artifact 禁止包含 mock/seed/debug/local/test host 与跨环境 URL；`prod-sim` 仍属于 `prod` 环境，但全部公共入口必须使用 `*.sim.quwoquan.com`，不得命中生产 host、增加第五环境或放宽 `prod-hosted` 纯度门。
- Web Origin 固定为 Alpha `https://alpha.quwoquan.com:17000`、Beta `https://beta.quwoquan.com:18000`、Gamma `https://gamma.quwoquan.com:19000`、Prod `https://quwoquan.com`；浏览器 API 固定走同源 `/api` 反代，禁止按请求头猜测 Web/API。
- API、RTC、Ops、CDN 与 Upload 分别使用 `api|rtc|ops|cdn|upload.<env>.quwoquan.com`；媒体读取按 `/media/avatar|image|video` 分段，App 下载固定为 CDN `/download`，上传保持独立 host。
- `quwoquan_ops/environments/domain_governance.yaml` 登记 public、derived deep-link、OAuth callback、east-west、third-party 与 test-only URL 分类；运行时消费者只能读取 topology resolver 投影，不得再定义公开 authority。
- `domain_governance.yaml` 只拥有 URL role 的身份、分类、owner、exposure 与 consumer；各环境 `runtime.yaml` 只拥有 `scheme / host / portRole / pathBase / tlsProfile`。resolver 只合并互不重叠的字段，任何重复 ownership 必须 `GATE_BLOCK`。
- derived link 的 origin 只来自 `publicWeb` role，path 只来自 `quwoquan_service/contracts/metadata/_shared/link_templates.yaml`；user-service 使用生成的 `linktemplates.UserWebPath`，App/Data/Service 禁止再拼接 `/u/`、`/post/` 等第二份公开业务路径。
- Alpha/Beta/Gamma 本地 target 使用同一个 `local-managed` TLS profile；stackctl 从 topology 解析 SAN，在 target-scoped 仓外部署根生成叶证书、CA 与 resolver handoff，并负责受管 Simulator/Emulator 的信任安装与撤销。App、测试和脚本不得关闭证书校验、使用 `curl -k`、改写 canonical URL 或增加 localhost fallback。
- local environment matrix 的 `emulator_only` 设备 profile 只要求 iOS Simulator 与 Android Emulator，并且只能签发 `ALPHA_BETA_GAMMA_EMULATOR_ONLY_FUNCTIONAL_GREEN`、`nonPromotable=true` 与 Android 真机 waiver；它不得写入正式 Green Matrix、Provider 140-cell 或 Prod artifact closure。正式 `ALPHA_BETA_GAMMA_LOCAL_GREEN` 继续要求独立 Android 真机回执。
- `prod-sim` 仍使用 DNS-01 公共 CA，`prod-hosted` 只接受公共 CA；任何 Prod package 必须拒绝 local-managed CA、信任材料与 resolver handoff。
- 非生产 Web 产物必须 `noindex` 且保持环境访问控制；四环境分别拥有 DNS、证书、配置与发布物，不从 Prod 继承。
- `stackctl status` 是严格只读诊断：只能读取既有进程、package、receipt 与 HTTP 状态，禁止创建或刷新 secret、物化 Provider、启动服务、执行修复或改变环境事实；缺失依赖必须以失败状态返回。
- `stackctl package` 的 immutable candidate 合同只用于 Prod 发布：开始与结束必须校验同一完整受管 workspace snapshot，将 staged、unstaged、untracked 输入绑定为唯一 `baselineId`，在 target-scoped 临时目录完成后原子发布；已存在候选只能在全部 digest 一致时复用，禁止覆盖。
- 完整候选根 `manifest.json` 必须绑定 canonical unversioned schema identity、source/workspace/package/build input/image/runtime digest、正式规格引用，以及候选和回滚 Data release attestation。
- 每个第一方镜像的 build input 必须覆盖服务 owner 与实际编译消费的共享 runtime、generated ContractGraph binding、platform package 和 module lock，不能只散列 owner 目录。
- 包内 OCI manifest 必须记录实际 image ID；`up` 只能使用该精确 ID，不能使用可漂移 tag。
- Prod 的 `stackctl up / health / verify` 只能消费已激活的不可变候选及其唯一 `environment_runtime.yaml`，不得隐式 package、build、重新解析工作树 URL 或重选候选；工作区与 active candidate 漂移必须阻断发布。
- Alpha/Beta/Gamma 的 `stackctl dev-session` 是开发者显式拥有的可变冷/热编排入口：直接从当前受治理拓扑与工作树实时 render 临时 runtime config、Compose 与 App handoff，不创建或激活 immutable candidate，也不要求 Data release attestation。开始/结束 source、config 与 generated digest 的变化写入 `mutableWorkspaceWarnings`，不得阻止编译或 App handoff；严格 health/verify 仍独立返回真实失败。
- `dev-session --all-nonprod` 在单工作站按 Alpha→Beta→Gamma 串行运行；隔离 runner 可并行执行不同 target，但不得共享端口、Compose project、secret、CA、release 或 runtime receipt。
- full runtime 是 App 会话的唯一 baseline。bounded content workload 在 full 健康时只复用其能力且不得覆盖 baseline receipt；独立 bounded runtime 必须使用 workload-scoped receipt，并在结束后恢复进入前状态。
- 四环境内容 consumer/commercial readiness 必须绑定同一份 immutable release 的 `releaseId + manifestDigest + sourceOwner=qwq_data`，并校验 discovery `identity=work`、视频书 `identity=work&type=video` 与 `premium_stream` 的 release-bound 非空读回；缺少 Data readiness receipt 或任一 exact query 为空时不得产生通过回执。
- commercial readiness 必须从同一 release 对象闭包投影 canonical `appUatEnvelope`，包含 homepage、article、image、video、Creator、Tag 与 attribution 的验收身份。App 自动验收不得从手工环境变量、fixture 或旧回执重建该信封。

<a id="req-003"></a>
### REQ-003 双端本地运行持有可释放 consumer lease

- `quwoquan_app/run.sh -d <device>` 是显式选择设备、持有 consumer lease 与准备平台 transport 的 canonical launcher；IDE launch profile 可以薄包装该入口。
- `quwoquan_app/run.sh --env alpha|beta|gamma -d <device>` 是推荐入口；裸 `flutter run` 与 IDE 直接 Flutter Debug 默认选择 metadata 声明的 `alpha-local`，并允许 `--dart-define=APP_RUNTIME_ENV=alpha|beta|gamma` 或 `QWQ_ENVIRONMENT` 选择对应 canonical local target，禁止选择 Prod 或直接覆盖 URL、密钥、target、manifest 与 release。
- direct Debug 必须把当前 topology 派生的 test-live runtime config 与 native manifest 交给 Dart 冷启动和 Hot Restart，不得在 App 代码中复制 Alpha endpoint。该配置记录可变摘要供诊断，但摘要变化不得阻止测试编译。
- `app_effective_launch_manifest` 在 `test_live` 中显式声明 `contentBindingState=unbound`，不得伪造 releaseId 或 receipt；Prod release manifest 才必须直接包含 `contentReleaseId`、`contentManifestDigest` 与 `contentReadinessReceiptDigest`，其 canonical digest 覆盖三项内容身份。
- direct Debug 只允许在未显式提供 target、launch mode 或任一 digest 时，把 `APP_RUNTIME_ENV`/`QWQ_ENVIRONMENT` 当作三环境选择器并生成完整 handoff；两个选择器冲突、Prod、任意 target override、过期/缺失 manifest 或摘要不一致均 fail-closed。Profile、Release 与 Prod direct build 禁止隐式推断。
- Android 从 topology 推导包名、设备与全部 `adb reverse` 端口，在 Flutter 构建前获取 release-bound lease；canonical launcher 通过 `trap` 在退出时释放，裸 Debug 的 provisional lease 在 App 停止后由 liveness 判为 stale 并等待显式 GC。
- iOS Simulator 同源准备环境包、系统公共 CA 预检、native runtime manifest 与 provisional lease。iOS lease 绑定 platform、Simulator UDID、bundle ID、target、启动宽限期与 handoff digest；宽限期后必须结合 `simctl get_app_container`、Simulator `user/<uid>` launchd 域中的 `UIKitApplication:<bundleId>` service 与 executable path 判定前台、后台或挂起进程。
- 已验证存活的 App lease 不受 12 小时 provisional 上限影响；`consumer-lease status` 和 down/package/roll 前检查必须严格只读，不得删除 stale 文件。只有显式 `release`/GC 可以清理 lease。
- canonical launcher 固定编译 production `lib/main_prod.dart`，裸 Debug 的默认 `lib/main.dart` 只能薄委托同一入口。
- 两者都连接完整 Remote topology，并消费同一 handoff 的 runtime package，禁止 alpha runner、fixture override 或只提供 mock/public-plane 子集的本地进程。
- Gradle/Xcode 对 canonical launcher 验证其完整 runtime package、制品摘要与设备证明；对 direct Debug 只允许从 metadata/topology 构建所选 canonical handoff并获取本平台 consumer lease，不得启动或修复环境、推断 URL、复制配置或吞掉准备脚本失败。
- iOS Profile/Release、显式非 Alpha 环境与 Beta/Gamma/Prod 均必须携带 canonical launcher 的 target、Dart defines digest、runtime config digest 与 immutable effective manifest digest，缺一即在安装前 `GATE_BLOCK`。
- Alpha/Beta/Gamma test-live 的 runtime/Provider/content 不健康、startup receipt 缺失、active candidate 过期以及 source/config/generated digest 漂移只形成结构化告警，不得使 Xcode/Gradle build phase 失败。依赖解析、真实编译、设备选择、target 冲突、无法生成最小 handoff、Prod endpoint/credential 泄露与不安全 secret 仍必须在构建前硬阻断。
- App launcher 不拥有环境生命周期，不得隐式执行 `stackctl up/down/repair`，只可调用只读 `stackctl app-debug-preflight/status`。test-live 预检以 `warning` + exit 0 报告服务、Provider、内容与漂移问题。严格 health/verify 继续失败并由明确 owner 恢复环境。
- direct Debug 与 canonical launcher 在安装前必须调用 `stackctl app-debug-preflight`。Alpha/Beta/Gamma test-live 只校验安全环境选择与最小 handoff并收集运行时诊断，不委托商业 `app-content-preflight`；Prod release 启动继续验证 immutable candidate、必要服务/Provider，并委托 `app-content-preflight` 绑定 commercial readiness、rollback/replay、首页/视频书、Creator 与媒体证据。
- 每次 Dart isolate 启动必须先生成新 `attemptId`，再调用原生 `beginStartupAttempt(attemptId)`。原生返回 `attemptKind=cold|hotRestart`、`processElapsedMs`、`attemptElapsedMs` 与 `deadlineOrigin=nativeProcess|dartHotRestart`。
- `startup_attempt_started` 只能在 native runtime package 已水合且 `configurationState=complete` 后发送；Cold Start 的 6 秒预算可使用进程时钟，Hot Restart 只能使用本次 attempt 时钟。进程总存活时间只作诊断，不得写入 `welcomeExitMs` 或消耗 Hot Restart 预算。
- `stackctl app-content-uat` 必须在唯一 environment operation owner 已完成同一 baseline/release activation 后，顺序对 Alpha、Beta、Gamma 执行上述预检、字面 `flutter run`、首页 Feed、`environment_app_core_readback` 与视频播放 Patrol。
- 自动验收在整个执行窗口持有 runtime-use lock；任一 target 失败即停止并输出首个 typed blocker 和可机读 receipt。禁止以 dry-run、旧 receipt 或单环境成功替代三环境结论。
- 自动验收必须在每个 target 的正向内容读回之后执行受控 API Edge 故障窗口：故障控制器只可操作当前 runtime receipt 绑定的 Compose project 与精确容器，App 必须在同一次安装中呈现与已确认原因匹配的唯一用户恢复动作；控制器恢复原容器并重新通过健康检查后，App 点击该动作必须无需重装即可恢复 release-bound 首页内容。任一步骤异常都必须在 `finally` 恢复环境并使验收失败，禁止遗留人为故障或以本地 double 替代。
- 活跃 lease 存在时，`stackctl down`、环境矩阵强制清理和端口强制回收必须 `GATE_BLOCK`。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 环境拓扑与打包

- GIVEN 开发、测试或运维角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“环境拓扑与打包”对应的公开行为。
- THEN 各环境 `runtime.yaml` 均声明完整 `edge / media / service / data` 子网与结构化 `urlRoles`。
- AND `stackctl package --env prod --target prod-sim|prod-hosted` 分别生成 target 隔离的 App 包，包内 URL 与 resolver 生成的 `publicBases` 一致，且 `prod-hosted` 仍拒绝本地或测试 host。
- AND Alpha/Beta/Gamma `dev-session` 从当前工作树与 topology 实时 render target 隔离的 test-live runtime，不创建 immutable candidate；工作区或配置变化进入告警，严格 health/verify 仍如实失败。
- AND Prod `stackctl package / up / health / verify` 只读取 immutable active candidate，重复 package 只在完整 manifest 和全部 digest 相同的情况下返回原始 receipt，不隐式重建或覆盖候选。
- AND `dev-session --all-nonprod` 顺序生成三份 target 隔离的 compile/launch、告警与 health 结果，单个 target 的 runtime health 失败不得抹除其真实编译结果。
- AND bounded content workload 复用健康 full runtime 后，App preflight 仍读取原 full receipt；独立 bounded runtime 的 receipt 不冒充 full readiness。
- AND `stackctl status` 在环境未启动、secret 缺失或 Provider 不可用时只返回诊断失败，不创建 secret、不启动或修复任何组件；consumer/commercial readiness 只有在 canonical Data receipt 与三个 release-bound exact query 均通过时才返回成功。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 Android 与 iOS App 会话保护本地运行时

- GIVEN 开发者通过 `quwoquan_app/run.sh --env alpha|beta|gamma -d <device>`，或在没有显式 handoff identity 时通过裸 `flutter run`，默认启动 Alpha App，或以 `APP_RUNTIME_ENV`/`QWQ_ENVIRONMENT` 显式选择对应环境。
- WHEN Flutter 构建、运行、正常退出或异常退出，或并行环境任务尝试 down/强制清理。
- THEN Android lease 在构建前绑定设备、包名、release handoff 与 topology 端口。
- AND canonical launcher 退出时由 trap 释放 Android lease，裸 Debug 在 App 停止后由 liveness 判为 stale。
- AND iOS Simulator lease 在构建前绑定设备、bundle ID、target 与 handoff digest，并通过 user launchd application service 与安装容器 executable 保活。
- AND consumer lease 的只读状态检查不删除 stale lease。
- AND 本地 Alpha 与 Beta/Gamma/Prod 使用同一 production Remote composition；首页、视频与 Creator 由已激活 release 提供，消息和我的主页由真实身份经领域公开 command/event 形成并由真实服务 query 提供，启动器和 UAT 不得隐式切入 Mock、fixture 或残缺 public plane。
- AND target/env 冲突、Prod endpoint/credential 泄露、依赖或真实编译失败时 App 在安装前失败；runtime digest、系统信任、Android `adb reverse`、API/User/Integration/SMS Provider/content 不可用时 test-live 记录告警并继续编译启动，严格环境验收仍失败。
- AND 裸 Android/iOS Debug `flutter run` 使用 `direct_flutter_run` canonical Alpha/Beta/Gamma handoff，冷启动与 Hot Restart 后环境、target 与 digest 保持一致并进入安全 Shell。
- AND 冷启动和连续 Hot Restart 均先完成 `beginStartupAttempt`，再以 `configurationState=complete` 发送 attempt 事件；Hot Restart 的 `welcomeExitMs` 始终相对本次 attempt 且不超过 6000ms。
- AND test-live 无内容绑定时只接受 canonical `outcome=empty + emptyReason=no_active_release` 或 typed unavailable，不以普通空列表冒充成功；Prod 安装前内容预检仍绑定 active candidate、commercial readiness 与 rollback/replay，任一 release-bound 证据缺失均阻断。
- AND `stackctl app-content-uat` 只有在 Alpha/Beta/Gamma 同 baseline、releaseId、manifest digest 与 `appUatEnvelope` 的预检、字面 `flutter run`、首页 Feed、核心 readback、视频播放，以及受控 API Edge 故障下的错误文案与同安装恢复均通过时生成 passed receipt；故障控制只作用于 runtime receipt 绑定的精确容器且始终恢复，任何 target 失败时保留已有证据并停止后续 App 执行。
- AND 显式但不完整的 handoff、Profile/Release 与非 Alpha direct build 在安装前失败，用户不得看到由开发配置缺失制造的启动恢复页。

## 6. 依赖

- 前置要求：[`runtime-config`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 环境拓扑与打包 验收证据

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺 Alpha/Beta/Gamma/Prod-sim live runtime，因而 live health、release activation 和三个 release-bound exact query 仍无通过证据；Alpha/Beta/Gamma 的 local-managed TLS/resolver 不依赖公网 DNS/ACME，Prod-sim 与 Prod 的公共 DNS/TLS 前置由 OPEN-002 保留。
- 目标：依次启动 Alpha/Beta/Gamma Remote topology，补齐 release activation、live health 与 consumer/commercial exact-query 矩阵；Prod-sim/Prod 继续等待其公网前置。
- 完成判定：`GWT-001` 的四环境 App/Service/activation 重建矩阵与 `GWT-002` 的 Android/iOS 会话保护、test-live 告警及 Prod fail-closed 矩阵全部通过，且真实测试以子句级 `spec_ref` 绑定同一候选 ResultBundle。

<a id="open-002"></a>
### OPEN-002 Prod 公网 DNS 与公共证书 live 准出

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：仓库具备公网 DNS plan/apply/verify、CAA、邮件防护与 DNS-01 证书签发链路，并隔离 DNS provisioning token 与 challenge-only token；但当前未提供 Cloudflare token/zone id 与 ACME account email，不能伪造 Prod 接入的 live DNS/TLS 成功证据。该阻断不得反向阻塞 Alpha/Beta/Gamma 的 local-managed 本地闭环。
- 目标：通过受保护变量提供 `QWQ_DNS_PROVISIONING_API_TOKEN`、`QWQ_ACME_DNS_API_TOKEN`、`QWQ_DNS_ZONE_ID`、`QWQ_ACME_ACCOUNT_EMAIL`，执行 Prod 接入所需的 apply、证书签发与公共 CA 验证并保存 receipt。
- 完成判定：Prod 接入要求的 DNS A/AAAA/CAA/MX/SPF、反向解析、证书 SAN/有效期及公开角色 HTTP/WSS 探针全部通过，且证据报告可回读。
