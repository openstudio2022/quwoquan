# L1 Design：用户身份画像与关系 (`user-identity-profile-relationship`)

> 对应规格：[L1 spec](./spec.md)

## 1. 背景与设计目标

- 设计目标：让用户以默认账号或明确选择的 Persona 安全进入应用、维护公开资料和设置、建立或解除关系，并在所有业务领域获得一致的主体与权限语义。

## 2. 领域模型与所有权

- authoritative ownership：拥有 `UserAccount`、`Persona`、资料快照、关注与拉黑关系、设备端点、用户设置和账号生命周期的写入决定权。
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

- [`auth-profile-snapshot`](./auth-profile-snapshot/spec.md)：认证、refresh token、OwnerAccount/Persona 快照与凭证管理的能力级 SIT 验收。
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

<a id="dec-002"></a>
### DEC-002 合集私有查询委托只由 UserAccount authority 签发与在线验证

- 决策：本次委托能力仅覆盖 content owner 的 `GetPostCollection` 已认证 viewer 读取与 `GetPostCollectionManagement` owner 管理读取。`user-service` 既有身份 authority 是唯一 issuer 与在线验证者；API Edge 仅凭已验签 service principal、窄申请 scope 和原用户 access credential 申请并转交 grant，不持有委托 signing secret，不可自行声明 account/persona 或签发授权。此决定不授权任意 operation、Assistant 工具或 command。
- 决策：authority 独立验证源用户 credential，并从 UserAccount 与 Persona 各自公开 application 边界核对当前 account-persona 归属、存续与账号状态/epoch；不得把 API Edge 自报标识或历史 JWT 签名视为当前归属。recipient 固定为 content-service，delegate 固定为 api-edge，owner 还须独立验证实际 service caller 与 grant 委托者一致，签名中的 actor 声明不能代替请求身份认证。
- 决策：grant 必须精确限制为一个 canonical query operation、合集 resource、persisted hash、实际内部请求摘要与 method/path、canonical surface 和真实请求关联身份；权限只能在 authority 合同允许集合内收窄。具体 operation ID、scope、字段名、编码、摘要算法、错误码与传输协议先由 user-service 对象 contracts authoring，再生成实现，设计不建立第二 wire 定义。
- 决策：新调用不得伪造 Assistant run/tool tuple。身份实现任务必须先在同一 canonical grant source 冻结真实请求关联与 Assistant 专属约束；已有 Assistant 验证与 command approval、单次消费和防重放边界不得削弱，不引入双键、双读或兼容 fallback。
- 决策：content owner 调用受限内部 authority verification 后只消费最小 verified identity/binding，继续自己裁决 collection owner、合集及成员当前可见性。公开匿名读取不产生用户委托，已认证委托失败不降级匿名；不借空 ViewerContext 或旧 delegated persona compatibility scope 读取私有数据。
- 理由：身份归属与撤权权威已经由 user-service 拥有，网关扩成 issuer 会扩大信任边界；在线验证避免给 API Edge/content 分发对称 signing secret，也避免把来源签名误当作当前授权。
- canonical owner：签发/验证的操作、请求响应、错误、隐私与 telemetry 由 `quwoquan_service/services/user-service/contracts/account/user_account/{operations,fields,errors,privacy}.yaml` 拥有；Persona 归属由 `contracts/persona_management/persona` 拥有；AccountSession 生命周期不迁入网关，也不把现有最小 account-security snapshot 扩成 persona 目录。真正跨服务的共享 grant 定义若需提取，只能从该 owner 单轨引用至 metadata 共享协议，不能保留两份 authoring。
- 关联要求/验收：本域 `REQ-001`/`DOM-001`；账号安全与撤权细化见 [settings DEC-003](./settings-and-device-token/design.md#dec-003)，并关联其 `REQ-004`/`SIT-003`；合集用户行为沿用 [ordered-post-collection GWT-002/GWT-003](../discovery-content/publish-comment-reaction/ordered-post-collection/spec.md#gwt-002)。
- 可测试性：local_contract 必须证明伪造源 credential、跨账号 persona、假 delegate、错 recipient/operation/resource/hash/digest/surface/scope、过期及 epoch 漂移均拒绝；api_integration 必须穿过真实签发/在线验证/owner 执行，并验证合法 owner 与不同 viewer 不扩大权限。测试应由各层现有 DOM/SIT/GWT 锚点绑定，不把仅 signer/verifier 单测或旧 REST/Mongo 测试算作此链通过。
- 实施状态与交接：这里只冻结决定，签发/验证 canonical wire、生产装配和上述真实结果尚未完成；身份实现任务须先取得 UserAccount exact owner/ref 与不重叠 claim，补足身份 owner 最低可关闭 spec 的验收及 OPEN，再进行 contracts→verify/codegen→实现/测试。当前不得声明 delegated 链 ready，也不关闭合集或 gateway 的现有 OPEN。

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
