# AppRoot Design：应用根规格

> 对应规格：[AppRoot spec](./spec.md)

## 1. 背景、设计目标与非目标

- 设计目标：趣我圈以内容事实、单一 Gathering、活动群聊与小趣官方 Skill 把一次内容发现转化为可加入、可协作、可完成和可传播的真实经历；AppRoot 统一用户旅程、跨领域场景、全局术语、边界和 UAT。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. 全局上下文与所有权

- [`assistant-run-learning`](./assistant-run-learning/spec.md)：让用户获得可恢复、可解释且上下文一致的小趣回答；让平台以版本化策略、学习事件、反馈聚合和用户确认的画像提案持续改进助手行为。
- [`chat-conversation`](./chat-conversation/spec.md)：拥有 Conversation、ConversationMembership、Message、Announcement、回执与通话事实；活动群聊是有效参与者加入后的默认主场，但不拥有 Gathering、Participation、容量、准入、Revision、Outcome 或 Plan。
- [`circle-community`](./circle-community/spec.md)：除 Circle 社区事实外，拥有 Gathering、root-owned GatheringParticipation、GatheringRevision、Outcome 与 room binding state，并签发公开详情和活动看板所需的活动投影。
- [`discovery-content`](./discovery-content/spec.md)：发现流、推荐排序、内容发布、评论互动、媒体处理与帮读能力。
- [`gateway-orchestrator-foundation`](./gateway-orchestrator-foundation/spec.md)：提供网关统一入口、鉴权限流、防护策略与跨服务编排基础能力。
- [`global-search-experience`](./global-search-experience/spec.md)：统一搜索覆盖联系人、会话、内容、圈子、主页、地点和网络结果，在本地联想与云侧最终结果之间保持清晰合同，并将反馈归因到搜索和推荐。
- [`object-homepage-network`](./object-homepage-network/spec.md)：`object-homepage-network` 是用户主页、圈子/群组主页、共享主页三类对象页的跨域体验与契约收口层。
- [`platform-ops-governance`](./platform-ops-governance/spec.md)：建立平台侧可观测、配置治理、服务治理、安全隐私、发布回滚的统一治理能力。
- [`product-ops-growth`](./product-ops-growth/spec.md)：建立产品运营侧的事件采集、实验分桶、反馈评估与策略优化闭环。
- [`recommendation-platform`](./recommendation-platform/spec.md)：为训练、推理和评估提供统一模型生命周期，使推荐策略能够基于真实反馈安全晋升或回滚，并通过 HTTP 或不可变离线产物与 Go 推荐引擎协作。
- [`runtime`](./runtime/spec.md)：runtime 作为跨端云机制领域服务，治理共享 runtime 包和 integration-service 等独立机制 进程；部署边界不形成新的 L1，业务对象与 Vendor SDK 不得穿透。
- [`shared-homepage-network`](./shared-homepage-network/spec.md)：让用户发现具体事物的长期主页、挂载内容和评价，并让可信主体通过认领、维护、状态上报与软下线保持主页事实可靠。
- [`travel-journey`](./travel-journey/spec.md)：定义 Gathering 上 Plan、Map、Calendar、Experience 的旅行体验组合，并治理现有 travel-service 到 Circle 目标模型的 target-only 迁移；不再把 Trip 定义为长期公共独立根。
- [`user-identity-profile-relationship`](./user-identity-profile-relationship/spec.md)：让用户以默认账号或明确选择的 Persona 安全进入应用、维护公开资料和设置、建立或解除关系，并在所有业务领域获得一致的主体与权限语义。

## 3. 跨域协作与数据流

