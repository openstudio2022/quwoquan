# L1 规格：对象主页网络升级

## 定位

`object-homepage-network` 是用户主页、圈子/群组主页、共享主页三类对象页的跨域体验与契约收口层。

它不替代 `user-identity-profile-relationship`、`circle-community`、`shared-homepage-network` 的领域主档职责，而是定义三类主页在同一套对象网络中的用户价值、信息架构、内容归属、交集解释、灰度运营、推荐回流与小艺主动服务合同。

用户前台不看到“对象主页网络”这个术语。前台只看到：

- 用户主页：这个人是谁、在创造什么、我和 TA 有什么关系、我能如何关注或协作。
- 圈子/群组主页：这群人围绕什么正在发生、我该加入哪里、有哪些内容和成员。
- 共享主页：这个学校、地点、景点、餐厅、酒店、车型等具体对象是什么、大家围绕它说了什么、有哪些相关内容和圈子。

## 背景与动机

当前三类主页已经具备共享壳层基础，但还没有达到一流商用上线标准：

1. 三类主页已有 `ObjectPageShell`，但用户、圈子、共享主页的 header、看点区、交集卡和行动入口视觉不统一。
2. 内容仍主要按首页、精品、圈子列表分发，缺少按用户、圈子、共享主页三种对象维度自然归属和回流的统一合同。
3. 交集理由、小艺解释、推荐排序、行为回流尚未完全消费同一套 `IntersectionReason + ObjectRelationEdge`。
4. 共享主页存在上线硬债：`HomepageType` 枚举漂移、entity-service 内存态、评论缺少实体关联、离线实体与运行时主页双 ID。
5. 商用上线需要运营灰度、埋点、实时推荐、小艺主动服务和回滚看板闭环，不能只做 UI 改版。

## 商用目标

本节点目标是达到“小红书级内容看点 + 微信级关系导航”的商用水准：

- 简洁美观：三类主页同源设计系统，首屏不堆砌，视觉重心明确。
- 有看点：每个对象页首屏都有精选内容、口碑或关系证据，而不是纯资料页。
- 有深度：交集理由来自真实标签、实体和关系边，不拼接假文案。
- 有关系：用户、圈子、共享主页可以互相跳转，且用户不迷路。
- 可运营：支持按地域、版本、白名单、分桶、对象类型灰度。
- 可学习：对象页事件实时回流推荐和小艺，形成曝光、理解、行动、反馈闭环。

## 能力范围

### R1：统一对象页信息架构

- 三类主页统一采用 `身份区 / 交集与小艺区 / 看点区 / 导航区` 四段式。
- 身份区包含封面、头像或对象图、类型徽章、可信状态、核心统计和主操作。
- 交集与小艺区展示 1 到 3 条真实交集证据，并提供小艺轻入口。
- 看点区展示 2 到 4 张高质量内容卡，承接精选作品、口碑、热议、相关圈子或共同关注。
- 导航区为吸顶 Tab，文案随对象类型自然变化，底层 section id 同源。

### R2：三类对象页定位

- 用户主页 Tab 冻结为 `看点 / 作品 / 圈子 / 互动`。
- 圈子/群组主页 Tab 冻结为 `首页 / 内容 / 群或组织 / 成员`。
- 共享主页 Tab 冻结为 `首页 / 内容 / 口碑 / 关联`。
- 前台文案必须使用用户语言，不向用户暴露 `entity`、`object graph`、`relation edge` 等工程术语。

### R3：对象关系契约

- 新增 `ObjectRelationEdge`，表达 `author_of / posted_to_circle / reshared_to_circle / mentions_entity / comment_about_entity / circle_under_entity / member_of / co_tagged / review_of`。
- 新增 `ObjectPageBundle`，统一返回 `identity / stats / intersectionReasons / highlightItems / contentSections / relatedObjects / assistantContext / rolloutContext`。
- 新增 `ObjectPageContext`，小艺和推荐共同消费 `objectType / objectId / canonicalEntityId / tagRefs / entityRefs / relationEdges / referralSource / feedRequestId / recommendationTraceId`。
- 端侧不得在 UI 拼装关系文案或维护第二套路由、surface、operation、tagRef、entityRef 表。

### R4：四项上线硬债清算

