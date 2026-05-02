# 用户身份画像与关系 —— 设计方案

## 设计动因

PRD 基线冻结了 `OwnerAccount / SubAccount` 双层账号模型，以及通讯录发现、邀请归因、登录多方式并行、子账号强隔离四条核心能力线。现有 metadata 只有 `UserProfile` 聚合（含 `UserAuth/Persona/UserDevice/UserSetting`），需要在不破坏现有云侧服务的前提下，把新对象拆分到正确的 metadata 层与存储层，并完整推导出端云一致的对象边界。

关键设计张力：
1. 现有 `Persona` 是 `UserProfile` 的轻量子实体（切换展示身份），而新需求要求"强隔离公开账号"——两者是不同语义。
2. 现有 `UserAuth` 只存密码+OTP，但新需求要支持微信/Apple 第三方凭证——需要扩展凭证模型。
3. 通讯录发现 / 邀请归因 / 生命周期档案是全新对象，没有任何现有 metadata 基础。

---

## 上游输入评审

spec.md 状态：4 份 spec 已完整基线，acceptance A1-A8 均已定义，对标输入已记录。**设计可以推进**。

待在本节点收口的三处模糊点：

| 问题 | 本设计给出的收口方案 |
|------|------|
| 现有 `Persona` 是否等于 `SubAccount` | 否，详见方案选型；`Persona` 升级为 `SubAccount`，保留现有字段，追加隔离约束 |
| `OwnerAccount` 是否是新表 | 是，但等于现有 `UserProfile` + 新凭证层；`UserProfile` 重命名为 `OwnerAccount`，用 migration 追加新字段 |
| 通讯录/邀请/生命周期对象归属哪个服务 | 通讯录归 `user-service`（主控域），邀请归 `user-service`（归因），生命周期档案归 `ops-service` |

---

## 对标输入分析

| 对标对象 | 借鉴点 | 不借鉴点 | 适用边界 |
|---------|--------|---------|---------|
| **微信** | 手机号+微信+Apple 并行绑定、多设备会话、强风控锁定、恢复申诉、通讯录建链 | 单账号强绑定、工作和生活身份完全打通 | 认证与安全基建完全对标；关系网络不对标（微信是私密强关系，我们是多身份隔离） |
| **小红书** | 用户主页经营、身份表达、创作者成长、内容人格化、分身发言（评论时选账号） | 单身份世界观、无法隔离多账号 | 主页展示层、评论身份选择对标 |
| **微博** | 运营账号心智、关系传播、粉丝关系、公开身份扩散、申诉恢复工作流 | 真实名制认证、单账号限制 | 申诉/恢复 workflow、关系传播对标 |
| **差距收敛计划** | 当前无法支持子账号强隔离、无第三方凭证绑定、无通讯录发现、无邀请归因 | — | 本次设计全部补齐 |

---

## 方案对比

### 方案 A：在现有 `UserProfile` 聚合上原地扩展

将 `OwnerAccount` 视为 `UserProfile` 的别名，把新字段（第三方凭证、通讯录匹配状态）直接追加到现有表；`Persona` 直接升级为强隔离 `SubAccount`；通讯录/邀请作为独立表加入同一聚合。

**优点：**
- 无需改变服务边界与路由
- migration 成本低（只追加列）
- 现有 codegen 产物可最大程度复用

**缺点：**
- `UserProfile` 聚合膨胀，领域边界模糊
- `OwnerAccount` 与 `SubAccount` 的语义差异在代码层容易混淆
- 凭证（第三方绑定）挂在 `UserAuth` 下，字段分级压力大（SECRET 与 PII 混在同一表）
- 通讯录/邀请数据量大，挂在用户聚合上会导致聚合边界越来越重

**适用条件：** 功能简单、没有强隔离要求、只是轻量展示分身的场景。

---

### 方案 B：引入独立聚合/实体层，保留现有聚合为 OwnerAccount（**选定**）

