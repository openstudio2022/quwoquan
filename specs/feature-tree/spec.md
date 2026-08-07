# AppRoot Spec：应用根规格

## 1. 产品目标与用户价值

趣我圈是一套以“遇见同趣，绽放热爱”为品牌表达、以“别人帮你刷内容，我们帮你遇到对的人”为产品主轴的端云一体社交应用。它通过内容、对象主页、交集、关系、圈子、Gathering、活动群聊、搜索和小趣助手，把内容消费转化为可加入、可协作、可完成、可沉淀的同趣行动与共同经历；AppRoot 统一用户旅程、跨领域场景、全局术语、边界和 UAT。

### 目标受众

首个高密度供给来自已有内容与受众的创作者、稳定 Circle、具有具体行动计划的 Persona，以及确有活动供给的 Entity Homepage Owner；需求侧覆盖低压力 1:1、多人兴趣活动和需要共同计划的多日行程。发起者需要低成本完成说明、招募、筛选、组织和通知，参与者需要先看清 Host、时间、地点、容量、要求和风险再响应，加入后直接在活动群聊与看板协作，完成后由用户确认把经历发布为内容；参与 Gathering 本身不自动建立关注、互关或其他关系。

### 竞品定位

同类产品各自只覆盖其中一段。出行预订类应用拥有完整地点与行程数据，但不保留照片的拍摄元数据，用户之间的共同经历也没有被表达为社交图谱。摄影社区拥有完整拍摄参数，但没有实体主页网络，作品只按题材聚合而不按现实对象连接。泛内容社区拥有社交关系，但内容不绑定结构化实体，拍摄事实无法参与推荐与解释。

趣我圈的可防御能力是把“真实内容事实链”“行程计划与修订”“群聊和圈子协作”“同行关系”“现场 Moment”归入同一条可持续生长的共同旅行时间线，再由小趣以 Skill、站内 Reader、公网证据和受控 Tool 持续服务。地点、时间与画面语义仍参与发现、搜索、推荐和连接；计划、变更、采用、随拍与分享则把一次内容浏览变成真实共同经历。组合后的事实链、协作链与关系链，而非一份孤立 AI 行程文本，才形成其他私人助手或公众服务助手难以短期补齐的资产。

## 2. 范围与非目标

### In Scope

- 覆盖用户从进入、发现、创作、互动、关系、消息、助手到持续运营的完整应用体验。
- 以旅行摄影为第一垂类建立标签纵深：地理、机位、画面主体、季节与光线构成可组合计算和解释的语义轴；器材与拍摄参数保留为作者可控披露事实，不进入搜索筛选、Creator chip 或可见交集。
- 以“活的共同旅行时间线”为旅行旗舰体验，覆盖行前吃玩住行共同计划、行中变化提醒和贴身讲解、随拍归档、行程地图，以及行后游记整理和关系沉淀。
- 以单一 Gathering 承载从内容、C 位或主页发起的 1:1、多人和多日行动，覆盖公开详情、准入、活动群聊与看板、Outcome 及内容回流。
- 以官方 Skill 为面向用户的能力封装，统一上下文读取、公网证据、受控外部应用连接、主动触发、长任务与 Adaptive Presentation。
- 境外目的地覆盖到主流出境目的地的一级行政区与主要城市两层，使境外内容与境内内容获得同等的定位精度。

### Out of Scope

- 不在特性树复制 metadata schema、实现任务、测试排列组合或执行历史。
- 第一阶段不提供收费、预订支付、私人导游撮合交易、第三方 Skill 市场、连续实时位置跟踪或替代公共应急服务。

## 3. 术语与全局要求

<a id="req-001"></a>
### REQ-001 发现、搜索与对象连接基础旅程

- 用户可从发现流进入内容详情，完成评论互动并跳转到真实作者或对象主页。
- 首页 Post 流与视频书在首屏、持续滚动、弱网、并发峰值与长会话下均必须在声明预算内进入可用或可恢复终态，且端侧资源、服务端并发与缓存保持有界。
- 用户可在统一搜索入口检索内容、圈子、会话、主页和地点，失败与空结果均有明确终态。
- 用户可从对象页理解交集依据并进入受关系、隐私和权限门禁保护的连接动作。

<a id="req-002"></a>
### REQ-002 文字、照片与视频创作、发布和结果回流

- 游客关闭登录回安全首页不循环，登录成功继续进入写文字。
- micro/article 两种形态由用户显式确认并分别回流详情或作品浏览器。
- 断网、杀进程、限流和依赖恢复后同一 intent 最多创建一个 Post。
- 长度/频控或安全 reject 不创建 Post；review/unavailable 只创建不可公开 pending_review Post 并进入人工 Case，未获批准的公开 Post 数恒为零。
- 发布后内容立即在作者可见读模型出现，公开性和圈子分发符合真实设置。
- 照片保持用户排序，原图按流上传，发布命令只携带 MediaAsset ID。
- 视频原片按流上传；worker 生成 H.264/AAC fast-start MP4、封面和预览轨道后才允许公开发布。
- 已发布、待审核和待重试均进入明确结果面；用户可查看作品或发布任务，不以 Toast 代替终态。

<a id="req-003"></a>
### REQ-003 应用安全进入与不可恢复异常恢复

- 正常启动优先进入登录页、首页、新用户流程或可安全运行的降级 Shell；启动等待超时本身不得被判定为致命异常。
- 启动前发生已确认的根级致命异常时停止后续初始化，静默保存脱敏异常，并进入不依赖业务框架的恢复页；启动阶段不提供重复重试。
- 运行中发生根级不可恢复异常时只允许一次受控主容器重建；成功直接替换路由进入首页，失败后不得形成恢复循环。
- 恢复页在全部状态提供官方网页版。
- 版本服务确认有新版且存在当前平台可安装通道后，Android 进入趣我圈官网受信 APK 下载通道；公众 iOS 进入趣我圈 PWA 安装指引，已登记测试设备才可使用受控 Ad Hoc 通道。只有版本服务确认后才能显示“需要更新”或“已是最新版本”。
- 页面只表达已确认事实、恢复状态和当前动作，不显示技术原因、诊断编号、日志进度、错误码或缺乏操作价值的不确定描述。

<a id="req-004"></a>
### REQ-004 我的主页转发互动双向历史

- 互动保持两层导航且选中转发后可切换收到的/我发起的。
- received 与 initiated 文案、预览、空态、分页、刷新、滚动恢复和点击优先级符合规格。
- received 未读与真实 impact 正确，initiated 不显示未读或 impact。
- 他人主页不请求转发列表，Persona切换不残留旧数据，服务端拒绝越权。
- 八个 share interaction 观测事件携带完整公共归因参数。

<a id="req-005"></a>
### REQ-005 iOS/Android 边缘滑动返回与退出保护

- 无底栏普通页面通过 iOS leading edge 或 Android 左/右边缘返回上一页。
- 沉浸式媒体浏览器边缘滑动触发返回，不误触媒体左右切换。
- Android 主页根页第一次边缘滑动只提示再次滑动退出。
- Android 主页根页第二次边缘滑动在 2 秒保护窗口内退出或交给系统返回。
- iOS 根页无可 pop 栈时不模拟退出应用。
- iOS 与 Android 的系统手势区域、阈值、动画和提示分别验证。

<a id="req-006"></a>
### REQ-006 对外引流与深链回流端到端价值闭环

- 5 类对象都能从统一分享面板分享到微信会话/朋友圈，并生成站外可点击的 HTTPS 落地链接。
- 已安装用户在微信内（Android/鸿蒙用 wx-open-launch-app、iOS 用 Universal Link）、在浏览器内（Universal Link/App Links/scheme）点击后回流到 App 对应详情页。
- 未安装用户进入趣我圈官网；Android 可明确点击下载正式签名 APK，iOS 可添加 PWA 到主屏幕，原生安装完成后的首启再通过延迟深链还原原始目标对象。
- 公开 Web 内容/主页可被搜索引擎索引（canonical/OG/JSON-LD/robots/sitemap），并提供安装转化入口。
- 一键海报（含二维码与口令）可投放到不支持外链的 UGC 平台，扫码或口令识别后回流到目标对象。
- 全链路携带 referralSource/share_id/UTM/口令归因，可在指标大盘按渠道与对象类型统计转化。

<a id="req-007"></a>
### REQ-007 消息社交连接端到端价值闭环

- 互关用户从 TA 的主页点击消息，可创建或复用 direct conversation 并完成发送/接收。
- 非互关用户只能先打招呼；对方回复后升级为正式 direct conversation，未回复前不得进入普通会话列表。
- 用户可从全局发起群聊入口选择服务端返回的候选来源与成员，建群后进入 group conversation。
- 用户可从兴趣圈子进入默认公共群或自建群；从学校组织主页进入院系/班级节点所绑定的班级群会话。
- 用户可从共享主页的相关群组卡片进入真实 Circle/CircleGroup 绑定的群会话，主页本身不拥有 conversation。
- 用户可在 1v1 或群会话中邀请小趣并 @小趣，收到 assistant_reply，且消息进入同一同步和审计链路。
- 合法关系或会话中的用户可发起、接听、拒绝、取消和结束音视频通话；在线事件与离线 ring/cancel 可靠送达，结束后回到原会话并产生 system_call_log。
- Provider 不可用、权限拒绝、弱网重连和超时均有结构化终态；Alpha/Beta/Gamma required 验收使用受管非生产租户的非内存 Provider 并绑定 conformance receipt，Prod 独立验证正式 APNs/FCM/LiveKit。