- AppRoot Journey 只编排参与 L1 的公开结果；写事实始终由所属 L1 的 command 完成。
- 跨域读取使用公开 query/projection，异步变化使用公开 event，任何缓存都不得成为写真相源。
- 内容驱动 Gathering 的主链固定为：Content 提供 Post/Media 来源引用，Circle 创建并发布 room-ready Gathering，Recommendation 只排序公开投影，Circle 完成准入并投影有效 Participation，Chat 提供活动群聊与 Announcement，Board 组合 owner 读模型，Circle 形成 Outcome，用户确认后 Content 发布回顾。
- ConversationMembership 是 GatheringParticipation/Organizer authority 的访问投影而非参与真相；投影延迟时保留可恢复等待态，禁止把裸建群、普通 direct、自动 mutual 或 App 本地状态当作降级成功。
- alpha/beta/gamma/prod 的 App 统一使用 production Remote composition，第一方业务内容经 `quwoquan_data` canonical publish、immutable release、环境 importer 后进入公开 query/projection。
- Alpha/Beta/Gamma 的用户交易事实由真实非生产主体经领域公开 command/event 产生并绑定候选与清理回执，Prod 只接受真实用户或正式运营行为。

## 4. 全局架构

- App 通过生成契约访问服务；服务本地 contracts 拥有业务 wire，中心 metadata 只保留跨服务共享 schema。
- 目录结构与父子 spec 表达特性树，运行时扫描生成上下文和变更报告，不提交人工索引。
- Skill 是面向用户的能力包而不是业务事实 owner：它只声明上下文、Reader、Tool、Connector、编排、触发和展示资产；每个业务事实仍由所属 L1 的公开 command/query/event 持有。

## 5. 关键决策

