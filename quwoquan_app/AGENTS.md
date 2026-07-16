# quwoquan_app Codex Guide

在 `quwoquan_app/` 工作时，除仓库根 `AGENTS.md` 外，默认补读仓库根 `.cursor/rules/` 下的以下规则：

1. `.cursor/rules/02-dart-coding.mdc`
2. `.cursor/rules/01-arch-constraints.mdc`
3. `.cursor/rules/08-mock-data-isolation.mdc`
4. `.cursor/rules/10-runtime-error-cutover.mdc`

按触达范围追加：

- 触及 `lib/ui/**/pages/**` 或 `lib/app/shell/*.dart`：补读 `.cursor/rules/09-page-horizontal-quality.mdc`
- 触及登录入口、登录成功/关闭回退路径：补读 `.cursor/rules/15-auth-entry-no-loop.mdc`
- 触及平台差异、Web/鸿蒙能力：补读 `.cursor/rules/14-cross-platform-portability.mdc`
- 触及 `lib/components/pageflip/**` 或 `lib/ui/content/article_reader/pageflip/**`：补读 `.cursor/rules/11-pageflip-geometry-guardrails.mdc`；若为 BACK 方向，再补读 `.cursor/rules/12-pageflip-backward-mainline.mdc`

## App 端硬约束

- UI 不得硬编码颜色、间距、字号、交互热区、中文文案；统一走 `AppColors`、`AppSpacing`、`AppTypography`、`UITextConstants`/`l10n`。
- UI、`lib/app/**`、`lib/core/**` 不直连 mock 目录，也不直接实例化 Mock/Remote Repository。
- Repository、route、surface、operation、错误码、decoder context 以 metadata/codegen 为真相源。
- 结构化错误统一走 `RuntimeFailure`、`RuntimeRecoveryPolicy`、runtime mapper；不要回退到原始字符串异常。
- 用户可见错误提示必须来自 codegen 错误枚举、`toDisplayMessage(context.l10n)`、`UITextConstants` 或 l10n；禁止在 UI/Provider 中 switch 硬编码错误码字符串或中文提示。
- `CloudException` 必须由 runtime mapper 生成并暴露 `runtimeFailure`；UI 状态只消费 `RuntimeFailure`、`runtimeErrorDisplayMessage` 和 `RuntimeRecoveryPolicy`，不得展示 raw exception/debugMessage。
- 新页面或页面行为变化，要同步核对页面横向质量矩阵、metadata-driven UI 清单与相关测试。
- App 端必须按 `alpha/beta/gamma/prod` 数据源语义开发：alpha 走 contract-seeded Mock，beta/gamma/prod 走 Remote，生产包无 Mock/Remote 切换入口。
- 新页面、入口、详情、搜索、创作、消息或推荐相关改动，必须补曝光、停留、异常、关键点击、`referralSource`/`feedRequestId`/trace 传递；内容消费页还要补消费深度和互动反馈。
- 用户反馈、点赞/评论/收藏/分享/关注、搜索点击、内容停留等行为必须能回流到推荐和运营分析，不得只停留在 UI 状态。
- 当前阶段未上线：发现不合理 UI/Repository/Provider/路由实现时直接替换为正确模式，不为旧错误保留兼容分支、fallback 或 allowlist。

## 错误体验与观测

- 每个用户可见错误都必须有提示、恢复动作和观测语义：提示用户发生了什么，恢复动作告诉用户下一步能做什么，观测记录 code/operation/surface/recovery/disruption/requestId/traceId。
- 权限、登录、网络、限流、服务不可用、数据校验、第三方依赖失败要有不同 UI 语义和恢复按钮，不得统一显示“出错了”。
- 登录返回账号摘要遵守“文本稳定、头像渐进增强”：头像仅在可信图片成功解码后显示；空值、加载中或失败时必须零占位、零间距、零头像语义，不得生成轮廓、首字、品牌图标或文字 fallback，昵称与脱敏账号提示不依赖头像。
- 登录入口必须区分返回会话与运营商能力：返回账号只有“具体账号线索 + 可立即执行恢复动作”同时成立才展示，主动作称“继续登录”；运营商入口只有 vendor/token/有效期完整正向证明后才展示，否则静默进入手机号验证码，不允许通过点击后的失败探测能力。
- 短信验证码发送成功后折叠大号手机号输入框，仅保留脱敏发送摘要和“更换手机号”；错误卡不得复制页面主按钮已经承担的恢复动作。
- 页面级错误要同时覆盖空态/错误态/权限态/加载态；可恢复错误提供重试或目标动作，不可恢复错误提供安全返回或联系支持路径。
- 错误埋点不得泄露 PII/SECRET/debug detail；用户看到的是本地化提示，日志/telemetry 看到的是结构化 code 与脱敏 context。

## 典型触发与 E2E

- 用户说“页面、登录、搜索、创作、消息、错误提示、恢复按钮、推荐曝光、行为反馈”时，默认加载本文件。
- 若同时涉及服务错误码、Remote API、数据导入、推荐反馈或环境发布，必须启用 `docs/agent_context_contract.md` 的跨域 E2E 模式。
- App 不得单独完成端云链路：`api_integration` Remote 行为必须能回到 `local_contract` Mock/Widget/Provider 断言。

## Review 与测试要求

- 每次改动都要按产品、架构、代码评审、质量、测试、用户、运维、运营八角色自检。
- `local_contract` 覆盖 metadata/codegen/静态规则、provider/widget/Mock 行为；`api_integration` 覆盖 Remote/API/真实存储或集成环境；`user_acceptance` 覆盖用户旅程、权限、弱网、性能或发布前 UAT。
- Remote 行为的 `api_integration` 断言必须在 `local_contract` Mock/Widget/Provider 测试中有对应断言；Mock 不是替代集成测试，而是集成行为的本地分解。
- 错误码链路的 `local_contract` 必须覆盖 mapper、Provider 状态、UI 文案、恢复按钮和 Mock 错误响应；`api_integration` 必须覆盖 RemoteRepository 对服务错误响应的映射。
- 新增页面必须同步检查页面矩阵、P1-P8、metadata-driven UI 清单、Mock 隔离、设计系统语义 token 和登录无死循环。

## 推荐验证

- 改 Dart 文件后读取最近改动文件的 lint。
- 页面/壳层改动：执行 `make verify-app-page-horizontal-quality`。
- 改动 runtime error 契约相关代码：执行 `dart quwoquan_ops/tools/runtime_error_codegen/bin/check_runtime_error_cutover.dart`。
- 根据触达范围跑对应 `flutter test`，必要时再跑 `bash quwoquan_ops/gate/gate_repo.sh --scope app`。
- 涉及环境、包纯度或部署验证时，使用 `python3 quwoquan_ops/cli/stackctl.py package/verify/health/inspect`，不要手写第二套 URL、端口或拓扑。