<a id="req-008"></a>
### REQ-008 无处不在的小趣私人助理商用主线

- 用户从首页、内容页、群聊、搜索页、个人页进入小趣时，入口语义和会话状态一致，不维护第二套助手体验。
- 用户在内容页提问时，小趣基于当前对象、内容片段、标签和站内外检索给出有引用边界的回答。
- 用户在群聊中 @小趣 时，消息以结构化 mentions 触发 AssistantMentioned，assistant-service 基于最近消息窗口与成员信息回群回复。
- 用户可订阅主题并投递到用户或会话；投递前执行 consent、频控、静默、去重与审计。
- 小趣回答后的赞/踩、采纳、撤销和引用打开能回流到 InteractionEvent，并携带 referralSource、triggerMessageId、assistantTurnId。
- 官方响应式 Skill 默认可发现和使用，用户启用设置、数据/能力 Consent、主动 Subscription 与共享场景 Placement 分别由独立对象表达，不相互冒充。
- 群聊或圈子中的小趣代表同一助手成员；可用 Skill 由 active package、共享安全声明和管理员禁用策略共同决定，不由 Chat Membership 绑定单一 Skill。

<a id="req-009"></a>
### REQ-009 当前全部跨对象 Journey 商用准出

- 当前全部 Journey 的 page/surface/operation/object/store/event/behavior/metric 节点可正向追踪，且无反向孤儿。
- command 经过该事实唯一 write owner，query 读取 named Slice；App 只访问 generated Gateway operation。
- 每条 Journey 至少跨两个真实业务对象，并验证权限、错误恢复、幂等、副作用、投影收敛和推荐/运营回流。
- 所有页面通过 light/dark、多屏、无障碍、语义 token、性能、弱网和 capability 降级检查。
- alpha/beta/gamma/prod 均使用同一个 production Remote composition；内容、Creator、实体与发布媒体只来自对应环境已激活的 canonical immutable release，用户、评论、圈子、会话与消息只经所属领域公开 command/event 生效。Alpha/Beta/Gamma 可创建候选绑定的真实非生产验收数据，Prod 只接受真实用户或正式运营行为。
- 环境名不再隐含内容分发成熟度；`productLifecycleState=research|commercial` 必须由受治理配置、immutable release、activation receipt 与 App readback 同源显式声明。
- `research` 可在内部四环境消费权利尚未验证但可合法取得的素材，前提是身份白名单、匿名访问关闭、私有短签媒体、禁止分享/导出/索引与审计日志全部有证据。
- `commercial` 只接受逐资产商业分发授权闭合的独立新 release。
- Alpha/Beta/Gamma required 验收绑定受管非生产租户的非内存 Provider，Prod 完成正式 Provider、实时 SLO、灰度和回滚验证；任何环境 App 均不含 seed/Mock/Memory/Noop 或运行时数据源切换。
- local_contract、api_integration、user_acceptance 均有真实断言和 CaseResult；禁止路径存在、动态 skip 或 Memory 假集成充当证据。

<a id="req-010"></a>
### REQ-010 以业务对象为中心的端云 Object Facade、统一公共 URL、存储无关 Data Ports、页面 Query Slice、错误恢复和三层测试合同

- 以业务对象为中心的端云 Object Facade、统一公共 URL、存储无关 Data Ports、页面 Query Slice、错误恢复和三层测试合同。
- App 业务实现按 canonical `service/context/object` 身份形成纵切，业务源码只位于 `lib/service/<service>/<context>/<object>/{domain,application,adapters,presentation}`，对象测试位于 `test/<layer>/service/<service>/<context>/<object>`；共享 runtime、设计系统与本地化不承担业务对象 owner，旧 `ui/cloud/core/app/application/infrastructure` 大桶不得成为并行入口。
- App 层义务由对象的真实端侧能力决定：被 App operation 消费才要求 application/adapters，被页面认领才要求 application/presentation，只有端侧承担不变式或状态机才要求 domain；未被 App 消费的纯云对象不得以空目录或占位 facade 冒充实现。
- 每个页面必须有唯一 source owner，并完整保留其参与对象；多对象页面由 source owner 的 presentation 组合其他对象公开 application port，不得因物理归档而丢失参与对象或直接导入兄弟对象私有层。
- App 依赖方向保持 `presentation -> application -> domain` 与 `adapters -> application/domain`，具体 adapter 只在唯一 composition root 装配；跨对象只经公开 port/facade/event，禁止 barrel re-export、旧路径 shim、双轨 import 或为错误目录提供 fallback。
- 业务对象 kind 是闭集：
  - `aggregate_root` 拥有一致性边界内的状态与不变式。
  - `append_only_fact` 是不可变事实流。
  - `projection` 是可由源事实重建的读模型。
  - `external_reference` 是外部系统身份与元数据的本地引用。
  - `runtime_session` 是会话生命周期内的运行态。
  - `process_manager` 编排跨对象长流程（saga）。
- 六类均已入仓；`process_manager` 的对象层、写入口与禁止层由架构门禁按真实对象树派生和验证，不得用其他 kind 顶替。
- 任何状态变更必须经该事实唯一 write owner 的 `aggregate_root` 或 `process_manager`；跨对象写只经目标 owner 的公开 command，不得绕过 owner 直写其存储或投影。
- `append_only_fact` 只能经其自身 append sink 追加，不得有 update 或 mutate 语义；纠正只能追加新事实，不得就地改写或删除历史。
- `projection` 与 `external_reference` 不得有任何写操作：projection 只由源事实重建，external_reference 只随外部系统同步刷新，二者均不作为写入口或真相源。
- `runtime_session` 不是持久化业务聚合，只在会话生命周期内存在；会话结束即失效，不得承载需要跨会话保留的业务事实。
- `process_manager` 承载长流程编排，拥有自身状态、进度、取消与恢复语义；它不复制被编排对象的事实，只按公开 command 推进并记录编排进度。
- query 直接读取强类型 Slice，不为形式统一加载聚合。
- App 只访问统一 Gateway base URL 和 generated operation，不感知服务进程、存储或内部 URL。
- 统一存储是对象专属 AggregateStore/Reader 的生成模式，不是万能 CRUD Repository。
- 页面必须满足主题、语义 token、多屏、多端、状态恢复、无障碍、性能和观测合同。
- alpha/beta/gamma/prod 的内容对象均绑定 release/import receipt，非生产交易对象绑定真实主体、公开 command receipt 与清理回执，Prod 交易对象只来自真实行为。
- 测试 double 只存在于 local_contract 测试树，四环境 artifact 均禁止 fixture/Mock/Memory/Noop。

<a id="req-011"></a>
### REQ-011 标签准入必须同时满足可采集、可消费、可反馈、可解释

- 新增或变更标签时必须声明具体写入通道，来源限于拍摄元数据、地点选择、创作者勾选、点评勾选与行为事件；没有任何写入通道的标签不得进入发布物。
- 新增或变更标签时必须声明在线消费方式，且至少落在召回过滤、排序因子、交集判定与搜索筛选之一；只被存储而不被任何在线路径读取的标签不构成能力。
- 每个标签必须至少能被一种用户行为带回，使正向与负向反馈都能改变后续分发，不允许只有正向信号的单向通道。
- 每个标签必须能出现在交集句或推荐理由中；无法向用户解释的标签不得作为对用户可见结论的依据。
- 标签轴之间必须保持正交，同一现实概念跨轴出现时由标签自身声明同义关系，跨轴关联不依赖路径前缀推测。

<a id="req-012"></a>
### REQ-012 活的共同旅行时间线

- 旅行必须表达为 Gathering 与可选 Plan、Map、Calendar、Experience 能力的体验组合；时间、容量、Host、参与、准入、会话绑定、生命周期和 Outcome 继续由 Gathering 真相源拥有，`Trip` 不作为长期公共独立根。
- 同一活动群聊可呈现多个旅行相关能力入口；小趣必须根据明确 Gathering 引用、当前上下文或用户消歧选择目标，不得默认修改错误活动或计划。
- 计划变化必须形成可读 Revision、影响范围和确认结果；主动提醒只投递给相关参与者并执行静默、频控、去重和隐私策略。
- Experience 只引用 MediaAsset、Post 或所属 Plan 项，不复制内容事实；公开分享必须移除私人住宿、联系方式、参与者名单和实时精确位置。
- 行程结束可生成用户可编辑的 LocalPostDraft；只有用户确认后 Content owner 才能发布，助手不得把草稿或生成结果伪装为已发布内容。

