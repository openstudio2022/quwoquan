# 新一轮规划输入 —— 全国景点主页放量遗留与依赖梳理

- 日期：2026-07-09（WP6 收口后）
- 性质：派生分析产物，供下一轮 `/prd` 或计划会话直接消费。**未登记也不登记** `docs/outstanding_risks_backlog.md`（用户明确决策：作为规划输入而非风险 backlog）。
- 来源：WP6 报告 §4.4 backlog 草案 6 项 + 全部已知缺口，含本轮 prod 实导（`prod_wp6_pilot6_20260709`）的新证据。
- 每项给出：事项 / 根因 / 影响 / 建议动作 / 预估工作量 / 建议验收意图与测试证据层。

## P0 — 放量吞吐的硬前置

### 1. entity-service homepage_state 导入停服窗口

- **事项**：每次主页数据发布必须「停 entity-service → homepage-import → 启容器」（R-HSE02），否则服务内存态覆盖导入器写入（gamma 首轮实际丢过数据）。
- **根因**：entity-service 仅在启动时把 `homepage_state` 单文档装入内存，无 reload 机制；importer 直写 DB 与服务内存态互为双写方。
- **影响**：放量期每次增量导入 = 一次 prod 服务中断（本轮 prod 实导停服窗口约 2 分钟，含导入 6 秒 + 容器起停）；按省批量发布时中断频次不可接受，且停服序列靠人肉纪律保证，一旦忘停即静默丢数据。
- **本轮新证据**：prod 实导按停服序列成功，`homepage_state` 66→72 无损；`release_rollout.json` 已把 R-HSE02 记为 knownGaps。
- **建议动作**：entity-service 增加 reload 端点（或订阅 data_release_state 变更自动重载），importer 完成后触发 reload；淘汰停服序列。metadata-first：先在 `contracts/metadata` 定义 reload operation 与错误码。
- **预估工作量**：2-3 人日（服务改造 + 合同测试 + 导入链路对接 + runbook 更新）。
- **验收意图/证据层**：contract（reload 端点契约、并发写一致性）→ `local_contract`；SIT（导入→reload→introduction 立即可见，不停服）→ `api_integration`。

### 2. 日产 10 万的云端并发架构依赖

- **事项**：WP5 实测 1-1.5 主页/h/worker，距日产 10 万有 50-100x 缺口；需 ~200 机等效弹性并发（WP5 §七推演）。
- **根因**：单机拓扑全链串行（download/author/审核/发布同 worker），author 纯生成仅 8-10 分钟/主页但被 IO 阶段稀释。
- **影响**：不解决则全国放量以年计；解决后 P1/P2 试点收口可压缩到 4-5 工作日/省。
- **建议动作**：① download 与 author 分离批处理（download 离线预跑，生成环节 2-3x 吞吐）；② 云端弹性 worker 池 + frozen plan 分发协议；③ 与 #1 联动实现导入免停服；④ token 预算与成本护栏（≈2626 tokens/主页 × 10 万/日）。
- **预估工作量**：架构设计 1 周 + 分阶段实施（download 分离 3-5 人日先行，worker 池另列专项）。
- **验收意图/证据层**：SIT（分离流水线端到端吞吐基准）→ `api_integration`；GWT（frozen plan 分发/回收/断点续跑规则）→ `local_contract`。

### 3. 多代理共仓治理冲突

- **事项**：Codex 治理代理反复 SIGTERM 长驻跑批进程（run-recipe/scaled-e2e/keeper）、清理 `.qwq_output`（舟山 frozen plan 三次被清）、改名家目录看护脚本。
- **根因**：治理代理的「长驻进程 = 违规」「`.qwq_output` = 可清理」判定与跑批产线的运行模型冲突；两个代理无共享的进程/产物白名单协议。
- **影响**：WP5 readiness 聚合与批次尾部被阻断 ≥5 波；frozen plan/workflow state 等 runtime 真相被清导致重建成本与证据丢失。放量期长驻 worker 池是常态，冲突会直接摧毁产线。
- **建议动作**：与用户共同定义跑批进程与产物保护协议（进程标记/lease 文件/保护目录清单），治理代理按协议豁免；短期先把 frozen plan 等真相源落到保护路径。
- **预估工作量**：协议设计 0.5 人日 + 双方代理接入各 1 人日；需用户裁决治理代理的豁免边界。
- **验收意图/证据层**：GWT（保护协议规则：标记进程不杀、保护目录不清）→ `local_contract`（协议校验脚本）；UAT（一轮跑批全程无误杀）→ `user_acceptance`。

