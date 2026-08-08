# L1 Domain Service：用户身份画像与关系 (`user-identity-profile-relationship`)

> 一句话定位：为用户提供账号、Persona、公开资料、关系图谱、设置与账号安全的唯一身份边界。

## 1. 目标与用户价值

让用户以默认账号或明确选择的 Persona 安全进入应用、维护公开资料和设置、建立或解除关系，并在所有业务领域获得一致的主体与权限语义。

## 2. 领域边界

### 本领域拥有

- 拥有 `UserAccount`、`Persona`、资料快照、关注与拉黑关系、设备端点、用户设置和账号生命周期的写入决定权。
- 只能通过本领域公开 command 修改其拥有事实。

### 本领域不拥有

- 不拥有其他 L1 的事实；跨域协作必须使用对方公开 command、query、projection 或 event。
- 不复制 metadata 中的字段、path、错误码和 wire 语义。

### 上下游协作

- 上游：AppRoot Journey 与公开输入事实。
- 下游：直接 L2 能力以及协作 L1 的公开结果。
- 跨域写入：目标领域公开 command；禁止直写目标存储。
- 跨域读取：目标领域公开 query/projection。

## 3. Journey / Scenario 职责

- [`JNY-001 / SCN-004`](../spec.md#scn-004)
  - 本领域负责：在“欢迎、授权、商业登录、Persona 与原动作续接”中，维护 UserAccount、Persona、Profile、Follow/Block 与隐私事实，并公开身份和关系结果。
  - 进入条件：用户发起“欢迎、授权、商业登录、Persona 与原动作续接”且身份、输入与权限前置成立。
  - 交付给下游的结果：维护 UserAccount、Persona、Profile、Follow/Block 与隐私事实，并公开身份和关系结果，供 `runtime` 继续处理。
  - 不负责：不拥有内容、圈子、会话、主页聚合或推荐事实。
- [`JNY-003 / SCN-009`](../spec.md#scn-009)
  - 本领域负责：在“内容详情跳转作者主页”中，维护 UserAccount、Persona、Profile、Follow/Block 与隐私事实，并公开身份和关系结果。
  - 进入条件：`discovery-content` 已交付其公开结果。
  - 交付给下游的结果：维护 UserAccount、Persona、Profile、Follow/Block 与隐私事实，并公开身份和关系结果，供 `shared-homepage-network` 继续处理。
  - 不负责：不拥有内容、圈子、会话、主页聚合或推荐事实。
- [`JNY-004 / SCN-001`](../spec.md#scn-001)
  - 本领域负责：在“写文字创建、可靠发布与结果回流”中，维护 UserAccount、Persona、Profile、Follow/Block 与隐私事实，并公开身份和关系结果。
  - 进入条件：`discovery-content` 已交付其公开结果。
  - 交付给下游的结果：维护 UserAccount、Persona、Profile、Follow/Block 与隐私事实，并公开身份和关系结果，供 `circle-community` 继续处理。
  - 不负责：不拥有内容、圈子、会话、主页聚合或推荐事实。
- [`JNY-004 / SCN-002`](../spec.md#scn-002)
  - 本领域负责：在“照片创建、像素编辑、原图可靠上传与发布回流”中，维护 UserAccount、Persona、Profile、Follow/Block 与隐私事实，并公开身份和关系结果。
  - 进入条件：`discovery-content` 已交付其公开结果。
  - 交付给下游的结果：维护 UserAccount、Persona、Profile、Follow/Block 与隐私事实，并公开身份和关系结果，供 `circle-community` 继续处理。
  - 不负责：不拥有内容、圈子、会话、主页聚合或推荐事实。
- [`JNY-004 / SCN-003`](../spec.md#scn-003)
  - 本领域负责：在“视频创建、转码处理、发布与结果回流”中，维护 UserAccount、Persona、Profile、Follow/Block 与隐私事实，并公开身份和关系结果。
  - 进入条件：`discovery-content` 已交付其公开结果。
  - 交付给下游的结果：维护 UserAccount、Persona、Profile、Follow/Block 与隐私事实，并公开身份和关系结果，供 `circle-community` 继续处理。
  - 不负责：不拥有内容、圈子、会话、主页聚合或推荐事实。
- [`JNY-007 / SCN-012`](../spec.md#scn-012)
  - 本领域负责：在“1v1 私信与打招呼升级”中，维护 UserAccount、Persona、Profile、Follow/Block 与隐私事实，并公开身份和关系结果。
  - 进入条件：`chat-conversation` 已交付其公开结果。
  - 交付给下游的结果：维护 UserAccount、Persona、Profile、Follow/Block 与隐私事实，并公开身份和关系结果，形成该场景中本领域负责的终态。
  - 不负责：不拥有内容、圈子、会话、主页聚合或推荐事实。
- [`JNY-007 / SCN-016`](../spec.md#scn-016)
  - 本领域负责：在“会话内音视频通话与离线来电可靠送达”中，维护 UserAccount、Persona、Profile、Follow/Block 与隐私事实，并公开身份和关系结果。
  - 进入条件：`chat-conversation` 已交付其公开结果。
  - 交付给下游的结果：维护 UserAccount、Persona、Profile、Follow/Block 与隐私事实，并公开身份和关系结果，供 `runtime` 继续处理。
  - 不负责：不拥有内容、圈子、会话、主页聚合或推荐事实。
- [`JNY-009 / SCN-017`](../spec.md#scn-017)
  - 本领域负责：在“内容与页面上下文感知问答”中，维护 UserAccount、Persona、Profile、Follow/Block 与隐私事实，并公开身份和关系结果。
  - 进入条件：`discovery-content` 已交付其公开结果。
  - 交付给下游的结果：维护 UserAccount、Persona、Profile、Follow/Block 与隐私事实，并公开身份和关系结果，供 `global-search-experience` 继续处理。
  - 不负责：不拥有内容、圈子、会话、主页聚合或推荐事实。
- [`JNY-009 / SCN-020`](../spec.md#scn-020)
  - 本领域负责：在“小趣主动订阅与用户/会话投递”中，维护 UserAccount、Persona、Profile、Follow/Block 与隐私事实，并公开身份和关系结果。
  - 进入条件：`runtime` 已交付其公开结果。
  - 交付给下游的结果：维护 UserAccount、Persona、Profile、Follow/Block 与隐私事实，并公开身份和关系结果，形成该场景中本领域负责的终态。
  - 不负责：不拥有内容、圈子、会话、主页聚合或推荐事实。
- [`JNY-010 / SCN-023`](../spec.md#scn-023)
  - 本领域负责：在“对象对外分享分发”中，维护 UserAccount、Persona、Profile、Follow/Block 与隐私事实，并公开身份和关系结果。
  - 进入条件：`discovery-content` 已交付其公开结果。
  - 交付给下游的结果：维护 UserAccount、Persona、Profile、Follow/Block 与隐私事实，并公开身份和关系结果，供 `circle-community` 继续处理。
  - 不负责：不拥有内容、圈子、会话、主页聚合或推荐事实。
- [`JNY-011 / SCN-027`](../spec.md#scn-027)
  - 本领域负责：在“结伴同行与线下相聚”中，维护 UserAccount、Persona、Profile、Follow/Block 与隐私事实，并公开身份和关系结果。
  - 进入条件：`recommendation-platform` 已交付其公开结果。
  - 交付给下游的结果：维护 UserAccount、Persona、Profile、Follow/Block 与隐私事实，并公开身份和关系结果，供 `chat-conversation` 继续处理。
  - 不负责：不拥有内容、圈子、会话、主页聚合或推荐事实。
- [`JNY-012 / SCN-010`](../spec.md#scn-010)
  - 本领域负责：在“我的主页转发互动双向历史”中，维护 UserAccount、Persona、Profile、Follow/Block 与隐私事实，并公开身份和关系结果。
  - 进入条件：用户发起“我的主页转发互动双向历史”且身份、输入与权限前置成立。
  - 交付给下游的结果：维护 UserAccount、Persona、Profile、Follow/Block 与隐私事实，并公开身份和关系结果，供 `discovery-content` 继续处理。
  - 不负责：不拥有内容、圈子、会话、主页聚合或推荐事实。

- [`JNY-009 / SCN-034`](../spec.md#scn-034)
  - 本领域负责：提供 account/persona authority、个人隐私与公开资质声明供 Skill 设置和共享执行校验。
  - 进入条件：主体已认证且目标 Persona 可用。
  - 交付给下游的结果：最小主体/权限/可披露事实。
  - 不负责：不保存 Skill setting、Connector credential 或共享 Placement。
- [`JNY-013 / SCN-033`](../spec.md#scn-033)
  - 本领域负责：在用户确认后通过既有 Follow/Conversation/Circle 机制延续旅行关系，并提供公开署名/资质引用。
  - 进入条件：目标主体与关系动作允许。
  - 交付给下游的结果：关系 command receipt 或明确拒绝。
  - 不负责：不创造额外关系等级或 GatheringParticipation 事实。

## 4. 业务能力

- [`auth-profile-snapshot`](./auth-profile-snapshot/spec.md)：认证、refresh token、OwnerAccount/Persona 快照与凭证管理的能力级 SIT 验收。
- [`onboarding-and-identity-entry`](./onboarding-and-identity-entry/spec.md)：负责从欢迎页、冷启动、未登录入口、登录中断恢复到登录后落点的完整身份进入链路。
- [`persona-follow-graph`](./persona-follow-graph/spec.md)：本能力统一分身生命周期、公开身份、关系隔离与跨域透传。
- [`profile-homepage-redesign`](./profile-homepage-redesign/spec.md)：统一个人主页的信息架构、状态模型与跨页面互动一致性。
- [`settings-and-device-token`](./settings-and-device-token/spec.md)：为已登录账号提供可真实读写的通知、隐私、通话和外观设置，并管理设备推送端点与登录凭证。
- [`user-service-cloud-delivery`](./user-service-cloud-delivery/spec.md)：让用户资料、统计、设置和关系状态由 user-service 持久化，并通过正式远端契约在 App 各页面一致展示和更新。

## 5. 领域要求

<a id="req-001"></a>
### REQ-001 用户身份画像与关系领域边界与不变量

- 领域边界、上下游依赖、工程映射和服务治理清晰。

<a id="req-002"></a>
### REQ-002 平台缺少一个统一的身份基线去承载多方式登录、Persona 切换、强隔离关系网络、通讯录发现、邀请归因与用户生命周期经营

- 平台缺少一个统一的身份基线去承载多方式登录、Persona 切换、强隔离关系网络、通讯录发现、邀请归因与用户生命周期经营。
- 提供从欢迎页到登录后身份建立的统一入口流程，支持手机号、微信、Apple 并行登录。
- 欢迎页（`welcome_screen.dart`）作为登录前后入口，必须归于本 L1。
- 多个 `Persona` 允许共享同一 `OwnerAccount` 与登录态容器，但对外不可见关联。
- 通讯录匹配归 `OwnerAccount`；一旦转为好友、圈子、群或社交关系，必须落到具体 `Persona`。
- Persona 切换必须可追踪并透传到推荐、聊天、评论、圈子、助手、通知等下游上下文。
- API path、operation、decoder context、route、surface、请求头上下文必须以 metadata 为唯一真相源。
- Persona 切换后，评论、发帖、聊天、圈子、好友、邀请主体必须立即一致切换。
- 登录、验证码、欢迎页落点、Persona 创建、资料编辑、关系建立与邀请操作失败后必须可重试并恢复上下文。
- 外部默认不可推断两个 `Persona` 归属于同一 `OwnerAccount`。

## 6. 领域验收

<a id="dom-001"></a>
### DOM-001 user identity profile relationship 领域边界验收

- 条件：本领域收到有效输入且前置领域事实成立。
- 可观察结果：领域边界、上下游依赖、工程映射和服务治理清晰。
- 禁止结果：不得绕过本领域公开 command/query/event 写入其拥有事实。

## 7. 工程归属

- App：`quwoquan_app/lib/service/user_service`、`quwoquan_app/lib/service/tag_service`
- Contracts：`quwoquan_service/services/user-service/contracts`
- Contracts（协作引用，不用于代码归属）：`quwoquan_service/services/tag-service/contracts`
- Service：`quwoquan_service/services/user-service`、`quwoquan_service/services/tag-service`
- 测试：
  - `local_contract`：`quwoquan_service/services/user-service/tests`
  - `api_integration`：`quwoquan_service/services/user-service/tests`
  - `user_acceptance`：`quwoquan_ops/tests/acceptance/user_acceptance`、`quwoquan_app/test/user_acceptance/journeys/account_closure`、`quwoquan_app/test/user_acceptance/journeys/profile`

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 user identity profile relationship 领域边界验收

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：领域边界、上下游依赖、工程映射和服务治理清晰。
- 完成判定：`DOM-001` 对应行为满足且真实测试 `spec_ref` 有效