<a id="req-013"></a>
### REQ-013 内容驱动 Gathering 与活动群聊闭环

- 用户可从首页发现、内容/视频书、Persona/Circle 主页或全局 C 位发起或打开同一 Gathering；Recommendation 只对 Circle 提供的合格公开投影排序，不拥有活动、准入或参与事实。
- 未加入者进入公开详情并只看到当前披露策略允许的 Host、时间地点范围、容量、要求、费用/风险说明和一个动态主动作；加入、申请、接受邀请、名额提醒、取消与完成必须遵循所属 canonical contracts。
- Circle 拥有 Gathering、root-owned GatheringParticipation、GatheringRevision、Outcome 与 room binding state。
- Chat 拥有 Conversation、ConversationMembership、Message 与 Announcement；Content 拥有 Post、Media 与 Report。
- 有效参与者加入后以活动群聊为默认主场，并从同一会话打开活动看板；活动看板是组合 owner 公开事实的可重建读模型，不是 Workspace 或第二聚合。
- 取消、提前结束、安全终止与完成必须保持可区分；`occurred` 不能仅由时间到达或单方声明产生。用户可从完成后的 Gathering 创建回顾草稿，经确认后发布并关联原活动、Host 与来源内容。
- GatheringParticipation 与 Follow、mutual、CircleMembership、ConversationMembership 分属不同事实；加入、到场或完成均不得自动建立 mutual 或任何额外关系等级。
- 字段、operation、route、surface、error、event 与 metric 只引用所属服务 contracts 或跨服务 metadata，不在本规格复制定义。

## 4. 用户旅程

### 领域服务导航

- [assistant-run-learning](./assistant-run-learning/spec.md)
- [chat-conversation](./chat-conversation/spec.md)
- [circle-community](./circle-community/spec.md)
- [discovery-content](./discovery-content/spec.md)
- [gateway-orchestrator-foundation](./gateway-orchestrator-foundation/spec.md)
- [global-search-experience](./global-search-experience/spec.md)
- [object-homepage-network](./object-homepage-network/spec.md)
- [platform-ops-governance](./platform-ops-governance/spec.md)
- [product-ops-growth](./product-ops-growth/spec.md)
- [recommendation-platform](./recommendation-platform/spec.md)
- [runtime](./runtime/spec.md)
- [shared-homepage-network](./shared-homepage-network/spec.md)
- [travel-journey](./travel-journey/spec.md)
- [user-identity-profile-relationship](./user-identity-profile-relationship/spec.md)

<a id="jny-001"></a>
### JNY-001 身份进入与动作续接

- 用户目标：游客完成欢迎、同意、商业登录、Persona 选择与账号安全后，登录成功继续原动作，关闭登录则回到安全状态且不循环。
- 起点：用户从应用或外部入口发起旅程。
- 成功终态：用户目标形成可观察且可恢复的业务结果。
- 失败恢复：失败进入可解释终态，并提供符合 canonical error/recovery 契约的恢复动作。
- 参与领域：
  - [user-identity-profile-relationship](./user-identity-profile-relationship/spec.md)
  - [runtime](./runtime/spec.md)

<a id="scn-004"></a>
#### SCN-004 欢迎、授权、商业登录、Persona 与原动作续接

- 场景目标：游客完成欢迎、同意、商业登录、Persona 选择与账号安全后，登录成功继续原动作，关闭登录则回到安全状态且不循环。
- 领域交接：user-identity-profile-relationship → runtime
- 对应验收：`UAT-009`

<a id="jny-002"></a>
### JNY-002 应用安全进入与不可恢复异常恢复

- 用户目标：应用能够安全运行时进入登录页、首页、新用户流程或降级 Shell；无法安全启动或继续使用时，用户获得确定、无技术暴露且始终可执行的更新、网页版或一次性重新进入动作。
- 起点：用户从应用或外部入口发起旅程。
- 成功终态：用户进入安全 Shell、一次性重新进入后的首页、iOS PWA、Android 官网下载或官方网页版。
- 失败恢复：外部通道打开失败仅显示短暂系统提示并恢复按钮；异常日志、版本服务或授权交换失败不得阻塞仍可用的恢复动作。
- 参与领域：
  - [runtime](./runtime/spec.md)
  - [product-ops-growth](./product-ops-growth/spec.md)

<a id="scn-005"></a>
#### SCN-005 启动与运行时不可恢复异常恢复

- 场景目标：根级致命异常由原生与 Flutter 同一恢复状态机收敛；启动失败不重试，运行时只重建一次，版本结论只来自版本服务，网页版始终可用，异常日志静默保存和补报。
- 领域交接：runtime → product-ops-growth
- 对应验收：`UAT-003`

<a id="jny-003"></a>
### JNY-003 内容发现到消费

- 用户目标：用户从发现页进入内容详情，并完成阅读、互动或跳转作者主页。
- 起点：用户从应用或外部入口发起旅程。
- 成功终态：用户目标形成可观察且可恢复的业务结果。
- 失败恢复：失败进入可解释终态，并提供符合 canonical error/recovery 契约的恢复动作。
- 参与领域：
  - [discovery-content](./discovery-content/spec.md)
  - [user-identity-profile-relationship](./user-identity-profile-relationship/spec.md)
  - [shared-homepage-network](./shared-homepage-network/spec.md)
  - [chat-conversation](./chat-conversation/spec.md)

<a id="scn-007"></a>
#### SCN-007 从内容流打开详情

- 场景目标：用户从发现页进入内容详情，并完成阅读、互动或跳转作者主页。
- 领域交接：discovery-content
- 对应验收：`UAT-001`

<a id="scn-009"></a>
#### SCN-009 内容详情跳转作者主页

- 场景目标：用户从发现页进入内容详情，并完成阅读、互动或跳转作者主页。
- 领域交接：discovery-content → user-identity-profile-relationship → shared-homepage-network
- 对应验收：`UAT-001`

<a id="scn-008"></a>
#### SCN-008 评论互动与回流

- 场景目标：用户从发现页进入内容详情，并完成阅读、互动或跳转作者主页。
- 领域交接：discovery-content → chat-conversation
- 对应验收：`UAT-001`

<a id="jny-004"></a>
### JNY-004 内容创作到发布回流

- 用户目标：用户从全局创作入口写文字、发照片或发视频，可靠保存草稿与媒体，经过安全准入和真实媒体处理后发布，并立即看到内容及真实分发去向；失败、排队、处理中和审核结果都有可恢复终态。
- 起点：用户从应用或外部入口发起旅程。
- 成功终态：用户目标形成可观察且可恢复的业务结果。
- 失败恢复：失败进入可解释终态，并提供符合 canonical error/recovery 契约的恢复动作。
- 参与领域：
  - [discovery-content](./discovery-content/spec.md)
  - [user-identity-profile-relationship](./user-identity-profile-relationship/spec.md)
  - [circle-community](./circle-community/spec.md)
  - [runtime](./runtime/spec.md)
  - [product-ops-growth](./product-ops-growth/spec.md)

<a id="scn-001"></a>
#### SCN-001 写文字创建、可靠发布与结果回流

- 场景目标：用户从全局创作入口写文字、发照片或发视频，可靠保存草稿与媒体，经过安全准入和真实媒体处理后发布，并立即看到内容及真实分发去向；失败、排队、处理中和审核结果都有可恢复终态。
- 领域交接：discovery-content → user-identity-profile-relationship → circle-community → runtime → product-ops-growth
- 对应验收：`UAT-002`

<a id="scn-002"></a>
#### SCN-002 照片创建、像素编辑、原图可靠上传与发布回流

- 场景目标：用户从全局创作入口写文字、发照片或发视频，可靠保存草稿与媒体，经过安全准入和真实媒体处理后发布，并立即看到内容及真实分发去向；失败、排队、处理中和审核结果都有可恢复终态。
- 领域交接：discovery-content → user-identity-profile-relationship → circle-community → runtime → product-ops-growth
- 对应验收：`UAT-002`

<a id="scn-003"></a>
#### SCN-003 视频创建、转码处理、发布与结果回流

- 场景目标：用户从全局创作入口写文字、发照片或发视频，可靠保存草稿与媒体，经过安全准入和真实媒体处理后发布，并立即看到内容及真实分发去向；失败、排队、处理中和审核结果都有可恢复终态。
- 领域交接：discovery-content → user-identity-profile-relationship → circle-community → runtime → product-ops-growth
- 对应验收：`UAT-002`

<a id="jny-005"></a>
### JNY-005 跨领域搜索

- 用户目标：用户在统一搜索入口中查找内容、圈子、聊天记录、主页和地点。
- 起点：用户从应用或外部入口发起旅程。
- 成功终态：用户目标形成可观察且可恢复的业务结果。
- 失败恢复：失败进入可解释终态，并提供符合 canonical error/recovery 契约的恢复动作。
- 参与领域：
  - [global-search-experience](./global-search-experience/spec.md)
  - [discovery-content](./discovery-content/spec.md)
  - [circle-community](./circle-community/spec.md)
  - [chat-conversation](./chat-conversation/spec.md)
  - [shared-homepage-network](./shared-homepage-network/spec.md)

