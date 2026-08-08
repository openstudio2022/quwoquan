# L3 Story：资料读取更新 (`profile-read-update`)

> 所属能力：[`auth-profile-snapshot`](../spec.md)
>
> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)
>
> 设计归属：[L1 DEC-001](../../design.md#dec-001)

## 1. 用户价值

作为管理账号、Persona 或关系的用户，我希望编辑资料字段契约，地区字段统一使用 tag-service 行政区标签引用，从而安全地维持身份、画像与关系状态。

## 2. 范围与非目标

### In Scope

- 首次创建资料后的默认昵称、用户号与 nicknameCustomized 语义
- App 我的主页进入编辑资料，按封面、头像、昵称、性别、生日、地区、手机号、趣我圈号、我的二维码、签名、标签顺序完成编辑与保存
- 手机号凭证绑定、系统分配趣我圈号只读展示、二维码分享落地、职业/兴趣标签体系校验
- 聊天消息记录快照继续消费历史 senderDisplayName/avatar snapshot，不被资料更新回写历史消息
- ProfileEditSnapshotWire.region + regionTagRef
- PATCH /user/profile regionTagRef
- tag-service ListTagChildren 行政区 direct children
- Data control_plane/governance/taxonomy 行政区真相源完整性

### Out of Scope

- 真实图片上传链路的对象存储端到端验证
- 群成员列表异步 fan-out/reconciliation 全链路压测
- 普通省份第三层区县选择
- 境外行政区完整填充

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 资料读取、编辑保存与聊天快照一致

- 首次创建资料时服务端必须生成符合约定格式的默认昵称，并标记为未自定义。
- 编辑资料保存后，我的主页必须读取新资料；历史聊天消息仍优先展示发送时的昵称与头像快照。
- 公开资料读取不得暴露手机号、生日等 owner 私有凭证。

<a id="req-002"></a>
### REQ-002 商用资料编辑页字段顺序、私有凭证与二维码闭环

- 编辑资料按媒体、基础资料、账号社交与扩展资料四区块呈现；签名最多 60 字，趣我圈号只读，手机号只展示绑定状态与脱敏摘要。
- `GetProfileEditSnapshot`、`GetProfileQrCard`、手机号绑定与 `UpdateUserProfile` 必须使用同一 owner/Persona 身份和标签引用。
- 保存后我的主页读取新资料，历史聊天头像仍使用发送快照；二维码必须由真实 SDK 渲染服务端 payload。

<a id="req-003"></a>
### REQ-003 编辑资料页必须采用 iOS 分组列表：封面/头像为独立紧凑媒体区块，基础资料、账号社交、扩展资料拆分为独立区块

- 编辑资料页必须采用 iOS 分组列表：封面/头像为独立紧凑媒体区块，基础资料、账号社交、扩展资料拆分为独立区块；普通字段的右侧值、图标和 chevron 必须在同一右侧槽位对齐。
- 编辑资料读取必须使用本人私有 `ProfileEditSnapshotWire`，公开主页资料不得暴露手机号、生日等私有字段；手机号只展示 owner credential 脱敏摘要。
- 我的二维码由服务端 `ProfileQrCardWire` 生成唯一公开主页 HTTPS payload，并附可撤销 `qrTokenId`；payload 禁止编码手机号、ownerId、样式版本或 bearer token。App 侧必须使用真实二维码 SDK 渲染 payload，不得用静态占位图或模拟图案。
- 标签选择必须进入 tag-service 标签体系：职业单选，兴趣多选；`identityTags` 只作为展示摘要，不作为 App 侧第二套标签真相源。
- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。
- 资料编辑字段、错误码、请求上下文、route/surface、DTO projection 先走 metadata，再由 codegen/verify 闭合；禁止手改生成物作为契约来源。
- 手机号绑定必须复用登录域 OTP/运营商一键能力：`SendOtp(sourceOperation=bind_phone)` + `BindPhoneCredential` 或 `BindCarrierPhoneCredential`；通用 `BindCredential` 不再承担手机号验证。
- 用户资料读侧缓存必须遵守 [`runtime-client-foundation/local-cache-architecture`](../../../runtime/runtime-client-foundation/local-cache-architecture/spec.md)，并只从 user-service canonical [`user_profile_view`](../../../../../quwoquan_service/services/user-service/contracts/account/user_account/projections/user_profile_view.yaml) 派生，不维护对象策略台账。
- 当前用户、关注用户、互相关注用户、聊天联系人、最近互动作者进入 `pinned` 或 `recent` 缓存；仅 feed 中偶遇的作者不得升级为长期保留对象。
- 普通缓存清理不得删除当前用户最小资料、关注/联系人关系、待同步关系 outbox。

<a id="req-004"></a>
### REQ-004 用户选择广东深圳后资料保存 regionTagRef 并回显地区

- 保存有效 `regionTagRef` 后，我的主页与编辑页必须展示对应地区名称。

<a id="req-005"></a>
### REQ-005 无效行政区引用使用统一错误语义

- Error：无效、不在 `Topic/地理/行政区/中国/` 下或不存在的行政区引用统一使用 `USER.PROFILE.invalid_region`。
- tag-service 可做只读缓存，但缓存只能从 Mongo warm；不得从 App 本地文件、user-service 配置或镜像配置维护第二份行政区树。

<a id="req-006"></a>
### REQ-006 我的二维码展示、物理扫码与服务端解析必须保持可撤销单轨

- “我的二维码”只能展示 `GetProfileQrCard` 返回的公开 HTTPS payload，并由真实二维码 SDK 渲染；不得使用静态图案、ownerId、手机号或 bearer token 生成第二套二维码。
- 相机与相册扫描必须先经严格 payload parser 提取受支持的公开 token，再由 `ResolveProfileQrToken` production Remote 校验当前有效性；端侧不得自行解析后直跳他人主页。
- 失效、撤销、格式非法、权限拒绝、网络失败或 canonical failure 均不得创建关系事实；页面必须保留安全恢复或重试入口。
- 服务端解析成功后只返回当前可公开资料与 relationship capability，后续关注或打招呼仍由对应 owning object 的公开 command 负责。

## 4. 契约引用

- canonical：`quwoquan_service/services/user-service/contracts/account/user_account/operations.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/account/user_account/fields.yaml`
- canonical：`quwoquan_service/services/chat-service/contracts/chat/conversation/fields.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/account/user_account/projections/profile_edit_snapshot_wire.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/account/user_account/fields.yaml#ProfileQrCardWire`
- canonical：`quwoquan_service/services/tag-service/contracts/tag/tag_node_view/operations.yaml`
- canonical：`quwoquan_service/services/tag-service/contracts/tag/tag_node_view/operations.yaml#ListTagChildren`
- canonical：`quwoquan_service/services/user-service/contracts/account/user_account/operations.yaml#UpdateUserProfile`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 资料读取、编辑保存与聊天快照一致

- GIVEN 用户首次登录并创建 owner/profile/persona。
- GIVEN 用户在 App 我的主页进入编辑资料页。
- GIVEN 聊天消息已有发送者名称与头像记录快照。
- WHEN 云侧生成默认昵称与 ownerId。
- WHEN 用户修改昵称和签名并保存。
- WHEN App 回到我的主页，并消费聊天消息 DTO。
- THEN 默认昵称满足「新同学_YYMMDD_7位尾号」云侧格式，nicknameCustomized=false。
- THEN 编辑资料保存后主页展示新昵称，签名长度按 60 字 UI/服务契约截断或拒绝。
- THEN 历史聊天消息继续优先展示 senderDisplayNameSnapshot 和 senderAvatarUrlSnapshot。

<a id="gwt-002"></a>
### GWT-002 商用资料编辑页字段顺序、私有凭证与二维码闭环

- GIVEN 用户已登录并拥有 active persona。
- GIVEN 服务端已为 active persona 系统分配 userHandle/趣我圈号。
- GIVEN tag-service 提供职业与兴趣 tagRef 校验。
- WHEN 用户从我的主页进入编辑资料页。
- WHEN 用户选择封面/头像单图、设置性别、生日、地区、签名、职业与兴趣标签。
- WHEN 未绑定手机号用户进入手机号页，先尝试运营商一键绑定，失败后使用手机号 OTP 绑定。
- THEN 编辑页字段顺序固定为封面、头像、昵称、性别、生日、地区、手机号、趣我圈号、我的二维码、签名、标签。
- THEN 编辑页拆分为媒体、基础资料、账号社交、扩展资料四个 iOS 分组区块；封面和头像为紧凑预览行且使用同一媒体预览语义尺寸，不与普通信息行混在同一视觉区块。
- THEN 普通字段右侧值、未填写轻提示、系统只读值、图标与 chevron 使用统一右侧槽位和语义 token；未填写提示用简短好处文案和弱视觉权重，不使用蓝色加粗按钮式 CTA。
- THEN 趣我圈号为只读展示，只显示系统分配的号，不显示编辑 chevron 或额外复制图标。
- THEN 手机号只来自 owner credential 摘要，公开 profile 不包含 phone。
- THEN 生日按 YYYY-MM-DD 自然日期保存
- AND 端侧性别入口仅暴露 male/female/unspecified，用户未设置时仅显示轻提示，历史或远端 other 值按未设置轻提示兜底
- AND 地区保存省市显示值与 regionCode。
- THEN QR payload 是公开主页 HTTPS link，由真实开源二维码 SDK 渲染，扫码后进入用户主页；陌生人展示加联系人/打招呼，联系人展示语音/私信。
- THEN 职业单选和兴趣多选均通过 tag-service validateRefs，App 不维护第二套标签真相源。

<a id="gwt-003"></a>
### GWT-003 用户选择广东深圳后资料保存 regionTagRef 并回显地区

- GIVEN 用户已登录并进入我的主页编辑资料页
- GIVEN tag-service 可返回 Topic/地理/行政区/中国 的 34 个省级节点
- WHEN 用户进入地区选择页
- WHEN 用户选择 广东 → 深圳
- WHEN 用户保存编辑资料
- THEN App 提交 payload.regionTagRef = Topic/地理/行政区/中国/广东省/深圳市
- THEN App 不提交 regionCode，也不提交任意非空 region 展示文案
- THEN user-service 派生 region = 广东 深圳
- THEN ProfileEditSnapshotWire 返回 region + regionTagRef

<a id="gwt-004"></a>
### GWT-004 我的二维码展示、物理扫码、撤销失效与失败恢复

- GIVEN 用户以 active persona 登录 production Remote composition，且 user-service 返回当前有效、可撤销的 `ProfileQrCard`。
- WHEN App 的“我的二维码”页面用真实二维码 SDK 渲染公开 HTTPS payload，并从物理相机或相册读取另一个真实账号的二维码。
- WHEN 严格 parser 接受 payload 后，App 只经 `ResolveProfileQrToken` production Remote 解析目标，再读取 canonical 公开资料与 relationship capability。
- THEN payload、日志、埋点和结果回执均不包含手机号、ownerId、bearer token 或内部身份映射；端侧不得绕过 Remote 直接导航到自解析目标。
- AND 格式非法的 payload 在调用 Remote 前被拒绝；已撤销或不存在的 token、相机/相册权限拒绝、网络失败与 canonical failure 均停留在安全页面并提供恢复或重试，不得创建 follow、block 或 conversation 事实。
- AND 解析成功只建立可继续操作的公开目标上下文，后续关系或会话写入仍由对应 owning object 的公开 command 完成。
- AND 只有绑定同一 candidate、真实 Provider 与 production Remote 的 Android 物理设备及 iPhone 物理设备 `ReadinessResultBundle` 均通过时，本验收场景才计通过；Widget、模拟器、静态二维码、动态 skip 或 typed double 不计。

## 6. 依赖

- 前置要求：[`auth-profile-snapshot`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L1 DEC-001](../../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 商用资料编辑页字段顺序、私有凭证与二维码闭环

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：App local_contract 覆盖字段顺序、四区块分组、媒体预览同宽、未填写简短好处提示、性别默认不显示“不展示”且无 other 入口、单图选择返回、签名 60 字、趣我圈号只读纯文本、手机号绑定状态和 QR 页真实 SDK 渲染。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 二维码双真机解析与撤销恢复证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：尚缺能够证明 `GWT-004` 的 production Remote、严格 parser、撤销失效、失败恢复及同一 candidate 双物理相机/相册行为的结果回执。
- 完成判定：职责匹配的真实 production runner 逐字声明 `GWT-004` `spec_ref`，并取得同一 candidate 的 Android 与 iPhone 物理设备 `ReadinessResultBundle`；failed、blocked、skipped、模拟器、静态二维码或测试 double 结果均不计通过。
