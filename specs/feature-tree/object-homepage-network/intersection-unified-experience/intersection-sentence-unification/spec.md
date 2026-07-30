# L3 Story：交集句主谓宾统一表达 (`intersection-sentence-unification`)

> 所属能力：[`intersection-unified-experience`](../spec.md)

> Journey / Scenario：[`JNY-011 / SCN-026`](../../../spec.md#scn-026)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为浏览对象主页的用户，
我希望 seed、服务响应与展示口径均与 `intersection_kind_registry.yaml` 及父能力
[`Display Contract / §17`](../spec.md#display-contract) 一致，
从而理解对象并继续探索其关系与内容。

## 2. 范围与非目标

### In Scope

- “交集句主谓宾统一表达”的输入、可观察主路径、失败语义以及与父能力的交接。
- 端侧统一交集句组件收敛（IntersectionReasonChip 单句主谓宾、蓝色、单行省略）。
- 两类 surface 句式层次（紧凑严格单句；列表入口结论句 + 至多一条辅助说明）。
- 事实通道概念合规（无朋友/好友/收藏/同趣），affinity 明确标注推荐。
- 云侧交集主句实例化：关系限定代表人 + 人数、真实动作、可点击 typed object、primarySpans join invariant。
- App 展示合同 fail-closed：不合格交集句不展示，禁止端侧补主句或修坏句。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 交集句主谓宾统一表达

- seed、服务响应与展示口径均与 `intersection_kind_registry.yaml` 及父能力 [`Display Contract / §17`](../spec.md#display-contract) 一致。

<a id="req-002"></a>
### REQ-002 交集种子、服务响应与展示口径一致

- seed、服务响应与展示口径均与 `intersection_kind_registry.yaml` 及父能力 [`Display Contract / §17`](../spec.md#display-contract) 一致。
- 结论句模板唯一登记在 `intersection_kind_registry.yaml#statementTemplates`；每条模板必须带 `l10nKey`，云侧下发 `primaryTextL10nKey`。

<a id="req-003"></a>
### REQ-003 坏主句清理与展示拒绝

- Service 坏预置 primaryText 被重算或清空；证据不足的句子不进入展示层。
- App 所有交集展示入口共用 display-contract gate，坏句不占位。
- gamma strict semantic probe 逐条断言 raw stats、泛词、target、actorEvidence、actionHints。

<a id="req-004"></a>
### REQ-004 join(primarySpans.text) == primaryText 必须成立

- `join(primarySpans.text) == primaryText` 必须成立。
- 数字主语必须有 `representativeActor`：代表人 target 为 `user`，且有具体 `relationLabel`；不能只写 `4位共同好友`、`8人都来这里互动过`、`你和这里`。
- 宾语必须落到可路由 `IntersectionTarget`：`user/circle/homepage/post/task`。内容类对象用 `post` + `workBrowser`，圈子/实体/人分别映射到对应对象页。
- 禁止主句 raw stats 和泛词：`2赞 1评 1转`、`同读者`、`相近主题的长文`、`TA的内容`、`相关圈子`、`我的连接`、`我的影响力`。
- `start_gathering` 必须绑定同一条 `coWishlistedEntity` 证据和可承接 target；没有真实 co-wisher / 承接页时不展示行动入口。
- 端侧统一交集句组件（收敛现有 `IntersectionReasonChip`）：单句、蓝色、单行省略；**仅**消费 `primaryText`（禁止 displayText 回退）。
- 概念合规：事实通道禁止「朋友/好友/收藏/同趣」。
- affinity 明确标注「推荐」。
- 我的主页/用户主页/实体主页/圈子主页统一使用「我的交集」口径。

<a id="req-005"></a>
### REQ-005 交集文案运营态覆盖与 fail-safe 回落

- 每条用户可见文案（结论句模板、主语/关系/维度/类别/动词/行动短标签）都带 `l10nKey`：
  `statementTemplates` 逐条登记，`presentationText` 与 `actionLabelByKey` 按各自
  `l10nKeyPrefix` + snake(条目键) 推导。
- 控制面以 `sys.intersection_text.<l10nKey>.<locale>` 下发覆盖，热更生效；改一句文案不发端也不发服务。
- 覆盖失败一律回落 codegen 基线：控制面不可达、key 未下发、值为空白、覆盖模板引用了本次没有值的槽位，
  都必须继续出基线句，禁止让交集因一次文案配置错误消失。
- 覆盖不改变 `primaryTextL10nKey`：端与译文按同一 key 对齐。
- 覆盖命中率由 `controlplane_intersection_text_override_total{result,locale}` 观测。

## 4. 契约引用

- canonical：`recommendation/recommendation/recommendation_model_release/projections/intersection_reason.yaml`
- canonical：`content/test_fixtures/scenarios/content_scenarios.json`
- canonical：`recommendation/recommendation/recommendation_model_release/projections/intersection_actor_evidence.yaml`
- canonical：`recommendation/recommendation/recommendation_model_release/projections/intersection_target.yaml`
- canonical：`recommendation/recommendation/recommendation_model_release/intersection_kind_registry.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 交集句主谓宾统一表达

- GIVEN 浏览对象主页的用户具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“交集句主谓宾统一表达”对应的公开行为。
- THEN seed、服务响应与展示口径均与 `intersection_kind_registry.yaml` 及父能力 [`Display Contract / §17`](../spec.md#display-contract) 一致。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`intersection-unified-experience`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 交集句主谓宾统一表达 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“交集句主谓宾统一表达”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。

<a id="open-002"></a>
### OPEN-002 交集文案按请求语言渲染

- 类型：`capability_gap`
- 优先级：`P2`
- 准出影响：`track`
- 影响或价值：当前渲染侧按进程级 `DefaultTextLocale`（zh）取覆盖值，尚未消费请求语言。
  `REQ-005` 的覆盖 key 已按 locale 分片、控制面可以为 `en` 备好整套文案，但交集句由数十个
  片段在 application 层深处合成，把 `X-Client-Locale` 送到每个片段需要贯穿约 60 个渲染函数。
  在此之前，非 zh 客户端仍会收到 zh 文案。
- 完成判定：`rterr` 的请求语言解析贯穿到 `intersection` 渲染层，
  同一请求内所有片段用同一 locale 取覆盖；契约测试断言 `en` 请求命中 `en` 覆盖、
  未下发条目回落 zh 基线。
