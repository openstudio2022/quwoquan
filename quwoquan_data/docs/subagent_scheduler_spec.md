# Subagent 并行调度与单篇隔离规范（公共层机制）

> 本文件只描述跨垂类通用的"并行执行 + 单对象隔离"机制，不包含任何具体 region/category/batch 实例经验。
> 垂类写法见 SOP，本批特例见任务 notes。

## 1. 为什么需要

单篇隔离不等于串行。多个内容对象（实体/文章）可以并行创作，但必须满足：

- **上下文隔离**：每个 Subagent 只读自己 ref 的 packet、SOP 摘要、授权图片与选定底稿；**禁止**读取同批其它文章正文当底稿（杜绝"换实体名同骨架"）。
- **证据隔离**：每个 ref 的 download/source/evidence 独立，reject 来源不得跨 ref 复用。
- **输出隔离**：每个 ref 的草稿、self-check、出口门各自落盘，互不覆盖。
- **质量门隔离 + 归并**：单篇 gate 通过后进对象级 done；批次级 reducer 再跑跨篇门，失败只回退受影响 ref。

## 2. 角色与组件

业界内容/标注/生成流水线的通用形态：`controller + work queue + isolated worker + handoff packet + retry policy + reducer gate`。

组织层角色与职责边界见 [`agent_content_supply_operating_model.md`](agent_content_supply_operating_model.md)。本文件只描述执行层调度机制；执行层不得改变组织层职责：

- Controller 只编排、限流、采纳 envelope 和跑 reducer，不写正文。
- Source Research、Creative Planner、Creator、Self Critic、Independent Review、Optimizer 是不同职责，不得把“自选源、自创作、自审通过”合并成一个无审计黑箱。
- 任一 worker 只能处理一个 `ObjectJob` 的一个 stage；完成标准是文件 + hash + gate，而不是会话回复。
- 快速失败对象进入 `dead`、`spilled`、`abandoned` 或 `manual_required`，不占用同批其它对象的并发槽位。

| 角色 | 职责 | 落地 |
|---|---|---|
| Controller / 主 Agent | 入队、限流、收集结果、推进 DAG、跑 reducer；**不写正文** | Cursor 主会话 + `qwq-data object-queue` |
| Work Queue | 每个 job = `ref + stage`，状态机 + lease + 互斥 + timing | `task/object_queue.py` |
| Isolated Worker / Subagent | 一次只拿一个 ref，按 packet 创作单篇 | Cursor Subagent |
| Handoff Packet | 结构化输入/输出，含证据、意图、图片槽位、禁用语域、出口门 | `_common/handoff.py` |
| Reducer Gate | 跨篇相似度、source 复用、intent/图文分布 | `_common/handoff.build_batch_reducer_gate` |
| Retry Policy | 每 ref 每 stage 最多 2 次 ReAct，超出转人工 | `object_queue` `maxAttempts=2 → dead` |

## 3. 队列工程保证（object-stage job）

`task/object_queue.py`，存储于 `batches/{batch}/_shared/object_queue/{jobId}.json`：

- **幂等**：`jobId = sha1(taskId|batchId|ref|stage)`，重复 enqueue 不产生重复 job、不重置 attempt。
- **lease 租约**：`acquire_lease` 写 `lease` token + `leaseExpiresEpoch`；只有持锁者能 `complete/fail/renew`（`lease mismatch` 抛错）。
- **崩溃恢复**：lease 过期（`now > leaseExpiresEpoch`）的 leased job 可被其它 worker 重取。
- **同源互斥**：同 `mutexKey`（默认 `baseSourceRef`，缺省退化为 ref）同时只允许一个 job 在跑，避免同底稿文章并行派生雷同。
- **失败升级**：`fail_job` 未超 `maxAttempts` → `failed`（可重取）；达到上限 → `dead`（转人工编辑队列）。
- **stage timing**：每个状态切换写入 `timings[]`，供 `run_journal` 观测端到端耗时。
- **定向回退**：reducer 跨篇门失败时 `requeue_refs` 只把受影响 ref 退回 `queued`，不全批重写。
- **controller lease**：同一 `task+batch` 只能存在一个 active Batch Controller；lease 锁为非阻塞硬门，第二 controller 直接 `GATE_BLOCK`，不得等待形成调度黑洞。
- **AssignmentLedger**：strict governance job 必须带父级授权、owner、读写根、预算、deadline 和 heartbeat；`acquire_lease` 会阻断缺授权 job 并写 `failure_ledger.jsonl`。
- **AssignmentState + Events**：`assignment_state.json` 按 `assignmentId` 幂等保存当前授权状态；`assignment_events.jsonl` 只记录真实 create/update 事件。重复 sync 不再追加重复 assignment，旧 `assignment_ledger.jsonl` 仅保留去重后的兼容事件流。
- **结果所有权**：`AgentResultEnvelope.files[].path` 必须落在 assignment 的 `allowedWriteRoots` 内；越权写入按 gate block/失败处理，不能由 controller 口头采纳。
- **失败账本**：`fail_job`、授权阻断、sourceUnit 冲突等必须写结构化 ledger，供批后质量报告聚合。

