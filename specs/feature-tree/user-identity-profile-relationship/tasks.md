# 用户身份画像与关系 —— 任务列表

> 执行顺序强制：metadata → codegen → 失败测试（Red）→ 业务逻辑（Green）→ 重构 → 补证据

---

## Story S1：OwnerAccount + SubAccount metadata 基线

### 当前交付任务

- [ ] S1-T1: [metadata] 更新 `contracts/metadata/user/user_profile/aggregate.yaml`
  - 追加 `CredentialBinding` 成员实体（1:N, cascade_delete: true）
  - 追加 `sub_account_count` 关联描述

- [ ] S1-T2: [metadata] 更新 `contracts/metadata/user/user_profile/fields.yaml`
  - `UserProfile` 实体（即 OwnerAccount）追加字段：
    - `ownerDisplayName`（string, NULLABLE, PII, api_exposure: drop, ops_exposure: read）
    - `subAccountCount`（int, NOT_NULL, DEFAULT_1, PUBLIC, api_exposure: read）
  - `Persona` 实体（即 SubAccount）追加字段：
    - `subAccountId`（string, NOT_NULL, UK, PUBLIC, api_exposure: read）
    - `isolationLevel`（enum IsolationLevel: open/semi/strict, NOT_NULL, DEFAULT_open）
    - `purposeHint`（string, NULLABLE, api_exposure: drop, ops_exposure: read）
    - `inviteCount`（int, NOT_NULL, DEFAULT_0, PUBLIC, api_exposure: read）
  - 新增 `CredentialBinding` 实体定义（见 S2-T1）

- [ ] S1-T3: [metadata] 更新 `contracts/metadata/user/user_profile/storage.yaml`
  - `personas` 表追加 `sub_account_id`, `isolation_level`, `purpose_hint`, `invite_count` 列
  - 追加 `UNIQUE(sub_account_id)` 索引
  - `user_profiles` 表追加 `owner_display_name`, `sub_account_count` 列

- [ ] S1-T4: [metadata] 更新 `contracts/metadata/user/user_profile/events.yaml`
  - 更新 `PersonaCreated` payload_fields（追加 `subAccountId`, `isolationLevel`）
  - 更新 `PersonaActivated` payload_fields（追加 `subAccountId`）
  - 新增 `SubAccountIsolationUpdated` 事件

- [ ] S1-T5: [codegen] `make verify-metadata && make codegen && make codegen-app`

- [ ] S1-T6: [测试-Red] 新增 `sub_account_isolation_contract_test.go`
  - 测试场景：创建子账号 → API 返回不含 `ownerAccountId`
  - 测试场景：同时只有一个 active SubAccount（激活排他性）
  - 测试场景：`isolationLevel=strict` 时 API 不返回 `subAccountId` 与其他子账号的关联

- [ ] S1-T7: [测试-Red] 更新 `persona_management_page_test.dart`
  - 切换子账号后 UI 状态更新正确
  - 子账号列表展示 `displayName + isolationLevel`（Widget 测试，Mock 模式）

- [ ] S1-T8: [业务逻辑-Green] 更新 Go domain service
  - `CreateSubAccount`：生成 `subAccountId`，设置 `isolationLevel`
  - `ActivateSubAccount`：原子切换 `isActive`，发布 `SubAccountActivated` 事件
  - `GetSubAccountsForOwner`：仅返回本 OwnerAccount 的子账号列表

- [ ] S1-T9: [业务逻辑-Green] 更新 Dart `UserProfileRepository`
  - `Mock`：从本地数据返回带 `subAccountId` 和 `isolationLevel` 的列表
  - `Remote`：调用 `/v1/owner/sub-accounts` 接口（使用 codegen 常量）

- [ ] S1-T10: [测试-Green] 让 S1-T6、S1-T7 测试转绿

- [ ] S1-T11: [gate] `make gate`

---

## Story S2：CredentialBinding（多方式登录凭证）

### 当前交付任务

