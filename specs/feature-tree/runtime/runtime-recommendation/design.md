# L2 Design：运行时推荐 (`runtime-recommendation`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“推荐运行时基础能力验收，覆盖 HotPath、SessionCache、Engine、Scorer、Rerank、降级与可观测”需要 `dual-channel-recommendation-engine` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：推荐运行时基础能力验收，覆盖 HotPath、SessionCache、Engine、Scorer、Rerank、降级与可观测。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`dual-channel-recommendation-engine`](./dual-channel-recommendation-engine/spec.md)：**SessionReader** 接口：统一读路径，HotPath / SessionCache 均实现。

## 3. 端云与数据流

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 推荐特征读取、策略解析和排序执行使用显式 Port
- 决策：推荐特征读取、策略解析和排序执行使用显式 Port。
- 理由：推荐运行时基础能力验收，覆盖 HotPath、SessionCache、Engine、Scorer、Rerank、降级与可观测。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`dual-channel-recommendation-engine`](./dual-channel-recommendation-engine/spec.md)
- 关联验收：`SIT-001`

<a id="dec-002"></a>
### DEC-002 业务确认事实、行为历史与当前推荐贡献分层单轨

- 决策：User 人物关系与 Content Reaction 是关注/互动事实唯一 producer；Recommendation FeatureProfile 通过所属对象声明的公开 durable event 消费边拥有在线长期画像。Content 行为历史可保存对原事实的归因与训练转换，但同一业务事实进入当前贡献只应用一次；UI 行为不具有确认命令权限。
- 理由：直接事实与行为转换同时累加会双计，删除历史则破坏合法训练归因；当前贡献必须可撤销，历史事实不因取赞改写成从未发生。
- 被否决方案：App 再宣告关注/点赞成功、继续写旧画像、跨服务私有 store join、取赞固定减常数或转为 dislike，以及移除全部行为历史以规避双计。
- 约束与影响：消费保留来源业务身份、主体维度与来源版本；当前贡献以成员新后态替换旧后态并撤销原剩余衰减贡献。各消费结果与其幂等收据原子落地，不把多个 consumer 合成一份全局 checkpoint；真实消费路径迁移后单次切换唯一 reader，离线影子仅对账。
- 失败、恢复与回滚：重复/旧事实不重复贡献，同来源同版本异内容保留 typed 冲突且不推进已应用水位；按 owner durable 来源与安全水位重放/重建，来源不可得时保持未就绪。永久关闭/删除的抑制不可逆，可恢复权限只能由 owning 新授权事实重新裁决；回滚不能恢复已撤贡献或启用第二写轨。
- 测量与测试 seam：命名观测区分实际提交到画像可用延迟、重复拒绝、撤销偏差、未归因样本与消费者积压；阈值取 [REQ-004](./spec.md#req-004) 及各 owner SLO。local_contract 用固定衰减时钟与乱序事实验证贡献 oracle；api_integration 用真实持久收据和自动 worker 证明同事实双到达只生效一次、取赞撤当前贡献而历史仍在。
- 关联要求与验收：[REQ-003](./spec.md#req-003)、[SIT-002](./spec.md#sit-002)；影响 Story：[`dual-channel-recommendation-engine`](./dual-channel-recommendation-engine/spec.md) 及 [`intersection-algorithm-closure`](../../object-homepage-network/intersection-unified-experience/intersection-algorithm-closure/spec.md)。运行证据缺口归本层 [OPEN-002](./spec.md#open-002)。

<a id="dec-003"></a>
### DEC-003 候选统计独立更新，冻结真实 scorer 输入与来源

- 决策：CandidateIndex 消费 Content 统计 owner 的已提交事实；统计版本与内容生命周期版本各自比较。FeatureProfile 本地 revision、关系/Reaction 版本、统计重建代际及每来源运输水位互不冒充；scorer 使用实际组装值并由 RankedRecommendationWindow 冻结输入身份。
- 理由：互动不是内容编辑；单一时间戳或跨域最大序号无法证明统计、权限和兴趣来自同一有效来源，更不能证明 scorer 消费了它们。
- 被否决方案：用 PostUpdated 驱动赞数、以 User 资料更新时间作为 reaction 版本、只检查消息收到就宣称热度生效、续页重读 live score，以及向所有共享候选写查看者关注布尔。
- 约束与影响：来源域、独立版本、统计事实与消费边只在 User/Content/Recommendation canonical contracts 定义；完整业务后态允许 no-op 造成的聚合版本跳号，连续运输检查点不以聚合版本补洞。内容生命周期不得覆盖较新统计，统计也不得复活被生命周期抑制的候选。
- 失败、恢复与回滚：统计源缺失或未就绪不能补零；按已声明读合同返回不可用或有来源的旧值。消费者从自己的安全 checkpoint 重放，重建先固定来源再追增量后切换单一代际；回滚保全已确认源事实与不可逆撤权，不恢复旧画像写入。
- 测量与测试 seam：追踪同一事实从统计提交、候选更新到实际 scorer 输入的端到端延迟与来源错配；告警以 [REQ-004](./spec.md#req-004) 的新鲜度及 owner 阈值裁定。local_contract 覆盖旧生命周期/新统计交错与合法数字下降；api_integration 读回候选和真实评分输入，证明业务事件版本跳号不阻塞、同版本冲突不被吞掉。
- 关联要求与验收：[REQ-004](./spec.md#req-004)、[SIT-003](./spec.md#sit-003)；影响 Story：[`dual-channel-recommendation-engine`](./dual-channel-recommendation-engine/spec.md)、[`personalized-ranking`](../../discovery-content/feed-orchestration-recommendation/personalized-ranking/spec.md)。合同及运行证据缺口归 [OPEN-002](./spec.md#open-002)。

<a id="dec-004"></a>
### DEC-004 新窗口有界追实际事实，旧窗口排序不变且当前权限优先

- 决策：普通流将查看者关注作者作为请求期批量软特征，following 按所属关注 owner 的当前资格硬过滤；窗口排序与固定期限遵守 [Feed DEC-003](../../discovery-content/feed-orchestration-recommendation/design.md#dec-003)。交付时重新裁决当前权限和 following 成员资格，只移除条目；不能安全续接时显式使窗口失效并开始新窗口。
- 决策：新 following 请求只接受受信 User 确认结果中的实际已发布关系事实引用，按来源及 consumer checkpoint 有界等待。no-op 的命令版本不是事件水位，必须回指最近有效业务事件；首次空关系由 authority 证明并终结对应关系因果要求，不生成填洞事件，也不据此推断全关注查询为空。因果引用数量、字节和等待 deadline 由 owning operation/config 限定。
- 理由：软特征变化不应造成重复翻页，权限又不能由旧窗口冻结；等待不存在的 no-op 事件会让已成功命令永久表现为推荐未就绪。
- 被否决方案：点赞后重排每页、客户端任选未来版本、未追齐就返回假空关注流、为每个 no-op 增发业务事件、同步向千万粉丝 fanout，以及为了分页稳定继续下发失权内容。
- 约束与影响：User 回执与 Recommendation 读面的因果协议须先由各 owner authoring；本 DEC 不复制 token、错误或事件字段。千级/万级作者集合读取使用独立批次、总扫描、内存与截止预算，不随业务关注上限无限扩大；不任意截断作者集合宣称完整。
- 失败、恢复与回滚：不可验证引用拒绝，投影未追齐按 canonical 未就绪恢复；安全依赖不可用 fail-closed，禁止用旧缓存授权。窗口失效后只有显式新首刷可重排；回滚只切换经源事实追齐的唯一实现，不复活失权候选或延长旧窗寿命。
- 测量与测试 seam：分别记录因果等待/超时、健康空态、当前资格移除、窗口失效及实际扫描成本；告警与负载阈值取 Feed、User owning SLO。local_contract 固定无事件 no-op/初始空态/恶意未来引用与稳定 ordinal；api_integration 经 User receipt、真实 consumer 和权限 reader 证明追齐、过滤及 cursor 不换排序；真机交付由 Feed SIT 承接，不能以引擎测试代替。
- 关联要求与验收：[REQ-005](./spec.md#req-005)、[SIT-004](./spec.md#sit-004)；影响 Story：[`dual-channel-recommendation-engine`](./dual-channel-recommendation-engine/spec.md)、[`unified-items-cursor`](../../discovery-content/feed-orchestration-recommendation/unified-items-cursor/spec.md)。无运行证据时保留 [OPEN-002](./spec.md#open-002)。

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 曝光记忆容量：`ExposureMemory` 按 `user+day` 分桶 + cardinality budget，海量阶段切 rolling bloom/CMS/分桶 ZSET，过滤开销不随会话曝光量线性放大。
