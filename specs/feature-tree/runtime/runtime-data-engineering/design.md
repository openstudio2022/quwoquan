# L2 Design：运行时数据工程 (`runtime-data-engineering`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“`runtime-data-engineering` 是运行时数据工程能力，负责把离线/半自动数据产物整理为 App 与云服务可消费的稳定契约输入”需要 `article-commercial-scale-closure`、`geo-content-trinity`、`image-commercial-scale-closure`、`video-commercial-scale-closure` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：`runtime-data-engineering` 是运行时数据工程能力，负责把离线/半自动数据产物整理为 App 与云服务可消费的稳定契约输入。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`article-commercial-scale-closure`](./article-commercial-scale-closure/spec.md)：缺来源或权利的对象保持 typed GATE_BLOCK，不能进入 canonical publish。
- [`geo-content-trinity`](./geo-content-trinity/spec.md)：图片来源、下载字节、授权与发布引用均可回放。
- [`image-commercial-scale-closure`](./image-commercial-scale-closure/spec.md)：缺任一 required rights 字段的资产不能进入 release。
- [`video-commercial-scale-closure`](./video-commercial-scale-closure/spec.md)：不满足 admission 的候选以 typed issue 阻断。

## 3. 端云与数据流

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 数据任务先冻结来源事实并经 immutable release 激活
- 决策：数据任务先冻结 reviewed commit、source digest、canonical entity catalog、来源、权利与目标事实，并让各 carrier 以独立 execution 分别调度和形成逐项终态，再经 canonical publish、immutable release 和环境 importer 激活；实际运行可串行或重叠，不要求固定四路并发、四个同时 workspace 或先通过 capacity soak。
- 理由：`runtime-data-engineering` 是运行时数据工程能力，负责把离线/半自动数据产物整理为 App 与云服务可消费的稳定契约输入。
- 被否决方案：环境内容 seed manifest、T3/UAT 自建内容对象、把评论/圈子/消息混入 Data release、post 依赖 homepage execution、把四载体塞入单一 execution，或调用方/页面复制本层状态并绕过 release/importer。
- 约束与影响：release 聚合只以冻结的 source/entity facts 和实际 carrier task 的逐项终态为输入；soak、workspace smoke、effective concurrency 与 resource samples 只作诊断。canonical publish 保持对象事务单写者，release exact closure 用 attestation `payloadSha256` 串联四环境 import/readiness，并在 cleanup 时以进程锁及 acceptance evidence 保留长期验收引用。
- 关联要求：`REQ-001`
- 影响 Story：[`article-commercial-scale-closure`](./article-commercial-scale-closure/spec.md)、[`geo-content-trinity`](./geo-content-trinity/spec.md)、[`image-commercial-scale-closure`](./image-commercial-scale-closure/spec.md)、[`video-commercial-scale-closure`](./video-commercial-scale-closure/spec.md)
- 关联验收：`SIT-001`

<a id="dec-002"></a>
### DEC-002 池记录只保存准入结论，环境只消费不可变 Manifest
- 决策：Data 作者记录只保存稳定身份、版本、过程/质量结论、证据引用与状态。
- 数据边界：Data 内容记录再增加 `usageScope` 与 `variantPurpose`。逐素材许可证、来源、署名和证明保留在 evidence receipt，不复制进推荐候选、搜索文档或 App DTO。
- 发布边界：Research/Commercial 共用 acquisition、semantic、review 与 canonical pool。环境 build 必须显式选择 release class，在同一 frozen pool snapshot 上让 Research 接受 `research|commercial`、让 Commercial 只接受逐对象商用授权闭合子集，并生成各自唯一 `releaseId + payload digest` Manifest。
- 导入边界：Content 正式导入命令原子写 Post 与 durable outbox。
- 理由：从内容生产者看只需回答“是否结束、质量是否合格、允许在哪里用”；从环境使用者看只需回答“这个 release 精确包含什么且是否验证通过”，不需要 PoolDelta、PoolSnapshot、SampleBundle 或 EnvironmentSelection 等并列业务身份。
- 被否决方案：按环境或 Research/Commercial 维护独立 acquisition/semantic/review/pool，按环境维护独立内容副本、把头像授权范围并入作者准入、为头像生成 commercial variant、直接 seed 推荐/搜索、把 Manifest 当首页固定列表、由 Data 修改真实用户 Persona 或 UGC。
- 约束与影响：Research 原版与 commercial variant 共享 `contentId` 并追加版本；Research release 优先最新 original，Commercial release 只取最新 commercial。Recommendation/Search 通过同一 Post lifecycle 消费 active Data release 与公开 UGC，Data release 切换不修改 UGC。
- 关联要求：`REQ-001`、`REQ-002`
- 影响 Story：文章、图片与视频三个 carrier Story 的 terminal replay/adopt。
- 关联验收：`SIT-001`

