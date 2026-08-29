# L2 Design：运行时配置 (`runtime-config`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：环境 topology、release lifecycle、双平台 App 会话、受控故障与失败恢复形成跨进程状态机，需要统一 command/query owner、锁、观测与回滚边界。

## 1. 背景、目标与非目标

- 设计目标：让同一环境与同一服务端状态下的配置、启动、内容 identity 和恢复动作可比较，并让 Alpha/Beta/Gamma 双模拟器证据不被父 report 提升为 promotion 事实。
- 非目标：复制 URL/端口、创建环境专用数据源、实现长期内容库或定义 App 业务对象。本设计覆盖四环境、双端与正式浏览器的合同和证据映射，但不把尚未执行或受外部账号、签名、设备、DNS/TLS、发布授权阻断的矩阵单元声明为已通过；这些单元的 OPEN 只在其真实证据到位后关闭。

## 2. Story 协作与状态流

- [`config-provider-layering`](./config-provider-layering/spec.md) 提供唯一配置分层与有效值。
- [`environment-ops-cli-and-skill`](./environment-ops-cli-and-skill/spec.md) 提供 stackctl command、只读状态和 create-once run result。
- [`environment-topology-and-packaging`](./environment-topology-and-packaging/spec.md) 组合 target resolver、consumer lease、release lifecycle、双平台 CaseResult 与故障恢复。

## 3. 端云与数据流

