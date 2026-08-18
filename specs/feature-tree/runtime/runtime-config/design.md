# L2 Design：运行时配置 (`runtime-config`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：环境 topology、release lifecycle、双平台 App 会话、受控故障与失败恢复形成跨进程状态机，需要统一 command/query owner、锁、观测与回滚边界。

## 1. 背景、目标与非目标

- 设计目标：让同一环境与同一服务端状态下的配置、启动、内容 identity 和恢复动作可比较，并让 Alpha 双模拟器证据不被父 report 提升为 promotion 事实。
- 非目标：复制 URL/端口、创建 Alpha 专用数据源、实现长期内容库、定义 App 业务对象，或把 Beta/Gamma/Prod 与真机证据并入此设计范围。

## 2. Story 协作与状态流

- [`config-provider-layering`](./config-provider-layering/spec.md) 提供唯一配置分层与有效值。
- [`environment-ops-cli-and-skill`](./environment-ops-cli-and-skill/spec.md) 提供 stackctl command、只读状态和 create-once run result。
- [`environment-topology-and-packaging`](./environment-topology-and-packaging/spec.md) 组合 target resolver、consumer lease、release lifecycle、双平台 CaseResult 与故障恢复。

## 3. 端云与数据流

- 本设计不新增业务 aggregate。环境 operation 是由 stackctl 独占推进的 process。
- target-scoped CaseResult、runtime receipt 与 release lifecycle/readback 是各自 append-only 的观察事实，不承载内容对象。
- 写路径只经 stackctl：环境 release apply/rollback/replay 由现有 release command 推进，App 验收由 `app-content-uat --targets alpha-local` 推进，受控 Edge target 只能操作当前 runtime receipt 绑定的精确 Compose project/container。
- 读路径只读取 topology resolver、只读 status、release lifecycle/readback 与 target-scoped CaseResult。App 从 Content API 响应读取 release identity；父 report 只能引用原始结果，不得重写为 Alpha-only aggregate 或 promotion passed。
- endpoint、证书、package identity、Compose project 与容器身份只来自 `quwoquan_ops/environments` 和 stackctl 产物；测试 target 不定义第二套 URL、端口或 runtime identity。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 Alpha 内容验收以三个可恢复窗口编排原始 CaseResult
- 决策：Alpha 验收按正向 active release、独立 empty-baseline、active suite 内受控 Edge 5xx 三个窗口执行。
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
### DEC-002 App 原生包身份由静态 flavor/scheme 在构建图解析前选择

- 决策：`app_artifact_manifest.yaml` 是 environment × BuildMode 包身份与显示名的唯一值真相源。
- 投影：确定性 codegen 将真相源投影为 Android productFlavor 与 iOS environment-specific xcconfig。
- 入口选择：Flutter CLI 使用同名 flavor，Xcode Run/Profile/Archive 使用提交的 shared scheme 与 `Debug|Profile|Release-<environment>` configuration。默认 flavor 固定为 Alpha。
- 决策：App identity 投影是只读构建输入。`run.sh`、stackctl 与 IDE profile 只选择 flavor/scheme 并校验 canonical handoff，不生成或改写共享“当前环境”文件。
- 构建边界：原生 build phase 不拥有 application/bundle ID、显示名、签名或 capability 的写入权。
- 理由：Xcode 在执行 build phase 前已经解析 `PRODUCT_BUNDLE_IDENTIFIER` 等 build settings。构建中刷新共享 xcconfig 只能影响下一次构建，导致首次环境切换失败，并在同 checkout 并发时产生跨环境覆盖。
- 被否决方案：共享 `QWQEnvironment.xcconfig`、修改 `Generated.xcconfig`、build phase 自愈后要求重试、以 `--dart-define` 反向决定原生 identity、按当前工作树动态写 Xcode project，以及以 clean/DerivedData 删除掩盖身份漂移。
- 失败恢复：flavor、scheme、handoff、target、environment 或 BuildMode 任一不一致时必须在编译/安装前返回 typed blocker，且不得写入源码树。重新选择一致 flavor 即可重试，不依赖修复上一次构建遗留状态。
- 可测试观察面：local_contract 比对 metadata 与全部生成 identity、Xcode scheme/configuration/Podfile 和 Gradle variant。
- 可测试观察面：平台构建集成执行无 clean 的 `alpha → beta → gamma → alpha` 首次成功与独立 worktree 并发。
- 可测试观察面：user_acceptance 回读 Android/iOS 安装身份、runtime package、Hot Restart 与图标冷启动指纹。
- 关联要求：[`environment-topology-and-packaging/REQ-003`](./environment-topology-and-packaging/spec.md#req-003)、[`REQ-004`](./environment-topology-and-packaging/spec.md#req-004)
- 关联验收：[`environment-topology-and-packaging/GWT-002`](./environment-topology-and-packaging/spec.md#gwt-002)、[`GWT-003`](./environment-topology-and-packaging/spec.md#gwt-003)

## 5. 失败与恢复

- 环境 operation lock、consumer lease、runtime identity、release identity、设备或 health 任一不满足时均在写前 fail closed。
- fault active、原 release 未恢复或任一平台 CaseResult 缺失时，父 report 只能失败；已有原始结果保持 append-only，不覆盖、不补写。
- 回滚只使用进入窗口前冻结的 immutable release、runtime receipt 与 target topology，不依赖重新 package、重新 build 或当前工作树。

## 6. 质量与观测

- 成本增加为固定的小型 Alpha 验收窗口：两个模拟器、一次 empty/original lifecycle 和一次受控 Edge 窗口；不随 M100/M1000 对象总量线性放大。
- Edge 与原 release 的恢复目标均为 5 分钟内完成；任何验收退出时 active fault 数必须为零，runtime health 必须通过，原 release readback 必须与进入前 digest 相同。
- SLI 直接读取 stackctl create-once run result、target CaseResult、fault cleanup、health 与 release lifecycle/readback；告警以未清理 fault、恢复超时、digest 漂移或平台结果缺失为触发，不维护第二份状态台账。
- rollout 只从 Alpha 两个模拟器开始且固定 `nonPromotable=true`。Beta/Gamma、Android 真机、正式 Green 与 Prod 保持对应 OPEN 和人工门，不能由本 DEC 推导通过。
