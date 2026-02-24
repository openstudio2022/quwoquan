# 反馈、体验指标与自动优化 / 自学习统一规范

目标：
- 让“推荐、助手等 AI 能力”的优化从一开始就是**可自动化、可评估、可灰度、可回滚**的系统能力，而不是靠人工拍脑袋调参。
- 把“用户体验指标（RUM/端侧体验 SLIs）”也纳入反馈闭环：用体验指标驱动系统级优化，并分解到模块/对象/接口的 SLI/SLO/SLA。

本规范定义：体验指标字典、反馈事件范围、事件字段、因果链（trace/causation）、评估记录、版本化与发布治理、以及从体验指标到接口 SLO 的分解方法。

---

## 1. 适用范围

- 推荐/排序：Content（发现流）、Circle（圈子内推荐）
- 助手：Assistant（tool 使用、模板、学习回放、profileUpdateProposal）
- 运营：Ops（实验/灰度、策略变更审计、反馈聚合）
- 体验指标（RUM）：端侧各页面（pageId 维度）与端云接口（requestId/traceId 维度）

---

## 2. 用户体验指标（RUM SLIs）

> 体验指标建议用业内常见术语表达（SLI/SLO/SLA、RUM、Crash-free、ANR、p95/p99）。
> 指标应以 `pageId`（端侧来源）+ `traceId/requestId`（端云链路）为主键做关联（见 `contracts/openapi/common.yaml` 与 `contracts/error_codes.md`）。

### 2.1 指标分层（从用户视角到系统分解）

- **用户旅程级（Journey SLIs）**：用户能否“完成任务”（打开首页、刷新 feed、打开详情、发送消息、完成一次助手 run）
- **页面级（Page SLIs）**：页面加载/交互体验（Time to First Render / Time to Content Ready / Jank）
- **接口级（API SLIs）**：接口可用性与尾延迟（success rate、p95/p99 latency）
- **依赖级（Dependency SLIs）**：DB/MQ/Cache 等错误与延迟（用于根因定位，不直接作为对用户 SLA）

### 2.2 体验指标字典（建议最小集合）

#### 2.2.1 稳定性（Stability）

- **Crash-free sessions / users**：无崩溃会话/用户占比
- **ANR rate**（Android）：应用无响应比例
- **Unhandled exception rate**：未捕获异常比例（端侧）
- **HTTP failure rate**：接口失败比例（按 endpoint/service/module 统计）

#### 2.2.2 性能（Performance）

移动端常用且可落地的术语（Flutter 适配）：
- **Cold start time / Warm start time**：冷启动/热启动耗时
- **Time to First Frame (TTFF)**：从启动到首帧渲染
- **Time to Content Ready (TTCR)**：到“首屏关键内容可用”（数据加载完成并渲染）
- **Interaction latency**：点击到响应（如打开详情、发送消息按钮反馈）
- **Frame time / Jank rate**：掉帧/卡顿比例（如 >16.7ms 或 >33ms 计为 jank，按设备刷新率校正）

#### 2.2.3 体验（Experience）

- **Apdex（可选）**：按阈值把请求分为 Satisfied/Tolerating/Frustrated，适合对管理层汇报
- **Error UI rate**：进入错误页/空状态页的比例（需区分“业务为空” vs “失败”）

#### 2.2.4 参与度（Engagement，运营 KPI，不等同于 SLO）

- **Session duration / Dwell time**：会话时长/页面停留时长
- **Retention / DAU/WAU/MAU**：留存与活跃

> Engagement 更偏运营 KPI；但它们的变化常用于触发“性能/稳定性回归调查”，不建议作为工程 SLO 的直接约束。

---

## 3. 体验埋点与监控事件（RUM Events）

> 体验事件也是“反馈”，建议统一走 Ops（运营）事件接收与平台可观测性体系（日志/指标）双写或可互相导出。
> 事件字段复用 `contracts/openapi/common.yaml` 里的端侧 headers（pageId/sessionId/sentAt/device/appVersion/traceId/requestId）。

### 3.1 事件类型（建议）

