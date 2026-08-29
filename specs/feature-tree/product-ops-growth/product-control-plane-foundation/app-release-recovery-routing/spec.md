# L3 Story：应用发布恢复路由 (`app-release-recovery-routing`)

> 所属能力：[`product-control-plane-foundation`](../spec.md)
>
> Journey / Scenario：[`JNY-002 / SCN-005`](../../../spec.md#scn-005)
>
> 设计归属：[L2 DEC-002](../design.md#dec-002)

## 1. 用户价值

作为无法启动或继续使用应用的用户，
我希望系统可靠判断本机版本是最新、可更新还是必须更新，并从官方渠道完成更新或恢复，
从而避免无效更新、第三方 APK 和版本错配。

## 2. 范围与非目标

### In Scope

- Android、iOS、Web 各平台唯一的 latest 与 minimum supported 已发布版本事实。
- 公开版本查询、通用官网下载页、Android APK、公众 iOS 官方 Web/PWA 恢复入口和 Web 强制刷新/恢复入口；App Store 安装渠道事实独立登记，不复用公众启动恢复的 `updateUrl`。
- User-Agent 平台识别、Build 数值比较、受信 URL 校验和下载失败终态。
- Android APK 生产签名、不可变 CDN 对象、SHA-256 与 latest 指针发布门禁。
- Apple App Store/TestFlight 与已登记 Android 受信市场（华为、小米、OPPO、vivo、应用宝）的渠道事实：channelId、store product 标识、当前 version/build、上架状态与回退方式。
- `stackctl package --kind app-release` 生成发布清单、Product Ops 版本事实环境配置，并可选对已上传 CDN 对象做全量摘要、大小、Content-Type 和 immutable 缓存校验。
- `stackctl deploy --artifact-kind web|app-release` 只消费同一候选 `ReleaseManifest` 已绑定的子清单，以 CAS 原子切换 Web `current` 或 Android `latest.json`；`stackctl verify --kind distribution` 与 `stackctl inspect --scope release` 只读复核本地发布根及可选公网响应。

### Out of Scope

- 领域模型版本、兼容握手、灰度客户端契约分支。
- 未登记的应用商店、来源不明 APK 与可变同名安装包。
- 应用内 APK 下载器、增量包、热更新、公众 iOS IPA 与 iOS 企业分发。
- 根据 User-Agent 判断客户端是否最新；最新版判断只使用客户端显式提交的 Build。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 版本查询只返回平台当前发布事实

- 查询只接收 canonical contract 声明的 platform、App Version 与 Build，其中 platform 只允许 `android`、`ios` 或 `web`，Build 必须是正十进制整数。
- 响应使用 canonical contract 返回平台、latest Version/Build、minimum supported Version/Build、`updateState`、平台允许的官方更新与恢复 URL；公众 iOS 的 `updateUrl` 必须为 `null` 且 `recoveryUrl` 只能指向官方 Web/PWA，App Store 渠道地址不得借该字段下发。不得返回领域模型版本或兼容协商信息。
- 当前 Build 大于或等于 latest Build 时 `updateState=none`。
- 当前 Build 不低于 minimum 且低于 latest 时 `updateState=available`；低于 minimum 时 `updateState=required`。
- 请求失败或响应非法不得生成版本结论。
- Android、iOS 与 Web 发布事实按平台独立校验和可用；一个平台的发布材料缺失不得使另一平台的官方通道下线。

<a id="req-002"></a>
### REQ-002 官网按平台自动分流

- 通用 `/download` 与 `/download/mobile` 使用显式 platform、Client Hint、浏览器平台信息和 User-Agent 识别 iOS、Android/鸿蒙或桌面，识别只决定推荐内容。
- iOS 显示官方 PWA 安装指引，Android/鸿蒙显示趣我圈官方 APK 下载动作；二进制只能由用户明确点击下载。
- 桌面显示 Android 下载与 iOS PWA 两个明确入口。
- 无法可靠识别时显示平台选择，不自行猜测或下载。

<a id="req-003"></a>
### REQ-003 Android 下载必须对应正式发布二进制

- `/download/android` 只重定向当前发布事实中的 HTTPS APK URL，目标域名必须在服务端白名单。
- APK 必须以不可变对象键发布，且发布记录的包名、Build、版本、签名证书摘要、文件大小和 SHA-256 与二进制一致。
- Android release 构建在未提供生产 keystore 时必须失败，不得使用 debug 签名生成可发布包。
- latest 指针只能在上传、可下载探测和签名/摘要校验全部通过后切换；发布失败继续保留上一已验证版本，不产生新版事实。
- APK 不可变对象、`latest.json` 与 Product Ops app-release 环境配置必须在同一分发事务中绑定相同 Build 和 SHA-256；任一 CAS 冲突或写入失败不得覆盖上一版本，历史 APK 不删除。

<a id="req-004"></a>
### REQ-004 地址安全与缓存一致性

- 所有页面、接口和 APK 地址必须使用 HTTPS；iOS PWA 和 Android 下载页只允许趣我圈官方 Web 域名，Android APK 仅允许趣我圈官方 CDN 白名单。
- 版本查询和下载重定向使用 `no-store`；APK CDN 对不可变对象使用长期 immutable cache。
- 非法远程配置必须使服务启动失败或该平台发布事实不可用，不得回退第三方地址。
- Web、Android、Portal、ContractGraph、Provider evidence 与三层 CaseResult 摘要必须被同一 canonical `ReleaseEvidenceManifest` candidate digest 引用；缺少任一引用时正式 deploy 与 prevalidate 均返回 `GATE_BLOCK`。

<a id="req-005"></a>
### REQ-005 最低支持 Build 与可完成恢复路径

- 最低支持 Build 按 Android、iOS、Web 平台独立配置，是平台级兼容政策；不得按领域对象、用户、stable/candidate 服务池或灰度阶段分别配置。
- 低于 minimum 的普通业务请求由 API Edge 返回 HTTP 426 和 canonical `client_upgrade_required` failure；版本查询、更新下载、恢复页、官网及完成更新所必需的认证入口必须保持可访问。
- `available` 时 Android 提示或使用官方 flexible update，公众 iOS 启动恢复只提供官方 Web/PWA，Web 提示刷新；`required` 时 Android 进入阻断更新页，公众 iOS 进入只提供官方 Web/PWA 的恢复页，Web 清除旧 service-worker/cache 并强制加载当前发布，仍不满足时进入恢复页。
- 独立登记且已就绪的 iOS App Store 渠道只可用于普通安装/更新引导，不得进入公众启动恢复 `updateUrl`；其更新必须服从系统和 App Store 能力，不得承诺或实现绕过系统的静默安装。Android 只有在平台和用户设置允许时才可执行静默更新。

<a id="req-006"></a>
### REQ-006 Minimum 提升门禁与原子投影

- 提升 minimum 前必须先运行只观测不阻断的 `would_block`，并证明旧版本活跃安装占比连续 30 天低于 0.1%、正常支持不少于 12 个月、对应平台的更新和恢复通道可真实完成；安全事件只能经高风险审批例外提升。
- 正式提升由同一环境发布包原子更新 Product Ops 权威事实与 API Edge 只读投影，并校验 source digest 一致；任一目标写入或回读失败不得形成新 minimum 成功事实。
- latest 与 minimum 的历史 App Version/Build 分布、`would_block` 命中数、426 数量和恢复结果必须按平台可观测；App 版本仅用于用户更新体验、兼容门和灰度 audience，不向领域模型版本或端侧迁移状态继续扩展。

<a id="req-007"></a>
### REQ-007 受信分发渠道事实单一真相源

- 每个平台的受信安装渠道集合只由 `app_release` 发布事实声明。
- iOS 受信原生安装渠道为 Apple App Store，TestFlight 仅用于内测轨；公众启动恢复通道固定为官方 Web/PWA，且不返回原生安装地址。
- Android 受信安装渠道为官网 CDN APK 与已登记受信市场（华为、小米、OPPO、vivo、应用宝）。
- Web 受信安装渠道为官方 PWA。
- 未在发布事实登记的渠道不得出现在任何查询响应或页面。
- 每个市场渠道声明 channelId、store product 标识、该渠道当前已上架 version/build、上架状态与回退方式；一个渠道审核未过或下架不得使其他渠道的发布事实不可用。
- Android 恢复页“前往更新”固定走官网 HTTPS CDN 下载；市场渠道只用于更新引导（跳转本机安装来源对应市场的详情页），不作为恢复页下载源。
- 官网 APK 的 `androidApkUrl`、`androidApkSha256`、`androidPackageName`、`androidSigningCertificateSha256` 是恢复页、更新提示与官网/网页版安装转化组件共用的唯一真相源，禁止任何组件持有第二份下载配置或硬编码地址。
- 市场上传、审核与发布回执按渠道独立登记为 install-channel 事实；缺少某渠道账号、凭据或审核回执时该渠道保持 `GATE_BLOCK/OPEN`，不得以另一渠道回执替代。

## 4. 契约引用

- canonical：`quwoquan_service/services/product-ops-service/contracts/product_ops/app_release/operations.yaml`
- canonical：`quwoquan_service/services/product-ops-service/contracts/product_ops/app_release/fields.yaml`
- canonical：`quwoquan_service/services/product-ops-service/config/schema.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 平台识别和版本判断一致

- GIVEN iOS、Android、Web、鸿蒙与桌面入口，以及当前 Build 分别低于 minimum、位于 minimum/latest 之间、等于或高于 latest 的请求。
- WHEN 用户访问官网下载页或客户端查询版本。
- THEN 页面按平台推荐官方更新或恢复入口，版本接口只按对应平台 Build 返回 `required`、`available` 或 `none`，且与同一已发布事实一致。

<a id="gwt-002"></a>
### GWT-002 Android 官网完成受信 APK 下载

- GIVEN 发布流水线已上传并验证生产签名 APK，latest 指针已原子切换。
- WHEN Android 用户打开官网更新地址。
- THEN 浏览器从白名单 HTTPS CDN 下载包名、Build、证书摘要和 SHA-256 均与发布记录一致的 APK；未知地址、调试签名或校验不一致均被发布门禁拒绝。

<a id="gwt-003"></a>
### GWT-003 低于 minimum 的客户端可完成更新或恢复

- GIVEN Android、iOS、Web 客户端 Build 低于各自 minimum，且更新、恢复和必要认证入口已通过真实环境检查。
- WHEN 客户端访问普通业务 operation 或执行版本恢复流程。
- THEN 普通业务请求收到 426 与 canonical 恢复动作，版本查询和官方更新/恢复链路不被该门阻断；完成更新后客户端可重新进入正常业务面。
- AND minimum 提升前的 `would_block`、30 天活跃安装比例、12 个月支持窗口、发布包原子更新及 source digest 回读均有不可变证据，否则保持上一 minimum。

<a id="gwt-004"></a>
### GWT-004 受信市场渠道路由与回执

- GIVEN `app_release` 发布事实已登记 iOS App Store 与五个 Android 受信市场的渠道事实，其中部分渠道可能未就绪。
- WHEN 客户端或官网查询平台安装/更新路由，或发布流水线登记某渠道的上传、审核与发布回执。
- THEN 查询只返回该平台已登记且就绪的受信渠道，并遵循以下路由。
  - Android 更新引导按本机安装来源匹配市场渠道，恢复页下载仍固定官网 CDN。
  - 独立的 iOS 原生安装/更新引导只跳转 App Store；公众启动恢复查询的 `updateUrl` 为 `null`，只返回官方 Web/PWA recovery URL。
- AND 每个渠道的上传、审核、发布与真机安装回执独立登记；未就绪渠道显式保持 `GATE_BLOCK/OPEN`，不阻塞其他渠道，也不得由其他渠道回执替代。

## 6. 依赖

- 前置要求：[`product-control-plane-foundation`](../spec.md) 的范围、要求与 SIT。
- 协作 Story：[`cold-start-performance`](../../../runtime/runtime-client-foundation/cold-start-performance/spec.md)、[`public-content-web-entry`](../../../runtime/runtime-client-foundation/public-content-web-entry/spec.md)。
- 父级设计：[L2 DEC-002](../design.md#dec-002)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 正式发布材料与 CDN 外部阻断

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：仓库已禁止 Android release 回退 debug signing，但当前仍没有生产 keystore Secret、经正式域名/CDN 上传并校验的 APK 对象以及四环境 Web DNS/TLS，无法形成可对外宣称的正式下载事实。
- 完成判定：`GWT-002` 使用生产签名和官方 CDN 真文件通过，公众 iOS 恢复通道由真实 iPhone 打开官方 Web/PWA，Web PWA 由正式浏览器安装并以 standalone 模式启动；`GWT-004` 的独立 App Store 与五个 Android 受信市场渠道分别绑定真实上传、审核、发布与真机安装回执，未就绪渠道保持显式阻断且不得改变公众 iOS `updateUrl=null` 的事实。
- 依赖：移动端发布 Secret、官方 CDN、Web 部署与 DNS/TLS、各市场开发者账号与审核。

<a id="open-002"></a>
### OPEN-002 三平台 minimum 更新与恢复能力证据缺口

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前实现尚未证明 Android、iOS、Web 使用同一权威 latest/minimum 投影形成 `none/available/required`，也未形成 426 例外、`would_block`、支持窗口和真实更新/恢复闭环证据；不得把本次规格刷新宣称为已支持。
- 完成判定：`GWT-001`、`GWT-003` 的对应行为满足，复合结果子句均由真实 `local_contract`、`api_integration` 与 `user_acceptance` 精确绑定。

<a id="open-003"></a>
### OPEN-003 应用市场渠道查询与回执契约缺口

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前 canonical `app_release` 只有公众版本恢复投影，没有 install-channel 查询、channelId/store product、渠道状态或上传/审核/发布/真机安装回执 contract，也没有对应 readiness case；因此不得宣称 App Store、TestFlight 或五个 Android 市场的渠道路由与回执已经具备。该缺口不改变公众 iOS `updateUrl=null` 与官方 Web/PWA 恢复的单轨行为。
- 完成判定：`GWT-004` 的每条结果子句都有所属 canonical install-channel authoring contract、真实 operation/receipt schema、逐渠道 readiness case 与上传、审核、发布、真机安装回执；公众恢复投影继续不暴露 iOS 原生安装地址。
- 依赖：应用市场产品标识与账号、渠道发布流水线、审核 API/回执、Android/iPhone 实体设备。