## P1 — 放量正确性与口径

### 4. ready 回填精度折扣（~20-30% 虚高）

- **事项**：WP5 实测 9 个放弃中 7 个是「sourceScreen 无权威主源」，即 sourceReadiness=ready 的回填存在 ~20-30% 乐观偏差。
- **根因**：WP2 ready 判定基于源清单存在性，未做逐实体权威源核验；sourceScreen 是运行时才执行的深核验。
- **影响**：产能与时间预估虚高（两省 ready 492 实际可成稿约 355-395）；排产计划失真。
- **建议动作**：把 sourceScreen 前置为独立排产前置阶段（`qwq-data` CLI 子命令化），批量核验 ready 存量并回写 sourceReadiness 三态（ready/degraded/no_primary_source）；coverage 账本增加核验时间戳。
- **预估工作量**：2 人日（CLI 化 + 回写契约 + 两省 ready 存量首轮核验跑批）。
- **验收意图/证据层**：contract（sourceScreen 结果回写 schema）→ `local_contract`；SIT（两省 ready 存量核验后账本折扣率实测）→ `api_integration`。

### 5. tag inverted 无祖先标签展开（省/市级聚合断链）

- **事项**：`object_tag_index` 精确匹配 tagRefs；省级标签（`Topic/…/浙江省`）反查返回 0，只有实体 tagRefs 中显式存在的区县/叶子标签可命中（gamma 与 prod 本轮均复现）。
- **根因**：实体打标只写区县级叶子 geo 标签；反查存储无祖先链物化，查询侧也无展开。
- **影响**：省/市级聚合页（放量后的主要流量入口形态）无法直接用 inverted API；标签→实体发现链路在行政区上层断链。
- **建议动作**：二选一并冻结契约——① 打标时物化祖先链进 tagRefs（存储放大，查询 O(1)）；② tag-service 查询侧按 tag_nodes 树展开子孙标签聚合（存储不变，查询放大）。建议 ②（tag_nodes 已有树结构，且避免重刷全量实体）。metadata-first：先改 tag metadata 的查询语义契约。
- **预估工作量**：3 人日（服务查询实现 + 合同测试 + gamma/prod 验证）。
- **验收意图/证据层**：contract（祖先展开查询语义）→ `local_contract`；SIT（省级标签反查含全部子级实体，gamma 实测）→ `api_integration`。

### 6. introduction API 不支持多段 entityRef path（链接契约统一 homepageId 口径）

- **事项**：`/v1/homepages/{id}/introduction` 的 `{id}` 按 `/` 切分只取单段；`地点/景区/普陀山` 形式 404，仅 homepageId 或 canonicalName 可用。
- **根因**：HTTP handler path 解析与 homepage_lookup 的多格式解析能力不对齐；原计划文案「`{base}/v1/homepages/{entityRef}/introduction`」推导口径错误。
- **影响**：所有链接生产方（link_targets、coverage 账本、App 路由、运营配置）必须统一 homepageId 口径，否则出死链；homepageId 是 per-env 序号（同一实体 gamma=homepage_99 / prod=homepage_54），跨环境不可移植，链接必须 per-env 生成。
- **建议动作**：冻结「homepageId 为唯一链接 key」契约并写入 metadata（route/path_template）；或服务端支持 URL-encoded entityRef 单段解析（`%2F` 转义）作为稳定跨环境 key。建议先冻结前者（现状已工作，coverage 账本/账期链接均已按此生成），后者列为增强。
- **预估工作量**：契约冻结 0.5 人日；如做 entityRef 单段解析增强 +1.5 人日。
- **验收意图/证据层**：contract（path 契约 + 404 语义）→ `local_contract`；SIT（per-env 链接可用性矩阵）→ `api_integration`。

### 7. 存量 H100 gamma envImports 标记缺失（v2 schema 重放）

- **事项**：早期 `gamma_h100_full*/import-homepage-gamma.json` 为 v1 schema、无 `entityRefToHomepageId` per-entity 清单，coverage 账本据实标 `envImports.gamma.imported=false`，与 gamma 库内实际存在的存量主页不一致。
- **根因**：import report schema 从 v1 演进到 v2（v2 才携带 per-entity 映射），账本重建以报告为准、不猜测。
- **影响**：覆盖审计口径偏差（存量 54 实体的 gamma 触达在账本上不可见）；对 prod 无影响（prod54 已是 v2）。
- **建议动作**：对 gamma 用当前 publish 主线以 upsert 幂等重放一次 homepage import（生成 v2 报告），账本自动修正；重放前按 R-HSE02 序列停启 entity-service（或等 #1 reload 端点落地后免停服重放）。
- **预估工作量**：0.5 人日（一次受控重放 + 账本重建 + 抽查）。
- **验收意图/证据层**：SIT（重放后账本 gamma imported=true 且 introduction 抽查 200）→ `api_integration`。

