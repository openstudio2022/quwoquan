# L2 Business Capability：运行时推荐 (`runtime-recommendation`)

> 所属领域：[`runtime`](../spec.md)
>
> 设计引用：[本层 design.md](./design.md)

## 1. 能力目标

提供推荐 HotPath、SessionCache、Engine、Scorer 与 Rerank 的统一运行时，使候选排序、降级和观测使用同一会话与策略边界。

## 2. 范围与非目标

### In Scope

- Redis HotPath session 状态、negative/exposed/tag weights/realtime interest。
- 7 阶段 Engine 管线、多源召回、预排、过滤、特征组装、打分、重排。
- RuleScorer、RemoteModelScorer、CascadeScorer fallback。
- MMR/UCB1 探索、多样性、冷启动保底、SessionCache 与 BufferedHotPath。

### Out of Scope

- 首页 feed IA、频道布局、页面 route/surface；归 discovery-content/feed-orchestration-recommendation。
- 深度排序模型平台轨与双塔 ANN 在线服务。

## 3. Journey / Scenario 贡献

- [`JNY-001 / SCN-004`](../../spec.md#scn-004)
  - 本能力接收：该 Scenario 进入本能力边界的已授权主体与 canonical 输入。
  - 本能力处理：推荐运行时基础能力验收，覆盖 HotPath、SessionCache、Engine、Scorer、Rerank、降级与可观测。
  - 本能力输出：直属 Story 组合产生的可观察结果与明确失败终态。
  - 失败时终态：保留已确认事实，并返回可恢复的 canonical failure。

## 4. Story



- [`dual-channel-recommendation-engine`](./dual-channel-recommendation-engine/spec.md)：**SessionReader** 接口：统一读路径，HotPath / SessionCache 均实现。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 runtime recommendation 引擎能力 SIT

- HotPath 处理 impression/engagement/dislike 后，SessionState 中 exposed/negative/tagWeights 与实时兴趣可被读取。
- Engine 7 阶段管线必须区分召回源 skipped/not-applicable、succeeded-empty 与 failed；部分源失败且仍有候选可降级下发，全部失败或部分失败后零候选必须产生 typed failure。
- scorer 错误或对非空输入返回空输出不得记为成功；CascadeScorer 只有在 fallback scorer 产生有效输出时才可标记 degraded success。
- discovery/recommend 首刷必须非空或返回 typed failure；following 的健康零结果与有效 continuation 自然结束是唯一允许的推荐成功空态。
- RuleScorer 消费用户特征、交集信号、搜索意图、负反馈惩罚、UCB1 探索和 MMR 多样性。
- `SessionCache`、`BufferedHotPath` 与 Redis key hash-tag 必须在 pipeline 和 parallel 路径保持同一会话状态语义。

<a id="req-002"></a>
### REQ-002 CascadeScorer 保证 ML 不可用时降级到 RuleScorer

- CascadeScorer 保证 ML 不可用时降级到 RuleScorer。
- Primary scorer 的 `scorer_unavailable` / `scorer_empty_output` 必须保留为本次 degraded terminal 的低基数 failure stage；RuleScorer fallback 同样错误或空输出时返回 typed failure。

<a id="req-003"></a>
### REQ-003 关系与互动只由已确认持久事实进入唯一在线画像

- 人物关注以及点赞/评论 Reaction 对应的偏好贡献仅由 User 人物关系、Content Reaction 已提交的 durable fact 派生；UI 点击、乐观状态、超时后当前值相同或未确认意图都不能宣告第二次业务成功。
- Recommendation FeatureProfile 是唯一在线长期特征 owner；User 资料只展示本域允许的资料与统计，Content 行为通道可以保留源事实的历史与归因，但不得与直接事实消费重复增加当前偏好。被替换路径须按真实消费者迁移退役，不向旧画像或无人读取的 Feed 投影增加第二在线写轨。
- 同一事实在画像、统计、训练转换各自最多生效一次，保留原业务事实身份及已验证主体维度；device 不冒充公开 Persona 兴趣，多个 Persona 不因属于同一账号并账。
- 取赞撤销既有同一关系的当前贡献，包括按原贡献口径衰减后的剩余部分，不是固定减一次，也不是 dislike 或新的负反馈。合法历史训练事实按所属合同保留，不将当前 coLiked 与行为历史混为一谈。
- 曝光、点击、停留等行为仍走各自合法行为事实；没有合法曝光归因不能伪造推荐训练样本，不能为消除重复而删除全部行为历史。

<a id="req-004"></a>
### REQ-004 候选热度与评分使用可核验、独立版本的来源

- 候选热度只消费 Content 统计 owner 已提交的版本化统计事实，不因互动修改正文编辑时间、伪造内容更新或让生命周期快照覆盖更新统计。
- 关系聚合、Reaction、统计、内容生命周期与推荐本地画像各有独立版本来源；仅在同一来源身份及适用代际内比较，不跨 owner 比大小，也不以资料更新时间代替互动顺序。
- no-op 可推进聚合版本但不产生业务变化事件；消费方按实际业务事件的完整后态接受合法跳号，运输检查点只追踪实际已发布事件，不等待每个聚合版本均有事件。
- 验收必须读回候选实际热度和本次 scorer 的实际输入；consumer 收到消息、统计投影有值或 UI 数字变化均不能单独证明评分已经消费。
- 在 owning load profile 声明的正常负载下，已确认事实到新窗口可用推荐特征的端到端 P99 新鲜度目标不超过 10 秒；用同一事实的端到端实测分布与超预算比例证明，缺峰值或运行证据时不宣称已达标。窗口内已冻结输入不因该目标被改写。

<a id="req-005"></a>
### REQ-005 following 因果读取与普通推荐稳定窗口分开裁决

- 普通推荐中查看者关注作者是请求期批量组合的软特征，不写入跨查看者共享候选；following 频道按其所属关注类型的当前已确认资格硬过滤，人物关系不替代 SubjectFollow。
- 点赞、取赞及新增关注仅影响明确刷新或新窗口；已创建窗口保持原有排序与固定期限，续页不重新评分、不偷换窗口或拼入另一排序。
- following 取关与 block、可见性收缩在交付前按当前权威资格重新过滤，只移除不重排；无法安全续接时返回 canonical 窗口失效并明确新首刷。不得把不可变排序理解为权限快照永久有效。
- following 新窗口可请求追齐受信 User 确认结果引用的最近实际关系事件；no-op 只推进命令仲裁版本时仍引用当前状态的最近有效事件。首次关系空态没有事件时，由 User 权威证明终结该关系的因果要求，不等待不存在的事件或伪造事件；单 Pair 空态不能证明整个关注流为空，健康空流仍须验证完整查询范围。
- 因果要求必须可验证来源、主体与目标，并受数量、字节及总等待预算约束；未追齐则明确未就绪，任意未来版本或不可验证引用不得让请求无限等待或伪装“没有关注”。

## 6. 契约与依赖

- 上游能力：[`runtime`](../spec.md) 声明的领域入口；业务事实分别由 [`follow-relationship`](../../user-identity-profile-relationship/persona-follow-graph/follow-relationship/spec.md#req-008) 与 [`reaction-state-counter`](../../discovery-content/publish-comment-reaction/reaction-state-counter/spec.md#req-006) 拥有。
- 唯一在线消费对象：`quwoquan_service/services/recommendation-service/contracts/recommendation/recommendation_feature_profile_view/`、`recommendation_candidate_index_view/` 与 `ranked_recommendation_window/`（后两者同属上述 recommendation 契约目录）。
- User 来源：`quwoquan_service/services/user-service/contracts/relationship/persona_relationship/`；Content 来源：`quwoquan_service/services/content-service/contracts/content/content_reaction/`、`content_behavior_fact/` 与 `post/`（后两者同属上述 content 契约目录）。源事件和消费反向边只在各 owner 的 `events.yaml` / `object.yaml` 定义，不在本规格复制 payload、字段或错误码。
- 事件因果引用、独立统计版本、来源水位与恢复形态须先在上述 owner contract 冻结并生成；本规格不声称现有 wire 已具备，未闭合由 [`OPEN-002`](#open-002) 阻断。
- 下游能力：本目录直接 Story 及其公开结果；Feed 稳定交付由 [`feed-orchestration-recommendation`](../../discovery-content/feed-orchestration-recommendation/spec.md#req-004) 承接，当前交集贡献由 [`intersection-algorithm-closure`](../../object-homepage-network/intersection-unified-experience/intersection-algorithm-closure/spec.md#req-006) 承接。
- 一致性要求：遵循 [DEC-002](./design.md#dec-002)、[DEC-003](./design.md#dec-003) 与 [DEC-004](./design.md#dec-004)；跨域异步收敛不扩大成全局事务。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 runtime recommendation 引擎能力 SIT

- GIVEN 执行“runtime recommendation 引擎能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“runtime recommendation 引擎能力”对应动作。
- THEN HotPath 处理 impression/engagement/dislike 后，SessionState 中 exposed/negative/tagWeights 与实时兴趣可被读取。
- THEN Engine 能区分召回 skipped、健康空、部分失败和全部失败；部分失败有候选时降级下发，失败后零候选不伪装成功空态。
- THEN scorer 非空输入的错误/空输出只在有效 RuleScorer fallback 后成为 degraded success，否则返回 typed failure。
- THEN discovery/recommend 首刷非空或失败；following 健康空与有效 continuation end 可返回成功空数组。
- THEN RuleScorer 消费用户特征、交集信号、搜索意图、负反馈惩罚、UCB1 探索和 MMR 多样性。
- THEN pipeline 与 parallel 路径读取相同会话状态，Redis key 落在预期 hash slot，重放不重复更新。

<a id="sit-002"></a>
### SIT-002 confirmed 事实单轨更新且取赞只撤当前贡献

- GIVEN 同一有效主体的关注与点赞已由 User/Content 提交，UI 归因与服务端历史转换也到达，存在重复、乱序与衰减后的当前偏好。
- WHEN 真实 consumer 应用这些事实，再应用取关或取赞并重放旧事件。
- THEN FeatureProfile、统计和训练转换分别只应用同一业务事实一次；当前贡献按完整后态收敛，取赞移除原剩余贡献且不变成 dislike，合法行为历史仍按合同保留。
- AND device、匿名 Persona、已登录 Persona 不串主体；缺合法曝光只能缺归因，不伪造曝光、业务成功或训练样本。
- AND 手动 drain 或 UI 乐观态不能替代真实自动 worker、持久幂等收据与读回。

<a id="sit-003"></a>
### SIT-003 独立统计事实实际进入新窗口 scorer

- GIVEN 内容生命周期、统计和画像分别有有效来源，关系或 Reaction 存在 no-op 导致的合法业务版本跳号。
- WHEN 实际统计提交并经 consumer 更新候选，再创建新推荐窗口，期间插入重复或迟到生命周期事件。
- THEN 候选热度与真实 scorer 输入均为有效统计版本对应值；合法取赞下降被接受，旧生命周期不覆盖新统计，不修改正文编辑时间。
- AND consumer 不等待不存在的 no-op 事件，各来源 checkpoint 独立；在声明负载下按同一事实测量 [REQ-004](#req-004) 的完整新鲜度，不能用消息到达或分项分位数代替。
- AND 负载未冻结或证据缺席时不得判新鲜度达标。

<a id="sit-004"></a>
### SIT-004 following 因果追齐、硬过滤与旧窗不重排

- GIVEN 同主体持有可信关系确认结果且普通/关注窗口已创建，包含新关注、取关、无事件 no-op 与首次权威空态。
- WHEN 新首刷携带有界因果要求，旧窗口同时续页，并发生点赞、取赞、屏蔽或可见性收缩。
- THEN 新窗口只等待真实事件，追齐前明确未就绪；no-op 不无限等待，无事件关系空态只终结对应因果要求，完整查询范围经验证为空才返回健康空流，不接受任意未来引用。
- AND 普通流关注仅作软特征、following 只交付当前合格对象；旧窗口保序，只安全移除或显式失效，不偷换 cursor 排序、不重新赋予权限。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 runtime recommendation 引擎能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：HotPath 处理 impression/engagement/dislike 后，SessionState 中 exposed/negative/tagWeights 与实时兴趣可被读取。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 confirmed 事实到画像、评分与窗口的合同及运行证据未闭合

- 类型：`capability_gap`
- 优先级：`P0`
- 准出影响：`block`
- 影响或价值：[REQ-003](./spec.md#req-003)、[REQ-004](./spec.md#req-004)、[REQ-005](./spec.md#req-005) 新冻结了跨 owner 消费边界，但尚无当前候选的独立统计事实、原业务事实归因去重、无事件 no-op 因果引用与真实自动 consumer 全链证据。本层承接跨对象组合缺口；不以已有 HotPath 或 FeatureProfile 局部测试冒充下游完成。
- 完成判定：[SIT-002](./spec.md#sit-002)、[SIT-003](./spec.md#sit-003)、[SIT-004](./spec.md#sit-004) 均由同候选真实测试直接绑定完整 `spec_ref`：`local_contract` 证明归因/贡献 oracle、版本交错及时序与预算；`api_integration` 必须证明 production 自动 worker、持久幂等收据、实际候选、评分输入、真实 User 确认、窗口续接及权限裁决与源提交读回，手动 drain 或 UI 乐观态不能替代；端侧行为由 Feed 的集成验收补齐。各 owner 完成事件/来源版本/因果读面 authoring 与生成，真实 worker、候选和 scorer 输入读回、窗口安全续接及声明负载新鲜度全部通过。仅源码或合同通过不能关闭。负载未冻结或证据缺席时不得判达标。
- 依赖：User 人物关系回执和完整后态、Content Reaction 统计事实与行为历史归因、Recommendation 消费反向边/独立版本及窗口读协议。wire 未定义时保持对应实现准入阻断，不在本 spec 补第二份字段或错误语义。