将现有 `UserProfile` 聚合正式重命名语义为 `OwnerAccount`，作为主控账号的 metadata 承载体；把现有 `Persona` 升级为 `SubAccount`（追加隔离约束字段）；把 `UserAuth` 扩展出独立的 `CredentialBinding` 成员承载第三方凭证；新增独立实体 `ContactDiscoveryRecord` 和 `InviteRecord`；生命周期档案 `LifecycleProfile` 归运营域。

**优点：**
- 语义与 PRD 完全对齐
- `OwnerAccount`（管理平面）和 `SubAccount`（应用平面）边界清晰
- `CredentialBinding` 独立成员，可精细化控制 SECRET/PII 字段隔离
- `ContactDiscoveryRecord` / `InviteRecord` 作为独立表，可按需分区/归档
- migration 渐进：现有表结构无破坏性变更，新列均可 nullable 追加

**缺点：**
- 新增成员实体后，`aggregate.yaml` 成员列表增加
- 需要在 `fields.yaml` 追加新对象定义
- 端侧 codegen 产物需要同步更新

**适用条件：** 当前场景，强隔离多账号体系，PRD 已明确 `OwnerAccount/SubAccount` 双层模型。

---

### 方案 C：把 SubAccount 拆为独立微服务

新建 `sub-account-service`，独立承载 `SubAccount` 的 metadata、存储与 API；`user-service` 只管 `OwnerAccount`。

**优点：**
- 服务边界极度清晰
- 可独立扩缩容

**缺点：**
- 当前用户体量不需要独立服务
- 跨服务事务（主控账号创建 + 默认子账号建立）需要 saga
- 运维复杂度大幅上升

**适用条件：** 子账号流量远超主控账号、需要独立 SLA 的成熟阶段。

---

## 选型决策

**选定方案 B**：保留现有 `UserProfile` 聚合作为 `OwnerAccount` 语义基础，扩展成员实体，追加独立对象。

**理由：**
- 最小破坏性：现有 `user_profiles` 表 0 破坏性变更，只追加列
- 语义对齐：`Persona` 升级为 `SubAccount`，`UserAuth` 扩展为 `CredentialBinding`
- 新对象独立存储：`contact_discovery_records`、`invite_records` 单独分表，便于归档与容量控制

---

## 关键设计决策

### KD-1：OwnerAccount = 现有 UserProfile（语义升级，表结构不破坏）

现有 `user_profiles` 表保持不变，新增以下字段（均 nullable，migration 追加）：
- `owner_display_name`：主控账号管理视角昵称（仅用于自己的控制台，不对外展示）
- `sub_account_count`：当前子账号数量（冗余计数，便于 UI 快速展示）

代码层通过命名与注释明确"此对象是主控账号管理平面，不是应用展示主体"。

### KD-2：Persona 字段扩展为 SubAccount（向后兼容，追加列）

`personas` 表追加以下字段：
- `sub_account_id`：全局唯一子账号 ID（UUID，区别于 `personas.id`，用于跨域引用）
- `isolation_level`：枚举 `open / semi / strict`，控制外部关联可见度
- `purpose_hint`：用户自定义用途备注（仅主控账号视角可见）
- `invite_count`：该子账号发起的邀请转化数（冗余计数）

**约定**：API 层对外调用时，`subAccountId` 用于跨域上下文传递（推荐、聊天、评论、圈子的身份标识）；`personas.id` 只在用户域内部使用。

### KD-3：CredentialBinding 作为新成员实体（独立表，1:N）

现有 `UserAuth` 保留密码/OTP/session/锁定字段，职责为"主控账号安全凭证"。

新增 `credential_bindings` 表承载第三方凭证：
- `phone`：手机号绑定（一个 OwnerAccount 最多 1 个）
- `wechat`：微信 UnionID + OpenID 绑定
- `apple`：Apple Subject 绑定
- 可扩展：email、google 等

