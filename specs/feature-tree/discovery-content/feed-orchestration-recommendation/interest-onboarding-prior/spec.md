# L3 Story：兴趣引导先验 (`interest-onboarding-prior`)

> 所属能力：[`feed-orchestration-recommendation`](../spec.md)

> Journey / Scenario：[`JNY-003 / SCN-007`](../../../spec.md#scn-007)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为首次使用推荐的用户，
我希望选择受统一标签体系约束的兴趣并能确认或修正推荐先验，
从而在缺少历史行为时仍获得相关内容。

## 2. 范围与非目标

### In Scope

- “兴趣引导先验”的输入、可观察主路径、失败语义以及与父能力的交接。
- 标签、垂类、地点、内容类型兴趣先验。
- 上游页面以 `onboarding_interest` 公开行为提交路径制 `tagRefs`，服务端同步写入
  session HotPath，使首个推荐请求可进入 TagRecall。
- 游客可跳过；选择后以安装级加密草稿保留同一 `clientEventId`，登录成功恢复同一 intent，
  登录关闭回安全首页且不形成登录循环。
- 四维目录（topic/audience/format/entity）、版本、根节点和数量边界只由
  `content/post/ui_config.yaml` 声明；页面只查询 Tag Catalog，不维护标签常量，并只把
  live catalog 解析得到的 active leaf 作为可选项，禁止把根或分类节点显示为可提交兴趣。
- 确认型提交只有在服务端成功处理后才标记 submitted；失败保留 pending 草稿，同一
  `feedSessionId` 失效后重读首屏，跳过维持 generic 保底。
- Gamma 验收由 local stack 的 production Remote App composition 执行：tag-service 是同一
  本地栈内的一方服务，Content 仍经其 typed active-leaf port 校验；真正的第三方依赖则由
  环境 `externalBindings` 选择受控替代实现。不得把 App Mock/fixture 当作 Gamma UAT。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 兴趣引导先验

- “兴趣引导先验”必须通过父能力公开契约交付可观察结果；失败时返回 canonical failure，不写入成功事实。

<a id="req-002"></a>
### REQ-002 兴趣先验字段 metadata-first，不能在 UI 本地维护第二套标签列表

- 兴趣先验字段 metadata-first，不能在 UI 本地维护第二套标签列表。

<a id="req-003"></a>
### REQ-003 首启提交必须可信且可重试

- `catalogVersion`、路径制 tagRefs、四维根节点与数量边界必须在任何 HotPath、raw event
  或长期投影写入前 fail-closed 校验；客户端传入的空白、重复或目录外标签不得产生成功事实。
- `catalogVersion` 与 `taxonomyReleaseId` 是不同且必须同时由客户端携带的发布身份；
  服务端必须将二者与 `onboarding_interest_catalog` 的绑定精确比较，并把已确认的绑定随
  raw event 持久化。不得由服务端替客户端补写 taxonomy release。
- 首次接收的每批兴趣事件必须在任何去重、HotPath 或 raw event 写入前，针对客户端绑定
  release 的 active leaf snapshot 完成一次权威校验。父节点、inactive、旧 release、不存在
  标签、无 active release 及依赖失效均不得产生部分成功事实。
- 同一完整已确认 `clientEventId` 批次重放必须先通过只读 receipt 识别并直接成功，不得因
  taxonomy 依赖暂时不可用或 active release 后续变更改写既有结果；确认型网络失败不得转为
  尽力队列或伪称已个性化。

## 4. 契约引用

- canonical：`quwoquan_service/services/content-service/observability/slo/recommendation_slo.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/content/post/behaviors.yaml`
- canonical：`quwoquan_service/services/content-service/contracts/content/post/ui_config.yaml`
- canonical：`quwoquan_service/contracts/metadata/_shared/{app_routes,ui_surfaces,page_object_contract}.yaml`
- canonical：`quwoquan_service/services/user-service/contracts/account/user_account/fields.yaml`
- canonical：`quwoquan_service/services/content-service/tests/local_contract/content/post/application/behavior/onboarding_interest_taxonomy__local_contract_test.go`
- canonical：`quwoquan_service/services/content-service/tests/local_contract/content/post/infrastructure/taxonomyvalidation/http_active_leaf_validator__local_contract_test.go`
- canonical：`quwoquan_service/services/content-service/tests/api_integration/content/post/post_behavior_contract__api_integration_test.go`
- canonical：`quwoquan_app/test/api_integration/cloud/content/onboarding_author_impact_gamma__api_integration_test.dart`
- canonical：`quwoquan_app/test/user_acceptance/patrol/discovery/interest_onboarding__user_acceptance_test.dart`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 兴趣引导先验

- GIVEN 内容创作者或浏览者具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“兴趣引导先验”对应的公开行为。
- THEN 通过父能力公开契约交付“兴趣引导先验”的可观察结果。
- AND 相同 `clientEventId` 的重放不得重复累加权重；空白或重复 `tagRefs` 必须先
  canonicalize，最终没有有效标签时返回 `CONTENT.USER.invalid_argument`，且不得写入
  HotPath 成功事实。
- AND 目录版本未知、根节点不匹配、根节点或一层分类路径、或超过数量边界必须在成功事实之前返回
  `CONTENT.USER.invalid_argument`；确认提交失败后重试必须复用同一 `clientEventId`。
- AND 每个 tagRef 仅在 `onboarding_interest_catalog.taxonomy_release_id` 指向的 active
  snapshot 内是 active leaf 时可接受；parent、inactive、旧 release、缺失或无 active
  release 的标签均不得写入成功事实。
- AND 请求中的 `taxonomyReleaseId` 必须精确等于该 catalog 的发布绑定，且成功事实保留
  `catalogVersion + taxonomyReleaseId`；相同 catalogVersion 的旧 snapshot 不得被服务端
  重解释为当前 snapshot。
- AND 同一批中任一兴趣标签无效或 taxonomy 依赖不可用时，dedup、HotPath 与 raw event
  均保持零写入；首次有效批次只进行一次 taxonomy 校验，已确认重放不再调用依赖且只保留
  一份事实。
- AND 在 Gamma-local，真实 Remote Dart adapter 对相同 `clientEventId` 的提交可安全重放，
  对分类父节点返回 `CONTENT.USER.invalid_argument`；Patrol 从 live Tag Catalog 选择 leaf，
  等到确认完成后才返回首页。

## 6. 依赖

- 前置要求：[`feed-orchestration-recommendation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