- `HomepageType` 与模板体系收口，支持首发校园与旅游出行对象，不再出现 fixture 与 enum 漂移。
- entity-service 主页读模型产品化，具备持久化、聚合内容、相关圈子、口碑和关系边能力。
- 评论支持关联共享主页或规范实体引用，评论可进入对象页口碑或讨论证据链。
- 数据工程实体归一 ID 与运行时 Homepage ID 建立单一对象键映射，避免 `/entity/...` 与 `/homepages/{id}` 双真相源。

### R5：运营灰度与回滚

- 全量功能一次性开发完成，但发布必须可按 `region / city / campus / appVersion / buildNumber / userWhitelist / experimentBucket / objectType / runtimeEnv` 灰度。
- 生产 App 仍只有一个 `prod` 包；灰度由应用市场分发、端侧上下文和云侧策略协同完成。
- 每个灰度 cohort 必须能独立观测曝光、交集理解、行动转化、异常率、接口 RT、小艺触发率和 dismiss 率。
- 任一 cohort 指标跌破阈值，可关闭对象页新模板、关系证据区、小艺主动提示或推荐策略变体。

### R6：埋点到实时推荐闭环

- 对象页事件统一进入行为管道，至少包括：
  - `object_page_exposed`
  - `intersection_reason_impression`
  - `intersection_reason_click`
  - `relation_edge_click`
  - `highlight_item_click`
  - `object_tab_switch`
  - `assistant_suggestion_impression`
  - `assistant_suggestion_click`
  - `assistant_suggestion_accept`
  - `assistant_suggestion_dismiss`
  - `object_action_follow`
  - `object_action_join`
  - `object_action_comment_about_entity`
  - `object_action_claim`
- 事件必须携带 `objectType/objectId/canonicalEntityId/tagRefs/entityRefs/relationEdgeIds/intersectionReasonIds/referralSource/feedRequestId/recommendationTraceId/experimentBucket/rolloutCohort`。
- 推荐系统按对象关系和交集反馈更新排序，不允许只消费普通点击事件。

### R7：小艺主动服务闭环

- 小艺主动提示由 `ObjectPageContext`、`IntersectionReason`、`ObjectRelationEdge` 和 rollout 策略共同决定。
- 主动提示必须有置信度、触发原因、冷却时间和可 dismiss 状态。
- 小艺主动入口形态为轻 dock 或证据旁提示，不允许覆盖核心内容或制造打扰。
- 用户接受、点击、忽略、关闭都必须回流行为管道，供推荐和小艺策略学习。

### R8：视觉与交互基线

- 三类主页共享 `ObjectIdentityHeader / ObjectRelationRibbon / ObjectHighlightSection / ObjectContextTabBar / ObjectAssistantActionDock`。
- 人、群组、共享主页使用同源组件内的差异化形态：圆形头像、群像卡、场景封面。
- 多列瀑布流中插入横向运营流时，横向流整行独占并保持统一上下留白，避免列错位。
- 空态、加载、弱网、无交集、数据稀疏必须有专门设计，不能展示空白或假交集。
- 跨对象跳转必须带来源面包屑、`referralSource`、返回栈语义和一致转场，避免用户迷路。

## Out of Scope

- 不在本节点内新增交易、预约、支付、团购闭环。
- 不以本节点替代 user/circle/entity 各自的主档、权限、治理和生命周期归属。
- 不新增第二套标签枚举；标签真相源为数据工程 `control_plane/governance/taxonomy`，metadata 只声明 `tagRef` 契约，App/Service 消费发布后的 serving projection。
- 不允许为了兼容旧 UI 保留并行主页分支；本轮按新架构替换。

## 验收重点

- A1：三类主页 3 秒内讲清“它是谁/是什么”“我和它有什么关系”“我能做什么”。
- A2：内容可按用户、圈子、共享主页三维自然归属和流转。
- A3：交集卡、推荐理由、小艺解释、行为回流消费同一对象关系契约。
- A4：四项上线硬债关闭，且 metadata/codegen/fixture 不漂移。
- A5：灰度、埋点、实时推荐、小艺主动服务和回滚看板形成闭环。
- A6：页面横向质量 P1-P8、Mock 隔离、语义 token、弱类型预算、runtime error、local_contract-user_acceptance 全部满足。