- `ux.app_start`：冷启动/热启动、TTFF
- `ux.page_load`：页面加载（TTFR/TTCR）
- `ux.interaction`：关键交互（tap→response）
- `ux.api_call`：端侧发起的关键 API 调用（只记录关键字段，避免高基数）
- `ux.error`：端侧错误（异常、渲染失败、网络失败）
- `ux.jank`：卡顿/掉帧摘要（聚合后上报，避免高频）

### 3.2 统一字段（最小集合）

在 §1 的“统一反馈字段”基础上，体验事件建议追加：
- `deviceTier`：设备档位（high/mid/low，可按机型/CPU/内存映射）
- `networkType`：wifi/5g/4g/3g/unknown
- `durationMs`：耗时（如 TTFF/TTCR/API latency）
- `result`：ok/error/cancel
- `errorCode`：如有（复用 `contracts/error_codes.md` 的 `MODULE.KIND.REASON`）
- `endpoint`：规范化路由名（如 `orch.discovery.feed.get`，避免把 path 参数直接当 label）

---

## 4. 从体验指标分解到模块/对象/接口的 SLI/SLO（方法）

### 4.1 术语（统一口径）

- **SLI**：可量化的指标（如成功率、p95 延迟、TTCR）
- **SLO**：内部目标（如 p95<300ms，月成功率≥99.9%）
- **SLA**：对外承诺（通常比 SLO 松，且包含违约条款；建议后期再固化）

### 4.2 分解步骤（强制执行）

1. 选关键用户旅程（P0/P1）：例如“打开首页发现流”“进入帖子详情”“发送消息”“一次助手 Run”
2. 为旅程定义 Journey SLI：成功率、端到端耗时（TTCR）、错误 UI 率
3. 将旅程拆分为页面阶段 + API 调用链（由 traceId 关联）
4. 为每个 API 定义 API SLI：success rate、p95/p99 latency、依赖错误率
5. 把 Journey SLO 的“误差预算”分配到各 API（例如：TTCR 预算中 server 预算 40%、network 30%、client 30%）

---

## 5. 建议的 SLO（初始基线，可按设备档位/网络分层）

> 下面给出“可先落地”的初始目标。上线后应按真实分布校准阈值，并按 deviceTier/networkType 分层统计。

### 5.1 用户旅程级（Journey SLO）

- **首页发现流（Discovery Feed）**
  - Journey SLI：`ux.page_load`（`orch.discovery_feed.list`）的 TTCR
  - 建议 SLO：TTCR p95 ≤ 2500ms（wifi/5g），p95 ≤ 4000ms（4g）；失败率 ≤ 0.5%
- **帖子详情（Post Detail）**
  - SLO：TTCR p95 ≤ 2000ms（wifi/5g），p95 ≤ 3500ms（4g）；失败率 ≤ 0.5%
- **聊天会话列表（Conversation List）**
  - SLO：TTCR p95 ≤ 2000ms（wifi/5g）；失败率 ≤ 0.3%
- **聊天消息加载（Message List）**
  - SLO：TTCR p95 ≤ 1500ms（wifi/5g）；失败率 ≤ 0.3%
- **发送消息（Send Message）**
  - Journey SLI：tap→本地 UI ack + 服务端确认
  - SLO：端到端确认 p95 ≤ 1200ms（wifi/5g）；失败率 ≤ 0.2%
- **助手 Run（Assistant Run / Tooling）**
  - SLO：首段可读响应（first token/first chunk）p95 ≤ 2500ms；完成率 ≥ 99.0%

稳定性全局（建议）：
- Crash-free sessions ≥ 99.8%
- ANR rate ≤ 0.1%（Android）

### 5.2 接口级（API SLO，按模块/对象/接口）

> API SLO 以网关入口或服务入口统计均可，但必须能按 `endpoint` 归因。

#### 5.2.1 Gateway（系统级入口）

- SLO：请求成功率 ≥ 99.95%（月），p95 延迟 ≤ 50ms（不含下游），429 可单独统计

#### 5.2.2 Orchestrator（聚合接口，直接影响页面 TTCR）

