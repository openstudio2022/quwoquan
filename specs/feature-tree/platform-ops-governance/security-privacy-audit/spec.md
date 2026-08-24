# L2 Business Capability：安全隐私审计 (`security-privacy-audit`)

> 所属领域：[`platform-ops-governance`](../spec.md)
>
> 设计归属：[L1 DEC-001](../design.md#dec-001)

## 1. 能力目标

统一发布前与运营期的权限、隐私、审计和供应链检查

## 2. 范围与非目标

### In Scope

- 由本目录 Story 组合交付“security-privacy-audit”的独立业务结果。

### Out of Scope

- 其他 L2 的事实所有权、metadata schema 与实现施工步骤。

## 3. Journey / Scenario 贡献

- 横切工程能力：不直接拥有 AppRoot Scenario；调用本能力的业务领域仍承担对应 Journey 的产品责任。
  - 本能力处理：统一发布前与运营期的权限、隐私、审计和供应链检查。
  - 本能力输出：可供业务领域组合的公开结果与明确失败终态。

## 4. Story



- [`compliance-reporting`](./compliance-reporting/spec.md)：从法律版本、权限用途、SDK 清单和危险动作审计事实生成可复核报告。
- [`data-classification-policy`](./data-classification-policy/spec.md)：在 canonical contract 中声明数据类别、保留、加密与访问边界，未知敏感度默认拒绝发布。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 security privacy audit 能力 SIT

- 本能力必须组合直属 Story 与公开契约，交付“统一发布前与运营期的权限、隐私、审计和供应链检查”所定义的业务结果；失败终态必须可区分且不得伪造成功。
- 法律正文通过 legal-static 独立包发布，不依赖 App 包、service 包、内容发布包或数据工程内容包。
- stable URL 与 manifest currentVersion 一致，版本 URL 不可变，prod 发布前先完成 gamma legal-static 探测。
- alpha / flutter run Remote public plane 可直接访问 `/legal/user-agreement`、`/legal/privacy-policy`、`/legal/permissions`、`/legal/third-party-sdk-list`，不得回退 fixture/mock API 路由。
- 协议 URL 不可达或返回非成功状态时，App 展示原生错误态、提供重试和返回，不暴露 raw HTTP/WebView 错误页，且不阻断登录协议勾选与验证码登录流程。

<a id="req-002"></a>
### REQ-002 法律文本、权限用途说明和第三方 SDK 共享清单由 `legal-static` 不可变版本包发布

- 法律文本、权限用途说明和第三方 SDK 共享清单由 `legal-static` 不可变版本包发布；可达 URL 和版本号必须与登录页 `agreementVersion/privacyVersion` 对齐。
- 审计留痕：危险动作 / 双签动作 / 放量动作经统一审计事件可检索（对齐 ops-portal 审计）。
- 法律文本与版本是上架硬阻断项；`/legal/user-agreement`、`/legal/privacy-policy`、`/legal/permissions`、`/legal/third-party-sdk-list` 任一 URL 不可达即 No-Go。
- 协议正文不得放入其他业务领域服务代码，不随 App、内容页或数据工程内容包一起打包；唯一源目录为 `quwoquan_service/static/legal/`，发布包为 `QWQ_DEPLOY_WORK_ROOT/<target>/packages/legal-static/<version>/`。
- alpha / `flutter run` 的 Remote gateway 必须挂载 `legal-static` 的 `/legal/*` 静态目录，禁止回退到 fixture 404 HTML 或业务 API mock 路由。
- 隐私相关文案与同意版本以 `auth_legal_config.dart` + 登录契约为准，不得在业务代码硬编码第二套版本。
- 协议页 URL 不可达、HTTP 非成功或 WebView 资源失败时，App 必须展示原生错误态与重试/返回动作；该错误不阻断用户返回登录页、勾选协议与继续验证码登录。
- 权限用途、SDK 数据类别必须与端侧实际行为一致，禁止低报或漏报。
- 账号注销 / 恢复申诉 / 锁定态：必须具备 App 可达入口、后端状态机、客服 handoff
- 数据主体权利：数据导出、撤回同意、隐私设置留痕必须可达且可审计；设置页可以展示阻断说明，但 release 包不得只保留“待接入”空壳。

## 6. 契约与依赖

- 上游能力：[`platform-ops-governance`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 security privacy audit 能力 SIT

- GIVEN 执行“security privacy audit 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“security privacy audit 能力”对应动作。
- THEN 直属 Story 共同交付“统一发布前与运营期的权限、隐私、审计和供应链检查”，失败终态可区分且不产生伪成功事实。
- THEN 法律正文通过 legal-static 独立包发布，不依赖 App 包、service 包、内容发布包或数据工程内容包。
- THEN stable URL 与 manifest currentVersion 一致，版本 URL 不可变，prod 发布前先完成 gamma legal-static 探测。
- THEN alpha / flutter run Remote public plane 可直接访问 `/legal/user-agreement`、`/legal/privacy-policy`、`/legal/permissions`、`/legal/third-party-sdk-list`，不得回退 fixture/mock API 路由。
- THEN 协议 URL 不可达或返回非成功状态时，App 展示原生错误态、提供重试和返回，不暴露 raw HTTP/WebView 错误页，且不阻断登录协议勾选与验证码登录流程。
- THEN 对外分发的 web/android 描述文件必须绑定到 release 已登记的同一 build product，产物内容摘要与描述文件本身被篡改时分发都失败关闭。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 security privacy audit 能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：统一发布前与运营期的权限、隐私、审计和供应链检查。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 上架合规正文、签名与商店材料

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：未获法务确认的正文、备案、正式签名、全尺寸图标、商店截图与审核说明会直接阻断 iOS/Android 上架。
- 完成判定：`SIT-001` 的 legal-static 发布与 URL/版本可达行为满足——法律正文和 SDK/权限清单经法务确认并由 legal-static 发布
- 正式 AAB/IPA 签名与商店材料完整
- 测试账号可走通 AppRoot UAT。
- 依赖：法务、设计、运营、渠道账号与签名 secrets。

<a id="open-003"></a>
### OPEN-003 对外分发描述文件缺少文件级完整性锚点

- 类型：`risk`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：ReleaseEvidence 迁到 canonical build product 编址后，`applicationPackages` 登记的是产品通用包，对外分发的 web/android 描述文件改由 `publicWeb`、`androidOfficialRelease` 两个 descriptor 承载，而这两项不在 release manifest 的顶层字段闭集内。`deploy_official_distribution` 只拿得到 release manifest，因此现在只能绑定产物内容摘要（`contentSHA256`/`apkSHA256`）与 `buildProductId`。后果是篡改描述文件中不进产物摘要的字段——例如把 `apkUrl` 指向另一台主机——不会被这一层发现，只剩 `apkHostAllowlist` 兜底。
- 完成判定：`SIT-001` 的对外分发完整性子句满足——分发描述文件的文件级摘要在 release manifest 内可达，且有负例证明仅篡改下载地址即失败关闭。
