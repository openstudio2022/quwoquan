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
- like/favorite/share/comment/dislike/report/block user/block keywords 对象归属与端云链路。
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
### REQ-002 Discovery 侧反馈入口统一接入 Provider/Repository（Works + Moment）

- Discovery 侧反馈入口统一接入 Provider/Repository（Works + Moment）。
- 更多操作面板只展示已具备真实结果或安全终态的能力；禁止“功能开发中”假入口。
- 打赏、会员、虚拟币等交易能力；交易合规、计费与退款契约不完整时不得展示入口。
- `like/favorite/comment/report` 走专用路由，禁止混入 batch tracker。
- `block keywords` 必须 metadata-first，先补 `UserSetting.blockedKeywords` 再接 UI。
- 推荐实时链路依赖 `sessionId`，端侧 headers 必须稳定注入。
- Post 举报必须先选择 metadata `ReportReason`，不得固定提交 `other`。
- `block user` 文案必须明确表达“拉黑”及其影响，不能用轻量措辞包装重操作。
- `block keywords` 必须由用户确认具体词，并提供查看、删除与恢复入口。

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
