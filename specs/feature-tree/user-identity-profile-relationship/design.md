# L1 Design：用户身份画像与关系 (`user-identity-profile-relationship`)

> 对应规格：[L1 spec](./spec.md)

## 1. 背景与设计目标

- 设计目标：让用户以默认账号或明确选择的 Persona 安全进入应用、维护公开资料和设置、建立或解除关系，并在所有业务领域获得一致的主体与权限语义。

## 2. 领域模型与所有权

- authoritative ownership：拥有 `UserAccount`、`SubAccount/Persona`、资料快照、关注与拉黑关系、设备端点、用户设置和账号生命周期的写入决定权。
- write boundary：只能通过本领域公开 command 修改其拥有事实。
- 非本域对象：不拥有其他 L1 的事实；跨域协作必须使用对方公开 command、query、projection 或 event。
- 非本域对象：不复制 metadata 中的字段、path、错误码和 wire 语义。

## 3. 上下文边界与协作

- [`JNY-001 / SCN-004`](../spec.md#scn-004) — 在“欢迎、授权、商业登录、Persona 与原动作续接”中，维护 UserAccount、Persona、Profile、Follow/Block 与隐私事实，并公开身份和关系结果。
- [`JNY-003 / SCN-009`](../spec.md#scn-009) — 在“内容详情跳转作者主页”中，维护 UserAccount、Persona、Profile、Follow/Block 与隐私事实，并公开身份和关系结果。
- [`JNY-004 / SCN-001`](../spec.md#scn-001) — 在“写文字创建、可靠发布与结果回流”中，维护 UserAccount、Persona、Profile、Follow/Block 与隐私事实，并公开身份和关系结果。
- [`JNY-004 / SCN-002`](../spec.md#scn-002) — 在“照片创建、像素编辑、原图可靠上传与发布回流”中，维护 UserAccount、Persona、Profile、Follow/Block 与隐私事实，并公开身份和关系结果。
- [`JNY-004 / SCN-003`](../spec.md#scn-003) — 在“视频创建、转码处理、发布与结果回流”中，维护 UserAccount、Persona、Profile、Follow/Block 与隐私事实，并公开身份和关系结果。
- [`JNY-007 / SCN-012`](../spec.md#scn-012) — 在“1v1 私信与打招呼升级”中，维护 UserAccount、Persona、Profile、Follow/Block 与隐私事实，并公开身份和关系结果。
- [`JNY-007 / SCN-016`](../spec.md#scn-016) — 在“会话内音视频通话与离线来电可靠送达”中，维护 UserAccount、Persona、Profile、Follow/Block 与隐私事实，并公开身份和关系结果。
- [`JNY-009 / SCN-017`](../spec.md#scn-017) — 在“内容与页面上下文感知问答”中，维护 UserAccount、Persona、Profile、Follow/Block 与隐私事实，并公开身份和关系结果。

## 4. 架构与数据流

- [`auth-profile-snapshot`](./auth-profile-snapshot/spec.md)：认证、refresh token、owner/subAccount 快照与凭证管理的能力级 SIT 验收。
- [`onboarding-and-identity-entry`](./onboarding-and-identity-entry/spec.md)：负责从欢迎页、冷启动、未登录入口、登录中断恢复到登录后落点的完整身份进入链路。
- [`persona-follow-graph`](./persona-follow-graph/spec.md)：本能力统一分身生命周期、公开身份、关系隔离与跨域透传。
- [`profile-homepage-redesign`](./profile-homepage-redesign/spec.md)：统一个人主页的信息架构、状态模型与跨页面互动一致性。
- [`settings-and-device-token`](./settings-and-device-token/spec.md)：为已登录账号提供可真实读写的通知、隐私、通话、外观设置，并管理设备推送端点与登录凭证。
- [`user-service-cloud-delivery`](./user-service-cloud-delivery/spec.md)：让用户资料、统计、设置和关系状态由 user-service 持久化，并通过正式远端契约在 App 各页面一致展示和更新。
- 工程边界由 spec 的“工程归属”声明；设计不复制具体实现文件。

## 5. 关键决策

<a id="dec-001"></a>
### DEC-001 账号、Persona 与关系使用独立对象边界
- 决策：账号、Persona 与关系使用独立对象边界。
- 理由：让用户以默认账号或明确选择的 Persona 安全进入应用、维护公开资料和设置、建立或解除关系，并在所有业务领域获得一致的主体与权限语义。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 关联能力：[`auth-profile-snapshot`](./auth-profile-snapshot/spec.md)、[`onboarding-and-identity-entry`](./onboarding-and-identity-entry/spec.md)、[`persona-follow-graph`](./persona-follow-graph/spec.md)、[`profile-homepage-redesign`](./profile-homepage-redesign/spec.md)、[`settings-and-device-token`](./settings-and-device-token/spec.md)、[`user-service-cloud-delivery`](./user-service-cloud-delivery/spec.md)

## 6. 质量与运行约束

- 安全与隐私：凭证、会话和通讯录信息最小化存储，日志禁止记录 token 和原始联系人值。
- 一致性：账号与凭证强一致；关系计数和下游 projection 可最终一致但必须可重放。
- 可观测性：记录 operation、对象版本、授权拒绝、projection 延迟和 canonical error。
- 灰度与回滚：以服务 deployment 和 metadata 单轨版本为边界，不恢复旧 wire。

## 7. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：按 canonical recovery action 重试、刷新或回滚到上一份已验证配置。
- 禁止 fallback：不得使用 Mock、旧 wire、双读双写或跨域直写伪造成功。
