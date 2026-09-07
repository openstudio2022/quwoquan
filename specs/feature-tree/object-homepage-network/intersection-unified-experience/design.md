# L2 Design：交集统一体验与推荐 (`intersection-unified-experience`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“以统一的交集事实、置信度、保鲜期和展示契约驱动发现、对象主页、圈子、聊天、个人主页与助理场景”需要 `circle-homepage-intersection-redesign`、`entity-homepage-intersection-redesign`、`home-recommend-intersection-redesign`、`intersection-algorithm-closure`、`intersection-sentence-unification`、`object-homepage-gamma-real-data-closure`、`user-profile-intersection-redesign` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：以统一的交集事实、置信度、保鲜期和展示契约驱动发现、对象主页、圈子、聊天、个人主页与助理场景。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`circle-homepage-intersection-redesign`](./circle-homepage-intersection-redesign/spec.md)：标题统一为「圈子打动的人」，文案口径与 `intersection_kind_registry.yaml` 登记的 kind / dimension / actionHint 口径一致。
- [`entity-homepage-intersection-redesign`](./entity-homepage-intersection-redesign/spec.md)：定义“实体主页交集重做”的可观察主路径、失败语义及父能力交接。
- [`home-recommend-intersection-redesign`](./home-recommend-intersection-redesign/spec.md)：spotlight 文案口径与 `intersection_kind_registry.yaml` 登记的 kind / dimension / actionHint 口径一致。
- [`intersection-algorithm-closure`](./intersection-algorithm-closure/spec.md)：ranking-signal-fusion spec 登记 intersection fact/affinity 权重入口。
- [`intersection-sentence-unification`](./intersection-sentence-unification/spec.md)：seed、服务响应与展示口径均与 `intersection_kind_registry.yaml` 及本 Story Display Contract 一致。
- [`object-homepage-gamma-real-data-closure`](./object-homepage-gamma-real-data-closure/spec.md)：metadata 与 compose 静态契约通过。
- [`user-profile-intersection-redesign`](./user-profile-intersection-redesign/spec.md)：他人/我的主页二级过滤同一实现。

## 3. 端云与数据流

- 上游能力：[`object-homepage-network`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 把交集的展示与推荐统一到一套契约和一组共享组件上
- 决策：把交集的展示与推荐统一到一套契约和一组共享组件上。
- 理由：以统一的交集事实、置信度、保鲜期和展示契约驱动发现、对象主页、圈子、聊天、个人主页与助理场景。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`circle-homepage-intersection-redesign`](./circle-homepage-intersection-redesign/spec.md)、[`entity-homepage-intersection-redesign`](./entity-homepage-intersection-redesign/spec.md)、[`home-recommend-intersection-redesign`](./home-recommend-intersection-redesign/spec.md)、[`intersection-algorithm-closure`](./intersection-algorithm-closure/spec.md)、[`intersection-sentence-unification`](./intersection-sentence-unification/spec.md)、[`object-homepage-gamma-real-data-closure`](./object-homepage-gamma-real-data-closure/spec.md)、[`user-profile-intersection-redesign`](./user-profile-intersection-redesign/spec.md)
- 关联验收：`SIT-001`

<a id="dec-002"></a>
### DEC-002 垂类扩展只允许「vertical + objectKind + taxonomy 子树 + 事实生产者」四件套

- 决策：新增一个垂类 = 注册一个 `vertical` 值 + 注册若干 `objectKind`（每个必须映射到已有 homepage 类型或已有对象，且 `routeId` 在 `app_routes.yaml` 真实存在）+ 建一棵 taxonomy 子树 + 建一个事实生产者（把原始素材或行为转成 tagRef 与对象引用）。**禁止新增 kind、dimension、actionKey，禁止端侧引入任何垂类分支。**
- 理由：`kind + vertical + objectKind` 是正交三元组。垂类的差异化应体现在**事实的丰富度**，而不是结构分叉。一旦为垂类开 kind，同一件事就有 general 与垂类两套句子与两套排序权重（第二真相源），并且端侧不得不按 `vertical` 分叉渲染，垂类数量与端侧分支数线性绑定。
- 推论：旅行摄影**零新 kind**，三类事实各自归位到已登记的通用 kind 或推荐通道。
  - 同地到访 = 已登记的 `coVisitedEntity` / `followeeVisited`，只缺 `post.visitedAt` + `geoTagRef` 生产者，不缺 kind。
  - 器材 / 焦段 / 曝光参数**不做成交集句**，只作为作者可控披露、推荐解释与内容理解事实。`gear` objectKind 只保留既有 homepage 结构能力，不因 EXIF 自动生成交集。
  - 光线条件进入画面氛围语义轴；它可以参与推荐与内容理解，但仍不得作为不可导航 tag 生成交集主句。上述事实统一登记在 `recommendationOnlyFacts`。