关键约束：
- 一个 `OwnerAccount` 最多同时绑定 1 个手机号、1 个微信、1 个 Apple（可扩展）
- 至少保留 1 个激活凭证（不能全部解绑）
- 跨凭证的全局唯一性（同一手机号不能绑定两个 OwnerAccount）

### KD-4：ContactDiscoveryRecord 作为独立实体（不挂在聚合内）

通讯录发现数据量大（每次导入最多数千条），生命周期短（发现后建立关系即归档），不适合挂在 UserProfile 聚合内。

设计为独立实体 `ContactDiscoveryRecord`，存在 `user-service` 的 `contact_discovery_records` 表：
- 输入：`OwnerAccount` 上传已哈希的手机号集合
- 输出：匹配到的已注册 `SubAccount` 列表（按 `subAccountId` 返回，不泄露 `OwnerAccount` 关联）
- 状态：`pending → matched → dismissed / linked`
- 数据保留：72 小时后自动删除（隐私合规）

### KD-5：InviteRecord 作为独立实体（归属于 SubAccount）

邀请归因记录归属于发起邀请的 `SubAccount`，而不是 `OwnerAccount`。

`invite_records` 表核心字段：
- `inviterSubAccountId`：发起邀请的子账号
- `inviterOwnerAccountId`：内部审计字段（仅后台可见，普通 API 不暴露）
- `channel`：邀请渠道（link / qrcode / contact / sms）
- `inviteePhone`：被邀请手机号（哈希存储，PII）
- `status`：`generated → delivered → viewed → accepted → activated`
- `convertedAt`：激活时间（null 表示未转化）

### KD-6：SubAccount 上下文全链路透传

子账号切换后，以下下游必须同步更新上下文：
- 推荐引擎：传入 `subAccountId` 作为个性化 key
- 聊天服务：发言身份、群/会话成员身份以 `subAccountId` 标识
- 评论服务：评论归属以 `subAccountId` 标识
- 圈子服务：成员身份以 `subAccountId` 标识
- 通知服务：推送 token 绑定 `subAccountId`（可选，高级需求）
- 助手服务：上下文 persona 字段改为 `subAccountId`

**传递机制**：HTTP 请求头 `X-Sub-Account-Id`，由 gateway 注入当前 session 的激活 `subAccountId`，各下游从请求头读取，不需要重复查询。

### KD-7：OwnerAccount 视图 vs SubAccount 视图严格分离

| API 路径前缀 | 返回视图 | 说明 |
|-------------|---------|------|
| `/v1/owner/...` | `OwnerAccount` 视图 | 仅自己可调用，包含凭证、设备、子账号列表、通讯录发现 |
| `/v1/user/{subAccountId}/...` | `SubAccount` 视图 | 公开侧，主页、关注、作品、互动数据 |
| `/v1/me/...` | 当前激活 `SubAccount` 的快捷视图 | 等同于 `/v1/user/{activeSub}/...` |

---

## 元数据唯一源分层

| 信息类型 | 唯一真相源 | 禁止出现在 |
|---------|---------|---------|
| `OwnerAccount / SubAccount` 字段策略、API 暴露、PII 分级 | `user/user_profile/fields.yaml` | 业务代码、Dart DTO 硬编码 |
| 凭证绑定 (`CredentialBinding`) 字段与策略 | `user/user_profile/fields.yaml`（新增成员） | 业务代码 |
| 通讯录发现 (`ContactDiscoveryRecord`) | `user/contact_discovery/` 新目录 | 业务代码 |
| 邀请归因 (`InviteRecord`) | `user/invite_record/` 新目录 | 业务代码 |
| 错误码 | `user/user_profile/errors.yaml`（扩展） + `user/invite_record/errors.yaml` | 业务代码字符串 |
| operation / path / method | `user/user_profile/service.yaml` | Go handler、Dart Repository |
| `X-Sub-Account-Id` 等请求头语义 | `_shared/request_context.yaml`（追加） | 业务代码字符串 |
| 恢复/申诉 workflow | `product-ops-growth` 控制面 YAML | user-service 业务代码 |