- `GET /v1/orch/discovery/feed`（`orch.discovery_feed.list`）
  - SLO：成功率 ≥ 99.5%，p95 ≤ 600ms，p99 ≤ 1200ms
- `GET /v1/orch/circles/{circleId}/activities`
  - SLO：成功率 ≥ 99.5%，p95 ≤ 600ms，p99 ≤ 1200ms

#### 5.2.3 Content（核心业务对象：Post/Comment/Reaction/Feed）

- `GET /v1/content/feed`（候选/非编排路径）
  - SLO：成功率 ≥ 99.5%，p95 ≤ 400ms
- `GET /v1/content/posts/{postId}/comments`
  - SLO：成功率 ≥ 99.5%，p95 ≤ 300ms
- `GET /v1/content/posts/{postId}/counters`
  - SLO：成功率 ≥ 99.9%，p95 ≤ 120ms

#### 5.2.4 Chat（核心业务对象：Conversation/Message）

- `GET /v1/chat/conversations`
  - SLO：成功率 ≥ 99.7%，p95 ≤ 300ms
- `GET /v1/chat/conversations/{conversationId}/messages`
  - SLO：成功率 ≥ 99.7%，p95 ≤ 250ms

#### 5.2.5 User（核心业务对象：Auth/Profile/Persona）

- `POST /v1/user/auth/login`（登录）
  - SLO：成功率 ≥ 99.9%，p95 ≤ 300ms
- `GET /v1/user/profile/{userId}`
  - SLO：成功率 ≥ 99.7%，p95 ≤ 250ms

#### 5.2.6 Ops（运营服务：事件接收/实验）

- `POST /v1/ops/events`（体验/行为事件接收）
  - SLO：成功率 ≥ 99.9%，p95 ≤ 200ms（写入可异步落库，但必须幂等）
- `GET /v1/ops/experiments/{experimentId}/bucket`
  - SLO：成功率 ≥ 99.9%，p95 ≤ 80ms（建议强缓存）

#### 5.2.7 Assistant（自学习与推理）

- `POST /v1/assistant/learning/ingest`（反馈入库）
  - SLO：成功率 ≥ 99.9%，p95 ≤ 300ms（可异步写入，但需幂等）
- `POST /v1/assistant/run`（如采用流式，需定义首段响应 SLO）
  - SLO：见 §5.1

### 5.3 分解示例：发现流 TTCR → 接口误差预算（p95）

以“首页发现流 TTCR p95 ≤ 2500ms（wifi/5g）”为例，可按经验先做一个可操作的预算拆分，后续再用真实数据校准：

- **Client（端侧渲染/解码/首屏布局）**：≤ 700ms
- **Network（端到网关往返 + 抖动）**：≤ 600ms
- **Server（网关+编排+下游服务）**：≤ 1200ms
  - Gateway 自身开销：≤ 50ms（不含下游）
  - Orchestrator 聚合：≤ 600ms
  - 下游并行（示例）：
    - Content 候选/排序：≤ 300ms
    - User profileSnapshot：≤ 150ms
    - Ops 行为摘要/实验查询：≤ 100ms
  - **Buffer（预留）**：≤ 50ms（用于尾部抖动）

成功率预算（示例）：
- Journey 失败率 ≤ 0.5% 可以分配为：Orchestrator 0.3% + 下游（并行中任一失败）0.2%，并要求“可降级返回”（例如缺少部分字段仍可渲染），将失败转化为可用但降级的体验。

### 5.4 接口与业务对象的 SLO 分级（用于统一 SLA/SLO 口径）

> 目的：把“体验指标”稳定地映射到“模块/对象/接口”的 SLO 要求，避免口径漂移。

- **P0（关键旅程）**：直接影响“能否完成任务”的对象与接口
  - 例：发现流 feed、登录、聊天消息加载/发送、助手 run、实验分桶、埋点/体验事件接收
  - 建议：成功率 ≥ 99.7%～99.95%，p95/首段响应有明确约束；必须支持降级/回滚
