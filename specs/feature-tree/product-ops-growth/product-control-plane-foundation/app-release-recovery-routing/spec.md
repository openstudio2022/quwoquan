# L3 Story：应用发布恢复路由 (`app-release-recovery-routing`)

> 所属能力：[`product-control-plane-foundation`](../spec.md)
>
> Journey / Scenario：[`JNY-002 / SCN-005`](../../../spec.md#scn-005)
>
> 设计归属：[L2 DEC-002](../design.md#dec-002)

## 1. 用户价值

作为无法启动或继续使用应用的用户，
我希望系统可靠判断本机是否已有更新，并从官方渠道获取与平台匹配的版本，
从而避免无效更新、第三方 APK 和版本错配。

## 2. 范围与非目标

### In Scope

- iOS、Android 两个平台唯一已发布版本事实。
- 公开版本查询、通用官网下载页、Android APK 下载端点和 iOS PWA 安装指引。
- User-Agent 平台识别、Build 数值比较、受信 URL 校验和下载失败终态。
- Android APK 生产签名、不可变 CDN 对象、SHA-256 与 latest 指针发布门禁。
- `stackctl package --kind app-release` 生成发布清单、Product Ops 版本事实环境配置，并可选对已上传 CDN 对象做全量摘要、大小、Content-Type 和 immutable 缓存校验。
- `stackctl deploy --artifact-kind web|app-release` 只消费同一候选 `ReleaseManifest` 已绑定的子清单，以 CAS 原子切换 Web `current` 或 Android `latest.json`；`stackctl verify --kind distribution` 与 `stackctl inspect --scope release` 只读复核本地发布根及可选公网响应。

### Out of Scope

- 发布渠道、最低支持版本、复杂更新模式、灰度客户端分支或第三方应用商店。
- 应用内 APK 下载器、增量包、热更新、公众 iOS IPA 与 iOS 企业分发。
- 根据 User-Agent 判断客户端是否最新；最新版判断只使用客户端显式提交的 Build。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 版本查询只返回平台当前发布事实

- 查询只接收 `platform`、`appVersion`、`buildNumber`，其中 platform 只允许 `ios` 或 `android`，Build 必须是正十进制整数。
- 响应只包含 `latestVersion`、`latestBuild`、`updateUrl`、`recoveryUrl`。
- 远端 Build 大于当前 Build 表示有新版；远端 Build 小于或等于当前 Build 表示当前已是最新。
- 请求失败或响应非法不得生成版本结论。
- iOS 与 Android 发布事实按平台独立校验和可用；一个平台的发布材料缺失不得使另一平台的官方通道下线。

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
- Web、Android、Portal、ContractGraph、Provider binding 与三层 CaseResult 摘要必须被同一 `mainline-release-artifact` 摘要引用；缺少任一引用时正式 deploy 与 prevalidate 均返回 `GATE_BLOCK`。

## 4. 契约引用

- canonical：`quwoquan_service/services/product-ops-service/contracts/product_ops/app_release/operations.yaml`
- canonical：`quwoquan_service/services/product-ops-service/contracts/product_ops/app_release/fields.yaml`
- canonical：`quwoquan_service/services/product-ops-service/config/schema.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 平台识别和版本判断一致

- GIVEN iOS、Android、鸿蒙与桌面 User-Agent，以及当前 Build 小于、等于或大于已发布 Build 的请求。
- WHEN 用户访问官网下载页或客户端查询版本。
- THEN 页面按平台推荐 PWA、官方 APK 或平台选择，版本接口只按对应平台 Build 返回同一已发布事实。

<a id="gwt-002"></a>
### GWT-002 Android 官网完成受信 APK 下载

- GIVEN 发布流水线已上传并验证生产签名 APK，latest 指针已原子切换。
- WHEN Android 用户打开官网更新地址。
- THEN 浏览器从白名单 HTTPS CDN 下载包名、Build、证书摘要和 SHA-256 均与发布记录一致的 APK；未知地址、调试签名或校验不一致均被发布门禁拒绝。

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
- 完成判定：`GWT-002` 使用生产签名和官方 CDN 真文件通过，iOS PWA 由正式 Safari 安装并以 standalone 模式启动。
- 依赖：移动端发布 Secret、官方 CDN、Web 部署与 DNS/TLS。