状态机：`queued → leased → succeeded`；失败分支 `leased → failed → leased ... → dead`；reducer 回退 `succeeded → queued`。

## 4. Ralph Loop 分工

**Subagent 的 Ralph Loop（单 ref）**——业界 Ralph 的"文件即真相源 + 验证门 backpressure + max 兜底"：

1. `read`：**每轮重新读取**本 ref 的 `author_job_packet.json`、当前 `3.compose/writing_pack.json`（含最新 assetId/mustIncludeFacts）、SOP 摘要、`baseSourceRef`。**禁止依赖会话记忆里的旧 assetId**（抗 context 漂移与资产漂移）。
2. `draft`：写本 ref 的 `4.draft/draft.article.md`，引用的 `asset://` 必须取自本轮读到的 `writing_pack.assets`。
3. `self-check`：确认主线唯一、图片已插入正文、事实已覆盖、无跨篇模板句、**无私人电话/微信/QQ、无清单式机械小标题**；写 `4.draft/author_self_check.json`。
4. `hook-check`：触发单 ref review（`ref_review_gate`，含 contactInfo/mechanicalHeading 等门）。
5. `repair`：gate 失败只修本 ref → 回到步骤 1 重读、重写、重 review，**循环直到 `ref_review_gate.passed`（reviewDecision=approved）**。
6. `exit`：完成判据是 **gate 状态 approved**，不是口头"我已完成"。超 `deadlineEpoch`（默认 20min 墙钟）则写 `author_self_check.json` 标 `timeout` 并由 controller `fail`（达上限转 `dead`→`spillover` 独立修复批），**不得假装完成**。

**主 Agent 的 Ralph Loop（调度归并）**：

1. `lease`：发放 job 租约（并发受队列 `concurrency` 配置约束）。
2. `await`：等待 Subagent 结果（文件路径 + self-check，不接受"我已完成"口头准出）。
3. `ref-gate`：跑单篇 `ref_review_gate`。
4. `reduce`：全部对象 done 后跑 `batch_reducer_gate`。
5. `rebalance`：按 `fallbackStage`/`affectedRefs` 重排队列。

## 5. 出口要求（硬约束）

- Subagent 不允许把"我已完成"作为准出，必须有文件路径 + `author_self_check.json` + `ref_review_gate.passed`。
- 主 Agent 不允许在缺 `ref_review_gate` 的情况下把 ref 标 done。
- 批次不允许在缺 `batch_reducer_gate` 的情况下进入 publish。
- 创作自由只在 `ObjectEvidencePacket` 和 `CreativeBrief` 内发生；Subagent 不得自行扩展来源、换图、改变载体或写入未发布 refs。
- 已完成的 `generator=agent` 且非占位草稿不得被普通 prepare 回退为 `pending`；只有显式上游 retry/rebuild 能降级，并必须写明 `downgradeReason`。
- 同一 `baseSourceRef` 被多篇使用时，reducer 标记 `source_reuse_risk` 并写 conflict ledger；运行中不询问人工，批后由 Reconciler 判断误报、保留最佳项或安排重选底稿。
- `ref_review_gate` 含的出口门（单一 gate library）：`writingIntentConsistency` / `imageReferenceClosure` / `skeletonSimilarity` / `registerMismatch` / `sourceRejectBlock` / `contactInfo`（私人电话/微信/QQ）/ `mechanicalHeading`（清单式标题）。
- 超墙钟（`deadlineEpoch`）的 ref 由 `reap` 标 `timeout` 失败，不阻塞同批其它 ref。

## 6. 并发档位

并发只在 source/gate 稳定后逐档提升，**禁止**直接拉满：

- 小批试运行：`concurrency=2`
- 质量稳定后：`concurrency=4`
- 规模化验证：仅在 SLO 达标后提升，不允许直接 20 并发。

## 7. 连续队列调度协议（流式，非批次式）

> 业界对齐：visibility-timeout + heartbeat + DLQ + 指数退避 + reaper（见 SQS / Postgres SKIP LOCKED / Redis Streams 通用模式）。
> 目标：**完成一个立即补一个、始终保持 N 个活跃**，慢/卡的单篇不拖垮整批。

主 Agent（controller）循环：

