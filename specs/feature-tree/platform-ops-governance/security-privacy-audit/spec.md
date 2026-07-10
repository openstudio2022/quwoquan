# L2 特性：security-privacy-audit

## 功能说明

面向首发上架与持续运营的安全与隐私合规收口能力。覆盖发布前必须就绪、并在运营期持续审计的关键合规面：

- 法律文本：隐私政策、用户协议、权限用途说明、第三方 SDK 共享清单，均由 `legal-static` 独立静态包发布，有可达 URL 与版本号（与登录页 `agreementVersion/privacyVersion` 对齐）。当前免费社区版本为 `2026-07`，历史 `2026-06` 保持不可变。
- 权限最小化：仅申请主旅程必需权限；每项权限有明确用途说明（双端商店审核要求）。
- 第三方 SDK 清单：列出 SDK 名称、用途、收集的数据类别、共享对象（含 iOS PrivacyInfo.xcprivacy / Android 数据安全表单口径）。
- 数据主体权利：账号注销、数据导出、撤回同意的可达入口。
- 备案：ICP 备案、算法备案（推荐为算法驱动，需备案）。
- 治理闭环：内容/用户举报与拉黑可真实提交并处置（内容级与用户级均接 Remote）。
- 审计留痕：危险动作 / 双签动作 / 放量动作经统一审计事件可检索（对齐 ops-portal 审计）。

## 约束

- 法律文本与版本是上架硬阻断项；`/legal/user-agreement`、`/legal/privacy-policy`、`/legal/permissions`、`/legal/third-party-sdk-list` 任一 URL 不可达即 No-Go。
- 协议正文不得放入业务领域服务代码，不随 App、service、内容页或数据工程内容包一起打包；唯一源目录为 `quwoquan_service/services/legal-static/`，发布包为 `.qwq_output/env/<env>/release/legal-static/<version>/`。
- alpha / `flutter run` 的 mock gateway 必须同样挂载 `legal-static` 的 `/legal/*` 静态目录，禁止回退到 mock 404 HTML 或业务 API mock 路由。
- 隐私相关文案与同意版本以 `auth_legal_config.dart` + 登录契约为准，不得在业务代码硬编码第二套版本。
- 协议页 URL 不可达、HTTP 非成功或 WebView 资源失败时，App 必须展示原生错误态与重试/返回动作；该错误不阻断用户返回登录页、勾选协议与继续验证码登录。
- 权限用途、SDK 数据类别必须与端侧实际行为一致，禁止低报或漏报。
- 错误码 / 用户文案走 metadata→codegen，不在审计/治理代码硬编码（R06）。
- 生产包默认 Remote、无 Mock/Remote 切换入口、无 test_fixtures（与 `08-mock-data-isolation` 发行态一致）。

## 验收标准（A1~A8 重点组）

- A1 法律文本：隐私政策 / 用户协议 / 权限说明 / SDK 清单由 `stackctl package --env <env> --kind legal-static` 独立打包，URL 全部 200 可达，版本与登录契约一致，prod 前完成 gamma 探测。
- A2 权限最小化：申请权限集 = 主旅程必需集；每项有用途说明。
- A3 第三方 SDK：清单完整，iOS PrivacyInfo.xcprivacy 与 Android 数据安全表单口径一致。
- A4 数据主体权利：账号注销 / 数据导出 / 撤回同意入口可达且生效。
- A5 备案：ICP + 算法备案确认有效。
- A6 治理闭环：内容级与用户级举报 / 拉黑可真实提交并进入处置队列（用户级已接 Remote）。
- A7 审计留痕：危险/双签/放量动作可在审计视图检索，保留 actor / env / 时间。
- A8 发行纯净：生产包无 Mock 切换入口、无 test_fixtures、默认 Remote。

## 登录与账号商用 Go/No-Go 口径

当前状态：`No-Go`，除非下列阻断项均形成端云实现与 local_contract-user_acceptance 证据，否则不得进入商用发布：

- 账号注销 / 恢复申诉 / 锁定态：必须具备 App 可达入口、后端状态机、冷静期或立即注销策略、撤销路径、客服 handoff 与结构化错误。
- 数据主体权利：数据导出、撤回同意、隐私设置留痕必须可达且可审计；设置页可以展示阻断说明，但 release 包不得只保留“待接入”空壳。
- 法律文本与同意记录：登录页携带的 `agreementVersion/privacyVersion` 必须落 consent record，并能按 owner 查询；法律 URL 与版本必须通过 `legal-static` 发布包校验和发布前探测。
- 账号安全审计：凭证绑定/解绑、最后一个凭证保护、多设备退出、异常登录、账号注销/恢复、拉黑/举报等危险动作必须产生统一审计事件。
- 发行纯净：prod 包默认 Remote，无 Mock 切换入口，无 test fixtures、seed/reset 或调试开关泄漏。

最小证据包：

- local_contract：`make verify-app-auth-policy`、`stackctl verify --env gamma --kind legal-static`、错误码/法律版本/权限清单静态校验。
- local_contract：`quwoquan_app/test/local_contract/ui/settings/pages/settings_page_appearance__local_contract_test.dart`、登录门/会话恢复 Widget 与 Provider 测试。
- api_integration：user-service `auth_contract_test.go` / `credential_contract_test.go` / `persona_contract_test.go` 以及 App RemoteRepository contract。
- user_acceptance：Patrol 或真机证据覆盖首次登录、OTP/一键登录、退出登录、会话过期重登、账号注销/撤销、数据导出/撤回同意。