<a id="scn-011"></a>
#### SCN-011 全局搜索查询与筛选

- 场景目标：用户在统一搜索入口中查找内容、圈子、聊天记录、主页和地点。
- 领域交接：global-search-experience → discovery-content → circle-community → chat-conversation → shared-homepage-network
- 对应验收：`UAT-001`

<a id="jny-006"></a>
### JNY-006 应用根导航安全

- 用户目标：用户通过系统边缘手势返回上一页或退出根页时，获得符合平台习惯且不误触的体验。
- 起点：用户从应用或外部入口发起旅程。
- 成功终态：用户目标形成可观察且可恢复的业务结果。
- 失败恢复：失败进入可解释终态，并提供符合 canonical error/recovery 契约的恢复动作。
- 参与领域：
  - [runtime](./runtime/spec.md)
  - [discovery-content](./discovery-content/spec.md)

<a id="scn-006"></a>
#### SCN-006 全局无底栏页面边缘返回

- 场景目标：用户通过系统边缘手势返回上一页或退出根页时，获得符合平台习惯且不误触的体验。
- 领域交接：runtime
- 对应验收：`UAT-005`

<a id="scn-021"></a>
#### SCN-021 沉浸式媒体浏览器边缘滑动返回

- 场景目标：用户通过系统边缘手势返回上一页或退出根页时，获得符合平台习惯且不误触的体验。
- 领域交接：runtime → discovery-content
- 对应验收：`UAT-005`

<a id="scn-022"></a>
#### SCN-022 主页边缘滑动退出保护

- 场景目标：用户通过系统边缘手势返回上一页或退出根页时，获得符合平台习惯且不误触的体验。
- 领域交接：runtime
- 对应验收：`UAT-005`

<a id="jny-007"></a>
### JNY-007 消息社交连接

- 用户目标：用户能从主页、联系人、搜索、圈子、组织节点、相关群组和会话内小趣入口，清晰进入 1v1、请求箱、群聊与助手参与的消息路径。
- 起点：用户从应用或外部入口发起旅程。
- 成功终态：用户目标形成可观察且可恢复的业务结果。
- 失败恢复：失败进入可解释终态，并提供符合 canonical error/recovery 契约的恢复动作。
- 参与领域：
  - [chat-conversation](./chat-conversation/spec.md)
  - [circle-community](./circle-community/spec.md)
  - [user-identity-profile-relationship](./user-identity-profile-relationship/spec.md)
  - [circle-community](./circle-community/spec.md)
  - [shared-homepage-network](./shared-homepage-network/spec.md)
  - [assistant-run-learning](./assistant-run-learning/spec.md)
  - [global-search-experience](./global-search-experience/spec.md)
  - [runtime](./runtime/spec.md)

<a id="scn-012"></a>
#### SCN-012 1v1 私信与打招呼升级

- 场景目标：用户能从主页、联系人、搜索、圈子、组织节点、相关群组和会话内小趣入口，清晰进入 1v1、请求箱、群聊与助手参与的消息路径。
- 领域交接：global-search-experience → chat-conversation → user-identity-profile-relationship
- 对应验收：`UAT-007`

<a id="scn-013"></a>
#### SCN-013 私建群、圈子群、组织节点群与主页相关群入口

- 场景目标：用户能从主页、联系人、搜索、圈子、组织节点、相关群组和会话内小趣入口，清晰进入 1v1、请求箱、群聊与助手参与的消息路径。
- 领域交接：chat-conversation → circle-community → shared-homepage-network
- 对应验收：`UAT-007`

<a id="scn-015"></a>
#### SCN-015 小趣作为会话成员参与消息

- 场景目标：用户在群会话中 @小趣，小趣以会话成员身份基于最近消息窗口与会话内被引用对象的标签与交集事实回群回复，并给出可打开的引用边界。
- 领域交接：chat-conversation → assistant-run-learning
- 对应验收：`UAT-007`、`UAT-011`

<a id="scn-016"></a>
#### SCN-016 会话内音视频通话与离线来电可靠送达

- 场景目标：用户能从主页、联系人、搜索、圈子、组织节点、相关群组和会话内小趣入口，清晰进入 1v1、请求箱、群聊与助手参与的消息路径。
- 领域交接：chat-conversation → user-identity-profile-relationship → runtime
- 对应验收：`UAT-007`

<a id="jny-008"></a>
### JNY-008 圈子、实体主页与讨论协作

- 用户目标：用户从实体主页或搜索进入圈子与组织节点，完成加入、群单元进入、内容协作和权限治理，且主页、圈子、群与会话边界清晰。
- 起点：用户从应用或外部入口发起旅程。
- 成功终态：用户目标形成可观察且可恢复的业务结果。
- 失败恢复：失败进入可解释终态，并提供符合 canonical error/recovery 契约的恢复动作。
- 参与领域：
  - [circle-community](./circle-community/spec.md)
  - [shared-homepage-network](./shared-homepage-network/spec.md)
  - [chat-conversation](./chat-conversation/spec.md)
  - [discovery-content](./discovery-content/spec.md)

<a id="scn-014"></a>
#### SCN-014 实体主页到圈子、组织节点、群单元与会话协作

- 场景目标：用户从实体主页或搜索进入圈子与组织节点，完成加入、群单元进入、内容协作和权限治理，且主页、圈子、群与会话边界清晰。
- 领域交接：circle-community → shared-homepage-network → chat-conversation → discovery-content
- 对应验收：`UAT-009`

<a id="jny-009"></a>
### JNY-009 无处不在的小趣私人助理

- 用户目标：用户在首页、内容页、搜索页、个人页和群聊中都能唤起同一个小趣；小趣理解当前对象、最近会话、站内搜索、社交关系、画像与标签，并能在授权后主动把有价值的信息投递给用户或会话。
- 起点：用户从应用或外部入口发起旅程。
- 成功终态：用户目标形成可观察且可恢复的业务结果。
- 失败恢复：失败进入可解释终态，并提供符合 canonical error/recovery 契约的恢复动作。
- 参与领域：
  - [assistant-run-learning](./assistant-run-learning/spec.md)
  - [runtime](./runtime/spec.md)
  - [global-search-experience](./global-search-experience/spec.md)
  - [chat-conversation](./chat-conversation/spec.md)
  - [circle-community](./circle-community/spec.md)
  - [user-identity-profile-relationship](./user-identity-profile-relationship/spec.md)
  - [discovery-content](./discovery-content/spec.md)
  - [shared-homepage-network](./shared-homepage-network/spec.md)

<a id="scn-017"></a>
#### SCN-017 内容与页面上下文感知问答

- 场景目标：用户在首页、内容页、搜索页、个人页和群聊中都能唤起同一个小趣；小趣理解当前对象、最近会话、站内搜索、社交关系、画像与标签，并能在授权后主动把有价值的信息投递给用户或会话。
- 领域交接：assistant-run-learning → runtime → discovery-content → user-identity-profile-relationship → global-search-experience
- 对应验收：`UAT-008`

<a id="scn-018"></a>
#### SCN-018 群聊话题理解与会话内回复

- 场景目标：用户在首页、内容页、搜索页、个人页和群聊中都能唤起同一个小趣；小趣理解当前对象、最近会话、站内搜索、社交关系、画像与标签，并能在授权后主动把有价值的信息投递给用户或会话。
- 领域交接：assistant-run-learning → chat-conversation → runtime
- 对应验收：`UAT-008`

<a id="scn-019"></a>
#### SCN-019 搜索 handoff 与统一 grounding

- 场景目标：用户在首页、内容页、搜索页、个人页和群聊中都能唤起同一个小趣；小趣理解当前对象、最近会话、站内搜索、社交关系、画像与标签，并能在授权后主动把有价值的信息投递给用户或会话。
- 领域交接：assistant-run-learning → global-search-experience → discovery-content → chat-conversation → shared-homepage-network
- 对应验收：`UAT-008`

<a id="scn-020"></a>
#### SCN-020 小趣主动订阅与用户/会话投递

- 场景目标：用户在首页、内容页、搜索页、个人页和群聊中都能唤起同一个小趣；小趣理解当前对象、最近会话、站内搜索、社交关系、画像与标签，并能在授权后主动把有价值的信息投递给用户或会话。
- 领域交接：assistant-run-learning → chat-conversation → runtime → user-identity-profile-relationship
- 对应验收：`UAT-008`

<a id="scn-034"></a>
#### SCN-034 Skill 发现、设置、授权与共享场景挂载

- 场景目标：用户在 Skill Center 理解官方 Skill 的价值、数据使用、所需连接、主动规则和示例成果，完成个人设置或主动订阅；群/圈管理员维护共享 Skill 禁用策略并查看运行活动。
- 领域交接：assistant-run-learning → runtime → chat-conversation → circle-community → user-identity-profile-relationship
- 对应验收：`UAT-008`