1. **维持 N 活跃**：当前活跃 Subagent < N 时，循环 `object-queue lease-next` 租新 job、发给新 Subagent；租不到（返回 `leased:false`）则进入等待/收口。
2. **心跳握手**：长任务 Subagent 周期回报，controller 对其 job 调 `object-queue heartbeat` 续租；只续 `leaseExpiresEpoch`，**不延长 `deadlineEpoch`（墙钟硬上限）**。
3. **完成即补**：Subagent 出口（`ref_review_gate.passed`）→ controller `object-queue complete` → 立即 `lease-next` 补位。
4. **超时/崩溃回收**：周期 `object-queue reap`：
   - 超 `deadlineEpoch` 的 leased job → 强制 `timeout` 失败（按 `maxAttempts` 升级 `dead`）；
   - lease 过期但未超 deadline（崩溃/无心跳）→ 回收为 `queued` 可重取。
5. **失败隔离 + spillover**：达 `maxAttempts` → `dead`；`object-queue dead-list` 巡检后 `object-queue spillover --target-batch <repair_batch>` 把 dead 溢出到**独立修复批**（attempt 归零、原批留痕 `spilled`），当前批不因个别失败阻塞，继续推进 reducer。
6. **失败退避**：`failed`→可重取前有指数退避 + jitter（`notBeforeEpoch`），防惊群。

逐 job 墙钟上限默认 `maxWallClockSeconds=1200`（20min），入队时 `--max-wall-clock` 可配。

## 8. CLI 入口（worker 可驱动的完整状态机）

```bash
# 入队（幂等）；--max-wall-clock 配逐 job 墙钟硬上限（秒）
qwq-data object-queue enqueue --task <task> --batch <batch> --stage author [--max-wall-clock 1200]

# 队列状态汇总
qwq-data object-queue list --task <task> --batch <batch>

# 租一个 job 并打印 handoff packet（含 Ralph 出口契约），供 Subagent 直接消费
qwq-data object-queue lease-next --task <task> --batch <batch> --worker <id> [--stage author] [--ttl 1800]

# 出口：完成 / 失败（需持有 lease）
qwq-data object-queue complete  --task <task> --batch <batch> --job <jobId> --lease <lease>
qwq-data object-queue fail      --task <task> --batch <batch> --job <jobId> --lease <lease> --error "<reason>"

# 长任务续租（心跳）
qwq-data object-queue heartbeat --task <task> --batch <batch> --job <jobId> --lease <lease> [--ttl 1800]

# reaper：回收过期 lease + 强制 timeout 超墙钟 job
qwq-data object-queue reap --task <task> --batch <batch>

# 失败隔离：列 dead / 溢出到独立修复批
qwq-data object-queue dead-list  --task <task> --batch <batch>
qwq-data object-queue spillover  --task <task> --batch <batch> --target-batch <repair_batch> [--stage author]
```

CLI 只生成队列与 gate，**不直接生成正文**；正文只由 Subagent 会话创作。

## 9. 规模化：外部 SDK 多 worker（10 万/日）

**必须直说的并发现实**：单个 Cursor 聊天会话的 `Task` 并行 Subagent 受会话级约束（量级十几个，**不可能 500**），且 N 个并行≈N 倍 token。`日产 10 万 = 5min/篇 × 500 并发` 只能由**外部 `cursor-sdk` 多进程 worker** 实现；聊天内 `Task` 仅用于开发与小批验证。

外部 runner 设计（基于 Cursor 官方能力）：

- **执行层**：`@cursor/sdk` / `cursor-sdk` 的 **cloud runtime**（官方定位 "many agents in parallel" + "survive disconnecting"）。
- **1 任务 = 1 独立 cloud agent**：同一 cloud agent 并发跑两个 run 会 `409 agent_busy`（不可重试）；高并发只能是多个不同 agent 并行，**不得**给一个 agent 灌并发 run。
- **编排层（自建）**：多进程 worker 各持 `worker_id`，循环 `object-queue lease-next` 消费同一队列；进程重启用 `Agent.resume(agentId)` 接管未完成 run（队列 lease 过期由 `reap` 回收）。
- **限流/退避**：遇 `RateLimitError` / `isRetryable` 按指数退避；并发天花板=计费 + API 速率限制（**Cloud Agents 强制 Max Mode + 按 API 计费，须先设 spend limit**），上线前向 Cursor 确认账号/团队 API 速率配额。
- **真实启动探针**：`env ready --json` 默认执行一次最小 `Agent.prompt` startup probe，覆盖当前 model、runtime、cwd、token、网络与 envelope；只通过 import/network 的环境不允许进入百级 author-runner。
- **author-runner 断路器**：外部 runner 放大前先执行 1-job startup probe；probe 失败直接返回 `retry.infra` blocker，不 lease author job，不消耗 worker 槽位。连续 startup fail 归入基础设施预算，不占内容质量预算。
- **完成通知**：webhook 推送 "coming soon"，当前靠 `run.wait()` / 状态监听 / 轮询 `listRuns`，由 worker 把终态回写 `object-queue complete|fail`。

