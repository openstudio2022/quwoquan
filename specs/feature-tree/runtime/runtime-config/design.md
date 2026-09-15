# L2 Design：运行时配置 (`runtime-config`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：环境 topology、release lifecycle、双平台 App 会话、受控故障与失败恢复形成跨进程状态机，需要统一 command/query owner、锁、观测与回滚边界。

## 1. 背景、目标与非目标

- 设计目标：让同一环境与同一服务端状态下的配置、启动、内容 identity 和恢复动作可比较，并让 Alpha/Beta/Gamma 双模拟器证据不被父 report 提升为 promotion 事实。
- 非目标：复制 URL/端口、创建环境专用业务模型、第二套内容库或假服务；Alpha canonical 快照 adapter 与 Remote 只在组合根不同。本设计覆盖四环境、双端与正式浏览器的合同和证据映射，但不把尚未执行或受外部账号、签名、设备、DNS/TLS、发布授权阻断的矩阵单元声明为已通过；这些单元的 OPEN 只在其真实证据到位后关闭。

## 2. Story 协作与状态流

- [`config-provider-layering`](./config-provider-layering/spec.md) 提供唯一配置分层与有效值。
- [`environment-ops-cli-and-skill`](./environment-ops-cli-and-skill/spec.md) 提供 stackctl command、只读状态和 create-once run result。
- [`environment-topology-and-packaging`](./environment-topology-and-packaging/spec.md) 组合 target resolver、consumer lease、release lifecycle、双平台 CaseResult 与故障恢复。

## 3. 端云与数据流

- 本设计不新增业务 aggregate。环境 operation 是由 stackctl 独占推进的 process。
- target-scoped CaseResult、runtime receipt 与 release lifecycle/readback 是各自 append-only 的观察事实，不承载内容对象。
- 写路径只经 stackctl：环境 release apply/rollback/replay 由现有 release command 推进，App 验收按 `alpha-local,beta-local,gamma-local` 的冻结顺序推进，受控 Edge target 只能操作当前 runtime receipt 绑定的精确 Compose project/container。
- 读路径读取 topology resolver、status、release readback 与 CaseResult；Remote 从 Content API 确认 active identity，Alpha 从已验证制品快照取得独立 source identity。父 report 只引用原始结果，不改写 authority；离线不代填服务环境事实。
- endpoint、证书、package identity、Compose project 与容器身份只来自 `quwoquan_ops/environments` 和 stackctl 产物；测试 target 不定义第二套 URL、端口或 runtime identity。

## 4. 关键决策