---

## TDD / ATDD 策略

每个 Story 执行顺序：
```
1. 更新/创建 metadata YAML（aggregate/fields/storage/events/service/errors）
2. make verify-metadata（元数据内部一致性）
3. make codegen（生成 Go struct/repository/handler 骨架）
4. make codegen-app（生成 Dart DTO/错误码）
5. 先写失败测试（Red）：T1 契约测试 + T2 Widget 测试骨架
6. 实现最小业务逻辑（Green）
7. 重构（Refactor）
8. 补齐 T3 云侧契约测试 + T4 旅程测试
```

每个 Story 完成后自动执行 `make gate`。

---

## Story 与测试层映射

### Story S1：OwnerAccount + SubAccount metadata 基线

**T1（契约/静态）：**
- `fields.yaml` 新字段 codegen 后 Dart DTO 字段一致性校验
- `errors.yaml` 新错误码 round-trip 测试
- `_shared/request_context.yaml` 追加 `X-Sub-Account-Id` 后 codegen 常量校验

**T2（模块/交互）：**
- `PersonaManagementPage` 从本地 mock 切换到 `UserProfileRepository`（Mock 模式）的 Widget 测试
- 子账号切换后上下文提示 Widget 测试

**T3（端云集成）：**
- Go 契约测试：`sub_account_isolation_contract_test.go`
  - 创建子账号 → 按 `subAccountId` 读取 → 外部接口不返回 `ownerAccountId`
  - 子账号激活排他性（同时只有一个 active）

**T4（旅程/设备）：**
- 多子账号选择器旅程：登录 → 选择子账号 → 进入正确落点

---

### Story S2：CredentialBinding（手机号/微信/Apple 并行凭证）

**T1：**
- `CredentialBinding` DTO 字段与 `fields.yaml` 一致
- 凭证类型枚举（phone/wechat/apple）codegen 正确

**T2：**
- 登录入口 Widget 测试：三种方式并行显示，选择后进入正确流程
- 凭证绑定设置页 Widget 测试：已绑定/未绑定状态正确渲染

**T3：**
- Go 契约测试：`credential_binding_contract_test.go`
  - 手机号登录成功 → 返回 access/refresh token
  - 同一手机号绑定两个账号 → 409 Conflict
  - 解绑最后一个凭证 → 400 Bad Request

**T4：**
- 真机 Apple/微信 OAuth 授权流程旅程（Patrol）

---

### Story S3：ContactDiscoveryRecord（通讯录发现）

**T1：**
- `ContactDiscoveryRecord` DTO 字段一致性
- 匹配结果只返回 `subAccountId`，不泄露 `ownerAccountId`

**T2：**
- 通讯录发现入口 Widget 测试：权限未授权/已授权/匹配结果渲染
- 发现结果转化为好友/圈子邀请的选择 Widget 测试

**T3：**
- Go 契约测试：`contact_discovery_contract_test.go`
  - 批量上传哈希手机号 → 返回匹配的 subAccountId 列表
  - 72h 后记录自动过期
  - 匹配结果不含 ownerAccountId

**T4：**
- 真机通讯录权限申请旅程

---

### Story S4：InviteRecord（邀请归因）

**T1：**
- `InviteRecord` DTO 字段一致性
- 邀请状态枚举 codegen 正确

**T2：**
- 邀请分享入口 Widget 测试（分享卡片/二维码/短信）
- 邀请状态跟踪页 Widget 测试

**T3：**
- Go 契约测试：`invite_attribution_contract_test.go`
  - 生成邀请 → 被邀请人注册 → 归因到正确 subAccountId
  - 邀请过期后无法归因