> 文件队列适用于开发/小批；规模化时把 `object_queue` 后端切到 Redis Streams/SQS（保持同一状态机语义：lease/heartbeat/deadline/dead/spillover）。
> 容量规划：`queue_len / (workers × throughput_per_worker) < client_timeout`。

## 10. 队列后端抽象 + per-lane 限流背压 + 成本护栏（运行时工程地基）

> 真相源：`task/object_queue.py`。后端切换、限流、成本护栏不改变 §3 状态机语义与 §8 CLI 表面——同一组 `enqueue/lease/heartbeat/complete/fail/reap/spillover` 在任意后端下语义一致。

### 10.1 队列后端抽象（local_file ↔ reliabletask，不改调用方）

后端由统一标识符切换，调用方代码与 jobId 不变（遵守 R10 存储无关）：

- `QUEUE_BACKEND_LOCAL = "local_file"`：文件队列，开发/小批/十级~千级的真相源（`batches/{batch}/_shared/object_queue/{jobId}.json`）。
- `QUEUE_BACKEND_RELIABLETASK = "reliabletask"`：生产可靠队列后端，日产万级及以上准入要求（`verify scale-readiness` 在 `daily_target>=10000` 强制 `queueBackend=reliabletask`）。
- 后端解析：`_backend_name(backend)` 读显式参数或环境变量 `QWQ_OBJECT_QUEUE_BACKEND`，仅接受 `SUPPORTED_QUEUE_BACKENDS`，未知后端抛错（杜绝静默回退）。
- 路由契约：本地文件队列同时携带 `_reliabletask_ref(...)` 声明式 bridge payload（`taskType=data.content_object.execute` / `queue=reliabletask.data.content_supply` / `dedupeKey=task|batch|job` / `partitionKey` / `payloadAllowlist=object_job`）。服务侧 adapter（`quwoquan_service/runtime/reliabletask`）据此经 MongoStore + RedisReadyIndex 分发，**不改 jobId、不改幂等键、不改状态机**——这就是"千级稳定后切可靠后端，接口不变"的落地接缝。

### 10.2 per-lane 限流与背压（吞吐与外站/计费约束的解耦）

各 lane 独立限流，慢/受限 lane 不拖垮其它 lane：

- `download` lane：受外站 robots/限速约束，`data download` / `scaled-e2e prepare` 以 `--max-workers` 控制并发抓取（实测十级 e2e 即由该 lane 主导吞吐）。
- `author` lane：受 Cursor API rate + spend 约束，并发档位见 §6（2→4→SLO 达标后提升），外部 SDK 多 worker 见 §9。
- `import` lane：受 mongo 写入约束，由 release/import 阶段独立节流。
- 背压：`author` lane 积压超阈值时，controller 暂停上游 `enqueue`（§7 维持 N 活跃的反向约束），避免队列无界增长。

### 10.3 成本护栏（硬熔断）

- 逐 job 预算字段：`DEFAULT_TOKEN_BUDGET` / `DEFAULT_COST_BUDGET_USD`（`>0` 时为 SDK runner 侧硬上限，超出强制 `dead`，不消耗同批其它对象槽位）。
- 累计护栏：`record_usage` 落 `TokenLedger`；`verify scale-readiness` 以 TokenLedger 为证据投影单对象 token、单位通过成本与缓存命中率，缺失即阻断放量。
- 断路器与退避：同一失败指纹连续 `DEFAULT_STUCK_THRESHOLD` 轮不变 → 判定卡死直接 `dead`+notify（不空耗 attempts）；`failed→可重取` 之间走 `BACKOFF_BASE_SECONDS` 指数退避 + jitter（防惊群）。
- 事件可观测：超时/断路/预算超限写 `_notifications.jsonl`，编排循环（Codex 盯盘）可订阅。

### 10.4 与放量准入门的对账

`verify scale-readiness` / `verify site-scale-readiness` 是本节的程序化对账面：source-ready 容量、Cursor startup、target satisfaction、measured throughput、firstPassRate、作品判定纯净性（`nonWorkMaterializedCount`）、semanticMentions 覆盖、TokenLedger、release/import 证据、`queueBackend`/`maxConcurrency` 共同决定档位是否可升。本节任一保证缺证据，对应门即阻断，禁止口头放量。