- 本设计不新增业务 aggregate。环境 operation 是由 stackctl 独占推进的 process。
- target-scoped CaseResult、runtime receipt 与 release lifecycle/readback 是各自 append-only 的观察事实，不承载内容对象。
- 写路径只经 stackctl：环境 release apply/rollback/replay 由现有 release command 推进，App 验收按 `alpha-local,beta-local,gamma-local` 的冻结顺序推进，受控 Edge target 只能操作当前 runtime receipt 绑定的精确 Compose project/container。
- 读路径只读取 topology resolver、只读 status、release lifecycle/readback 与 target-scoped CaseResult。App 从 Content API 响应读取 release identity；父 report 只能引用原始结果，不得重写为 Alpha-only aggregate 或 promotion passed。
- endpoint、证书、package identity、Compose project 与容器身份只来自 `quwoquan_ops/environments` 和 stackctl 产物；测试 target 不定义第二套 URL、端口或 runtime identity。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 三环境内容验收以可恢复窗口编排原始 CaseResult
- 决策：Alpha/Beta/Gamma 每个 target 都在正向 release-bound 首页读回后、同一次安装内执行受控 Edge 5xx 窗口；窗口结束必须恢复精确 receipt-bound runtime 并重新读回同一 release。empty-baseline/lifecycle 证据仍由 release owner 独立执行，不由 App fault window 代写。
- 状态流：正向窗口先冻结原 release 与两平台身份。
- 状态流：空态窗口保存原 release、应用已核验 empty baseline、顺序取得 Android/iOS 原始结果后 same-digest replay。
- 状态流：5xx target 由 suite plan 明确包含，并在 `finally` 恢复精确 Edge 容器与 health。所有窗口结束时原 release 必须恢复。
- 理由：active release、无 active content 与运行时失败是三种不同服务端事实。分窗可避免把合法空态解释为失败，也避免为了测空态而污染 active-release suite；原始结果可保留平台差异而不误签 aggregate Green。
- 被否决方案：在 App 注入空列表/fixture、把 no-active-release 合并为 active suite 步骤、手工停止任意 Edge、以父 report 替代平台结果、跳过失败后的 release/container 恢复，或让 App 制品携带期望 release identity。
- 失败恢复：网络失败保留同页唯一重试，身份拒绝通过 canonical AuthContinuation 重新登录或回安全 Shell。
- 失败恢复：故障 target 无论在哪一步失败都先恢复容器并通过 health，空态窗口中断先 same-digest replay 原 release。恢复失败保留首个 typed blocker并停止后续窗口，不产生 passed。
- 可测试观察面：suite plan 必须出现受控 Edge target。
- 可测试观察面：target raw result 可回读 platform、release/App/package/startup identity、window outcome 与 `nonPromotable=true`。
- 可测试观察面：release lifecycle/readback 证明 empty/original 切换，runtime health 与 fault cleanup 证明无遗留故障。local_contract 观察编排与结果语义，api_integration 观察 lifecycle，user_acceptance 在 production Remote composition 上观察两端恢复。
- 关联要求：[`environment-topology-and-packaging/REQ-005`](./environment-topology-and-packaging/spec.md#req-005)
- 影响 Story：[`environment-topology-and-packaging`](./environment-topology-and-packaging/spec.md)
- 关联验收：[`environment-topology-and-packaging/GWT-004`](./environment-topology-and-packaging/spec.md#gwt-004)

<a id="dec-002"></a>
### DEC-002 App 原生制品与目标运行配置按静态信任域和安装后激活分离

- 对象边界：`AppArtifact`、不可变 `RuntimeConfigPackage` 与平台私有容器中的单槽 `ActiveRuntimeConfigPointer` 是三个独立事实。runtime package 不作为 AppArtifact 的 owned entity，也不得进入 APK、AAB、IPA、`.app`、Flutter kernel、Mach-O 或 DEX；active pointer 只引用一份已验证 package digest，不内嵌历史或无界 ACK 集合。
- 构建身份：`app_artifact_manifest.yaml` 是 `buildProfile(nonprod|prod) × BuildMode` 包身份与显示名的唯一值真相源。运行环境继续是 Alpha、Beta、Gamma、Prod，但不参与 application/bundle ID 或二进制编译身份。确定性 codegen 只投影 Android `nonprod/prod` productFlavor 与 iOS profile-specific xcconfig、scheme 和 configuration；默认 Debug 固定为 nonprod，Prod 只允许 prod Release。
- 信任边界：每个 build profile 的独立 `runtime_config_trust_envelope` 是 AppArtifact 的只读构建输入，由平台 App 签名保护，只含 schema、build profile、Ed25519 算法与非空可信公钥环，不含 environment、target、endpoint、package、公钥私钥引用或 secret。nonprod 信任根只接受 Alpha、Beta、Gamma 的签发者，prod 信任根只接受 Prod 签发者；信任根轮换属于新的 AppArtifact 构建，不通过 runtime package 自举。
- 写路径：stackctl/canonical launcher 是目标配置 activation 的唯一外部 owner，在安装后把完整 activation request 写入 App 私有容器，由冷启动原生 activation coordinator 在首个业务 Shell 前消费。coordinator 先用制品内信任根验证 schema、profile、environment、target、签名、摘要和 freshness，再以临时文件、同步落盘和原子替换推进 active pointer；不得改写源码树、构建输出或已签名 AppArtifact，Flutter channel 不提供任何安装 command。
- 入口边界：受支持的启动入口可以有不同 command surface，但只能向本 owner 提交同一份当前生成的 activation contract，不得拥有第二套配置生成、验证、激活或回执协议。入口、构建、安装、attach 与启动终态的实现由各自 owner 裁决；本设计只裁决它们与 runtime config 交界时的输入、结果与恢复不变量，见 [`DEC-003`](#dec-003)。
- 读路径：原生 `RuntimeConfigPackageReader` query 只返回平台私有容器中的 active package 与制品内 trust envelope，Dart resolver 再执行同一契约验证。读者不读取 bundle/asset 中的 target package，不接受 Dart define、环境变量、手写 JSON keyring或 package 自带公钥作为 fallback。冷启动、Hot Restart 与图标启动均消费同一 active digest。
- 首次启动：新安装若尚无 active package，原生层返回 typed absent，Dart 进入阻断式配置页；它不得降级为空 map、零配置、通用网络错误或业务 Shell。Prod 可从制品内稳定 bootstrap authority 获取受签 package，但获取结果仍经同一 installer 激活，bootstrap authority 不携带 rollout stage 或业务配置。
- 失败恢复：新 package 无效、过期、写入失败或 readback 不一致时 activation 失败且 active pointer 保持上一份已验证 digest；首次安装无上一份时保持 absent。回滚只把 pointer 条件更新到仍在保留窗内的上一份已验证 package，目标 5 分钟内完成，不 clean、不重编、不重签 AppArtifact。
- 被否决方案：environment-specific flavor/scheme、endpoint `--dart-define`、把 target package 注入 asset/plist 后重签，以及 bundle package 与私有容器双读。
- 被否决方案：package 携带并自证 trusted keyring、手写 JSON keyring 环境变量、共享“当前环境”文件、build phase 自愈，以及旧环境 flavor 或旧 handoff 字段 fallback。
- 被否决方案：任一启动、构建或测试入口自行生成 trust envelope、注入 endpoint，或维护第二套 installer、reader 或状态机。
- 可测试观察面：local_contract 由 metadata 驱动覆盖 trust envelope、package、installer、reader 和 resolver 的必填字段、签名、profile/target、原子替换及 absent/failed 四态，并比对生成的 profile identity，证明旧环境 flavor 和 target package bundle writer 数量为零。
- 可测试观察面：local_contract 覆盖所有受支持入口只能提交当前 generated activation contract；对于未经 canonical handoff 的入口，只断言本 owner 的 typed 配置失败、active pointer 不变与无伪成功回执。入口解析、设备选择、工具链和 attach 行为由它们的 owner 测试，不在本 DEC 复制。
- 可测试观察面：api_integration 只构建一次 nonprod APK/`.app`，记录完整 AppArtifact digest，安装后顺序激活 Alpha、Beta、Gamma package；每次 activation 仅 package/active digest 改变，AppArtifact digest、签名和可执行文件 digest全部不变，失败 activation 保留上一 active digest。
- 可测试观察面：user_acceptance 回读 Android/iOS 安装 identity、trust envelope digest、active package digest、runtime environment 与 target，并证明冷启动、连续 Hot Restart、图标启动和配置回滚保持同一规范化身份；首次无 package 显示配置阻断页。
- SLI/SLO：activation attempt 及 active receipt 的记录面只引用 [`app_launch_manifest.yaml` 的 `schemas.runtime_config_activation_receipt`](../../../../quwoquan_service/contracts/metadata/_shared/app_launch_manifest.yaml)，不在 Design 维护第二份字段表或旧精确字段集。有效 package 的本地 activation 在 5 秒内成功率目标为 99.9%；禁止记录 endpoint、密钥或 package 原文。无 active package、签名失败、过期、身份错配与原子 readback 失败均立即告警，配置回滚目标为 5 分钟内完成。
- Schema 迁移恢复：host executor、native 与 Dart 的运行路径只接受上述 canonical metadata 当前 generated schema，不得删字段推断旧 schema、继续轮询旧 receipt 或 dual-read。已安装基线如存在历史 receipt，只允许在新 activation 开始前执行一次性离线迁移：将旧 receipt 从运行时可见路径隔离并写独立迁移审计，随后由 canonical activation 全量校验 active package 并产生当前 schema receipt。迁移不得伪造缺失字段、产生兼容 reader 或将历史回执当作 CAS 成功证据；迁移未完成时 activation fail closed 且 active pointer 保持不变。
- 关联要求：[`environment-topology-and-packaging/REQ-003`](./environment-topology-and-packaging/spec.md#req-003)、[`REQ-004`](./environment-topology-and-packaging/spec.md#req-004)
- 关联验收：[`environment-topology-and-packaging/GWT-002`](./environment-topology-and-packaging/spec.md#gwt-002)、[`GWT-003`](./environment-topology-and-packaging/spec.md#gwt-003)

<a id="dec-003"></a>
### DEC-003 所有启动入口只能消费同一 runtime-config activation 合同

- 对象边界：本 owner 只拥有 build-profile 信任域、runtime package、activation request/receipt、active pointer 和配置可用结果之间的一致性。工作区入口投影、构建/安装、工具链、原生插件图、依赖投影、设备选择与 attach 归 [`environment-topology-and-packaging`](./environment-topology-and-packaging/spec.md) 及其实现 owner；启动安全终态归 [`cold-start-performance`](../runtime-client-foundation/cold-start-performance/spec.md) owner。本 DEC 只消费这些 owner 的 canonical 输入/结果，不规定其版本、命令、组件图或终态内部字段。
- 真相源：[`app_artifact_manifest.yaml`](../../../../quwoquan_service/contracts/metadata/_shared/app_artifact_manifest.yaml) 与 [`app_launch_manifest.yaml`](../../../../quwoquan_service/contracts/metadata/_shared/app_launch_manifest.yaml) 是交界处 schema、状态、typed failure 与信任策略的唯一 authoring source。Design 只引用 canonical metadata anchor，不复制 receipt 字段、允许值、错误码或历史字段集。
- Command 边界：入口 owner 只能将当前 generated activation request 提交给 canonical activation coordinator；只有 coordinator 可验证制品信任、package 与 request 身份，并以 CAS 推进 active pointer。入口、test host 和 host executor 不得代写、补全或转译 activation receipt。
- Query 边界：native、Dart 与 host readback 只消费 [`schemas.runtime_config_activation_receipt`](../../../../quwoquan_service/contracts/metadata/_shared/app_launch_manifest.yaml) 当前 generated schema 的 canonical result。入口 provenance、启动终态或缓存的旧回执不得被推断为配置成功，也不得成为第二个 query source。
- 结果边界：任一受支持入口只有在 canonical activation receipt 与 active package readback 同时满足当前 metadata contract 时，才能声明 runtime config 可用。启动 owner 得到的 attached、safe-terminal 或页面结果是配置证据的下游消费者，不能反向补齐缺失或无效的 activation result。
- 失败恢复：当前 schema 缺失、非法、身份错配或 readback 不一致均按 metadata 的 typed 结果 fail closed，active pointer 保持上一份已验证 digest；首次安装则保持 absent。历史 receipt 只能走 [`DEC-002`](#dec-002) 的 activation 前一次性离线迁移，运行路径不提供兼容 reader。
- 被否决方案：在 Design 锁定入口命令、SDK/构建工具版本、原生插件图、依赖 component 与 cold-start 内部终态，在平台或入口复制 metadata 字段，或为历史 receipt 引入 dual-read。
- 可测试观察面：metadata local contract 验证 authoring source 与各生成消费面的指纹一致，未知或历史 schema fail closed；runtime-config local contract 验证不同入口提交同一 contract 时得到同一配置结果，失败不改变上一 active pointer。命令解析、构建投影、依赖图、attach 和 safe-terminal 测试归各自 owner，本 DEC 不重述其断言。
- SLI/SLO：activation 保持 [`DEC-002`](#dec-002) 的时延、成功率、告警和回滚目标；记录面只跟随 canonical metadata，不维护第二份观测 schema。
- 关联要求：[`environment-topology-and-packaging/REQ-003`](./environment-topology-and-packaging/spec.md#req-003)、[`REQ-004`](./environment-topology-and-packaging/spec.md#req-004)
- 影响 Story：只影响 [`environment-topology-and-packaging`](./environment-topology-and-packaging/spec.md) 与 runtime-config 的 contract 交界。
- 关联验收：[`environment-topology-and-packaging/GWT-002`](./environment-topology-and-packaging/spec.md#gwt-002)、[`AppRoot UAT-003`](../../spec.md#uat-003)

<a id="dec-004"></a>
### DEC-004 三环境矩阵以 release train 冻结 source，以 target baseline 绑定环境制品

- 对象边界：`environmentArtifact.releaseTrainId` 是 Alpha/Beta/Gamma 跨 target 的共同 source train 身份；`baselineId` 是 package input capsule 的 target-scoped 身份，包含各环境配置输入，不是跨 target 标量。矩阵结果分别持久化单一 `releaseTrainId` 与闭集 `packageBaselines[target]`。
- 状态流：每个 target 的 package 成功后立即回读 fresh active candidate manifest，在任何 `up`、Data 变更或 Patrol 前校验 package result、active pointer、manifest 与 `environmentArtifact.sourceCapsule.baselineId` 四者一致。首个 target 冻结 release train，后续 target 只允许相同 train 并记录自己的 baseline。
- 读路径：App UAT 聚合回执和只读 availability 按 target 读取 `packageBaselines[target]`，并要求 `runtimeBindings[target].candidateDigest == startup.candidateDigest == package baseline`。空 scalar、从 Alpha 任取一个 baseline、缺 target key、release train 漂移和旧 startup/UAT 都是 typed generation mismatch。
- 失败恢复：任一 target 的 train、baseline、candidate digest 或 active manifest 漂移时保留已完成的 target evidence，在首个 Patrol 前停止；不得用旧 UAT、当前 active pointer 的后来值或重新解释的 scalar 补齐。normal `down` 与既有 release lifecycle 仍是唯一恢复路径。
- 被否决方案：要求三环境 `baselineId` 相同、用 Alpha baseline 代表矩阵、只比较 receipt 时间、接受空 `packageBaseline`，或在 UAT 后重新读取可变 active pointer 推断代际。
- 可测试观察面：local contract 覆盖三个不同 baseline/同一 train 通过、train 漂移与 target baseline 漂移在 device runner 前阻断、matrix receipt 字段精确，以及 read-only availability 拒绝 startup candidate 或 target baseline 不同的旧 UAT。
- 关联要求：[`environment-topology-and-packaging/REQ-002`](./environment-topology-and-packaging/spec.md#req-002)、[`REQ-003`](./environment-topology-and-packaging/spec.md#req-003)
- 关联验收：[`environment-topology-and-packaging/GWT-001`](./environment-topology-and-packaging/spec.md#gwt-001)、[`GWT-002`](./environment-topology-and-packaging/spec.md#gwt-002)

## 5. 失败与恢复

- 环境 operation lock、consumer lease、runtime identity、release identity、设备或 health 任一不满足时均在写前 fail closed。
- fault active、原 release 未恢复或任一平台 CaseResult 缺失时，父 report 只能失败；已有原始结果保持 append-only，不覆盖、不补写。
- 回滚只使用进入窗口前冻结的 immutable release、runtime receipt 与 target topology，不依赖重新 package、重新 build 或当前工作树。

## 6. 质量与观测

- 成本增加为每个本地 target 固定的小型验收窗口：两个模拟器与一次受控 Edge 窗口；不随 M100/M1000 对象总量线性放大。release lifecycle/rollback/replay 继续作为独立证据，不由该窗口隐含完成。
- Edge 与原 release 的恢复目标均为 5 分钟内完成；任何验收退出时 active fault 数必须为零，runtime health 必须通过，原 release readback 必须与进入前 digest 相同。
- SLI 直接读取 stackctl create-once run result、target CaseResult、fault cleanup、health 与 release lifecycle/readback；告警以未清理 fault、恢复超时、digest 漂移或平台结果缺失为触发，不维护第二份状态台账。
- rollout 已扩展到 Alpha/Beta/Gamma 两个模拟器并固定 `nonPromotable=true`；每个 target 必须独立执行受控 Edge 恢复，不能用 Alpha 结果代替 Beta/Gamma。Android/iOS 真机、正式 Green 与 Prod 仍保持对应 OPEN 和人工门，不能由本 DEC 推导通过。

### 启动与恢复证据分层映射

| Environment | Platform / entrypoint | 行为与验收锚点 | `local_contract` | `api_integration` | `user_acceptance` / 证据源 |
| --- | --- | --- | --- | --- | --- |
| Alpha/Beta/Gamma | Android/iOS：`run.sh`、packaged Debug | 完整 runtime package 得到 `configurationState=complete`；runtime/content 不可用只进入安全 Shell；[`GWT-002`](./environment-topology-and-packaging/spec.md#gwt-002)、[`UAT-003`](../../spec.md#uat-003) | `quwoquan_app/test/local_contract/runtime/config/`、launcher/handoff/identity suites；直接消费生产 resolver 与生成 handoff | immutable capsule 复制到私有 projection 后完成 profile 编译、package identity、install/launch receipt；结果按 compile/package/install/attach/safe-terminal 分段 | Android Emulator/登记真机与 iOS Simulator/登记 iPhone 的冷启动、Hot Restart、图标启动和安全终态原始 CaseResult；VM attach 与报告读取测试都不替代同制品 safe terminal |
| Alpha/Beta/Gamma | Android/iOS：字面 `flutter run`（`workspace_flutter_run`） | facade 归一化进入 canonical launcher 同一执行体，trust/build/install/activation/attach 与 `run.sh` 完全相同；[`GWT-002`](./environment-topology-and-packaging/spec.md#gwt-002)、[`UAT-003 install-launch-equivalence`](../../spec.md#install-launch-equivalence) | facade 透传/接管、SDK 单轨/无递归、设备选择、参数拒绝、realpath、projection/resolution 分态与 raw backend 负例 | 新工作区终端经 facade 完成 trust 生成、compile/install/activation/launch receipt 分段证据 | 新终端真实执行 `flutter run -d <device>` 完成同一 attempt，不由测试主动 prepend PATH 或注入 trust |
| Alpha/Beta/Gamma | Android/iOS：受控制 IDE attach（`workspace_ide_debug`） | pre-launch 进入同一 executor，IDE 只连接 attempt-scoped VM service；[`GWT-002`](./environment-topology-and-packaging/spec.md#gwt-002)、[`UAT-003 install-launch-equivalence`](../../spec.md#install-launch-equivalence) | projection 生成/回退、profile、pre-launch/attach 状态、超时与错误码契约 | canonical executor 产出 compile/install/activation/launch/attached 分段 receipt，IDE 不生成第二 handoff | Reload 后从受控制 profile 启动并完成真实 attach，结果与同设备 `run.sh`/字面命令行为指纹一致 |
| Prod | Android/iOS：Release package、`prod-sim`/`prod-hosted` | Debug 禁止、exact artifact、签名与纯度 fail closed；[`GWT-001`](./environment-topology-and-packaging/spec.md#gwt-001)、[`GWT-003`](./environment-topology-and-packaging/spec.md#gwt-003) | Prod Debug 拒绝、manifest/identity/purity、测试依赖泄漏负例 | Android Release artifact 与 iOS unsigned iphoneos compile；签名、安装和 hosted 前置逐层记录 | 只消费已授权 exact Release artifact；缺正式 ID、签名、市场账号、真机或授权的单元保持 `OPEN-002/003`，不得由 simulator/package-only 代替 |
| Alpha/Beta/Gamma/Prod | Web：`package --kind web`、`app-artifact --app-platform web`、`dev-session` | 单一 Web 编译 writer、exact manifest/current 投影、静态恢复面不依赖 API 健康；[`GWT-001`](./environment-topology-and-packaging/spec.md#gwt-001)、[`public-content-web-entry GWT-006`](../runtime-client-foundation/public-content-web-entry/spec.md#gwt-006) | Web bootstrap 状态机、authoring source/codegen、单 writer 与 manifest digest 契约 | exact artifact 的 HTML/字体 HTTP status、UTF-8、MIME、digest、缓存/Service Worker；API plane 关闭时静态恢复面仍可读 | Chrome/Safari 的字体 200、慢载、404、首次离线、缓存离线和 SW 更新；四环境公网缺口继续由 `public-content-web-entry OPEN-004` 承接 |
| Alpha/Beta/Gamma/Prod | 原生 fatal recovery → 官方 Web CTA | CTA 打开本环境 exact origin 且中文可读；[`UAT-003`](../../spec.md#uat-003)、[`public-content-web-entry GWT-006`](../runtime-client-foundation/public-content-web-entry/spec.md#gwt-006) | fatal 注入状态机、canonical URL 与单一恢复动作 | 恢复 URL 的 HTTP 200、UTF-8、字体/HTML digest 与 artifact manifest 绑定 | 真正点击 CTA 后的浏览器页面、中文像素、键盘可达与恢复动作；`UIApplication.open`/Intent 成功本身不计通过 |

所有 CaseResult 只按 [`app_launch_manifest.yaml` 的 canonical attempt schema](../../../../quwoquan_service/contracts/metadata/_shared/app_launch_manifest.yaml) 与 [`app_artifact_manifest.yaml`](../../../../quwoquan_service/contracts/metadata/_shared/app_artifact_manifest.yaml) 绑定同一冻结 source/capsule、制品、启动证据与本次 attempt，Design 不复制字段表。静态门禁、真实编译、package、install/VM attach、同制品 startup safe terminal、runtime health 和用户可见终态分别报告，前一层不得替代后一层。
