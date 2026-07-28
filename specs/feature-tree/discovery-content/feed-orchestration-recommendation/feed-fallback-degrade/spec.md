# L3 Story：内容流回退降级 (`feed-fallback-degrade`)

> 所属能力：[`feed-orchestration-recommendation`](../spec.md)

> Journey / Scenario：[`JNY-003 / SCN-007`](../../../spec.md#scn-007)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容创作者或浏览者，
我希望推荐依赖失败时保留可用内容并明确标记降级，不伪造个性化结果，
从而完成可恢复的内容创作、发现或互动。

## 2. 范围与非目标

### In Scope

- “内容流回退降级”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 内容流回退降级

- “内容流回退降级”必须通过父能力公开契约交付可观察结果；失败时返回 canonical failure，不写入成功事实。
- discovery/recommend 首刷只有两种合法终态：至少一条通过 published/safety/block/negative/hide/hydration 检查的真实内容，或所属服务 contracts 已声明的 canonical failure；禁止用 HTTP 成功空数组伪装供给、召回、打分或装配成功。
- following 在所有适用召回源健康且确实无候选时可返回成功空数组；持有有效 continuation 的分页请求到达自然末尾时也可返回成功空数组。召回源失败、scorer 对非空输入返回空输出、active supply 缺失或非空候选全量 hydration miss 不属于合法空态。
- 服务边界复用 `CONTENT.SYSTEM.required_dependency_unavailable`，不得为推荐阶段新增公开错误码；内部只以低基数 `failureStage` 区分 `recall_all_failed`、`recall_partial_failed_empty`、`scorer_unavailable`、`scorer_empty_output`、`active_supply_missing`、`hydration_full_miss`、`exposure_exhausted`。

<a id="req-002"></a>
### REQ-002 服务本地契约引用边界

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 内容流回退降级

- GIVEN 内容创作者或浏览者具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“内容流回退降级”对应的公开行为。
- THEN 通过父能力公开契约交付“内容流回退降级”的可观察结果。
- AND 失败时返回 canonical failure，且不产生伪成功事实。
- AND discovery/recommend 首刷非空；若 active release、召回、scorer 或 hydration 无法形成可下发内容，则返回 `CONTENT.SYSTEM.required_dependency_unavailable` 并携带低基数 `failureStage`。
- AND following 健康零候选及有效 continuation 自然结束可返回成功空数组。

## 6. 依赖

- 前置要求：[`feed-orchestration-recommendation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
