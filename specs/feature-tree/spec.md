# AppRoot Spec：应用根规格

## 1. 产品目标与用户价值

趣我圈是一套以“遇见同趣，绽放热爱”为品牌表达、以“别人帮你刷内容，我们帮你遇到对的人”为产品主轴的端云一体社交应用。它通过内容、对象主页、交集、关系、圈子、会话、搜索和小趣助手，把内容消费转化为可证、安全、可沉淀的同趣连接；AppRoot 统一用户旅程、跨领域场景、全局术语、边界和 UAT。

## 2. 范围与非目标

### In Scope

- 覆盖用户从进入、发现、创作、互动、关系、消息、助手到持续运营的完整应用体验。

### Out of Scope

- 不在特性树复制 metadata schema、实现任务、测试排列组合或执行历史。

## 3. 术语与全局要求

<a id="req-001"></a>
### REQ-001 发现、搜索与对象连接基础旅程

- 用户可从发现流进入内容详情，完成评论互动并跳转到真实作者或对象主页。
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
- 他人主页不请求转发列表，子账号切换不残留旧数据，服务端拒绝越权。
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
- Provider 不可用、权限拒绝、弱网重连和超时均有结构化终态；Gamma 以 Port 对等本地替身验证完整第一方链路且不使用 UI Mock，Prod 独立验证真实 APNs/FCM/LiveKit。

<a id="req-008"></a>
### REQ-008 无处不在的小趣私人助理商用主线

- 用户从首页、内容页、群聊、搜索页、个人页进入小趣时，入口语义和会话状态一致，不维护第二套助手体验。
- 用户在内容页提问时，小趣基于当前对象、内容片段、标签和站内外检索给出有引用边界的回答。
- 用户在群聊中 @小趣 时，消息以结构化 mentions 触发 AssistantMentioned，assistant-service 基于最近消息窗口与成员信息回群回复。
- 用户可订阅主题并投递到用户或会话；投递前执行 consent、频控、静默、去重与审计。
- 小趣回答后的赞/踩、采纳、撤销和引用打开能回流到 InteractionEvent，并携带 referralSource、triggerMessageId、assistantTurnId。

<a id="req-009"></a>
### REQ-009 当前全部跨对象 Journey 商用准出

- 当前全部 Journey 的 page/surface/operation/object/store/event/behavior/metric 节点可正向追踪，且无反向孤儿。
- command 经过 aggregate owner，query 读取 named Slice；App 只访问 generated Gateway operation。
- 每条 Journey 至少跨两个真实业务对象，并验证权限、错误恢复、幂等、副作用、投影收敛和推荐/运营回流。
- 所有页面通过 light/dark、多屏、无障碍、语义 token、性能、弱网和 capability 降级检查。
- alpha/beta/gamma/prod 均使用同一个 production Remote composition，第一方 App 可见业务数据只来自对应环境已激活的 canonical immutable release。
- 非 Prod 外部 Provider 可绑定 Port 对等 sandbox/local substitute，Prod 完成真实 Provider、实时 SLO、灰度和回滚验证；任何环境 App 均不含 seed/Mock/Memory/Noop 或运行时数据源切换。
- local_contract、api_integration、user_acceptance 均有真实断言和 CaseResult；禁止路径存在、动态 skip 或 Memory 假集成充当证据。

<a id="req-010"></a>
### REQ-010 以业务对象为中心的端云 Object Facade、统一公共 URL、存储无关 Data Ports、页面 Query Slice、错误恢复和三层测试合同

- 以业务对象为中心的端云 Object Facade、统一公共 URL、存储无关 Data Ports、页面 Query Slice、错误恢复和三层测试合同。
- command 必须经过唯一 write owner 的聚合根；query 直接读取强类型 Slice，不为形式统一加载聚合。
- App 只访问统一 Gateway base URL 和 generated operation，不感知服务进程、存储或内部 URL。
- 统一存储是对象专属 AggregateStore/Reader 的生成模式，不是万能 CRUD Repository。
- 页面必须满足主题、语义 token、多屏、多端、状态恢复、无障碍、性能和观测合同。
- alpha/beta/gamma/prod 的 App 可见业务对象均绑定 release/import receipt，测试 double 只存在于 local_contract 测试树；四环境 artifact 均禁止 fixture/Mock/Memory/Noop。

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

