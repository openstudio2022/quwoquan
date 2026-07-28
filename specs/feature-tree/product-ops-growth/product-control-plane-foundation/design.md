# L2 Design：产品运营控制面基础 (`product-control-plane-foundation`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“统一产品事件、实验、反馈优化与发布治理”需要 `app-release-recovery-routing` 与 `product-control-plane-contract` 共享发布事实、受信地址和审计边界。

## 1. 背景、目标与非目标

- 设计目标：统一产品事件、实验、反馈优化与发布治理。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`app-release-recovery-routing`](./app-release-recovery-routing/spec.md)：读取每个平台唯一已发布版本，并把公众 iOS PWA、Android 官网 APK 和通用恢复页投影为公开只读恢复结果。
- [`product-control-plane-contract`](./product-control-plane-contract/spec.md)：每个控制面动作必须声明 operation scope；危险动作必须记录操作者、目标、原因、revision 与结果，失败时不得生成成功审计。

## 3. 端云与数据流

- 上游能力：[`product-ops-growth`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 产品控制面统一承接治理处置与增长策略工作流
- 决策：产品控制面统一承接治理处置与增长策略工作流。
- 理由：统一产品事件、实验、反馈优化与发布治理。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`app-release-recovery-routing`](./app-release-recovery-routing/spec.md)、[`product-control-plane-contract`](./product-control-plane-contract/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- `ops.*` 与端侧 IA / 体验配置的关系。
- 按用户 / 人群 / 实验灰度。
- 用于表达 `ops.*` 业务配置。
- 超过 SLA 必须进入工作台告警。

<a id="dec-002"></a>
### DEC-002 官网只分发经过发布门禁的不可变 Android APK
- 决策：Android 正式 APK 由发布流水线使用生产密钥签名、验证包名/Build/证书摘要和 SHA-256 后上传到官方 CDN 的不可变对象键。产品运维配置只在对象可下载且校验一致后原子切换 latest 指针。官网下载端点只重定向该已确认对象。公众 iOS 只返回官方 PWA 安装与网页版地址，已认证且设备已登记的内测成员才可使用受控 Ad Hoc 通道。
- 理由：版本查询、官网页面和二进制必须共享同一发布事实，避免页面显示新版但下载到旧包、调试签名包或第三方地址。
- 被否决方案：运行时扫描对象存储猜测最新版、覆盖同名 APK、在应用内下载并安装、Android 跳第三方商店、使用 debug 签名发布、公众 iOS 跳 App Store 或分发 IPA。
- 约束与影响：正式签名材料只由 CI Secret 注入。服务端和客户端仅接受 HTTPS 白名单，下载失败不得回退到未知镜像。
- 关联要求：`REQ-001`
- 影响 Story：[`app-release-recovery-routing`](./app-release-recovery-routing/spec.md)
- 关联验收：`SIT-001`