- [ ] S2-T1: [metadata] `contracts/metadata/user/user_profile/fields.yaml` 追加 `CredentialBinding` 实体
  - 字段：`id`, `ownerId`, `credentialType`（enum: phone/wechat/apple）, `credentialKey`（手机号哈希/UnionID/SubjectID）, `displayLabel`, `isActive`, `boundAt`, `lastUsedAt`
  - `credentialKey`: classification: SECRET, log_policy: drop, api_exposure: drop
  - `credentialType`: classification: PUBLIC, api_exposure: read

- [ ] S2-T2: [metadata] 更新 `aggregate.yaml` 追加 `CredentialBinding` 成员

- [ ] S2-T3: [metadata] 更新 `storage.yaml` 追加 `credential_bindings` 表
  - 约束：`UNIQUE(credential_type, credential_key)`（跨 OwnerAccount 唯一）
  - 约束：`CHECK(isActive = true)` 至少一行（通过 trigger）

- [ ] S2-T4: [metadata] 更新 `events.yaml`
  - 新增：`CredentialBound`（用户绑定新凭证）
  - 新增：`CredentialUnbound`（用户解绑凭证）
  - 新增：`LoginSucceeded`（payload: ownerId, credentialType, loginAt, deviceId）
  - 新增：`LoginFailed`（payload: credentialType, failReason, attemptAt）

- [ ] S2-T5: [metadata] 更新 `service.yaml` 追加 API 端点
  - `POST /v1/auth/login/phone`：手机号+验证码登录
  - `POST /v1/auth/login/wechat`：微信授权码换 token
  - `POST /v1/auth/login/apple`：Apple ID token 换 token
  - `POST /v1/auth/token/refresh`：刷新 access token
  - `POST /v1/owner/credentials/bind`：绑定新凭证
  - `DELETE /v1/owner/credentials/{credentialType}`：解绑凭证

- [ ] S2-T6: [metadata] 扩展 `errors.yaml`
  - `USER.AUTH.otp_expired`：验证码已过期
  - `USER.AUTH.otp_mismatch`：验证码错误
  - `USER.AUTH.credential_conflict`：凭证已绑定其他账号
  - `USER.AUTH.last_credential`：不能解绑最后一个凭证
  - `USER.AUTH.login_locked`：账号已锁定
  - `USER.AUTH.wechat_auth_failed`：微信授权失败
  - `USER.AUTH.apple_auth_failed`：Apple 授权失败

- [ ] S2-T7: [codegen] `make verify-metadata && make codegen && make codegen-app`

- [ ] S2-T8: [测试-Red] 新增 `credential_binding_contract_test.go`
  - 手机号登录成功 → 200 + access_token + refresh_token
  - 错误验证码 → `USER.AUTH.otp_mismatch`
  - 同手机号绑定两个账号 → `USER.AUTH.credential_conflict`
  - 解绑最后凭证 → `USER.AUTH.last_credential`

- [ ] S2-T9: [测试-Red] 新增 `login_page_test.dart`（Widget 测试）
  - 三种登录方式同时显示
  - 手机号输入格式校验
  - 验证码倒计时状态

- [ ] S2-T10: [业务逻辑-Green] 实现 Go `AuthDomainService`
  - `LoginWithPhone`：发送/验证 OTP，查找或创建 OwnerAccount，生成 JWT
  - `LoginWithWechat`：验证授权码，获取 UnionID，绑定或创建 OwnerAccount
  - `LoginWithApple`：验证 ID token，获取 Subject，绑定或创建 OwnerAccount
  - `RefreshToken`：验证 refresh token 有效性，滑动延期
  - `BindCredential`：原子绑定新凭证（检查全局唯一性）
  - `UnbindCredential`：验证不是最后一个凭证再解绑

- [ ] S2-T11: [业务逻辑-Green] 实现 Dart `AuthRepository`
  - `Mock`：本地返回 mock JWT（不发 HTTP）
  - `Remote`：调用 codegen 常量路径，统一错误处理

- [ ] S2-T12: [测试-Green] 让 S2-T8、S2-T9 测试转绿

- [ ] S2-T13: [gate] `make gate`

---

## Story S3：ContactDiscoveryRecord（通讯录发现）

### 当前交付任务

