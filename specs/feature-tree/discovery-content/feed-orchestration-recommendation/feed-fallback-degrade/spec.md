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
- discovery/recommend、premium_stream/similar 与具名作品首刷的 HTTP 成功 envelope 必须由所属服务 contracts 的 canonical `outcome` 描述：非空条目为内容结果；健康零供给为成功空结果并携带闭集 `emptyReason`。空条目缺失合法结果语义属于协议错误，禁止 App 猜测。
- ActiveSupply reader 健康且明确不存在 active release，或 active release 读回一致但当前路由资格计数为零时，可以返回 canonical 成功空结果。following 健康零候选与有效 continuation 自然末尾同样属于成功空结果；四类事实必须由不同的 canonical empty reason 区分。
- 召回源失败、scorer 异常、scorer 对非空输入返回空输出、Redis 硬排除读取失败、ActiveSupply reader 未装配/读取失败/绑定或 readback 不一致、非空候选全量 hydration miss 均属于 canonical failure，不得包装成成功空结果。
- discovery/recommend、premium_stream/similar 与 `identity=work&type=video` 首刷使用当前环境 `sourceOwner=qwq_data` 的 active release snapshot。存在 active release 时 snapshot 必须包含 `status=active`、非空 `activeReleaseId`、与 immutable attestation 一致的 canonical `manifestDigest`、实时 `readbackStatus=passed` 以及同 release 的实时 Post/Discovery/Premium playable-video 计数；导入尝试计数不得替代实时读回。生产装配缺少 snapshot reader 不得绕过。
- release-bound 首刷最终下发集中必须至少有一条 `sourceOwner=qwq_data + releaseId=activeReleaseId + lifecycleStatus=active` 的可交付项。正常 UGC 可参与混合流，但不能单独满足 canonical release 准出。
- 推荐候选与 hydrated Post 必须同时匹配当前 active release；任一侧缺字段、旧 release 或非 active lifecycle 均不得下发。
- `identity=work&type=video` 无 cursor 首刷只读取当前 canonical release；健康零供给返回 canonical 成功空结果，读取、绑定、过滤或 hydration 链故障返回 canonical dependency failure。有效 PostReader cursor 的自然分页末尾仍为 canonical 成功空结果。
- 显式负反馈、隐藏作者与隐藏类型属于 Redis 硬过滤事实：读失败必须 fail closed；session 个性化与 served/impressed 长期曝光记忆属于软依赖，读取失败可保留同一请求快照内已完成的硬过滤后降级，不得重新放入硬排除内容。
- 服务边界复用 `CONTENT.SYSTEM.required_dependency_unavailable`，不得为推荐阶段新增公开错误码；内部 `failureStage` 是闭集，只允许 `none`、`recall_all_failed`、`recall_partial_failed`、`recall_partial_failed_empty`、`recall_empty_output`、`scorer_unavailable`、`scorer_empty_output`、`active_supply_missing`、`hard_exclusion_state_unavailable`、`personalization_unavailable`、`exposure_memory_unavailable`、`ranked_window_unavailable`、`hydration_full_miss`、`exposure_exhausted`。

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
- AND 健康零 active release 或当前路由资格计数为零时返回 canonical 成功空结果；发布 readiness 仍要求 discovery 与 premium/video-book exact query 非空，成功空态不得充当发布豁免。
- AND 首刷仅有 UGC、旧 release 候选、旧 release hydrated Post 或不可播放视频时不得算作 canonical release 发布成功；服务依赖异常返回 `CONTENT.SYSTEM.required_dependency_unavailable` 并携带闭集低基数 `failureStage`，有效 cursor 自然结束返回 canonical 成功空结果。
- AND Redis 硬排除事实不可读时返回 canonical failure；仅 session 个性化或 served/impressed 长期曝光记忆不可读时允许可观测降级，且不得绕过同一请求已加载的硬排除快照。
- AND following 健康零候选及有效 continuation 自然结束返回带合法原因的 canonical 成功空结果。

## 6. 依赖

- 前置要求：[`feed-orchestration-recommendation`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)