- 被否决方案：为旅行摄影新增 `sameGearUsed` / `sharedPhotoSpot` / `sameLightWindow` 等 `travel.*` 私有 kind；或在端侧按 `vertical` 分支渲染垂类专属卡片与专属页面。
- 约束与影响：契约与四条禁令（`forbidNewKind` / `forbidNewDimension` / `forbidNewActionKey` / `forbidClientVerticalBranch`）登记在 `intersection_kind_registry.yaml` 的 `verticalExtensionContract`，事实生产者只引用同文件 `factProducerShapes` 的受控输入与输出 shape，并由 `verify_intersection_kind_registry.py` 阻断自由文本生产者、recommendation-only 事实回流成交集句和当前 kind 缺模板。端侧 `IntersectionTargetNavigator` 只按生成的当前 `actionKeyMeta.dispatch` 闭集分发。
- 关联要求：`REQ-005`
- 影响 Story：[`intersection-algorithm-closure`](./intersection-algorithm-closure/spec.md)、[`intersection-sentence-unification`](./intersection-sentence-unification/spec.md)
- 关联验收：`SIT-005`

<a id="dec-003"></a>
### DEC-003 经历类一等 kind `coExperiencedGathering`（交集飞轮回流环）

- 决策：在 `intersection_kind_registry.yaml` 注册一等事实 kind `coExperiencedGathering`（dimension=relationship、objectKind=person、countObjectKind=gathering、valueTier=T1、evidenceRank=5、moment=retrospective），生产者为受控 shape `gathering_shared_experience`。产出条件：双方在同一 Gathering 均持有 active Participation，且各自主动发布了关联该 Gathering（`content.post.gatheringRef`）的公开内容。
- 对象形状：经历是两个人之间的关系事实，reason 主对象（`objectKind`/`actionTargetId`）是对方本人；共同行动只作 `subjectContext: gathering:<id>` 锚点与 `intersectionPoints` 样本，被计数对象仍是 gathering。这样对方主页的 `host_implicit` 校验（reason target 必须等于宿主）成立；收件箱与「我的经历」读 subject 快照，因此经历事实同时按对方本人聚合进入 subject 快照（`_co_experienced_subject_reasons`），行对象即对方、由收件箱读面以 reason 自身对象作宿主套用展示合同。行动阶梯只到人（`start_gathering` / `message_person`），「回看行动详情」由端侧解析 `subjectContext` 而不是 `actionTargetId`。主句按 counted 模板以 `mutualPair` 主语渲染（Recommendation 快照不持有行动名）；生产者同时把对方本人挂为具名 `representativeActor`（称谓出自注册表 `relationLabels`），使「你们」在收件箱行之外的宿主面（内容卡）也可解释——该规则由 [`intersection-sentence-unification` REQ-004](intersection-sentence-unification/spec.md#req-004) 统一裁定，Content 输出口以 `mutualPairSubjectExplainable` 执行。
- 同形推广：`sharedCircle` 是同一类「两个人之间的关系事实」，采用相同对象形状——注册表 `objectKind=person`、`countObjectKind=circle`，生产者以对方本人为 reason 主对象、共同圈子只经 `subjectContext: circle:<id>` 与 `intersectionPoints` 计数承载（样本文本不放圈子 id），行动阶梯只到人（`greet_person` / `message_person`）：注册表 `objectKind` 与生产者输出必须同为对方本人，`join_circle` 对双方本就都在圈内的事实没有意义，因而不进入该 kind 的行动阶梯。
- 理由：交集飞轮（意图交集 → 行动 → 经历交集 → 更强撮合）的增值环需要模型载体；一起完成过一次行动是强度最高的可证共同点，直接决定复约信任与命中率。DEC-002 的「禁止新增 kind」针对垂类扩展防腐，一等通用事实 kind 的演进是注册表本体升级，属本 DEC 的合法路径，仍要求：先登记注册表（含 statementTemplates/actionHints），再 codegen，端侧零分支。
- 诚实边界（到访/浏览/想去红线延伸到经历）：时间到达、聊天频率、位置或单方声明**不得**触发本 kind；「成形」（room ready + ≥2 有效参与者）与「经历」（≥2 参与者主动发布关联内容）两级计数不得互相冒充。结论句只说「一起参加过」，occurred 语义由 Gathering Outcome 独立承载。个人空闲时间不在任何模型内，产品与助手禁止宣称「对方有空」。
- 被否决方案：把经历做成 travel 垂类私有 kind、由聊天频率/共同定位推断“见过面”、用 Outcome occurred 直接生成交集（占用尚无独立证据链的语义）；以 gathering 作 reason 主对象（Content 水合会派生出 `user:<gatheringId>` 幽灵 target，对方主页 host_implicit 校验必然失败而被隐藏，且 explicit_link 需要快照不持有的行动名）。
- 关联要求：`REQ-009`
- 关联验收：`SIT-008`

<a id="dec-004"></a>
### DEC-004 社会证明四锚点计数，不做对人评分

- 决策：成行与经历的社会证明以四锚点事实计数呈现——实体主页（促成同行 N/共同经历 M）、内容溯源（促成同行 N）、创作者主页（成行力：内容促成 N 次同行/带来 M 段经历）、发起人可信卡（发起 N/成形 M/经历 K）。计数只由「成形」「经历」两级诚实事实派生；时间已过无内容只显示已结束、不进计数。**不做对人星级/评分**，负面走举报/Block/安全终止通道，不进公开评价区。
- 理由：评分把同行者异化为被打分的服务者，制造评价焦虑与刷分动机，与「不打卡、不推断见面」原则冲突；共同经历内容（照片+文字+可溯源）本身就是最可信的富评价。创作者「成行力」是竞品不具备的创作者激励，其溯源链为：经历 Post → `gatheringRef` → Gathering `sourceRefs` → 原内容 → 创作者。
- 归属（实现修订，单一真相源）：四锚点计数**统一由 recommendation 聚合承载**——它是唯一消费全事件链（`GatheringPublished` + `GatheringParticipationChanged` + Post(`gatheringRef`)）的域；`GatheringPublished` 事件为此携带 organizer 与 canonical `sourceRefs`（objectKind + objectId），计数在读时按锚点从发起证据、active Participation 与公开回顾事实聚合派生（`GetRecommendationGatheringSocialProof`，internal），Content 以 `GetGatheringSocialProof` 代理为 App 公开读面，任何域不落计数缓存副本。原「发起人统计归 circle host 投影」方案被本修订取代：拆两个 owner 会让「经历 K」跨域事实出现第二真相源。
- 被否决方案：五星评分/爽约信用分；把浏览量、群消息数、口头意愿计入社会证明。
- 关联要求：`REQ-009`
- 关联验收：`SIT-008`

<a id="dec-005"></a>
### DEC-005 保鲜冷却与曝光转化漏斗：曝光按 intersectionId 冷却过滤、过期由读面重物化、cohort 是策略身份

- 决策（曝光冷却）：曝光冷却集 `rec:icool:{userId}` 以 `intersectionId` 为成员键，与行为管道 `impression` / `click` / `intersection_expand` 携带的归因键同源；Content 只在行为管道收到 `impression(state=impressed)` 且携带 `intersectionId` 时写入（`IntersectionService.ReportExposure`），Feed / ObjectIntersections 合并时命中即**过滤**（`intersection_feed_filtered_total{reason="seen"}`），不再「降权保留」；用户对该交集发生点击、证据展开或正向转化（`follow` / `join_circle` / `add_contact` / `like` / `comment` / `share` / `wishlist_add` 携带 `intersectionId`）即**清零**（`ClearExposure`，ZREM），窗口（`policy.yaml` `intersection.cooldownDays`，默认 14 天）到期自然恢复。负反馈冷却 `rec:ineg` 继续以 subject（`actionTargetId`）为键，语义不变。
- 决策（过期重算）：`computedAt/expiresAt` 由 Recommendation 生产者写入；Recommendation 读面 rebuild-on-read 的物化收据按 (`source_event_id`, evidence digest) create-once，evidence 不变时快照不重写。读面在当前快照存在任一 `expiresAt <= now` 的 reason 时，把最早过期的 `expiresAt` 拼进 `source_event_id`（`…:{digest}:refresh:{expiresAt}`），使 projector 产生新收据并真正重物化；同一份过期快照在重物化前得到同一标记（幂等），重物化后回到纯 evidence digest 路径。Content 的 `isFresh` 过滤只是安全网并计 `stale`，不再声称「触发重算」。
- 决策（cohort）：`cohort` 定义为**交集策略身份**——产出该 reason 的 `intersection_kind_registry.yaml` 在 ContractGraph 登记的源文件 sha256（`sha256:<hex>`），由 `codegen_rec_intersection` 生成为 Go `IntersectionPolicyDigest` / Python `INTERSECTION_POLICY_DIGEST`，Content 水合出口统一写入 `IntersectionReason.cohort`（生产者只保留空槽位）。端在曝光 / 点击 / 展开 / 转化 / 负反馈事件中以 `intersectionCohort` 原样回传，不展示；灰度期间不同策略版本即不同 cohort，它不是用户分桶，也不替代 Feed 的 `policyDigest`。
- 理由：REQ-004 说的是「不再重复推荐」，降权保留只是把重复曝光挪到窗尾，无法证明；以 `intersectionId` 记账让曝光、点击、清零三步在同一身份上闭合，且与端上报的归因键零翻译。过期重算放在 Recommendation 读面而不是 Content，是因为只有生产者能重算事实与 `expiresAt`，Content 触发跨服务写会制造第二个物化权威。cohort 用注册表摘要而不是新建实验分桶服务，是因为交集体验的灰度单位就是注册表版本（kind / 行动阶梯 / 模板 / 阈值），且该摘要已是 ContractGraph 的既有身份，不需要第二套登记。
- 被否决方案：曝光冷却继续按 `actionTargetId` 记账（与行为事件缺 targetId 的归因键对不上，需要端多传一份对象身份）；由 Content 在发现 stale 时调用 Recommendation 重算 RPC（读路径引入同步跨服务写与风暴风险，违反读路径零同步计算）；把 `cohort` 做成按用户哈希的实验分桶（仓内无该服务，且与 `policyDigest` 语义重叠）。
- 失败与恢复：Redis 不可用时 `ReportExposure` / `ClearExposure` 走 `degradeRedis`（`intersection_redis_degraded_total{op=exposure_write|exposure_clear}`），不阻断行为 ingest 与 Feed，最坏是该次请求缺少冷却抑制；重物化失败保留旧快照并由下一次读取重试（收据 create-once 保证不会半写）；`cohort` 缺失只影响漏斗分桶，不影响展示与行动。
- 测试 seam：Go `intersection_service__local_contract_test.go`（`sit-004.t1`：窗口内过滤、清零恢复、到期恢复）与 `behavior_intersection_feedback__local_contract_test.go`（`sit-004.t1/.t3`：impression 写、click/expand/follow 清零、cohort 透传）；Python `test_intersection_reader__expiry_refresh__local_contract_test.py`（`sit-004.t2`：过期收据标记幂等）；Go `intersection_cohort__local_contract_test.go` 与 Dart `intersection_attribution__local_contract_test.dart`（`sit-004.t3`：生成表摘要 = 注册表摘要、水合盖章、端全链回传）。
- 关联要求：`REQ-004`
- 关联验收：`SIT-004`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 冷却窗口与保鲜期交叉：以 `policy.yaml` 单一真相源配置，避免双处硬编码。
- 隐私门槛：`commonContact` 必须先过双向可见性才产出。
- 性能与容量弹性（冷热三档，云侧部分后置）