**T4：**
- 邀请链接点击 → 注册 → 激活 → 归因确认旅程

---

## 实时性与弱网设计

| 场景 | 一致性模型 | 重试策略 | 弱网降级 |
|------|-----------|---------|---------|
| 子账号切换 | 强一致（session 写入 + 下游上下文同步） | 失败 → 保留当前账号不切换，提示重试 | 不降级，必须成功才切换 |
| 凭证登录 | 强一致 | 最多 3 次，超频锁定 | 降级到密码登录（若已设置） |
| 通讯录匹配 | 最终一致（异步批量处理） | 失败 → 72h 内可重新触发 | 展示空状态 + 重试按钮 |
| 邀请链接生成 | 幂等（同 subAccountId + channel 复用已有记录） | 失败 → 重试生成 | 本地缓存上一次链接 |
| 资料更新提案 | 乐观锁（version 字段） | 版本冲突 → 提示重新加载再修改 | 草稿本地暂存，在线后上传 |

---

## 并发性能与容量设计

| 场景 | 峰值假设 | 防护策略 |
|------|---------|---------|
| 登录高峰（活动/节假日） | 10x 平时 QPS | 验证码服务单独限流，登录端点设置 rate limit |
| 通讯录批量上传 | 每用户最多 5000 条哈希 | 异步队列处理，限制每天触发次数 |
| 邀请裂变（活动爆发） | 单用户最多 1000 次邀请/天 | `invite_records` 写入异步，前端乐观插入 |
| 子账号切换频率 | 正常用户 <10 次/天 | 无限制，session 写入走 Redis，P95 < 50ms |
| 通讯录匹配热点 | 新注册用户大量同时导入 | 批量哈希匹配走离线 Bloom Filter，减少数据库压力 |

---

## 灰度发布与回滚设计

| 能力 | 灰度策略 | 回滚条件 |
|------|---------|---------|
| 子账号隔离能力 | 按 `OwnerAccount` 渐进放量 5→25→50→100% | 出现跨子账号数据串号 |
| 第三方凭证绑定 | 按平台（先 Apple → 微信 → 手机号） | 授权失败率超过 5% |
| 通讯录发现 | 按用户分群（早期用户先放量） | 隐私合规投诉超阈值 |
| 邀请归因 | 按邀请渠道（先链接 → 二维码 → 短信） | 归因错误率超过 1% |

---

## 角色职责与多重防护网

- 产品：定义子账号世界观、体验目标、隔离边界与增长路径
- 架构：定义 OwnerAccount/SubAccount metadata 边界、凭证模型、上下文传递协议
- 开发：按 TDD 落地 metadata → codegen → 测试先行 → 业务逻辑
- 测试：建立 T1（契约）→ T2（交互）→ T3（云侧契约）→ T4（旅程）四层证据
- 发布：按子能力灰度、设置 SLO 观测指标、定义回滚条件

---

## 未来演进

- E1：`SubAccount` 独立成微服务（当子账号流量显著高于 OwnerAccount 时）
- E2：通讯录发现接入 Bloom Filter 离线匹配（当 DAU > 100 万时）
- E3：邀请归因扩展为多层奖励链（当增长成为核心策略时）
- E4：`LifecycleProfile` 从运营控制面下沉到 user-service 的轻量投影（当用户分群成为实时推荐信号时）
- E5：`CredentialBinding` 支持 email、Google、GitHub 等更多第三方凭证

---

## 存量带规划任务

- L1：`Persona` → `SubAccount` 存量数据迁移（存量 `personas` 记录追加 `sub_account_id` 字段）
- L2：现有 `persona_management_page.dart` 接入真实 Repository（当前是本地 mock）
- L3：`edit_profile_page.dart` 的保存逻辑接入真实 `updateProfile` API
- L4：设备推送 token 与 `subAccountId` 绑定（当前只绑定到 OwnerAccount）