<a id="jny-010"></a>
### JNY-010 对外引流与深链回流

- 用户目标：用户在站外（微信朋友圈/聊天群、小红书/今日头条等 UGC 平台、浏览器、搜索引擎）看到内容或主页的卡片/海报/口令/链接，点击后可靠回流到 App 对应页面；未安装时被引导下载并在安装后还原原始目标。
- 起点：用户从应用或外部入口发起旅程。
- 成功终态：用户目标形成可观察且可恢复的业务结果。
- 失败恢复：失败进入可解释终态，并提供符合 canonical error/recovery 契约的恢复动作。
- 参与领域：
  - [product-ops-growth](./product-ops-growth/spec.md)
  - [runtime](./runtime/spec.md)
  - [discovery-content](./discovery-content/spec.md)
  - [user-identity-profile-relationship](./user-identity-profile-relationship/spec.md)
  - [circle-community](./circle-community/spec.md)
  - [shared-homepage-network](./shared-homepage-network/spec.md)

<a id="scn-023"></a>
#### SCN-023 对象对外分享分发

- 场景目标：用户在站外（微信朋友圈/聊天群、小红书/今日头条等 UGC 平台、浏览器、搜索引擎）看到内容或主页的卡片/海报/口令/链接，点击后可靠回流到 App 对应页面；未安装时被引导下载并在安装后还原原始目标。
- 领域交接：product-ops-growth → discovery-content → user-identity-profile-relationship → circle-community → shared-homepage-network
- 对应验收：`UAT-006`

<a id="scn-024"></a>
#### SCN-024 外链深链回流到 App 目标页

- 场景目标：用户在站外（微信朋友圈/聊天群、小红书/今日头条等 UGC 平台、浏览器、搜索引擎）看到内容或主页的卡片/海报/口令/链接，点击后可靠回流到 App 对应页面；未安装时被引导下载并在安装后还原原始目标。
- 领域交接：runtime
- 对应验收：`UAT-006`

<a id="scn-025"></a>
#### SCN-025 公开 Web SEO 与安装转化

- 场景目标：用户在站外（微信朋友圈/聊天群、小红书/今日头条等 UGC 平台、浏览器、搜索引擎）看到内容或主页的卡片/海报/口令/链接，点击后可靠回流到 App 对应页面；未安装时被引导下载并在安装后还原原始目标。
- 领域交接：runtime → discovery-content
- 对应验收：`UAT-006`

<a id="jny-011"></a>
### JNY-011 内容发现或全局发起到 Gathering 完成回流

- 用户目标：用户从首页、内容/视频书、Persona/Circle 主页或 C 位把兴趣变成可加入的 Gathering，经公开详情和 Host 准入进入活动群聊与看板协作，完成行动并把经确认的经历发布为内容。
- 起点：用户看到 Gathering 公开卡，或从 C 位、内容、主页、会话讨论发起活动。
- 成功终态：Gathering 具有可验证 Outcome；参与者在活动群聊与看板获得一致协作事实，回顾内容关联原 Gathering、Host 与来源内容，是否关注或互关由用户另行决定。
- 失败恢复：登录关闭回安全来源且不循环；满员、待审批、邀请失效、room access 未就绪、取消、重大变更、提前结束或安全终止进入可区分终态，不以裸建群、自动 mutual 或本地合成成功降级。
- 参与领域：
  - [object-homepage-network](./object-homepage-network/spec.md)
  - [circle-community](./circle-community/spec.md)
  - [user-identity-profile-relationship](./user-identity-profile-relationship/spec.md)
  - [recommendation-platform](./recommendation-platform/spec.md)
  - [chat-conversation](./chat-conversation/spec.md)

<a id="scn-026"></a>
#### SCN-026 对象页交集行动深化（同趣围观到破冰升级）

- 场景目标：用户在对象页从交集卡围观同趣的人，沿"围观→轻触→对话"携带交集依据破冰，并在对方回复后升级为保留破冰依据的正式 1v1 会话。
- 领域交接：object-homepage-network → recommendation-platform → chat-conversation
- 对应验收：`UAT-001`、`UAT-011`

<a id="scn-027"></a>
#### SCN-027 内容驱动 Gathering、活动群聊与 Outcome 回流

- 场景目标：Host 从内容或 C 位发起同一 Gathering，用户从首页或主页进入公开详情，经开放加入、申请审批或邀请接受成为有效参与者，随后默认进入活动群聊并使用看板与可选 Plan 协作；旅行多人多日计划与新生同校兴趣活动仅由 canonical Topic/tag、来源和 ExperiencePackage 配置区分，活动完成后由证据形成 Outcome，参与者确认发布回顾内容，且参与不自动改变关注关系。
- 领域交接：circle-community → recommendation-platform → user-identity-profile-relationship → chat-conversation
- 对应验收：`UAT-001`、`UAT-011`

<a id="scn-029"></a>
#### SCN-029 可行动对象进入会话

- 场景目标：用户把内容、主页、圈子或 Gathering 分享进会话后得到可行动 card，card 的行动按云侧登记的行动键与可达性分流，尚不可承接的行动展示为不可执行的规划口径而不伪造成行。
- 领域交接：object-homepage-network → recommendation-platform → chat-conversation
- 对应验收：`UAT-011`

<a id="jny-012"></a>
### JNY-012 我的主页私有互动历史

- 用户目标：当前用户在自己的主页按互动类型和方向查看可靠、可恢复且不向他人公开的互动历史。
- 起点：用户从应用或外部入口发起旅程。
- 成功终态：用户目标形成可观察且可恢复的业务结果。
- 失败恢复：失败进入可解释终态，并提供符合 canonical error/recovery 契约的恢复动作。
- 参与领域：
  - [user-identity-profile-relationship](./user-identity-profile-relationship/spec.md)
  - [discovery-content](./discovery-content/spec.md)

<a id="scn-010"></a>
#### SCN-010 我的主页转发互动双向历史

- 场景目标：当前用户在自己的主页按互动类型和方向查看可靠、可恢复且不向他人公开的互动历史。
- 领域交接：user-identity-profile-relationship → discovery-content
- 对应验收：`UAT-004`

<a id="jny-013"></a>
### JNY-013 Gathering 上的活的共同旅行体验

- 用户目标：组织者在一个多人多日 Gathering 上启用 Plan、Map、Calendar 与 Experience，把群聊、内容收藏、公开链接、预算和偏好整理为可共同维护的吃玩住行计划；参与者在行中获得下一步、变化提醒和讲解，行后把共同经历整理为可编辑内容。
- 起点：用户从活动群聊、看板、Circle、内容或小趣打开一个旅行 Gathering。
- 成功终态：Gathering 保持唯一参与、准入、生命周期、会话与 Outcome 真相；可选 Plan 具有当前 Revision，时间线与地图可查看计划、变化与 Experience，结束后可生成并确认发布回顾草稿。
- 失败恢复：目标 Gathering 或 Plan 不明确时要求消歧；权限、外部证据、Connector 或领域写入失败时保留当前 Revision 和可恢复 Run，不创建独立 Trip 成功事实。
- 参与领域：
  - [travel-journey](./travel-journey/spec.md)
  - [assistant-run-learning](./assistant-run-learning/spec.md)
  - [chat-conversation](./chat-conversation/spec.md)
  - [circle-community](./circle-community/spec.md)
  - [discovery-content](./discovery-content/spec.md)
  - [shared-homepage-network](./shared-homepage-network/spec.md)
  - [user-identity-profile-relationship](./user-identity-profile-relationship/spec.md)
  - [runtime](./runtime/spec.md)

<a id="scn-030"></a>
#### SCN-030 从活动群聊与真实内容共同创建吃玩住行计划

- 场景目标：组织者让小趣从活动群消息、收藏内容、公开 URL、时间、预算和偏好提取约束，为既有 Gathering 形成可确认的 Plan Revision 和吃玩住行计划项，而不是一次性聊天文本或独立 Trip 根。
- 领域交接：assistant-run-learning → circle-community → travel-journey → chat-conversation → discovery-content → shared-homepage-network → runtime
- 对应验收：`UAT-012`

<a id="scn-031"></a>
#### SCN-031 行中变更、主动提醒与贴身讲解

- 场景目标：组织者确认计划调整后形成不可变 Plan Revision 和明确 diff，相关 GatheringParticipation 收到不重复的变化提醒；参与者按时间地点获得下一步、天气交通风险、集合、餐饮住宿提示和有来源的导游讲解。
- 领域交接：circle-community → travel-journey → assistant-run-learning → chat-conversation → runtime
- 对应验收：`UAT-012`

<a id="scn-032"></a>
#### SCN-032 Experience、内容与计划点组成时间线和地图

- 场景目标：参与者上传照片、视频、语音或文字后，系统建议所属 Plan 项，用户确认即进入共同时间线和地图；既有 Post 可与 Gathering/计划点建立引用关系并供有权参与者查看传播。
- 领域交接：circle-community → travel-journey → discovery-content → shared-homepage-network → assistant-run-learning
- 对应验收：`UAT-012`