- 场景目标：用户能从主页、联系人、搜索、圈子、组织节点、相关群组和会话内小趣入口，清晰进入 1v1、请求箱、群聊与助手参与的消息路径。
- 领域交接：chat-conversation → assistant-run-learning
- 对应验收：`UAT-007`

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
### JNY-011 交集行动深化到结伴同行

- 用户目标：用户从内容、实体与位置发现"同趣"的人和场，沿"围观→轻触→对话→同趣→同行→线下→实时"行动阶梯逐级深化，完成结伴同行、线下相聚与实时连接，并安全沉淀为可管理的关系（趣友/密友/联系人标签）。
- 起点：用户从应用或外部入口发起旅程。
- 成功终态：用户目标形成可观察且可恢复的业务结果。
- 失败恢复：失败进入可解释终态，并提供符合 canonical error/recovery 契约的恢复动作。
- 参与领域：
  - [object-homepage-network](./object-homepage-network/spec.md)
  - [circle-community](./circle-community/spec.md)
  - [user-identity-profile-relationship](./user-identity-profile-relationship/spec.md)
  - [recommendation-platform](./recommendation-platform/spec.md)
  - [chat-conversation](./chat-conversation/spec.md)

<a id="scn-026"></a>
#### SCN-026 对象页交集行动深化（同趣围观到破冰升级）

- 场景目标：用户从内容、实体与位置发现"同趣"的人和场，沿"围观→轻触→对话→同趣→同行→线下→实时"行动阶梯逐级深化，完成结伴同行、线下相聚与实时连接，并安全沉淀为可管理的关系（趣友/密友/联系人标签）。
- 领域交接：object-homepage-network → recommendation-platform → chat-conversation
- 对应验收：`UAT-001`

<a id="scn-027"></a>
#### SCN-027 附近同趣·结伴同行·线下局

- 场景目标：用户从内容、实体与位置发现"同趣"的人和场，沿"围观→轻触→对话→同趣→同行→线下→实时"行动阶梯逐级深化，完成结伴同行、线下相聚与实时连接，并安全沉淀为可管理的关系（趣友/密友/联系人标签）。
- 领域交接：circle-community → recommendation-platform → user-identity-profile-relationship → chat-conversation
- 对应验收：`UAT-001`

<a id="scn-028"></a>
#### SCN-028 派生称谓与联系人标签驱动连接

- 场景目标：用户从内容、实体与位置发现"同趣"的人和场，沿"围观→轻触→对话→同趣→同行→线下→实时"行动阶梯逐级深化，完成结伴同行、线下相聚与实时连接，并安全沉淀为可管理的关系（趣友/密友/联系人标签）。
- 领域交接：user-identity-profile-relationship → chat-conversation → recommendation-platform
- 对应验收：`UAT-001`

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

## 5. 全局验收

<a id="uat-001"></a>
### UAT-001 发现、搜索与对象连接基础旅程

- GIVEN 用户拥有可见的发现内容、可检索对象和至少一个可解释交集。
- WHEN 用户从发现流打开详情、执行互动或搜索，并从对象页发起连接动作。
- THEN 内容、作者/对象主页和搜索结果均来自 canonical projection，导航保持目标身份与 viewer 上下文。
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
- THEN 他人主页不请求转发列表，子账号切换不残留旧数据，服务端拒绝越权。
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
- THEN Provider 不可用、权限拒绝、弱网重连和超时均有结构化终态；Gamma 以 Port 对等本地替身验证完整第一方链路且不使用 UI Mock，Prod 独立验证真实 APNs/FCM/LiveKit。

<a id="uat-008"></a>
### UAT-008 无处不在的小趣私人助理商用主线

- GIVEN 执行“无处不在的小趣私人助理商用主线”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“无处不在的小趣私人助理商用主线”对应动作。
- THEN 用户从首页、内容页、群聊、搜索页、个人页进入小趣时，入口语义和会话状态一致，不维护第二套助手体验。
- THEN 用户在内容页提问时，小趣基于当前对象、内容片段、标签和站内外检索给出有引用边界的回答。
- THEN 用户在群聊中 @小趣 时，消息以结构化 mentions 触发 AssistantMentioned，assistant-service 基于最近消息窗口与成员信息回群回复。
- THEN 用户可订阅主题并投递到用户或会话；投递前执行 consent、频控、静默、去重与审计。
- THEN 小趣回答后的赞/踩、采纳、撤销和引用打开能回流到 InteractionEvent，并携带 referralSource、triggerMessageId、assistantTurnId。

