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
- 公开版本查询、通用官网下载页、Android APK 下载端点和 iOS App Store 跳转。
- User-Agent 平台识别、Build 数值比较、受信 URL 校验和下载失败终态。
- Android APK 生产签名、不可变 CDN 对象、SHA-256 与 latest 指针发布门禁。

### Out of Scope

- 发布渠道、最低支持版本、复杂更新模式、灰度客户端分支或第三方应用商店。
- 应用内 APK 下载器、增量包、热更新与 iOS 企业分发。
- 根据 User-Agent 判断客户端是否最新；最新版判断只使用客户端显式提交的 Build。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 版本查询只返回平台当前发布事实

- 查询只接收 `platform`、`appVersion`、`buildNumber`，其中 platform 只允许 `ios` 或 `android`，Build 必须是正十进制整数。
- 响应只包含 `latestVersion`、`latestBuild`、`updateUrl`、`recoveryUrl`。
- 远端 Build 大于当前 Build 表示有新版；远端 Build 小于或等于当前 Build 表示当前已是最新；请求失败或响应非法不得生成版本结论。

<a id="req-002"></a>
### REQ-002 官网按平台自动分流

- 通用 `/download` 与 `/download/mobile` 根据 User-Agent 识别 iOS、Android/鸿蒙或桌面。
- iOS 只重定向官方 App Store 产品页；Android/鸿蒙只重定向趣我圈官方 APK 下载端点；桌面显示两个明确入口。
- 无法可靠识别时显示平台选择，不自行猜测或下载。

<a id="req-003"></a>
### REQ-003 Android 下载必须对应正式发布二进制

- `/download/android` 只重定向当前发布事实中的 HTTPS APK URL，目标域名必须在服务端白名单。
- APK 必须以不可变对象键发布，且发布记录的包名、Build、版本、签名证书摘要、文件大小和 SHA-256 与二进制一致。
- latest 指针只能在上传、可下载探测和签名/摘要校验全部通过后切换；发布失败继续保留上一已验证版本，不产生新版事实。

<a id="req-004"></a>
### REQ-004 地址安全与缓存一致性

- 所有页面、接口和 APK 地址必须使用 HTTPS；iOS 仅允许 Apple 官方域名，Android APK 仅允许趣我圈官方 CDN 白名单。
- 版本查询和下载重定向使用 `no-store`；APK CDN 对不可变对象使用长期 immutable cache。
- 非法远程配置必须使服务启动失败或该平台发布事实不可用，不得回退第三方地址。

## 4. 契约引用

- canonical：`quwoquan_service/services/product-ops-service/contracts/product_ops/app_release/operations.yaml`
- canonical：`quwoquan_service/services/product-ops-service/contracts/product_ops/app_release/fields.yaml`
- canonical：`quwoquan_service/services/product-ops-service/config/schema.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 平台识别和版本判断一致

- GIVEN iOS、Android、鸿蒙与桌面 User-Agent，以及当前 Build 小于、等于或大于已发布 Build 的请求。
- WHEN 用户访问官网下载页或客户端查询版本。
- THEN 页面按平台进入 App Store、官方 APK 或平台选择，版本接口只按对应平台 Build 返回同一已发布事实。

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
- 影响或价值：仓库当前 Android release 使用 debug signing，且没有生产 keystore Secret、正式 APK CDN 对象和 iOS App Store 产品 ID，无法形成可对外宣称的正式下载事实。
- 完成判定：`GWT-002` 使用生产签名和官方 CDN 真文件通过，iOS 正式产品页可访问。
- 依赖：移动端发布账号、CI Secret、官方 CDN 与 DNS/TLS。