<a id="scn-033"></a>
#### SCN-033 行后回顾、分段分享与用户选择的关系延续

- 场景目标：Gathering 完成后，小趣按实际时间线、地图、精选 Experience 和计划差异生成可编辑回顾草稿；用户可分享整段、某日、单点、路线或随拍集合，并自行选择是否继续 Follow、Conversation、Circle 或下一场 Gathering，不因共同参与自动 mutual。
- 领域交接：circle-community → travel-journey → assistant-run-learning → discovery-content → user-identity-profile-relationship → chat-conversation
- 对应验收：`UAT-012`

## 5. 全局验收

<a id="uat-001"></a>
### UAT-001 发现、搜索与对象连接基础旅程

- GIVEN 用户拥有可见的发现内容、可检索对象和至少一个可解释交集。
- WHEN 用户从发现流打开详情、执行互动或搜索，并从对象页发起连接动作。
- THEN 内容、作者/对象主页和搜索结果均来自 canonical projection，导航保持目标身份与 viewer 上下文。
- AND 首页首屏、翻页与视频准备在声明时限内进入内容或可恢复终态；弱网、并发峰值和持续滚动不出现无限加载、旧请求回写、资源无界增长或不可解释空白。
- AND 评论、空结果、超时、权限拒绝和失效对象都有明确且可恢复的终态。
- AND 交集行动遵守关系、隐私与权限门禁，不把概率推荐伪装成事实关系。

<a id="uat-002"></a>
### UAT-002 文字、照片与视频创作、发布和结果回流

- GIVEN 执行“文字、照片与视频创作、发布和结果回流”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“文字、照片与视频创作、发布和结果回流”对应动作。
- THEN 游客关闭登录回安全首页不循环，登录成功继续进入写文字。
- THEN micro/article 两种形态由用户显式确认并分别回流详情或作品浏览器。
- THEN 断网、杀进程、限流和依赖恢复后同一 intent 最多创建一个 Post。
- THEN 长度/频控或安全 reject 不创建 Post；review/unavailable 只创建不可公开 pending_review Post 并进入人工 Case，未获批准的公开 Post 数恒为零。
- THEN 发布后内容立即在作者可见读模型出现，公开性和圈子分发符合真实设置。
- THEN 照片保持用户排序，原图按流上传，发布命令只携带 MediaAsset ID。
- THEN 视频原片按流上传；worker 生成 H.264/AAC fast-start MP4、封面和预览轨道后才允许公开发布。
- THEN 已发布、待审核和待重试均进入明确结果面；用户可查看作品或发布任务，不以 Toast 代替终态。

<a id="uat-003"></a>
### UAT-003 应用安全进入与不可恢复异常恢复

- GIVEN Android 或 iPhone 正常启动、发生明确启动致命异常，或在安全 Shell 后发生根级不可恢复异常。
- WHEN 应用执行启动交接、版本确认、一次性运行时重建、更新、官网 APK 下载或网页版恢复。
- THEN 正常或可降级故障进入安全 Shell，单纯等待超时不进入恢复页；启动致命异常进入无重试的版本检查页，运行时重建最多一次且失败后不循环。
- THEN 版本服务确认有新版且存在可安装通道时，Android 从趣我圈官方 HTTPS 通道下载已签名 APK。
- THEN 公众 iOS 使用官方 PWA，已登记测试设备才可使用受控 Ad Hoc 通道。
- THEN 确认已最新、地址不可用或检查未完成时仍可进入官方网页版。
- THEN 页面不存在技术原因、诊断编号或日志状态；脱敏异常先保存后异步上报，上报失败不影响任何恢复动作。
- THEN Android/iOS 安装包、原生身份、runtime probe 与发布 provenance 绑定同一 effective launch manifest；package-only 编译不得替代真实 launcher/scene、safe terminal、motion、非 `unknown` attempt 与 telemetry readback 证据。

<a id="uat-004"></a>
### UAT-004 我的主页转发互动双向历史

- GIVEN 执行“我的主页转发互动双向历史”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“我的主页转发互动双向历史”对应动作。
- THEN 互动保持两层导航且选中转发后可切换收到的/我发起的。
- THEN received 与 initiated 文案、预览、空态、分页、刷新、滚动恢复和点击优先级符合规格。
- THEN received 未读与真实 impact 正确，initiated 不显示未读或 impact。
- THEN 他人主页不请求转发列表，Persona切换不残留旧数据，服务端拒绝越权。
- THEN 八个 share interaction 观测事件携带完整公共归因参数。

<a id="uat-005"></a>
### UAT-005 iOS/Android 边缘滑动返回与退出保护

- GIVEN 执行“iOS/Android 边缘滑动返回与退出保护”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“iOS/Android 边缘滑动返回与退出保护”对应动作。
- THEN 无底栏普通页面通过 iOS leading edge 或 Android 左/右边缘返回上一页。
- THEN 沉浸式媒体浏览器边缘滑动触发返回，不误触媒体左右切换。
- THEN Android 主页根页第一次边缘滑动只提示再次滑动退出。
- THEN Android 主页根页第二次边缘滑动在 2 秒保护窗口内退出或交给系统返回。
- THEN iOS 根页无可 pop 栈时不模拟退出应用。
- THEN iOS 与 Android 的系统手势区域、阈值、动画和提示分别验证。

<a id="uat-006"></a>
### UAT-006 对外引流与深链回流端到端价值闭环

- GIVEN 执行“对外引流与深链回流端到端价值闭环”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“对外引流与深链回流端到端价值闭环”对应动作。
- THEN 5 类对象都能从统一分享面板分享到微信会话/朋友圈，并生成站外可点击的 HTTPS 落地链接。
- THEN 已安装用户在微信内（Android/鸿蒙用 wx-open-launch-app、iOS 用 Universal Link）、在浏览器内（Universal Link/App Links/scheme）点击后回流到 App 对应详情页。
- THEN 未安装用户进入趣我圈官网；Android 可下载正式签名 APK，iOS 可安装 PWA，原生安装后的首启通过延迟深链还原原始目标对象。
- THEN 公开 Web 内容/主页可被搜索引擎索引（canonical/OG/JSON-LD/robots/sitemap），并提供安装转化入口。
- THEN 一键海报（含二维码与口令）可投放到不支持外链的 UGC 平台，扫码或口令识别后回流到目标对象。
- THEN 全链路携带 referralSource/share_id/UTM/口令归因，可在指标大盘按渠道与对象类型统计转化。

<a id="uat-007"></a>
### UAT-007 消息社交连接端到端价值闭环

- GIVEN 执行“消息社交连接端到端价值闭环”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“消息社交连接端到端价值闭环”对应动作。
- THEN 互关用户从 TA 的主页点击消息，可创建或复用 direct conversation 并完成发送/接收。
- THEN 非互关用户只能先打招呼；对方回复后升级为正式 direct conversation，未回复前不得进入普通会话列表。
- THEN 用户可从全局发起群聊入口选择服务端返回的候选来源与成员，建群后进入 group conversation。
- THEN 用户可从兴趣圈子进入默认公共群或自建群；从学校组织主页进入院系/班级节点所绑定的班级群会话。
- THEN 用户可从共享主页的相关群组卡片进入真实 Circle/CircleGroup 绑定的群会话，主页本身不拥有 conversation。
- THEN 用户可在 1v1 或群会话中邀请小趣并 @小趣，收到 assistant_reply，且消息进入同一同步和审计链路。
- THEN 合法关系或会话中的用户可发起、接听、拒绝、取消和结束音视频通话；在线事件与离线 ring/cancel 可靠送达，结束后回到原会话并产生 system_call_log。
- THEN Provider 不可用、权限拒绝、弱网重连和超时均有结构化终态；Alpha/Beta/Gamma required 验收使用受管非生产租户的非内存 Provider 并绑定 conformance receipt，Prod 独立验证正式 APNs/FCM/LiveKit。

<a id="uat-008"></a>
### UAT-008 无处不在的小趣私人助理商用主线

- GIVEN 执行“无处不在的小趣私人助理商用主线”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“无处不在的小趣私人助理商用主线”对应动作。
- THEN 用户从首页、内容页、群聊、搜索页、个人页进入小趣时，入口语义和会话状态一致，不维护第二套助手体验。
- THEN 用户在内容页提问时，小趣基于当前对象、内容片段、标签和站内外检索给出有引用边界的回答。
- THEN 用户在群聊中 @小趣 时，消息以结构化 mentions 触发 AssistantMentioned，assistant-service 基于最近消息窗口与成员信息回群回复。
- THEN 用户可订阅主题并投递到用户或会话；投递前执行 consent、频控、静默、去重与审计。
- THEN 小趣回答后的赞/踩、采纳、撤销和引用打开能回流到 InteractionEvent，并携带 referralSource、triggerMessageId、assistantTurnId。
- THEN Skill Center 展示 active package 对应的价值、示例、设置、数据/记忆/写操作说明、Connector 状态、主动订阅、共享 Placement 与最近 Run，且启用、授权、主动投递和共享挂载互不冒充。
- THEN 群聊或圈子中的小趣可使用全部共享安全且未被管理员禁用的官方 Skill；任何个人记忆、个人 Connector 和个人动作回执均不进入共享回答。