- 构建派生物封印与离线交互验收遵循 [`environment-topology-and-packaging` REQ-008/GWT-007](./environment-topology-and-packaging/spec.md#gwt-007)：iOS registrant 仅按精确路径从工具链模板及锁定插件声明验证完整字节，源 capsule CAS 与派生清单摘要分别绑定；SwiftPM 缓存预建在 private projection 内，不添加外部 symlink 例外。未知字节或路径越界终止，保留首错并由新 candidate/fresh projection 恢复，不修改依赖锁或全局缓存。
- 页面证据只由外部原生 test host 对生产 App 执行真实点击/滑动并观察；首页推荐视频与视频书分格，Tab 往返用控件实际坐标证明固定及恢复，不在 AUT 注入状态或路由。local_contract 验证篡改拒绝与步骤/观察完整性，双平台 user_acceptance 验证实际行为；未执行设备证据不提升为通过。

<a id="dec-001"></a>
### DEC-001 三环境内容验收以可恢复窗口编排原始 CaseResult
- 决策：Beta/Gamma Remote App 在同一次安装的正向读回后验证受控 Edge 恢复；独立 Alpha API gate 验证服务端 Edge 与 empty/replay lifecycle，Alpha 离线 App 则证明同一故障期间继续读取快照。两类 source 证据不互换；窗口只在目标维护租约与精确 receipt-bound runtime 内执行并恢复，不停止其他 target。
- 状态流：正向窗口先冻结原 release 与两平台身份。
- 状态流：Alpha API 空态窗口保存原 release、应用已核验 empty baseline、取得服务原始结果后 same-digest replay；它不覆盖 Alpha 离线 App 的 source 或生成其 no-active-release 结果。
- 状态流：5xx target 由 suite plan 明确包含，并在 `finally` 恢复精确 Edge 容器与 health。所有窗口结束时原 release 必须恢复。
- 理由：active release、无 active content 与运行时失败是三种不同服务端事实。分窗可避免把合法空态解释为失败，也避免为了测空态而污染 active-release suite；原始结果可保留平台差异而不误签 aggregate Green。
- 被否决方案：在 App 注入空列表/fixture、把 no-active-release 合并为 active suite 步骤、手工停止任意 Edge、以父 report 替代平台结果、跳过失败后的 release/container 恢复，或让 App 制品携带期望 release identity。
- 失败恢复：网络失败保留同页唯一重试，身份拒绝通过 canonical AuthContinuation 重新登录或回安全 Shell。
- 失败恢复：故障 target 无论在哪一步失败都先恢复容器并通过 health，空态窗口中断先 same-digest replay 原 release。恢复失败保留首个 typed blocker并停止后续窗口，不产生 passed。
- 可测试观察面：suite plan 必须出现受控 Edge target。
- 可测试观察面：target raw result 可回读 platform、release/App/package/startup identity、window outcome 与 `nonPromotable=true`。
- 可测试观察面：local_contract 观察编排与结果语义，api_integration 观察独立 Alpha API 与 Beta/Gamma lifecycle/cleanup，user_acceptance 观察 Beta/Gamma 两端 Remote 恢复及 Alpha 离线不受 Edge 故障影响；任一未测路径保持 OPEN。
- 关联要求：[`environment-topology-and-packaging/REQ-005`](./environment-topology-and-packaging/spec.md#req-005)
- 影响 Story：[`environment-topology-and-packaging`](./environment-topology-and-packaging/spec.md)
- 关联验收：[`environment-topology-and-packaging/GWT-004`](./environment-topology-and-packaging/spec.md#gwt-004)

<a id="dec-002"></a>
### DEC-002 App 原生制品与目标运行配置按静态信任域和安装后激活分离

- 对象边界：AppArtifact、受签 runtime document 与私有容器单槽 pointer 各自独立。Alpha 使用独立 signed offline bootstrap document 绑定 canonical 快照和完整媒体；Beta/Gamma/Prod 使用在线 runtime config package。两类文档都经同一 activation/CAS/receipt/read chain 验证并选定一份 active document，不建立直接读 bundle 的第二 bootstrap。离线文档不声明假 HTTPS endpoint、在线授权或 server active release，其独立完整性合同不等于忽略在线 expiry；source 判别由 canonical launch metadata 拥有，DEC-006 约束组合根消费。
- 构建身份：[`App artifact manifest`](../../../../quwoquan_service/contracts/metadata/_shared/app_artifact_manifest.yaml) 是 `buildProfile(nonprod|prod) × BuildMode` 包身份与显示名的唯一值真相源。运行环境继续是 Alpha、Beta、Gamma、Prod，但不参与 application/bundle ID 或二进制编译身份。确定性 codegen 只投影 Android `nonprod/prod` productFlavor 与 iOS profile-specific xcconfig、scheme 和 configuration；默认 Debug 固定为 nonprod，Prod 只允许 prod Release。
- 信任边界：每个 build profile 的独立 `runtime_config_trust_envelope` 是 AppArtifact 的只读构建输入，由平台 App 签名保护，只含 schema、build profile、Ed25519 算法与非空可信公钥环，不含 environment、target、endpoint、package、公钥私钥引用或 secret。nonprod 信任根只接受 Alpha、Beta、Gamma 的签发者，prod 信任根只接受 Prod 签发者；信任根轮换属于新的 AppArtifact 构建，不通过 runtime package 自举。
- 写路径：stackctl/canonical launcher 是目标配置 activation 的唯一外部 owner，在安装后把完整 activation request 写入 App 私有容器，由冷启动原生 activation coordinator 在首个业务 Shell 前消费。coordinator 先用制品内信任根验证 schema、profile、environment、target、签名、摘要和 freshness，再以临时文件、同步落盘和原子替换推进 active pointer；不得改写源码树、构建输出或已签名 AppArtifact，Flutter channel 不提供任何安装 command。同一 coordinator 按 canonical 文档类型校验在线 package 或独立 signed offline document，默认 Alpha 的离线请求同样经过 activation/CAS，不因缺在线 endpoint 而构造假配置；新在线 package 的 freshness 始终完整校验。
- 入口边界：受支持的启动入口可以有不同 command surface，但只能向本 owner 提交同一份当前生成的 activation contract，不得拥有第二套配置生成、验证、激活或回执协议。入口、构建、安装、attach 与启动终态的实现由各自 owner 裁决；本设计只裁决它们与 runtime config 交界时的输入、结果与恢复不变量，见 [`DEC-003`](#dec-003)。
- 读路径：原生 reader 只返回私有容器中的 active document 与制品内 trust envelope，Dart resolver 按 canonical 文档类型完成同一验证链。离线 bundle 只提供待激活 signed document 与被其绑定的内容资产，不是绕过 active pointer 的第二 bootstrap reader；冷启动、Hot Restart 与图标启动消费同一 active digest，不接受 define、环境变量、自带 keyring 或假 HTTPS fallback。
- 首次启动：Alpha 默认供给独立 signed offline document，经同一原生 activation/CAS 后读取所绑定完整快照；激活缺失或失败仍 typed absent/blocked，不绕过 read chain。在线 source 缺有效 package 则阻断，不以离线文档或空在线配置补齐。Prod 可从制品内稳定 bootstrap authority 获取受签 package，但获取结果仍经同一 installer 激活，bootstrap authority 不携带 rollout stage 或业务配置。
- 失败恢复：新 package 无效、过期、写入失败或 readback 不一致时 activation 失败且 active pointer 保持上一份已验证 digest；首次安装无上一份时保持 absent。回滚只把 pointer 条件更新到仍在保留窗内的上一份已验证 package，目标 5 分钟内完成，不 clean、不重编、不重签 AppArtifact。
- 被否决方案：environment-specific flavor/scheme、endpoint define、注入在线 package 后重签已签名制品、bundle 与私有容器故障双读，以及依赖仓库外 PATH/shell 才能默认启动。Alpha canonical 离线材料是显式 source，不是在线签名包失效后的第三输入。
- 被否决方案：package 携带并自证 trusted keyring、手写 JSON keyring 环境变量、共享“当前环境”文件、build phase 自愈，以及旧环境 flavor 或旧 handoff 字段 fallback。
- 被否决方案：任一启动、构建或测试入口自行生成 trust envelope、注入 endpoint，或维护第二套 installer、reader 或状态机。
- 可测试观察面：local_contract 由 metadata 驱动覆盖两种 signed document 的签名、profile/target、同一 installer/reader/resolver、CAS 与 absent/failed 结果；证明 Alpha 离线不伪造 endpoint、不豁免 online expiry，且无旧环境 flavor 或直接 bundle bootstrap 读取旁路。
- 可测试观察面：local_contract 覆盖所有受支持入口只能提交当前 generated activation contract；对于未经 canonical handoff 的入口，只断言本 owner 的 typed 配置失败、active pointer 不变与无伪成功回执。入口解析、设备选择、工具链和 attach 行为由它们的 owner 测试，不在本 DEC 复制。
- 可测试观察面：Beta/Gamma 共用在线 nonprod APK/`.app` 并仅更新已验证配置，完整 AppArtifact digest 与签名不变。Alpha 另用隔离制品，不要求 Alpha↔在线制品切换保持摘要不变；各自仍按同一 canonical activation/CAS/read chain 验信，在线 package 原子性与离线闭包完整性分别证明。
- 可测试观察面：user_acceptance 回读 Android/iOS 安装 identity、trust envelope digest、active package digest、runtime environment 与 target，并证明冷启动、连续 Hot Restart、图标启动和配置回滚保持同一规范化身份；首次无 package 显示配置阻断页。
- SLI/SLO：activation attempt 及 active receipt 的记录面只引用 [App launch manifest 的 `schemas.runtime_config_activation_receipt`](../../../../quwoquan_service/contracts/metadata/_shared/app_launch_manifest.yaml)，不在 Design 维护第二份字段表或旧精确字段集。有效 package 的本地 activation 在 5 秒内成功率目标为 99.9%；禁止记录 endpoint、密钥或 package 原文。无 active package、签名失败、过期、身份错配与原子 readback 失败均立即告警，配置回滚目标为 5 分钟内完成。
- Schema 迁移恢复：host executor、native 与 Dart 的运行路径只接受上述 canonical metadata 当前 generated schema，不得删字段推断旧 schema、继续轮询旧 receipt 或 dual-read。已安装基线如存在历史 receipt，只允许在新 activation 开始前执行一次性离线迁移：将旧 receipt 从运行时可见路径隔离并写独立迁移审计，随后由 canonical activation 全量校验 active package 并产生当前 schema receipt。迁移不得伪造缺失字段、产生兼容 reader 或将历史回执当作 CAS 成功证据；迁移未完成时 activation fail closed 且 active pointer 保持不变。
- 关联要求：[`environment-topology-and-packaging/REQ-003`](./environment-topology-and-packaging/spec.md#req-003)、[`REQ-004`](./environment-topology-and-packaging/spec.md#req-004)
- 关联验收：[`environment-topology-and-packaging/GWT-002`](./environment-topology-and-packaging/spec.md#gwt-002)、[`GWT-003`](./environment-topology-and-packaging/spec.md#gwt-003)

<a id="dec-003"></a>
### DEC-003 所有启动入口只能消费同一 runtime-config activation 合同

- 对象边界：本 owner 只拥有 build-profile 信任域、runtime package、activation request/receipt、active pointer 和配置可用结果之间的一致性。工作区入口投影、构建/安装、工具链、原生插件图、依赖投影、设备选择与 attach 归 [`environment-topology-and-packaging`](./environment-topology-and-packaging/spec.md) 及其实现 owner；启动安全终态归 [`cold-start-performance`](../runtime-client-foundation/cold-start-performance/spec.md) owner。本 DEC 只消费这些 owner 的 canonical 输入/结果，不规定其版本、命令、组件图或终态内部字段。
- 真相源：[App artifact manifest](../../../../quwoquan_service/contracts/metadata/_shared/app_artifact_manifest.yaml) 与 [App launch manifest](../../../../quwoquan_service/contracts/metadata/_shared/app_launch_manifest.yaml) 是交界处 schema、状态、typed failure 与信任策略的唯一 authoring source。Design 只引用 canonical metadata anchor，不复制 receipt 字段、允许值、错误码或历史字段集。
- Command 边界：入口 owner 只能将当前 generated activation request 提交给 canonical activation coordinator；只有 coordinator 可验证制品信任、package 与 request 身份，并以 CAS 推进 active pointer。入口、test host 和 host executor 不得代写、补全或转译 activation receipt。
- 角色入口边界：Make、IDE、raw SDK、受管字面命令与 run.sh 只消费同一 canonical 启动 contract，不持第二套配置生成或设备权威。默认 Alpha 的 signed offline document 经过同一 activation/CAS/read chain 并验证快照与设备绑定，无云栈、TLS/登录 readiness 前置；在线 source 消费目标签名配置和对应严格 readiness。direct 安全租约只防运行占用，不提升 managed/UAT authority；其余子命令和项目 exact 透传，设备选择由 canonical device authority 裁决。
- 终端注入边界：Cursor terminal profiles 与显式 opt-in、可逆的 user-zsh managed source block 只注入受管 PATH bin 目录（含 launcher `flutter` dispatcher）与钉定的 Flutter SDK/CocoaPods/Python 身份，不改 ZDOTDIR、不生成 terminal receipt；既有 shell 只能显式 source 刷新，移除注入即完全回退。terminal carrier receipt、`workspace_flutter_run` 与 `native_flutter_run` provenance 均已退役，`app_launch_attempt` 的两个 carrier 字段固定为空值。
- 依赖 staleness 恢复边界：只有 live worktree 的外层 canonical launcher 在创建 private workspace projection 前、stdin/stderr 双 TTY 的交互会话中，才允许对首个 `APP.DEPENDENCY.bundle_stale` 自动执行一次 canonical `stackctl app-dependency-sync` 并在 active readback 与本次 sync attempt 一致后重试一次 projection（one-shot）；非交互/CI/UAT、private projection 内、同步失败、activation ambiguous 与第二次 stale 均 fail-closed，首个 stale blocker 必须先输出且不得被替换。sync 事务自身的对象与恢复语义由 [`platform-ops-governance` design](../../platform-ops-governance/design.md#dec-003) 拥有，本 DEC 只冻结启动侧触发边界。
- VM discovery：iOS Simulator 组合入口的 exact device/PID 与 pre-launch log start 是唯一发现 authority；使用该设备结构化 PID 日志获得唯一 loopback VM URI，随后全局 lsof 必须返回 exact PID 单集合。退役按 bundle 名 dns-sd 全局查询，避免不同模拟器同包名解析到另一进程；不保留 mDNS fallback。15 秒预算内无记录可有界等候，跨 PID、多个 URI、格式不明或端口 owner 错配立即 fail closed；token 仅在受保护调用参数中传递，不写错误日志。
- Retry owner：iOS UAT parent 由 entry/toolchain owner 在 attempt-1 前一次性冻结 exact `PATH` 与同一 six-field physical CocoaPods binding，并由 attempt-1/retry 原样消费；ambient parent shell identity、attempt 间重发现与 child 反向传回均无 authority，binding 漂移在 Flutter child 前 typed block。
- UAT authority 边界：raw authority 仍固定为 `ReleaseUatSamplePlan → TargetUatBinding → raw ReadinessCaseResult → EnvironmentAcceptanceFact`；父 report 只读投影 raw refs、exact-byte digests、coverage 与缺口，无独立 outcome verdict，也不能进入或回写该链。
- Query 边界：native、Dart 与 host readback 只消费 [`schemas.runtime_config_activation_receipt`](../../../../quwoquan_service/contracts/metadata/_shared/app_launch_manifest.yaml) 当前 generated schema 的 canonical result。入口 provenance、启动终态或缓存的旧回执不得被推断为配置成功，也不得成为第二个 query source。
- 结果边界：两类 source 都要求同一 canonical activation receipt 和 active document readback 满足 metadata contract；Alpha 另验证所绑定完整快照。离线 receipt 只证明本地 bootstrap 文档激活，不证明在线 endpoint 或 server active release，不能为通过判断伪造在线回执。启动 owner 得到的 attached、safe-terminal 或页面结果是配置证据的下游消费者，不能反向补齐缺失或无效的 activation result。
- 失败恢复：当前 schema 缺失、非法、身份错配或 readback 不一致均按 metadata 的 typed 结果 fail closed，active pointer 保持上一份已验证 digest；首次安装则保持 absent。历史 receipt 只能走 [`DEC-002`](#dec-002) 的 activation 前一次性离线迁移，运行路径不提供兼容 reader。
- 被否决方案：在 Design 锁定入口命令、SDK/构建工具版本、terminal surface 枚举、原生插件图、依赖 component 与 cold-start 内部终态，在平台或入口复制 metadata 字段，为历史 receipt 引入 dual-read，静默修改全部 user shell；恢复 ZDOTDIR shim、terminal carrier receipt 或 `workspace_flutter_run` carrier；保留 `embedded_default_package` 构建期默认供给旁路；让 `native_flutter_run` 成为第二启动协议；managed 启动按 latest 猜测内容。
- 可测试观察面：metadata local contract 验证 authoring source 与各生成消费面的指纹一致、carrier 字段全空约束、未知或历史 schema fail closed；runtime-config local contract 验证不同入口提交同一 contract 时得到同一配置结果、在线 source 无合法 handoff 时 fail closed，raw SDK 默认 Alpha 与其他入口的离线完整性结果一致，失败不改变上一 active pointer。terminal 注入、命令解析、设备交互、构建投影、依赖图、attach 和 safe-terminal 测试归各自 owner，本 DEC 不重述其实现断言。
- SLI/SLO：activation 保持 [`DEC-002`](#dec-002) 的时延、成功率、告警和回滚目标；记录面只跟随 canonical metadata，不维护第二份观测 schema。
- 关联要求：[`environment-topology-and-packaging/REQ-003`](./environment-topology-and-packaging/spec.md#req-003)、[`REQ-004`](./environment-topology-and-packaging/spec.md#req-004)
- 影响 Story：只影响 [`environment-topology-and-packaging`](./environment-topology-and-packaging/spec.md) 与 runtime-config 的 contract 交界。
- 关联验收：[`environment-topology-and-packaging/GWT-002`](./environment-topology-and-packaging/spec.md#gwt-002)、[`AppRoot UAT-003`](../../spec.md#uat-003)

<a id="dec-004"></a>
### DEC-004 三环境矩阵以 release train 冻结 source，以 target baseline 绑定环境制品

- 对象边界：`environmentArtifact.releaseTrainId` 是 Alpha/Beta/Gamma 跨 target 的共同 source train 身份；`baselineId` 是 package input capsule 的 target-scoped 身份，包含各环境配置输入，不是跨 target 标量。矩阵结果分别持久化单一 `releaseTrainId` 与闭集 `packageBaselines[target]`。
- 状态流：每个 target 的 package 成功后立即回读 fresh active candidate manifest，在任何 `up`、Data 变更或 Patrol 前校验 package result、active pointer、manifest 与 `environmentArtifact.sourceCapsule.baselineId` 四者一致。首个 target 冻结 release train，后续 target 只允许相同 train 并记录自己的 baseline。
- 读路径：App UAT 聚合回执和只读 availability 按 target 读取 `packageBaselines[target]`，并要求 `runtimeBindings[target].candidateDigest == startup.candidateDigest == package baseline`。空 scalar、从 Alpha 任取一个 baseline、缺 target key、release train 漂移和旧 startup/UAT 都是 typed generation mismatch。
- 失败恢复：任一 target 的 train、baseline、candidate digest 或 active manifest 漂移时保留已有 evidence 并阻断该 suite，不用旧 UAT 或后来 pointer 补齐。package candidate 与运行 generation 独立，恢复只经目标显式 lifecycle/lease 协调；不能默认 down 已复用 runtime 或其他 target。
- 被否决方案：要求三环境 `baselineId` 相同、用 Alpha baseline 代表矩阵、只比较 receipt 时间、接受空 `packageBaseline`，或在 UAT 后重新读取可变 active pointer 推断代际。
- 可测试观察面：local contract 覆盖三个不同 baseline/同一 train 通过、train 漂移与 target baseline 漂移在 device runner 前阻断、matrix receipt 字段精确，以及 read-only availability 拒绝 startup candidate 或 target baseline 不同的旧 UAT。
- 关联要求：[`environment-topology-and-packaging/REQ-002`](./environment-topology-and-packaging/spec.md#req-002)、[`REQ-003`](./environment-topology-and-packaging/spec.md#req-003)
- 关联验收：[`environment-topology-and-packaging/GWT-001`](./environment-topology-and-packaging/spec.md#gwt-001)、[`GWT-002`](./environment-topology-and-packaging/spec.md#gwt-002)

<a id="dec-005"></a>
### DEC-005 Data 生命周期矩阵以 activation 结果作为 Exit 前驱

- 决策与 owner：Ops matrix 只编排下游 environment commands，不创建 producer facts；candidate 与 rollback 必须持有显式 handoff 或 empty-baseline system attestation，并在任何环境 mutation 前与 immutable release identity 精确对账。Data ship 仍拥有 prepared apply、activate、rollback、verify 与 Exit 的 append-only 结果，Content 仍按 runtime-data-engineering `DEC-003` 拥有 active pointer CAS。
- 状态流：original 和 same-digest replay 都执行 `apply → activate → verify`；apply 只准备 candidate 与导入报告，activate 成功后才能验证公开可见性。rollback 目标先 apply 准备，再消费刚读回的 Content active release/digest/revision 作为 expected-current 三元组，成功后 verify；不从旧 verify、counts 或环境名猜 current。
- Exit 边界：canonical `environment_release_lifecycle_exit.schema.json` 的 original/replay run 槽绑定 activate 结果，其 import 前驱由 activation result 的 exact `importRunId` 追到 prepared apply；rollback 槽只绑定 rollback 结果。existing environment lifecycle verifier 是前驱及导入闭包的唯一检查点，Exit 补验阶段 kind、同环境、same-digest replay、distinct run IDs 与 canonical refs，不并列一套宽松验证。
- 就绪与配置边界：默认只有一套内容验证，不接受发布类别或命名 readiness 轨道；导入准备与可见性验证由已有生命周期动作和 exact 前驱区分。能力、观测、doctor 与运行隔离要求只消费显式环境配置，不在业务代码按环境名分流。完整 integration/release 验证单独声明 Exit evidence 需求，普通 managed/content-live 启动不强制 rollback/replay；Exit 只接受 original 或 replay 的精确 activation/verify 对，不只比较 import 身份。
- 理由与被否决方案：prepared apply 证明 stage 成功而不证明 CAS/公开可见，不能同时要求一个槽既为 apply 又为已 activated；不放宽 activated validator、不恢复 `--release-id` 隐式准入、不保留类别常量或选择参数，不通过 mock 跳过生命周期矛盾。
- 失败与恢复：任一 binding、CAS 或读回失败保留首个 typed blocker 和已完成原始结果，停止后续阶段；Exit create-once 且重算完整闭包。仅在现役 owner 命令允许且持有 exact 前驱时恢复，不手改 pointer、不重置环境，也不由本设计推导实际 Prod 执行授权。
- 可测试观察面：local_contract 覆盖无类别显式输入、环境配置、命令顺序、独立 Exit 要求、apply 不能充当 Exit activation、activation 到 prepared apply 的跨 release/run/digest 拒绝；api_integration 以真实 original/rollback/replay 和四入口 same identity readback 证明恢复。矩阵 aggregate 不代写 EAF 或 production authority。
- 关联要求与验收：[`environment-topology-and-packaging GWT-004`](./environment-topology-and-packaging/spec.md#gwt-004) 与 [`OPEN-018`](./environment-topology-and-packaging/spec.md#open-018)。
- 影响 Story：[`environment-topology-and-packaging`](./environment-topology-and-packaging/spec.md)；producer 完成不增加下游条件。

<a id="dec-006"></a>
### DEC-006 内容 source 在组合根选择，离线制品与在线配置分别验信

- 对象与 owner：canonical producer 拥有选定 release/cohort、许可与完整媒体闭包；App 只消费其不可变离线派生产物，不重选业务内容。Alpha 与在线是两个隔离的构建 composition，各自构造同一组 typed read ports；页面、domain/application、Provider 消费端不读取 source/profile。Alpha local adapter 与 Remote adapter 复用 canonical Post/Creator/实体投影，离线只发布 typed capability，不伪造服务 active identity。
- 构建隔离：在线入口传递 import/export/part（包括所有 conditional URI）及 path package 的 source closure 不得到达 Alpha adapter、bundle loader、fixture、Mock 或 test runner。production pubspec 不声明 Alpha 资产；Alpha 资产只可向 fresh 私有构建投影显式加入且保持 canonical snapshot exact bytes，禁止改 live pubspec、共享当前环境文件或借 runtime if/tree shaking 证明纯度。Beta/Gamma/Prod 消费同一真实业务/Remote 图，仅配置与既有信任域不同。构建门失败保留具体依赖链，禁止签发纯度成功。
- direct 投影身份：fresh repository projection 保留兄弟 path package 布局，记录原仓 audited Git identity 与逐文件 source digest；签发前重验原仓 Git identity、投影 source bytes 和投影 pubspec，不把 private 目录伪装为 Git worktree 或 immutable candidate。canonical immutable capsule 路径继续使用其既有验证，不由 direct 投影取代。
- 同源构建探针：需要 Alpha/Remote 同源对照时，只 capture 一次两个入口闭包的并集及构建输入，封存逐文件摘要和 audited Git identity 的只读 source manifest，再从该冻结目录分别派生两份可写 projection。派生和编译身份回读只校验冻结 manifest/exact bytes，不重新读取 live 字节或要求 live HEAD 不变；两份投影交集 source digest 必须完全相等。冻结 source manifest 只证明本地 build probe，不成为 package input capsule、candidate 或发布 authority；live 漂移只另报 currentness。
- 平台与入口交接：隔离 composition 入口必须先由 canonical launch metadata/codegen 声明，原生自供给仅对 Alpha 隔离产物有效；在线产物不得隐式嵌入 Alpha signed document。未迁移入口/native/purity 的闭包明确阻断，不能把新增投影函数或 source contract PASS 当作已构建制品。包身份、trust envelope、在线 expiry、activation/CAS/readback 不因构建隔离改变或绕过。
- Command/query：构建准备完整 snapshot 并验证 digest/引用/许可，由独立 signed offline bootstrap document 绑定；离线与在线 document 共用 canonical activation/CAS/receipt/read chain，只有文档类型的验证合同不同，不另建 bootstrap reader。AppContentSource 的 typed 取值只消费 [`App launch manifest`](../../../../quwoquan_service/contracts/metadata/_shared/app_launch_manifest.yaml) 的 source 策略，Dart/wire 映射不在设计复制。source 在 provider scope 创建前冻结，显式换环境结束设备绑定、取消旧请求/播放器/outbox，再冷启动或重建整个 scope，不修改旧 client base。
- 读取生命周期边界：启动级 rehearsal/auth/store/platform 初始化保留现有启动合同规定的执行次数；独立 read-generation factory 只构造本代 immutable catalog 与 read adapters，并返回精确绑定本代的 disposer。真实 `RuntimeRecoveryHost` 创建 R0、恢复为 R1、切 source 与 root disposal 均通过这一生命周期拥有并释放本代读取资源；不得以重新执行 bootstrap 或 rehearsal install 获取新 adapter，也不得复用 R0 静态 adapter 作为 R1。
- 目录身份与缓存：每个业务 generation 的 catalog 同时绑定 runtime identity、manifest pin、AssetBundle 实例 identity 与 generation，完整验证成功后才可在本代保留不可变目录及共享读取 flight；不得保留媒体全集。该设计将 adapter 已有的成功缓存集中为显式生命周期缓存，不是 static 全局永久缓存。任一身份改变均构造新代，不能只比较 manifest digest 而跨 bundle/runtime/generation 复用。
- 命中与释放：每次成功缓存命中、flight 结果发布和 adapter 返回前先检查本代 fence。disposer 只能使自己的 generation 失效并释放自己的目录/flight 引用；旧 disposer 重入或旧 flight 迟到完成不得清除、发布到或污染新代。root disposal 后不得残留可用读取缓存；共享 flight 的单个消费者取消只终止该消费者等待，不取消其他消费者或污染成功目录，整代 disposal 则阻断该代全部迟到结果。
- 完整性与失败：首次完整校验仍受既有 6 秒总预算约束，不以缓存改为延迟校验或放宽 deadline。失败、timeout、失效代结果不保存成功；重试从当前有效代的正常校验路径进入。目录成功命中不能替代媒体消费时的实际字节 hash 验证，媒体字节不因目录可信而免检。恢复不跨 source 回退或重新运行启动级初始化。
- 生命周期测试 seam：真实 `RuntimeRecoveryHost` 的 R0→R1、切源、root disposal 测试直接观察 factory/disposer 调用与旧 adapter 拒绝，不以手工调用 dispose 的替身代替根接线；分别改变 runtime identity、manifest pin、AssetBundle identity、generation，验证新旧隔离；用受控 flight 检验消费者取消、旧结果迟到及旧 disposer 不伤新代，用失败/timeout 与媒体篡改注入验证不缓存失败及逐次媒体 hash。public-media/rehearsal 未注入同一 scope 时明确只覆盖已接入的 read adapters，不宣称全部读取入口完成。真实设备 cold start 与 6 秒实测仍须独立 UAT。
- 关联增量验收：[`environment-topology-and-packaging GWT-009`](./environment-topology-and-packaging/spec.md#gwt-009)；未实现、未接线与设备冷启动证据归该 Story 的 [`OPEN-019`](./environment-topology-and-packaging/spec.md#open-019)。
- 信任与时间：离线完整性由独立 signed offline document、制品签名、source digest 和许可共同承担，不继承在线 24 小时到期；不能靠忽略在线 expiry 实现离线。在线 endpoint trust、profile、target、签名与新配置有效期不豁免。尚有效在线配置在刷新失败时保留，到期按 canonical 错误恢复，不能用离线包续命；同 authority 刷新保留授权 namespace。
- 验收装配：现役 `app-content-uat` 在编排边界按 canonical source 分流前置与测试集；页面和 application 不增加环境开关。`TargetUatBinding` 与 raw `ReadinessCaseResult` 用互斥的 source authority 表达离线制品/快照或在线 release/activation，复用 exact ref/digest、create-once 和设备/runner 绑定。离线不得填造在线字段，Remote 不因离线分支放宽验签、有效期、登录或 CAS/readback。
- 准出消费：同一 Alpha candidate 同时要求 Android/iOS 离线页面逐 case 执行事实和独立服务/API 事实。汇总器只检查身份、覆盖与 required 状态，不根据 suite 退出码、启动日志、首屏或服务回读补写页面 PASS；模拟器 raw result 不形成生产真机资格。
- 一致性：封存推荐/频道与 premium 选择、稳定对象/详情引用和本地 continuation，同 cohort 参数化证明过滤/空态/分页/去重/取消/重试等价，不复制个性化引擎。媒体以显式本地交付类型进入统一图片/播放器边界，不把 file/asset 假装 HTTPS 或签名 grant。
- 失败与恢复：不完整首装包在构建期阻断；升级只在新闭包全部验证后切换，失败保持旧完整快照。在线失败从不切离线。永久离线仅接受可公开离线再分发许可，需要即时撤权的内容禁止进入；真实网络、OTP、push 与在线 outbox 返回明确不可用，不假写远程成功。App 可达能力的本地演练由 [`DEC-007`](#dec-007) 拥有。
- 理由：统一用户可观察行为而非强迫同一传输，既使首次离线可用，也不把离线结果冒充在线健康或授权。
- 被否决方案：all-Remote、失败切 Mock/fixture、把视频全集当 premium、页面按 Alpha 分支、伪造 server active receipt、三套 nonprod 包名、动态换旧 client base、全局放宽签名 expiry 或永久离线即时撤权承诺。
- SLI/SLO 与测试 seam：分别计离线冷启动/浏览和在线推荐/premium、媒体首帧/播放/seek、stale 与恢复；沿用端侧 6 秒终态和既有在线 timeout/retry，不把目标记为实测。local_contract 比较同 cohort 两 adapter、完整性和到期边界；api_integration 证明 Remote identity/媒体闭包；user_acceptance 在四默认入口无后端首装、跨配置到期与升级故障中证明页面/播放器。线上 SLO 冲突在 OPEN-020 裁决前不得判绿。
- 关联要求：[`environment-topology-and-packaging REQ-008`](./environment-topology-and-packaging/spec.md#req-008)。
- 关联验收：[`GWT-007`](./environment-topology-and-packaging/spec.md#gwt-007)，未实现和未测保持该 Story 的 OPEN-019/020。
- 影响 Story：[`environment-topology-and-packaging`](./environment-topology-and-packaging/spec.md)。

<a id="dec-007"></a>
### DEC-007 Alpha 本地演练按对象级 adapter 闭环，身份与 Remote 凭据分离

- 对象边界：runtime-config 只拥有组合根接缝、演练空间隔离、凭据拒绝与制品纯度。业务事实、分页、权限投影与脚本会话归各 object owner；本 DEC 不把它们收成中央模拟执行器。
- Command/query：Alpha composition 安装对象级本地 executor/handler；页面不判断环境。command 原子提交 overlay 后 query 读回。canonical snapshot 只读。共享演练空间按 source+snapshot digest+instance 分区，actor 私有分区绑定 account/persona/device。
- 隔离请求准入：显式 isolated UAT 必须沿既有 canonical launch/config source 验证空间绑定，在任何 auth、pending OTP、rehearsal 的 read/write/delete（包括恢复时清坏记录及安装标识初始化）之前完成。三类存储只消费同一绑定派生的 namespace；缺失、错配或未接线不得回退 default、unbound、旧 target|env 或安装级 OTP 键。普通 Alpha 未提出 isolated 请求时保留现有默认空间启动行为；两类意图由 canonical source 区分，不能因 isolated 参数缺失把它误判为普通启动。内部授权理由不进入业务 wire，不另造授权台账或 receipt。
- 现役 control 与签名前校验：isolated 的 producer/launcher 交接只扩展同一 `quwoquan_ops.app_content_uat_launch_control.v1`，不创第二授权协议；空间选择限定已批准的 mode/instanceId/snapshotDigest，candidate/device/attempt 复用原身份。普通未请求 isolated 的 Alpha 不以 control 缺失阻断 standard/default，显式 isolated 无 control/选择、错配或在线 source 则在 signing material 准备及文档签名前拒绝。校验必须把私有 control 的 exact ref/digest、实际调用 target/device/attempt、candidate/source revision/capsule/projection evidence 的身份及精确引用/摘要交叉绑定，不能只分别自校各文档 hash。snapshot pin 从可信 source projection/capsule 制品输入取得，不从待签 document 或 runner 期待推断；签名后 resolver 再消费已批准 rehearsalSpace wire，不添加人类理由。control 不签发人工授权，创建空间权限保持既有用户/受管调用边界，不以 authorized 标志扩权；字段闭集由 canonical authoring 唯一拥有。本地私有签名材料矩阵验证正反例，真实密钥、设备及实际三存储 readback 不在该局部证明内。
- 唯一 namespace 算法：公共纯配置投影 `runtime/config/rehearsal_storage_namespace.dart` 只接受 resolver 实际验签构造的 `VerifiedRehearsalSpace`，拒绝 standard/default，捕获其对象 identity 并在存储调用前验证 currentSpace 相同。auth namespace 与 pending OTP key 保持既有 source/snapshot/instance 确定性派生字节，installId 独立派生隔离键而不触达全局 auth.install_id；同空间新验签对象派生相同键但旧投影必须拒绝新对象。Alpha verified binding 只委托公共投影，不复制散列算法；仅内部未验签纯值构造不能取得共享 namespace。普通 standard Alpha/在线原键语义不变，公共投影不导入 Alpha 实现、不暴露 runtime 或密钥、不提供 runner 字符串构造入口。
- 空间纯逻辑边界：在 Alpha-only 内核提供不执行 I/O 的显式空间验证，并将已验签 namespace 派生委托上述公共投影；绑定同时约束所选 source、snapshot 和 instance，isolated 请求的期望空间必须与已消费 canonical source 一致且不得等于普通 default 空间。存储适配器构造时拒绝绑定与 envelope/persistence namespace 不同，不能等旧空间读后才判断。当前仅纯逻辑接缝不签发信任或 runner authority，接线 owner 必须先提供已验证输入；共享 auth/OTP 消费该绑定的 typed 投影，不能反向导入 Alpha 实现进在线制品。
- 真实空间 readback：AUT 仅从已被实际存储消费的绑定发布经 privacy owner 分类的非敏感空间观察，不能回显 runner 期望字段作为成功证明。重启保留空间和 snapshot，生成新的 launch attempt/PID；隔离证明以私有测试存储旧空间 sentinel 验证 read/write/delete 全零及新空间恢复，真实旧空间不允许探测、迁移、清理或用作测试材料。只观察 rehearsal 文件分区不代表 auth/pending OTP 全链隔离。
- 存储观察边界：由实际 owner 维护当前实例的非资格性只读投影，配置未观察/已验证/失效与四 consumer（auth/installId/pending OTP/rehearsal）的未观察/构造/成功 I/O/失效分开；仅在实际 read/write/delete 成功且再次 fence 通过后更新已观察操作集合。读取投影不得调用任何初始化、exists/read/write/delete 或清坏记录，不影响 startup 或业务状态。桥接只消费实际 owner 的同进程/启动 generation/attempt 身份，不从 runner expected 或 actor fence 推导；无法可靠关联或未装配时返回不可用，失效不输出旧摘要作当前事实。由 launch authoring 在现有启动通道声明受治理只读方法/模型，与 recordStartupEvent/readStartupJournal 隔离，不假定 native 可直接访问 Dart。
- 观察隐私与authority：namespace/binding 摘要属于 INTERNAL，普通日志/遥测 drop，仅用于受控 isolated 私有设备证据；摘要按用途隔离，输入无账户、真实 installId、完整key/path，不输出未知键、自由文本、account/persona/challenge/request/session/payload。它不扩 SyntheticLoginEvidence/reject 白名单、不创建 isolationPassed 或资格receipt/台账；正向投影不能证明过去从未触达旧空间，私有 sentinel 与实际 gateway 审计分别必需。未有桥接/采集/审计证据则保持 OPEN-021，不授予设备、密钥或真实空间访问权限。
- 合成身份 owner 边界：明确非电话 namespace 与 Alpha-only typed challenge port 的安全语法、校验及公开流程由登录 owner 冻结，沿同一业务登录流程在组合根装配，不建万能 transport。不将非法标识塞入 phone、不放宽在线 phone 校验、不伪造 OTP 或 creator 归属。canonical privacy owner 必须先裁决仅本地且不能用于真实认证的合成标识/模拟 challenge 如何公开作为证据；真实 phone/OTP 的 drop 规则不变，未获安全分类则返回设计阻断，不修改日志采集规避。
- 启动级合成装配与双提交：standard 保留原本地 OTP 装配；isolated 在任何依赖构造与存储访问前消费实际 VerifiedRehearsalSpace/currentSpace，返回绑定同一 store 的 typed composition，不能重跑 read-generation 初始化或安装标准手机号演练端口。synthetic complete 只原子提交挑战消费/本地身份/幂等结果，AuthController.applySyntheticSession 单独提交 auth 身份；两者不是跨库事务，后者失败时只允许原显式用户意图同 request 重放结果再申请 auth 提交。isolated 启动恢复只以 auth store 为会话 authority；synthetic restore 是持久结果查询，不允许自动补写 auth。logout 后保留演练业务身份与幂等事实不等于恢复授权，旧请求的自动重试必须由 UI/auth owner 的意图 generation 取消，若该接缝未证明则保持 OPEN-021，不能把 auth clear 当成 synthetic store clear。
- 隔离可测试观察面：missing/mismatch/default 污染在任何存储调用前拒绝；auth/pending OTP/rehearsal 同 binding namespace；旧空间 read/write/delete sentinel 不触达；新实例同空间恢复、不同空间隔离、损坏空间不得清另一个空间。尚未跨 owner 接线及真实 AUT readback 时保持 OPEN-021，局部 PASS 不代替允许 runner 开始创建身份。
- 身份：演练身份命名空间独立；`isAuthenticated` 可在无 Remote bearer 时成立，HTTP/header factory 拒绝 `rehearsal.` 凭据。OTP 只出现在演练 UI 通道。challenge 绑定请求 owner、手机号、过期时间、已消费标记和失败尝试数；身份使用持久分配 ID，不以进程 hashCode 派生。错误尝试计数与成功消费均经存储事务。
- 事务：每次操作在串行队列内创建独立深拷贝工作空间；handler 的嵌套 commit 只修改该事务，状态、actor/operation/request 幂等响应与待发布本地事件作为单一 envelope 经可靠事务或 flush 后同目录 atomic replace 持久化，成功后才发布内存快照。decoder 与取消/fence 校验在持久提交之前执行。普通覆盖写与临时文件后再次覆盖目标不是原子实现，不支持原子能力的 gateway 必须拒绝写入。
- 代际：操作捕获 space/actor fence；reset 在入队时使旧请求失效，并串行提交重置后的新 generation。失败 reset 不删除已提交事实；恢复明确校验 envelope 格式、snapshot 与 instance。助手流逐事件重新核对 run/session owner、取消和代际，不能持旧 Map 引用走到 completed。
- 覆盖：对象 handler 注册表是实际 dispatch 与 covered IDs 的同一来源，默认/generic wire 不构成实现。目录分别呈现声明、descriptor 与实际绑定，并拒绝 localId 歧义；未完备能力保持 unsupported 与全量覆盖门禁失败。GraphQL 只将已匹配名称/摘要的生成 descriptor 分发到对应实现，bundle 失败向上传播。
- 故障测试 seam：延迟/失败持久化、decoder 抛错、取消与 reset 交错、跨 actor 同幂等键、重启损坏 envelope、OTP 到期/重用/错误尝试、助手中途取消和跨 owner 流均由 local_contract 直接执行；这些证据不替代双端 UAT 或真实 provider。
- 失败恢复：未 install rehearsal 时 bundled source 仍 fail-closed 拒绝 HTTP。写盘失败、损坏、取消与迟到结果不得伪造成功。重置递增 generation 并取消在途读写。
- 被否决方案：假登录、删 guard、万能 operation-ID Map、把演练 token 发给 Remote、跨 source 混读、把本地终态送进联网 outbox、把 Alpha 脚本打进在线包。
- 可测试观察面：能力闭包双向比较、身份持久/重置、关注赞评消息搜索助手读写、HTTP 拒绝 rehearsal token、在线制品 source closure。
- 关联要求：[`REQ-009`](./environment-topology-and-packaging/spec.md#req-009)
- 关联验收：[`GWT-008`](./environment-topology-and-packaging/spec.md#gwt-008)

## 5. 失败与恢复

- mutation 的目标 operation fence、使用租约、运行/内容身份或设备 ownership 不满足时写前 fail closed；默认 Alpha 离线校验不要求云侧 health，在线 freshness 不为离线例外放宽。
- fault active、原 release 未恢复或任一平台 CaseResult 缺失时，父 report 只能失败；已有原始结果保持 append-only，不覆盖、不补写。
- 回滚只使用进入窗口前冻结的 immutable release、runtime receipt 与 target topology，不依赖重新 package、重新 build 或当前工作树。

## 6. 质量与观测

- 成本增加为每个本地 target 固定的小型验收窗口：两个模拟器与一次受控 Edge 窗口；不随 M100/M1000 对象总量线性放大。release lifecycle/rollback/replay 继续作为独立证据，不由该窗口隐含完成。
- Edge 与原 release 的恢复目标均为 5 分钟内完成；任何验收退出时 active fault 数必须为零，runtime health 必须通过，原 release readback 必须与进入前 digest 相同。
- SLI 直接读取 stackctl create-once run result、target CaseResult、fault cleanup、health 与 release lifecycle/readback；告警以未清理 fault、恢复超时、digest 漂移或平台结果缺失为触发，不维护第二份状态台账。
- 目标验收覆盖 Alpha 离线与 Beta/Gamma Remote 的双模拟器，均保持 nonPromotable；服务 Edge/empty/replay 由独立 Alpha API gate 与 Beta/Gamma 验证。尚未执行的任一平台、真机、正式 Green 或 Prod 保持对应 OPEN，不使用已实现时态或另一环境的结果代填。

### 启动与恢复证据分层映射

| Environment | Platform / entrypoint | 行为与验收锚点 | `local_contract` | `api_integration` | `user_acceptance` / 证据源 |
| --- | --- | --- | --- | --- | --- |
| Alpha/Beta/Gamma | Android/iOS：`make app-dev` → `stackctl dev-session --launch-app --app-mode` → `run.sh`，以及 direct `run.sh`、packaged Debug | `app-dev` 只提供人类一键薄入口，默认 Alpha/content-live 并委托 canonical device authority；完整 runtime package 得到 `configurationState=complete`；[`GWT-002`](./environment-topology-and-packaging/spec.md#gwt-002)、[`UAT-003`](../../spec.md#uat-003) | Make 参数/default/多设备拒绝、无第二状态与 launcher/handoff/identity suites | 真实 stackctl 委托与 immutable projection 的 profile 编译、package identity、install/launch receipt；结果按 compile/package/install/attach/safe-terminal 分段 | `run.sh` 是 required human surface；Android Emulator/登记真机与 iOS Simulator/登记 iPhone 观察冷启动、Hot Restart、图标启动和安全终态原始 CaseResult，VM attach 不替代同制品 safe terminal |
| Alpha | Android/iOS：raw SDK、受管字面 `flutter run`、IDE、run.sh | 同一默认离线 source 与完整性校验；[`GWT-007`](./environment-topology-and-packaging/spec.md#gwt-007) | 同 cohort typed ports、媒体闭包、到期边界、设备绑定与入口等价 | 真实制品派生/安装与 source digest；不以离线结果签 API activation | 无后端、断网、无预热首装及再次冷启动的首页/premium/详情/播放/seek；不要求云栈或登录 readiness |
| Alpha/Beta/Gamma | Android/iOS：受控制 IDE attach（`workspace_ide_debug`） | required human surface；pre-launch 进入同一 executor，IDE 只连接 attempt-scoped VM service；[`GWT-002`](./environment-topology-and-packaging/spec.md#gwt-002)、[`UAT-003 install-launch-equivalence`](../../spec.md#install-launch-equivalence) | projection 生成/回退、profile、pre-launch/attach 状态、超时与错误码契约 | canonical executor 产出 compile/install/activation/launch/attached 分段 receipt，IDE 不生成第二 handoff | Reload 后从受控制 profile 启动并完成真实 attach，结果与同设备 `run.sh`/字面命令行为指纹一致 |
| Alpha/Beta/Gamma | Android/iOS：`make app-uat` → `stackctl app-content-uat` | AI/自动化无交互薄入口，仅接受 nonprod local targets；按 canonical contract 编排而不替代 required human surfaces；[`GWT-002`](./environment-topology-and-packaging/spec.md#gwt-002) | 参数闭集、Prod 拒绝、无交互/无第二状态、父 report 无 verdict | 真实 app-content-uat 委托、iOS attempt-1/retry frozen Pod binding、raw refs/digests/coverage exact readback | 每个 target/platform/device 结果来自 canonical raw `ReadinessCaseResult`；父 report 只读且不签发 outcome，自动化结果不替代 `run.sh`、受管字面 `flutter run` 或 IDE 用户验收 |
| Prod | Android/iOS：Release package、`prod-sim`/`prod-hosted` | Debug 禁止、exact artifact、签名与纯度 fail closed；[`GWT-001`](./environment-topology-and-packaging/spec.md#gwt-001)、[`GWT-003`](./environment-topology-and-packaging/spec.md#gwt-003) | Prod Debug 拒绝、manifest/identity/purity、测试依赖泄漏负例 | Android Release artifact 与 iOS unsigned iphoneos compile；签名、安装和 hosted 前置逐层记录 | 只消费已授权 exact Release artifact；缺正式 ID、签名、市场账号、真机或授权的单元保持 `OPEN-002/003`，不得由 simulator/package-only 代替 |
| Alpha/Beta/Gamma/Prod | Web：`package --kind web`、`app-artifact --app-platform web`、`dev-session` | 单一 Web 编译 writer、exact manifest/current 投影、静态恢复面不依赖 API 健康；[`GWT-001`](./environment-topology-and-packaging/spec.md#gwt-001)、[`public-content-web-entry GWT-006`](../runtime-client-foundation/public-content-web-entry/spec.md#gwt-006) | Web bootstrap 状态机、authoring source/codegen、单 writer 与 manifest digest 契约 | exact artifact 的 HTML/字体 HTTP status、UTF-8、MIME、digest、缓存/Service Worker；API plane 关闭时静态恢复面仍可读 | Chrome/Safari 的字体 200、慢载、404、首次离线、缓存离线和 SW 更新；四环境公网缺口继续由 `public-content-web-entry OPEN-004` 承接 |
| Alpha/Beta/Gamma/Prod | 原生 fatal recovery → 官方 Web CTA | CTA 打开本环境 exact origin 且中文可读；[`UAT-003`](../../spec.md#uat-003)、[`public-content-web-entry GWT-006`](../runtime-client-foundation/public-content-web-entry/spec.md#gwt-006) | fatal 注入状态机、canonical URL 与单一恢复动作 | 恢复 URL 的 HTTP 200、UTF-8、字体/HTML digest 与 artifact manifest 绑定 | 真正点击 CTA 后的浏览器页面、中文像素、键盘可达与恢复动作；`UIApplication.open`/Intent 成功本身不计通过 |

所有 CaseResult 只按 [App launch manifest 的 canonical attempt schema](../../../../quwoquan_service/contracts/metadata/_shared/app_launch_manifest.yaml) 与 [App artifact manifest](../../../../quwoquan_service/contracts/metadata/_shared/app_artifact_manifest.yaml) 绑定同一冻结 source/capsule、制品、启动证据与本次 attempt，Design 不复制字段表。静态门禁、真实编译、package、install/VM attach、同制品 startup safe terminal、runtime health 和用户可见终态分别报告，前一层不得替代后一层。