- [ ] S3-T1: [metadata] 创建 `contracts/metadata/user/contact_discovery/` 目录
  - `entity.yaml`：`ContactDiscoveryRecord` 实体声明
  - `fields.yaml`：`ownerAccountId`, `hashedPhoneNumbers[]`, `matchedSubAccountIds[]`, `status`, `expireAt`, `createdAt`
    - `hashedPhoneNumbers`: classification: SECRET, log_policy: drop, api_exposure: drop
    - `matchedSubAccountIds`: classification: PUBLIC, api_exposure: read（不含 ownerAccountId）
  - `storage.yaml`：`contact_discovery_records` 表，TTL 72h（PostgreSQL row-level TTL via cron job）
  - `events.yaml`：`ContactDiscoveryInitiated`, `ContactDiscoveryCompleted`
  - `service.yaml`：
    - `POST /v1/owner/contact-discovery`：上传哈希手机号列表
    - `GET /v1/owner/contact-discovery/latest`：获取最近一次发现结果
    - `DELETE /v1/owner/contact-discovery/{id}`：主动删除记录

- [ ] S3-T2: [metadata] 创建 `contracts/metadata/user/contact_discovery/errors.yaml`
  - `USER.CONTACT.rate_limited`：今日发现次数已达上限
  - `USER.CONTACT.too_many_contacts`：单次上限 5000 条

- [ ] S3-T3: [codegen] `make verify-metadata && make codegen && make codegen-app`

- [ ] S3-T4: [测试-Red] 新增 `contact_discovery_contract_test.go`
  - 上传 100 条哈希手机号 → 返回匹配 subAccountId 列表
  - 结果不含 ownerAccountId 字段
  - 72h 后记录查询返回 404

- [ ] S3-T5: [测试-Red] 新增 `contact_discovery_widget_test.dart`
  - 权限未授权：展示授权入口
  - 权限已授权但空结果：展示空状态
  - 有匹配结果：展示匹配 subAccount 列表

- [ ] S3-T6: [业务逻辑-Green] 实现 Go `ContactDiscoveryService`
  - 批量接受哈希手机号，用 Bloom Filter 预过滤，再走数据库精确匹配
  - 异步处理，前端 polling 或 push 通知结果
  - 结果输出只含 `subAccountId`（不含 ownerAccountId）

- [ ] S3-T7: [业务逻辑-Green] 实现 Dart `ContactDiscoveryRepository`（三层）

- [ ] S3-T8: [测试-Green] 让 S3-T4、S3-T5 测试转绿

- [ ] S3-T9: [gate] `make gate`

---

## Story S4：InviteRecord（邀请归因）

### 当前交付任务

- [ ] S4-T1: [metadata] 创建 `contracts/metadata/user/invite_record/` 目录
  - `entity.yaml`：`InviteRecord` 实体声明
  - `fields.yaml`：
    - `id`, `inviterSubAccountId`, `inviterOwnerAccountId`（内部字段）, `channel`, `inviteePhone`（哈希，SECRET）, `status`, `linkCode`, `expireAt`, `generatedAt`, `deliveredAt`, `viewedAt`, `acceptedAt`, `convertedAt`
    - `inviterOwnerAccountId`: classification: SECRET, api_exposure: drop, ops_exposure: mask
    - `inviteePhone`: classification: PII, log_policy: drop, api_exposure: drop
  - `storage.yaml`：`invite_records` 表，幂等唯一约束 `(inviter_sub_account_id, channel, invitee_phone_hash)` 状态 `generated` 去重
  - `events.yaml`：`InviteGenerated`, `InviteAccepted`, `InviteConverted`, `InviteExpired`
  - `service.yaml`：
    - `POST /v1/me/invites`：生成邀请（幂等）
    - `GET /v1/me/invites`：查看我发出的邀请列表
    - `GET /v1/invites/{linkCode}`：公开：根据邀请码获取邀请信息（注册时携带）
    - `POST /v1/invites/{linkCode}/accept`：接受邀请（注册成功后调用）

- [ ] S4-T2: [metadata] 创建 `contracts/metadata/user/invite_record/errors.yaml`
  - `USER.INVITE.expired`：邀请已过期
  - `USER.INVITE.already_accepted`：邀请已被接受（幂等保护）
  - `USER.INVITE.daily_limit_exceeded`：今日邀请上限