<a id="uat-009"></a>
### UAT-009 当前全部跨对象 Journey 商用准出

- GIVEN 执行“当前全部跨对象 Journey 商用准出”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“当前全部跨对象 Journey 商用准出”对应动作。
- THEN 当前全部 Journey 的 page/surface/operation/object/store/event/behavior/metric 节点可正向追踪，且无反向孤儿。
- THEN command 经过 aggregate owner，query 读取 named Slice；App 只访问 generated Gateway operation。
- THEN 每条 Journey 至少跨两个真实业务对象，并验证权限、错误恢复、幂等、副作用、投影收敛和推荐/运营回流。
- THEN 所有页面通过 light/dark、多屏、无障碍、语义 token、性能、弱网和 capability 降级检查。
- THEN alpha/beta/gamma/prod 均使用同一个 production Remote composition，内容、Creator、实体与发布媒体只来自对应环境已激活的 canonical immutable release。
- AND 环境名与 `productLifecycleState` 解耦；research release 只对受白名单保护的内部 App 开放，commercial release 不得复用 research receipt，App readback 必须回传同一 release 的 `releaseClass/productLifecycleState/releaseId/manifestDigest`。
- AND 用户、评论、圈子、会话与消息只经所属领域公开 command/event 生效，Alpha/Beta/Gamma 验收数据绑定候选并可受控清理，Prod 不创建测试业务对象。
- AND Alpha/Beta/Gamma required 验收绑定受管非生产租户的非内存 Provider，Prod 完成正式 Provider、实时 SLO、灰度和回滚验证；任何环境 App 均不含 seed/Mock/Memory/Noop 或运行时数据源切换。
- THEN local_contract、api_integration、user_acceptance 均有真实断言和 CaseResult；禁止路径存在、动态 skip 或 Memory 假集成充当证据。

<a id="uat-010"></a>
### UAT-010 消息可靠可达与离线可读

- GIVEN 两个真实账号在同一会话中，且接收方设备已登记有效推送端点。
- WHEN 参与者在冷启动、断网、杀进程、弱网与离线场景下收发消息并翻阅历史。
- THEN 冷启动或飞行模式打开会话可从本地读到最近历史，来源可区分为离线只读，不以空列表冒充没有消息。
- THEN 向上连续翻阅历史按游标续接，合并结果按 seq 严格有序且无重复，到达最早一条后给出终止态。
- THEN 单侧断网期间对端连续发送的消息在恢复连接后被完整补齐，最终序列无缺号、无重复且顺序按 seq。
- THEN 杀进程后待发队列跨重启恢复，同一 clientMsgId 最多落一条。
- THEN 离线设备收到由真实 provider 投递的推送，打开后直达该会话且该会话未读收敛；provider 未回执时投递记录保持未确认态。
- THEN 群会话中单个接收方分发失败不影响其余接收方，网关按连接数与订阅积压扩缩并有对应告警。
- AND 长会话滚动 jank 比与发送到气泡确认延迟在声明预算内，超出预算时门禁阻断合入。

<a id="uat-011"></a>
### UAT-011 内容驱动 Gathering 与活动群聊闭环

- GIVEN 真实 Host 和参与者账号具有可见内容或 Circle 上下文，且所属 canonical contracts、风险义务、受治理 feature flag 与真实 Remote composition 均有效。
- WHEN Host 从内容或 C 位发起 Gathering，参与者从首页或主页公开卡进入详情，经开放加入、申请审批或邀请接受进入活动群聊与看板，并在活动后确认回顾内容。
- THEN C 位首层的发内容、发起活动、发起群聊并列且互不冒充；游客先看到动作面板，选择具体动作才登录，关闭回安全来源不循环，成功后续接原动作。
- THEN 公开详情只披露有权信息并保持一个状态驱动主动作；Recommendation 只排序 Circle 的合格公开投影，不写 Participation、容量、准入或 Outcome。
- THEN Circle 的 Gathering、root-owned GatheringParticipation、Revision、Outcome 与 room binding state 是唯一活动真相。
- THEN Chat 的 Conversation、ConversationMembership、Message 与 Announcement 是唯一会话真相；Board 只组合 owner 投影。
- THEN 并发响应不超员，待审批与邀请待响应不获得 room access；有效参与后默认进入活动群聊，退出、移除、Block 或撤权后访问按 canonical policy 收敛。
- THEN 开场前取消、开场后提前结束、安全终止、完成与 disputed/unverified 结果可区分，时间到达或单方声明不自动形成 occurred。
- THEN 回顾只在用户确认后成为 Content owner 的 Post/Media，并关联原 Gathering、Host 与来源内容；Participation、ConversationMembership、CircleMembership 与 Follow 独立，加入、到场、完成均不自动产生 mutual。
- AND 1:1、多人兴趣活动与多人多日旅行复用同一 Gathering/Participation/Room/Board/Plan/Outcome 合同；旅行与新生同校兴趣活动解析到同一 operation/route/surface/tool ID 集合，只通过 canonical Topic/tag、来源、政策与 ExperiencePackage 配置形成体验差异，观测按 `topicRef` 聚合。
- AND 校园 Post、Entity 与 tag 只在 `quwoquan_data` canonical immutable release 经环境 importer 激活并取得 readback 后进入 Remote UAT；缺 release/import receipt 时验收保持 OPEN，不以 fixture 或 production fallback 伪造成功。

<a id="uat-012"></a>
### UAT-012 Gathering 上的活的共同旅行体验

- GIVEN 2–8 名真实非生产账号已成为同一多人多日 Gathering 的有效参与者，且拥有可见内容、地点和公开网页证据。
- WHEN 组织者为该 Gathering 启用 Plan、Map、Calendar 与 Experience，成员共同补充吃玩住行约束，行中确认一次计划变更并追加 Experience，行后生成和确认分享。
- THEN Gathering 始终拥有 Host、Participation、准入、会话、生命周期与 Outcome；旅行能力不创建长期公共独立 Trip 根，也不复制成员或会话。
- THEN 每次计划修改形成不可变 Revision、可读 diff、影响参与者和单次去重提醒；旧 Revision 可回看但不是当前写真相源。
- THEN Experience 经用户确认归入计划项，时间线与地图从同一事实投影，Post 与 MediaAsset 只通过 canonical 引用关联且不被复制。
- THEN 行程结束生成可编辑 LocalPostDraft；发布与分段分享均经所属领域公开 command，公开结果不包含私人住宿、联系人、参与者名单或实时精确位置。
- AND Android/iPhone 真机完成日历确认、地图跳转、Adaptive Presentation、离线降级、后台恢复与变化通知，所有结果绑定同一候选、Skill package digest、Gathering 与 Plan revision。

## 6. 开放事项

<a id="open-001"></a>
### OPEN-001 文字、照片与视频创作、发布和结果回流

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：当前只有媒体发布 Remote UAT 直接引用 `UAT-002`，尚未在同一候选版本证明登录取消/续接、micro/article 分流、照片顺序、视频转码、重复 intent、拒绝不落 Post、pending_review 不公开及作者读模型回读的完整组合。
- 完成判定：测试树内对象级 typed double/Provider/Widget 与 Alpha、Beta、Gamma、Prod 的真实 Remote HTTP、对象存储、Mongo、worker 和 App user_acceptance 使用同一 intent 集合逐项通过；文字、照片、视频三条 CaseResult 均直接引用 `UAT-002`，并证明失败恢复后最多一个 Post。
- 依赖：[`publish-comment-reaction`](./discovery-content/publish-comment-reaction/spec.md)、[`media-processing-helper-read`](./discovery-content/media-processing-helper-read/spec.md) 与 [`onboarding-and-identity-entry`](./user-identity-profile-relationship/onboarding-and-identity-entry/spec.md) 的最低节点 OPEN。

<a id="open-002"></a>
### OPEN-002 应用安全进入与不可恢复异常真环境验收

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：当前已有 Android 原生 Gate instrumentation、iOS pre-engine recovery scene 模拟器证据和 immutable effective launch manifest 门禁，但尚缺 Alpha/Beta/Gamma Remote canonical release 的双端安装启动、Android 真机 20-run、iPhone 真机 20-run、四环境正式 Web DNS/TLS、Android/IPA 生产签名发布，以及 Prod 故障注入、telemetry/恢复 API 与媒体读回的共同闭合。
- 完成判定：以下三层 release-bound 证据同时通过。
  - 仓内 local_contract 继续证明启动/运行时状态机、一次性根容器重建、静默异常队列和恢复页语义。
  - Alpha/Beta/Gamma 的双模拟器与 Android 真机读取同一 release-bound 首页、实体主页、文章、图片、视频和头像。
  - Prod Android/iPhone 以同一签名候选完成启动、故障恢复与媒体读回；每个 runtime CaseResult 绑定内嵌 effective launch manifest 摘要、非 `unknown` attempt、motion/safe terminal 与 telemetry readback，并直接引用 `UAT-003`。