- **P1（重要体验）**：影响体验但不阻断核心旅程
  - 例：评论列表、互动状态、圈子活动流、用户画像快照
  - 建议：成功率 ≥ 99.5%，p95 有约束；允许短时降级为“延迟加载/弱一致”
- **P2（非关键/后台）**：不直接影响当下交互或可异步完成
  - 例：媒体资产状态查询、部分运营报表查询、离线评估产物落库
  - 建议：以吞吐与成本优化为主，成功率/延迟约束可更宽；但必须可观测、可追踪

SLA 建议策略：
- **对外 SLA** 通常只对 P0 旅程承诺，且数值应比内部 SLO 略松（避免频繁违约）。
- **内部 SLO** 覆盖 P0/P1/P2 全量接口，作为工程交付门槛与告警依据。

---

## 6. 与公共库的关系（强制）

- 体验事件模型与字段：应由 `runtime/learning`（或等价）提供统一结构
- 日志/指标/trace：必须使用 `runtime/observability`
- MQ envelope 与因果链：必须使用 `runtime/messaging`
- 配置与阈值：必须使用 `runtime/config`，并遵从 `contracts/configuration.md`

---

## 7. 反馈事件（Feedback Events，业务/AI 反馈）

### 7.1 必须覆盖的反馈类型

- **显式反馈**：like/favorite/follow/comment/share/not_interested/report、对摘要/帮读的偏好等
- **隐式反馈**：曝光（impression）、点击（click）、停留（dwell）、滚动深度、跳出等
- **助手反馈**：
  - interaction events（多轮对话、工具调用、用户纠错）
  - scorecards（显式评分/满意度/采纳与否）
  - profileUpdateProposal 的 confirm/reject/apply 结果

### 7.2 统一事件字段（最小集合）

所有服务产生/接收的反馈事件都应具备：

- `eventId`：全局唯一（支持幂等）
- `eventType`：稳定枚举（如 `content.like` / `assistant.scorecard`）
- `occurredAt`：事件发生时间（ISO8601）
- `userId` / `personaId`（可空，取决于事件）
- `pageId`：三段式（见 `contracts/openapi/common.yaml`）
- `traceId` / `parentTraceId` / `causationId`：追踪与因果链（见 `contracts/error_codes.md` 与 `contracts/messages/envelope.schema.json`）
- `target`：被作用对象（如 postId/circleId/conversationId/runId 等）
- `context`：可选上下文（脱敏，避免高基数爆炸；大对象用引用）
- `labels`：可选（如 experimentId/bucket/modelVersion/policyVersion）

> 事件 envelope（异步）必须遵从 `contracts/messages/envelope.schema.json`。

---

## 8. 自动化优化闭环（Learning Loop）

### 8.1 最小闭环（必须具备）

1. **采集**：反馈事件持续进入（HTTP ingest 或 MQ）
2. **评估**：离线评估（AUC/CTR/满意度/采纳率等）+ 线上监控（错误率/延迟/SLO）
3. **产物版本化**：策略/模型/模板必须有 `version`（可回溯）
4. **发布**：灰度到人群（实验/分桶）或灰度到实例（系统层）
5. **回滚**：指标异常可快速回滚到上一版本

### 8.2 版本元数据（必须）

- `artifactType`：`reco_model` / `reco_policy` / `assistant_template` / `assistant_policy` ...
- `artifactVersion`：语义版本或 hash
- `createdAt` / `createdBy`
- `trainDataRange`（或数据集标识）
- `evaluationReportId`（评估报告引用）
- `rollout`（灰度范围与实验号）

---

## 9. 服务职责建议（边界）

- **Content/Circle**：负责推荐/排序策略与产物消费；负责把关键事件（曝光/点击/互动）产出为反馈事件
- **Assistant**：负责助手相关 feedback 的采集、评估与策略/模板版本化；对外暴露 ingest 与 policy 获取
- **Ops（运营）**：负责实验/分桶与运营配置治理；负责把“发布/灰度/回滚/审计”做成业务侧可操作能力
- **平台模块**：负责 trace/日志/指标/告警与系统配置治理（见 `platform/*` 与 `contracts/configuration.md`）