<a id="uat-009"></a>
### UAT-009 当前全部跨对象 Journey 商用准出

- GIVEN 执行“当前全部跨对象 Journey 商用准出”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“当前全部跨对象 Journey 商用准出”对应动作。
- THEN 当前全部 Journey 的 page/surface/operation/object/store/event/behavior/metric 节点可正向追踪，且无反向孤儿。
- THEN command 经过 aggregate owner，query 读取 named Slice；App 只访问 generated Gateway operation。
- THEN 每条 Journey 至少跨两个真实业务对象，并验证权限、错误恢复、幂等、副作用、投影收敛和推荐/运营回流。
- THEN 所有页面通过 light/dark、多屏、无障碍、语义 token、性能、弱网和 capability 降级检查。
- THEN alpha/beta/gamma/prod 均使用同一个 production Remote composition，第一方 App 可见业务数据只来自对应环境已激活的 canonical immutable release。
- AND 非 Prod 外部 Provider 可绑定 Port 对等 sandbox/local substitute，Prod 完成真实 Provider、实时 SLO、灰度和回滚验证；任何环境 App 均不含 seed/Mock/Memory/Noop 或运行时数据源切换。
- THEN local_contract、api_integration、user_acceptance 均有真实断言和 CaseResult；禁止路径存在、动态 skip 或 Memory 假集成充当证据。

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
- 影响或价值：尚缺 AppRoot 直接 user_acceptance；需要以双账号真实数据证明 received/initiated 分页、未读与 impact、刷新/滚动恢复、子账号切换隔离、他人主页零请求、越权拒绝及八个归因事件。
- 完成判定：App local_contract 覆盖 Mock/Provider/Widget 和页面六态，Beta、Gamma 以双账号真实 HTTP/存储执行 received 与 initiated 全路径；服务拒绝他人读取且观测 readback 字段完整，CaseResult 直接引用 `UAT-004`。
- 依赖：[`owner-subaccount-homepage-unification`](./user-identity-profile-relationship/profile-homepage-redesign/owner-subaccount-homepage-unification/spec.md) 与 Content `ProfileInteractionActivityView` 对象证据。

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
- 完成判定：AssistantConversation/Run/Turn、InteractionEvent、LearningFact、PolicyRelease/Rollout 各自 local/API 合同全部通过。Alpha、Beta、Gamma 在五入口执行同一会话与失败矩阵，Behavior/Recommendation/Product Ops 可回读反馈，CaseResult 直接引用 `UAT-008`。正式模型 Provider receipt 由 Prod 单独关闭。
- 依赖：[`assistant-run-learning`](./assistant-run-learning/spec.md)、[`recommendation-platform`](./recommendation-platform/spec.md) 与 14 类 Provider conformance。

<a id="open-008"></a>
### OPEN-008 当前全部跨对象 Journey 商用准出

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：当前 12 Journey、28 Scenario、9 UAT 尚未由同一候选版本的三层 CaseResult 和 Alpha/Beta/Gamma/Prod 回执闭合；四环境尚无同一 canonical release 的 tag/creator/entity/post/media activation、真实 public-slice 字节、自然启动和精确 UI readback 证据，任何 fixture/self-seed/skipped-success 都会阻断准出。
- 完成判定：`UAT-009` 的派生覆盖图对全部验收锚点建立 direct `spec_ref`，同一 release digest 在 Alpha/Beta/Gamma/Prod 具有 import/API/media/rollback receipt；三环境双模拟器与 Android 真机、Prod Android/iPhone 双真机均完成精确对象和媒体读回，required executed 大于零且 skipped 为零。所有 Prod 回执及灰度回滚完成后才删除本 OPEN 并判定 `READY`。
- 依赖：前七项 AppRoot OPEN、全部最低节点 block OPEN、14 类 Provider 九格、Data publish/release/import/readback 与四环境 `stackctl verify`。