<a id="dec-003"></a>
### DEC-003 canonical reset 以 empty release 作为环境栅栏
- 决策：canonical publish tree 与 inventory sidecar 是同一个 reset 一致性边界，但不是新的内容聚合或长期内容库。唯一写入口为现有 `release reset-canonical` command；它先消费所有受影响环境的 empty immutable release lifecycle/readback，再在全局 release operation lock 内获取 canonical publish lock 并原子清空两者。读面分别使用 release lifecycle/readback 与 `release pool-inspect`，不经通用 Repository 或数据库旁路。
- 理由：先把消费者收敛到可验证的零对象 release，才能确保清空供应侧 canonical 状态时没有环境继续引用被作废对象；双锁顺序使 reset 与 pool delivery/release build 不会交错形成部分成功。
- 被否决方案：手工删除 publish 或 inventory、以状态文件代替实际 lease/flock、在环境仍读旧 release 时清空、改写旧 execution receipt，以及 reset 后重新运行已闭合的 acquisition、author 或 review。
- 失败恢复：任一环境未进入 empty baseline、锁冲突或 inventory 漂移均在写前 fail closed；写后恢复只消费 immutable release 与 terminal execution evidence，通过同 ID resume 或新 `retryOf` sequence replay/adopt。环境回滚与 canonical 重建均不依赖重新构建旧 release。
- 可测试观察面：`release reset-canonical` 输出、publish/inventory digest、锁冲突结果、empty baseline lifecycle/readback、terminal execution 的 `retryOf` 与 pool inspection。local_contract 观察原子性和锁，api_integration 观察 baseline lifecycle，真实 release 消费观察重建 closure。
- 关联要求：`REQ-004`
- 影响 Story：[`article-commercial-scale-closure`](./article-commercial-scale-closure/spec.md)、[`image-commercial-scale-closure`](./image-commercial-scale-closure/spec.md)、[`video-commercial-scale-closure`](./video-commercial-scale-closure/spec.md)
- 关联验收：`SIT-002`

<a id="dec-004"></a>
### DEC-004 image generator 由 Post manifest schema 单轨拥有
- 决策：Post manifest materializer 是 `generator` 的唯一写 owner，并只写 schema 已声明的 `agent`。image evidence pack 继续作为 execution/source/review 的内部 evidence，不成为第二个 generator 值；pool validator 与 release selector 只读通过 canonical schema 的 manifest。
- 理由：`generator` 表达交付 copy 的 authoring 身份，而 evidence pack 表达素材与审核证据。把两者塞进同一 wire 字段会让 schema、materializer 与 release reader 对对象身份产生分叉。
- 被否决方案：schema 增加 `image_evidence_pack`、reader 双读、warn-only 放行、按 carrier 推导默认值，或原地修补旧 manifest/receipt。
- 失败恢复：非 canonical generator 使单对象 typed excluded，不阻断同池其它对象；仅允许基于原 terminal evidence 的 replay/adopt 创建新 manifest，不重跑已闭合上游。
- 可测试观察面：Post manifest schema validation、image materialize 输出、provenance/pool record 与 release selection；对象级 local_contract 证明所有交付 manifest 为 `agent` 且不存在 compatibility fallback。
- 关联要求：[`image-commercial-scale-closure/REQ-004`](./image-commercial-scale-closure/spec.md#req-004)
- 影响 Story：[`image-commercial-scale-closure`](./image-commercial-scale-closure/spec.md)
- 关联验收：[`image-commercial-scale-closure/GWT-004`](./image-commercial-scale-closure/spec.md#gwt-004)

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突、锁冲突、环境 baseline 未收敛、inventory 漂移或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：写前失败保持 canonical 不变；reset 后只按 terminal evidence replay/adopt，环境恢复只 replay 已核验 immutable release。调用方不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 成本影响保持同量级：reset 只处理当前 publish/inventory 元数据，replay 成本与被选 terminal execution 数量线性相关，不引入长期内容副本。
- reset 写阶段在取得锁后 60 秒内完成或 fail closed；环境从 empty baseline 恢复原 release 的目标为 5 分钟内完成。超时只产生失败 receipt，不放宽锁或 closure。
- SLI 直接读取 create-once reset receipt、empty/replay lifecycle、pool inspection 与 execution receipt 的完成状态和耗时；这些回执也是告警与审计来源，不新增第二份状态台账。
- rollout 先在 Alpha 以最小 rollout stage 执行；回滚使用已核验 empty/original immutable release 与 same-digest replay，不重新构建 release。Beta/Gamma/Prod 与长期 `content_library + holdings` 保持现有 OPEN。