- 依赖：[`cold-start-performance`](./runtime/runtime-client-foundation/cold-start-performance/spec.md)、[`unrecoverable-runtime-recovery`](./runtime/runtime-client-foundation/unrecoverable-runtime-recovery/spec.md) 与 [`app-release-recovery-routing`](./product-ops-growth/product-control-plane-foundation/app-release-recovery-routing/spec.md) 的正式回执。

<a id="open-003"></a>
### OPEN-003 我的主页转发互动双向历史

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：尚缺 AppRoot 直接 user_acceptance；需要以双账号真实数据证明 received/initiated 分页、未读与 impact、刷新/滚动恢复、Persona切换隔离、他人主页零请求、越权拒绝及八个归因事件。
- 完成判定：App local_contract 覆盖 Mock/Provider/Widget 和页面六态，Beta、Gamma 以双账号真实 HTTP/存储执行 received 与 initiated 全路径；服务拒绝他人读取且观测 readback 字段完整，CaseResult 直接引用 `UAT-004`。
- 依赖：[`owner-persona-homepage-unification`](./user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md) 与 Content `ProfileInteractionActivityView` 对象证据。

<a id="open-004"></a>
### OPEN-004 iOS/Android 边缘滑动返回与退出保护

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：尚缺 iOS/Android 真机对普通页面 interactive pop、沉浸媒体手势冲突、Android 根页首次提示/两秒内二次退出以及 iOS 根页不模拟退出的统一 UAT 回执；现有证据只覆盖原生 Page 工厂和返回策略 local_contract。
- 完成判定：本地策略、路由工厂和 Widget 测试分别直接引用三个 L3 GWT；Beta、Gamma 的 iPhone/Android 真机执行普通页、沉浸页、根页矩阵并记录帧流畅度与结果，AppRoot CaseResult 直接引用 `UAT-005`。
- 依赖：[`native-edge-gesture-navigation`](./runtime/native-edge-gesture-navigation/spec.md) 的三个 Story 与真实设备执行资源。

<a id="open-005"></a>
### OPEN-005 对外引流与深链回流端到端价值闭环

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：尚未用正式域名和渠道证明五类对象卡片、微信会话/朋友圈、系统分享、海报二维码/口令、Universal Link/App Links、延迟深链、Web SEO 与 share_id/UTM 归因从站外回到 canonical 对象页的闭环。
- 完成判定：local_contract 校验对象映射、隐私和归因契约。Beta/Gamma 验证受控 HTTPS 落地与 App 回流。Prod 使用正式域名、微信开放平台、Android 官网生产签名 APK 与公众 iOS PWA 完成已安装/未安装矩阵，Product Ops readback 与 AppRoot `UAT-006` CaseResult 绑定同一 share_id。
- 依赖：[`outbound-share-distribution`](./product-ops-growth/outbound-share-distribution/spec.md) 与正式域名、微信开放平台、商店及 CDN 外部资源。

<a id="open-006"></a>
### OPEN-006 消息社交连接端到端价值闭环

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：尚缺同一候选版本的双账号 Remote Journey，覆盖互关私信、非互关 GreetingRequest 回复升级、三来源建群、圈子/组织/主页群绑定、@小趣、消息离线投递以及 RTC 接听/拒绝/取消/弱网/后台唤醒。
- 完成判定：Chat/Circle/User/Assistant/Realtime/Notification/RTC 的对象 local_contract 与真实 API integration 全部通过。Beta、Gamma 双账号真机完成消息及通话矩阵，Gamma 使用 Port 对等替身、Prod 使用正式 APNs/FCM/LiveKit，CaseResult 直接引用 `UAT-007`。
- 依赖：[`chat-conversation`](./chat-conversation/spec.md)、[`circle-community`](./circle-community/spec.md) 及离线来电 Provider 正式回执。

<a id="open-007"></a>
### OPEN-007 无处不在的小趣私人助理商用主线

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：尚缺 AppRoot Remote UAT；需要证明五入口跨入口会话续接、内容/搜索 grounding、群聊结构化 mention、stream/cancel/resume、consent、工具失败、引用打开、订阅投递及赞踩/采纳/撤销学习回流。
- 完成判定：AssistantSession/Run/Turn、InteractionEvent、LearningFact、PolicyRelease/Rollout 各自 local/API 合同全部通过。Alpha、Beta、Gamma 在五入口执行同一会话与失败矩阵，Behavior/Recommendation/Product Ops 可回读反馈，CaseResult 直接引用 `UAT-008`。正式模型 Provider receipt 由 Prod 单独关闭。
- 依赖：[`assistant-run-learning`](./assistant-run-learning/spec.md)、[`recommendation-platform`](./recommendation-platform/spec.md) 与 ContractGraph 编译所得的 required Provider conformance capability set。

<a id="open-008"></a>
### OPEN-008 消息可靠可达与离线可读

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前消息时间线不落盘、历史分页无调用方、会话事件只做即时广播且不进推送通道，冷启动、离线、断连与杀进程四类场景下消息均不可读或不可达。消息域的差异化体验建立在这条链路之上，链路不成立时任何上层能力都不可商用。
- 完成判定：双账号真机在冷启动、断网、杀进程、弱网与离线推送矩阵下执行同一批断言，CaseResult 直接引用 `UAT-010`
- 依赖：[`chat-conversation`](./chat-conversation/spec.md) 的 `message-reliability-foundation`，以及与 `media-infrastructure` 共用的受控推送凭据。

<a id="open-009"></a>
### OPEN-009 内容驱动 Gathering、活动群聊与跨主题复用闭环

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：当前已有 Gathering/Chat 目标 contracts 与旅行/校园 metadata 复用证明，但尚缺内容与 C 位发起、公开详情、Host 准入、活动群聊与看板、计划协作、证据化 Outcome、内容回流和不自动 mutual 的同一候选 Remote 闭环；校园 canonical release/import 及真实账号 UAT 尚未执行。
- 完成判定：三层测试以创作者活动、Circle 活动、1:1、多人多日旅行和新生同校兴趣活动复用同一合同，CaseResult 直接引用 `UAT-011`；校园供给绑定 immutable release/import receipt/Remote readback，并证明并发不超员、room/board 撤权、开场后取消失败、安全终止、Outcome 证据、内容确认发布及登录 continuation 无循环。
- 依赖：[`circle-community`](./circle-community/spec.md) 的 [`gathering-coordination`](./circle-community/gathering-coordination/spec.md)、[`chat-conversation`](./chat-conversation/spec.md)、[`creation-mode-and-surface-ia-unification`](./discovery-content/content-type-framework/creation-mode-and-surface-ia-unification/spec.md) 与所属 contracts/metadata 后续准入。

<a id="open-010"></a>
### OPEN-010 Gathering 共同旅行体验与双端 UAT

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺实现：Gathering + optional Plan/Map/Calendar/Experience 在 activity room/Board 的 production Remote 体验与真实 Provider/Connector；尚缺验收证据：跨域 API integration、离线/隐私恢复及 Android/iPhone UAT。travel-service 生产主链已经静态退役，历史数据迁移由 `OPEN-011` 独立阻断。
- 完成判定：Circle/Assistant/Chat/Content/Integration 的 local_contract 与真实跨域 api_integration 通过，Alpha/Beta/Gamma 同一候选完成 `travel_companion`、Board Plan Revision 提醒、Experience 归档、地图/日历、回顾草稿和分享 readback，Android/iPhone CaseResult 直接引用 `UAT-012`；Prod 另行完成正式 Provider、灰度和回滚。
- 依赖：[`travel-journey`](./travel-journey/spec.md)、[`assistant-run-learning`](./assistant-run-learning/spec.md)、[`runtime`](./runtime/spec.md)、[`chat-conversation`](./chat-conversation/spec.md)、[`circle-community`](./circle-community/spec.md) 与 [`discovery-content`](./discovery-content/spec.md)。

<a id="open-011"></a>
### OPEN-011 travel-service 四环境历史数据 target-only 迁移准出

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：尚缺验收证据：alpha、beta、gamma、prod 真实历史 Trip 对象的 source inventory、canonical owner import/readback、parity、cutover 与 target-only rollback receipt。服务源码、契约、生成客户端、路由和运行拓扑已归零，现有仓内证据只验证合成快照上的迁移控制面合同。
- 完成判定：四环境分别完成真实 source inventory、owner-command import、target readback、100% parity 与永久 target-only cutover；Prod 另有目标备份和不恢复源服务的 rollback 演练。全部历史对象计数守恒、orphan/collision 为零、原始 PII 零输出，receipt 绑定同一 crosswalk、ContractGraph、mapping、候选、审批和配置激活摘要。
- 依赖：[`travel-journey OPEN-001`](./travel-journey/spec.md#open-001)、Circle/Chat/Content target owner、四环境受保护 inventory 与审批证据。