## P2 — 收尾与体验闭环

### 8. WP5 尾部 3 分区补跑（沙湾/市中区/岱山）

- **事项**：沙湾区（completion gate 修复已落码待实跑）、市中区（bridge 中断，可 resume 续跑）、岱山县（publish 空集修复已落码待实跑）。
- **根因**：三项产线修复代码已合入但被外部治理代理击杀事件（#3）阻断实跑验证。
- **影响**：两省覆盖缺口 3 分区；3 项产线修复缺实跑证据，放量期同类分区（全放弃/中断恢复）会再次踩到。
- **建议动作**：#3 协议落地后，按 `~/.qwq_wp5_notes/` 中已备好的 resume 命令与前置补跑三分区。
- **预估工作量**：1 人日（跑批为主）。
- **验收意图/证据层**：GWT（全放弃分区收口、resume 续跑规则实跑）→ `local_contract` + 跑批产物；SIT（新增成稿 gamma 导入验证）→ `api_integration`。

### 9. App 端 user_acceptance 旅程缺口（标签页→主页消费未接入）

- **事项**：本计划三层证据中 `user_acceptance` 层为空：App 端尚无「标签页点击→实体主页」的消费页面与路由接入，link_targets 的 `/homepages/{id}` routePath 无端侧消费方。
- **根因**：计划范围为数据/服务侧供给链；App 端 homepage 消费页是独立特性（涉及 `lib/ui/{domain}` 新页面、metadata route/surface、页面横向质量矩阵）。
- **影响**：供给链在用户体验层未闭环，UAT 无法验收；放量产出的内容用户触达不到。
- **建议动作**：立项 App 端「实体主页消费页」特性：metadata 先行（route/surface/operation + errors）→ codegen → 页面 + Provider + Repository 三层 → 埋点（R20：曝光/停留/深度）→ 页面矩阵与登录入口契约。
- **预估工作量**：独立特性，建议 1 周级专项（含三层测试与页面质量矩阵）。
- **验收意图/证据层**：UAT（标签→主页→introduction 旅程）→ `user_acceptance`；SIT（Repository↔API）→ `api_integration`；GWT/contract（DTO/错误码/Mock 一致）→ `local_contract`。

### 10. 两省 ready 未发布 474 + pending 599 的排产与扩源（WP6 roadmap P1/P2）

- **事项**：ready 存量 474（×75% 折扣 ≈ 355 可成稿）为 P1 排产对象；pending 599 需先扩源甄别（P2）。
- **根因**：供给瓶颈在生成吞吐（#2）而非源就绪；四川 pending 437 占比高（64%），扩源缺口大于浙江。
- **影响**：P1 在 16-worker 云并发下约 4 工作日/省；不启动则试点省覆盖率停留在 1.6%。
- **建议动作**：#4 sourceScreen 前置核验 → 按市州分区冻结 frozen plan（乐山 22% 覆盖模式复制）→ P1 排产；P2 扩源按「四川 pending > 浙江 pending」优先级推进；品类配比优先补 8 个零覆盖 entityType。
- **预估工作量**：P1 每省 4 工作日（16w 并发就绪后）；P2 扩源节奏依赖源采集专项。
- **验收意图/证据层**：UAT（省覆盖率阶段目标达成）→ `user_acceptance`（运营口径验收）；SIT（批次导入与链路可用性抽查）→ `api_integration`；GWT（分区收口规则）→ `local_contract`。

## 附：本轮 prod 实导新增的运维观察（供 #1/#2 规划参考，非独立条目）

- prod compose 各业务容器 podman healthcheck 长期显示 `unhealthy`（≥39h，先于本轮存在），但 stackctl edge health 4/4 绿——healthcheck 配置与实际探活语义不一致，建议纳入 #2 云端架构专项时一并修正。
- prod 媒体对象目录属主为 `prod-edge-svc`，service 平面账号无法在 `objects/sha256` 下 mkdir；跨平面媒体增量推送需按平面用 `PROD_EDGE_SSH_KEY`。本轮已按此完成（7 对象增量，304→311），已记入 `release_rollout.json` knownGaps。
- prod 磁盘使用率 90%（40G 盘余 3.9G）；媒体库随放量线性增长（当前 1GB/311 对象），P1 排产前需扩容或外置对象存储决策。