- [ ] S4-T3: [codegen] `make verify-metadata && make codegen && make codegen-app`

- [ ] S4-T4: [测试-Red] 新增 `invite_attribution_contract_test.go`
  - 生成邀请 → 返回 linkCode
  - 同 (subAccountId, channel, phone) 重复请求 → 返回已有记录（幂等）
  - 接受邀请 → 状态变更 → `InviteAccepted` 事件
  - 过期邀请接受 → `USER.INVITE.expired`

- [ ] S4-T5: [测试-Red] 新增 `invite_share_widget_test.dart`
  - 分享按钮展示邀请渠道选项
  - 邀请状态列表渲染（pending/accepted/converted）

- [ ] S4-T6: [业务逻辑-Green] 实现 Go `InviteService`
  - `GenerateInvite`：幂等创建，设置 expireAt（7天）
  - `AcceptInvite`：验证有效性，更新状态，归因到 `inviterSubAccountId`
  - `ConvertInvite`：注册完成 + 首次使用后触发，发布 `InviteConverted`

- [ ] S4-T7: [业务逻辑-Green] 实现 Dart `InviteRepository`（三层）

- [ ] S4-T8: [测试-Green] 让 S4-T4、S4-T5 测试转绿

- [ ] S4-T9: [gate] `make gate`

---

## Story S5：onboarding 流程接入（端侧）

### 当前交付任务

- [ ] S5-T1: [metadata] 创建 `contracts/metadata/user/user_profile/ui_config.yaml`（若不存在）
  - 定义 onboarding surfaces：`welcome_screen`, `login_method_selector`, `sub_account_selector`, `sub_account_creator`
  - 定义路由 path_template：与 GoRouter 路由对应

- [ ] S5-T2: [codegen] `make codegen-app`

- [ ] S5-T3: [测试-Red] 新增 / 更新 `welcome_screen_test.dart`
  - 未登录 → 进入 login_method_selector
  - 已登录单子账号 → 直接进 home
  - 已登录多子账号 → 进入 sub_account_selector
  - 登录失效 → 进入 login_method_selector（含提示文案）

- [ ] S5-T4: [业务逻辑-Green] 更新 Flutter 路由（`app_router.dart`）
  - 使用 codegen 生成的 surface/route 常量，禁止字符串字面量
  - 实现基于 session 状态的初始落点分发逻辑

- [ ] S5-T5: [业务逻辑-Green] 实现 `AuthSessionProvider`（Riverpod）
  - 管理 access/refresh token 生命周期
  - 管理当前激活 `subAccountId`
  - 提供 `loginState`（未登录/登录中/已登录/失效）

- [ ] S5-T6: [业务逻辑-Green] 实现登录页 UI（`login_page.dart`）
  - 三种方式并行（phone / wechat / apple）
  - 使用 codegen 生成的路由常量跳转

- [ ] S5-T7: [测试-Green] 让 S5-T3 测试转绿

- [ ] S5-T8: [gate] `make gate`

---

## 搁置任务（本次不交付，已识别）

- [ ] `LifecycleProfile`（生命周期档案）归运营控制面，待 `product-ops-growth` L2 节点设计后实现（重启条件：`product-control-plane-foundation` 完成 metadata 基线）
- [ ] 设备推送 token 与 `subAccountId` 绑定（重启条件：通知服务支持按子账号分发）
- [ ] 恢复/申诉 workflow 的端侧 UI（重启条件：运营控制面工单系统 metadata 完成）
- [ ] 邀请奖励积分系统（重启条件：积分/激励体系 metadata 完成）
- [ ] SubAccount 独立微服务拆分（重启条件：DAU 达到需要独立 SLA 的规模）

---

## 未来演进任务

- [ ] 存量 `personas` 记录追加 `sub_account_id` 字段（one-time migration）
- [ ] `ContactDiscoveryRecord` 接入 Bloom Filter 离线匹配（当 DAU > 100 万）
- [ ] `InviteRecord` 支持多层裂变奖励链（当增长成为核心策略）
- [ ] `CredentialBinding` 支持 email / Google / GitHub（按需扩展）
- [ ] 通讯录发现结果接入推荐引擎（"你可能认识的人"信号）
