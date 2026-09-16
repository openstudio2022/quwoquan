# L3 Story：content-action-intent-contract（8 类反馈闭环契约） (`content-action-intent-contract`)

> 所属能力：[`content-display-consistency`](../spec.md)

> Journey / Scenario：[`JNY-003 / SCN-007`](../../../spec.md#scn-007)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容创作者或浏览者，
我希望更多操作面板只展示已具备真实结果或安全终态的能力；禁止“功能开发中”假入口，
从而完成可恢复的内容创作、发现或互动。

## 2. 范围与非目标

### In Scope

- “content-action-intent-contract（8 类反馈闭环契约）”的输入、可观察主路径、失败语义以及与父能力的交接。
- like/share/comment/dislike/report/block user/block keywords 的现役对象归属与端云链路；标题中的“8 类”为保留的历史标识，不恢复第八条 Post 收藏写轨。
- 举报原因选择、reporter 私有进度、运营 Report/ModerationCase 审核与结案通知。
- 不感兴趣即时移除、短时 undo_dislike 补偿和未来窗口精确过滤。
- 首页 Feed 与 Work Browser 两个宿主的行为、归因、登录 continuation 和错误恢复一致性。
- 打赏、会员、虚拟币等交易能力；在交易合规、计费与退款契约具备前不得展示。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 content-action-intent-contract（8 类反馈闭环契约）

- 更多操作面板只展示已具备真实结果或安全终态的能力；禁止“功能开发中”假入口。

<a id="req-002"></a>
### REQ-002 Discovery 侧反馈入口统一接入 typed 领域 coordinator（Works + Moment）

- Discovery 侧反馈入口统一接入各自 owner 的 typed 领域 coordinator，再经公开 writer/query；页面不得直调 writer、局部 setFollowing 或复制队列作为成功旁路。
- 更多操作面板只展示已具备真实结果或安全终态的能力；禁止“功能开发中”假入口。
- 打赏、会员、虚拟币等交易能力；交易合规、计费与退款契约不完整时不得展示入口。
- `like/comment/report` 走各对象专用命令，禁止混入 batch tracker；人物关注仍由 User 关系 coordinator 拥有，SubjectFollow 保持独立目标与 writer。
- 不恢复 Post 收藏或把实体「想去」改成 Post 意图；既有想去的 owner/入口按 [发布互动 DEC-002](../../publish-comment-reaction/design.md#dec-002) 保持，本次不增加想去功能。
- `block keywords` 必须 metadata-first，先补 `UserSetting.blockedKeywords` 再接 UI。
- 推荐实时链路依赖 `sessionId`，端侧 headers 必须稳定注入。
- Post 举报必须先选择 metadata `ReportReason`，不得固定提交 `other`。
- `block user` 文案必须明确表达“拉黑”及其影响，不能用轻量措辞包装重操作。
- `block keywords` 必须由用户确认具体词，并提供查看、删除与恢复入口。

<a id="req-003"></a>
### REQ-003 现役全入口由真实 surface 发出同一 typed 意图

- Post 点赞覆盖 Feed、viewer 所有方向/控制区、评论内 Post、作者作品、搜索直达及路由直达；Comment 赞踩覆盖一级评论、回复与个人互动 Tab，保持独立三态与登录要求。
- 人物关注覆盖首页卡、作者主页、viewer、关注/粉丝列表、圈子成员/统计、账号搜索、联系人确认/二维码和通讯录发现；全部消费 User 的唯一目标解析、版本化关系/capability 与 coordinator，不把 handle 当 Persona，不把 Creator 当登录 actor。
- source surface 由实际宿主经 generated descriptor 传递；点赞不得默认标成 createWorkspace，circleStats 等现役入口必须拥有对应 metadata 授权，不能为通路放宽无关 surface。
- scope、配置、身份或 capability 错误是不可自动重试的 typed failure，不进入长期静默队列。关注最终态只云确认；点赞按钮可乐观但统计只读服务端事实；UI 点击/归因不产生第二份关注或点赞成功事件。
- 每个入口由生产 provider/descriptor/header factory 到 typed coordinator 的直接断言覆盖，并能反向指回 metadata surface；不另建人工中央入口 registry。

## 4. 契约引用

- canonical：`quwoquan_service/services/content-service/contracts/trust_safety/report/operations.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/trust_safety/report/events.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/content/content_behavior_fact/behaviors.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/trust_safety/post_moderation_case/operations.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/account/user_settings/operations.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/relationship/persona_relationship/operations.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 content-action-intent-contract（8 类反馈闭环契约）

- GIVEN 内容创作者或浏览者具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“content-action-intent-contract（8 类反馈闭环契约）”对应的公开行为。
- THEN 更多操作面板只展示已具备真实结果或安全终态的能力；禁止“功能开发中”假入口。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 全入口通过生产 descriptor 传递真实意图

- GIVEN `REQ-003` 列举的各人物关注、Post 点赞与 Comment 赞踩入口可达，且目标已被 owning resolver 唯一解析。
- WHEN 经实际页面 provider、descriptor/header factory 发起动作，而不是测试手工构造一个正确 Remote。
- THEN 每入口传递真实宿主 surface、canonical target、verified actor 与稳定命令身份，仅进入对应 typed coordinator；不存在页面直写、错误 createWorkspace 默认或放宽无关 surface。
- AND 关注最终态等云确认，Post 只乐观按钮且数字不 +1，Comment 独立三态；scope/身份/配置拒绝明确终态不排队重试，点击埋点不伪造业务成功。独立 SubjectFollow 不改成通用人物 Pair。

<a id="gwt-003"></a>
### GWT-003 历史 Post 收藏不回归

- GIVEN Feed、Work Browser 与直达详情渲染现役内容动作。
- WHEN 用户查看动作或触发恢复/登录续接。
- THEN 不存在 Post 收藏写入、计数或入口；已有实体「想去」仅服从现役 owner/合法锚点与宿主合同，本次不新增入口，不把想去当 Post 收藏替身。

## 6. 依赖

- 前置要求：[`content-display-consistency`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 更多操作面板失败语义尚无直接证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：缺 `GWT-001.t2` 的直接证据。t1 已由 `more_action_popup__functional__local_contract_test.dart` 精确断言（只展示有真实动作的入口、无「功能开发中」假入口）并实跑通过，但该测试不覆盖失败返回 canonical failure。
- 完成判定：`GWT-001.t1` 与 `GWT-001.t2` 各自被真实测试 `spec_ref` 绑定。

<a id="open-002"></a>
### OPEN-002 全入口 coordinator 与 surface 尚缺当前证据

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：`REQ-002`、`REQ-003`、`GWT-002` 尚待现役入口逐个接线与直接测试；手工 Remote 用例不能证明 production provider，Creator 资格缺失也不能通过隐藏全部作者关注入口关闭。
- 完成判定：`GWT-002` 所列每入口均有当前 surface/operation 对应的真实断言与适用 API/双真机证据；scope/身份错误不重试，不维护页面成功旁路或人工中央 registry。

<a id="open-003"></a>
### OPEN-003 Post 收藏退场的入口回归证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：`REQ-002` 与 `GWT-003` 尚缺覆盖 Feed/viewer/直达详情及恢复入口的当前直接证据；本次文案修正不意味着客户端与生成物已验证。
- 完成判定：无 Post 收藏写轨/入口，实体「想去」现役边界不扩张，真实测试直接绑定 `GWT-003`。

## 8. 待实现验收的测试绑定

- 全入口清单由当前页面源码、generated surface/operation 和运行断言重建，本段不记录完成状态。后续测试必须在直接断言旁绑定本 Story `GWT-002` 或 `GWT-003`，operations 的 required readiness 仍由各 owner 登记。
- App local_contract 优先扩展 `quwoquan_app/test/local_contract/journeys/cross_page_interaction_consistency/cross_page_interaction_consistency__local_contract_test.dart`、`quwoquan_app/test/local_contract/service/content_service/content/post/content_interaction_contract__local_contract_test.dart` 与 `quwoquan_app/test/local_contract/service/content_service/content/content_reaction/content_post_reaction_remote__local_contract_test.dart`；这些现有入口尚未被本次证明覆盖新矩阵。
- api_integration 扩展 `quwoquan_app/test/api_integration/service/content_service/content/content_reaction/content_reaction_remote__api_integration_test.dart`；人物与 circleStats 入口在对应 owner 测试目录补 production descriptor 场景，不能把人工正确 header 的 200 当页面证据。
- user_acceptance 扩展 `quwoquan_app/test/user_acceptance/service/content_service/content/content_reaction/like_post__user_acceptance_test.dart`、`quwoquan_app/test/user_acceptance/service/content_service/content/comment/comment_post__user_acceptance_test.dart`、`quwoquan_app/test/user_acceptance/journeys/profile/profile_journey__user_acceptance_test.dart`；每个列举入口单独覆盖，未覆盖者继续阻断 `OPEN-002`。
- canonical surface：`quwoquan_service/contracts/metadata/_shared/ui_surfaces.yaml`；Reaction 与人物关系命令/恢复分别引用 `quwoquan_service/services/content-service/contracts/content/content_reaction/operations.yaml` 与既有 User owning operations。