<a id="dec-001"></a>
### DEC-001 每个领域声明唯一且可验证的工程归属
- 决策：每个领域声明唯一且可验证的工程归属。
- 理由：趣我圈是一套以“遇见同趣，绽放热爱”为品牌表达、以“别人帮你刷内容，我们帮你遇到对的人”为产品主轴的端云一体社交应用。它通过内容、对象主页、交集、关系、圈子、会话、搜索和小趣助手，把内容消费转化为可证、安全、可沉淀的同趣连接；AppRoot 统一用户旅程、跨领域场景、全局术语、边界和 UAT。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`

<a id="dec-002"></a>
### DEC-002 四环境 Remote、内容 release 与领域 command 单轨
- 决策：alpha/beta/gamma/prod 的 App 使用同一 Remote composition；内容、Creator、实体与发布媒体只由环境已激活的 canonical immutable release 提供，用户、评论、圈子、会话与消息只由所属领域公开 command/event 产生。Alpha/Beta/Gamma 允许候选绑定的真实非生产验收数据，Prod 为真实数据专用。
- 决策：`productLifecycleState` 独立于环境名；当前四环境可承载 `releaseClass=research` 的内部研究 release，但必须关闭匿名内容/媒体、公开 CDN、分享、导出与索引，并使用白名单身份、内部签名、研究态标识、短期签名 URL 和访问审计。切换 `commercial` 时冻结新 source digest 与 release，只投影 `rightsStatus=verified && distributionDecision=commercial_allowed`，不得就地改写或复用 research release/receipt。
- 理由：环境内 Mock、fixture seed、数据库直写或派生投影预填会绕过 importer、媒体交付、鉴权、聚合不变量与事件恢复链路，产生无法晋级到生产的伪绿。
- 被否决方案：Alpha runner 注入聚合 Mock、由环境名推断 lifecycle、T3/UAT 直写数据库、服务失败后返回 fixture、把评论或消息混入内容 release、把 research receipt 冒充 commercial readiness、在 Prod 创建测试业务对象。
- 约束与影响：测试 double 只存在于 local_contract 测试树。Alpha/Beta/Gamma 的验收写入必须绑定真实非生产主体、公开 command receipt、候选摘要和受控清理；非 Prod 第三方 Provider substitute 只存在于服务防腐层并返回真实成功或结构化 unavailable。回滚仅允许上一 Remote artifact、service config 或 canonical release。
- 关联要求：`REQ-009`、`REQ-010`

<a id="dec-003"></a>
### DEC-003 共同旅行以 Gathering 与可选能力组合
- 决策：共同旅行的活动身份、Host、Participation、准入、会话、生命周期与 Outcome 由 Circle 的 Gathering 单轨拥有；Plan、Map、Calendar 与 Experience 是可选能力组合。`travel_companion` 只通过 active Skill package、公开 Reader、受控 Tool/Connector 和 typed ActionIntent 读取或提议改变 owner 事实。
- 理由：1:1、多人兴趣活动和多日旅行共享同一参与与协作不变量；继续让 Trip 成为公共独立根会复制成员、会话、取消与完成状态。聊天文本和 Assistant 状态同样不能承担不可变修订、主动提醒、地图与内容关联。
- 被否决方案：Trip 与 Gathering 长期双根、Chat Message 充当当前计划、Assistant 保存活动副本、按旅行垂类建立专用 App/Agent 分支。
- 约束与影响：现有 travel-service 只按逐对象 target-only 流迁移；切流后只读 Circle 目标，不双读、不双写、不保留兼容 fallback。Presentation 只通过安全语义 AST 与 canonical object reference 打开 owner 页面。
- 关联要求：`REQ-008`、`REQ-012`

<a id="dec-004"></a>
### DEC-004 Gathering 真相归 Circle，加入后产品主壳归 Chat
- 决策：Circle 拥有 Gathering root 及其 Participation、Revision、Outcome 与 room binding state；Chat 拥有唯一 contextual Conversation、ConversationMembership、Message 与 Announcement。活动看板是组合两域及可选能力投影的 typed read model，不是 Workspace 聚合。
- 理由：容量、准入、取消和 Outcome 必须与参与写入同属一个 owner；消息可靠性、公告、已读与文件索引必须留在 Chat。产品默认进入群聊不改变事实所有权。
- 被否决方案：把 Gathering 迁入 chat-service、以普通建群代替活动、建立 WorkspaceManifest、让 Recommendation 或 Feed 保存可写活动状态。
- 约束与影响：Publish 必须以 room binding ready 为前置；有效 Participation 才能获得 participant room access，Organizer authority 单独投影管理访问且不占参与席位。退出、移除、Block、取消和安全撤权均通过 owner event 收敛，不建立自动关系。
- 关联要求：`REQ-013`

## 6. 质量与运行约束

- 应用根负责跨领域编排、UAT、全局架构、技术约束、观测、灰度和回滚。
- `UserAccount` 只承担账号、认证和安全；`Persona` 是公开业务主体。
- Gathering 关键 SLI 包括公开详情可用率、响应成功到 room access 收敛时间、room/board 投影新鲜度、并发超员计数、撤权延迟、Outcome 证据完整率和回顾内容反向关联完整率；30 天窗口目标分别不低于 99.9%、P95 不超过 10 秒、P95 不超过 60 秒、超员为零、P95 不超过 10 秒、证据完整率不低于 99.99%。
- 生命周期、安全、准入写失败与撤权链路 100% 记录审计；普通读取 trace 可按受治理采样策略采样，在线 trace 默认保留 30 天，聚合漏斗默认保留 13 个月，安全证据按所属 retention contract 执行。
- 10 分钟窗口内公开详情成功率低于 99%、room access 或撤权 P95 超过 60 秒、任何超员或未授权 room access 立即告警；告警阈值、metric ID 与标签只引用所属 observability contracts。
- 创建、公开发现、准入、room/board 与 Outcome/回流分别受可独立关闭的受治理 feature flag 控制；回滚 owner 为 Circle 值班负责人，Chat 值班负责人负责 room/board 投影回滚，Content 值班负责人负责回流入口。回滚关闭新写和新曝光，不删除既有 Gathering，不恢复裸建群或双读。

## 7. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：游客关闭登录回安全首页不循环，登录成功继续进入写文字。
- 恢复动作：按 canonical recovery action 重试、刷新或回滚到上一份已验证配置。
- 禁止 fallback：不得使用 Mock、旧 wire、双读双写或跨域直写伪造成功。
