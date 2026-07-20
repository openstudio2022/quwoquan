# 运维运营能力 × 环境 × 数据轨 × 消费者矩阵

> 本文件记录 M0 的执行口径，不替代 `quwoquan_service/contracts/metadata/**` 的字段、
> operation 和错误码真相源。环境名称固定为 `alpha`、`beta`、`gamma`、`prod`；
> `prod` 的 gray-initial/carry-on/full 是 rollout stage，不是第五个环境。

## 1. 能力矩阵

| 能力 | alpha | beta integration | beta release | gamma integration | gamma release | prod | 数据消费者 |
|---|---|---|---|---|---|---|---|
| 产品事件 raw | Memory/fake-SLS contract | PostgreSQL local | 真实 SLS | PostgreSQL local | 真实 SLS | 真实 SLS | Portal 明细、审计、测试 probe |
| 产品事件 hourly | 内存聚合代数 | LocalRollup worker | SLS Scheduled SQL | LocalRollup worker | SLS Scheduled SQL | SLS Scheduled SQL | PV、会话 UV、漏斗、页面强度 |
| Runtime log | 本地 contract buffer | PostgreSQL local | SLS runtime raw/rollup | PostgreSQL local | SLS runtime raw/rollup | SLS runtime raw/rollup | Portal 异常下钻、Alertmanager |
| Behavior / 推荐反馈 | mock/contract adapter | Mongo + Redis + outbox | Remote Mongo + Redis + outbox | Remote Mongo + Redis + outbox | Remote Mongo + Redis + outbox | Remote Mongo + Redis + outbox | 推荐 HotPath、交集归因、推荐面板 |
| 服务 RED/告警 | local Prometheus test registry | local Prometheus | Prometheus + Alertmanager | local Prometheus | Prometheus + Alertmanager | Prometheus + Alertmanager | 发布 SLO、L1-L4、值班通知 |
| 配置/灰度/回滚 | contract state store | Postgres control plane | release ledger + hosted runner | Postgres control plane | release ledger + hosted runner | CAS release ledger + production lock | Portal、workflow、runbook |
| 审计/双签 | local contract | Postgres | Postgres + immutable receipt | Postgres | Postgres + immutable receipt | Postgres + retention/WORM policy | Portal 审计、合规复盘 |
| App 真机旅程 | 不做真机商业证据 | 设备 smoke | 不以 beta 替代 release | gamma-local 真机 | 真实 SLS + 真机 | gray-initial 后逐级放量 | UAT、QoE、恢复验证 |

## 2. 数据轨与边界

- **产品遥测轨**：`AppTelemetryReporter -> /ops/events -> EventBatchAppender -> raw -> rollup`。
  该轨只计算产品使用与客户端 QoE，不驱动推荐。
- **启动诊断轨**：受限 `/ops/startup-events` 只接固定脱敏字段；启动事实的批次身份来自
  本批 canonical digest，proof 只能作为匿名入口防滥用凭据，不能成为跨批幂等键。
- **Runtime 轨**：Dart/Go/Python/Portal 结构化日志统一进入 `RuntimeLogBatchAppender`；
  服务 RED 由 Prometheus histogram 产生，不能用 App page event 冒充。
- **Behavior 轨**：`BehaviorReporter -> content-service -> Redis/Mongo/outbox`，推荐反馈不写
  产品 SLS，防止一次反馈被两个消费者生效。
- **控制面轨**：配置、发布、审批、告警处置和回滚都经 typed control-plane object；
  Portal 只读同源 API，危险 mutation 必须双签、审计和 outbox 同事务。

## 3. 消费者契约

| 消费者 | 允许读取 | 禁止读取/推导 |
|---|---|---|
| Portal summary | `sourceKind=hourly_rollup`、freshness、水位、聚合维度 | SLS RAM、后端名称、客户端 raw secret |
| Portal drilldown | `sourceKind=raw_records`、脱敏 raw、最多 100 条 | 未授权 session、callStack 原文、用户身份键 |
| 发布 SLO gate | Prometheus query readback + 固定阈值 metadata | workflow 调用方传入的伪造数值 |
| 推荐引擎 | Behavior projection/Redis HotPath | 产品日志 raw、Portal snapshot seed |
| 告警路由 | Prometheus/Alertmanager/SLS freshness signal | 仅测试 seed 的 metric snapshot |
| 审计/合规 | principal、payload digest、decision、receipt | `X-Actor` 或客户端自报环境 |

## 4. 运营口径裁决

### 必建设

1. **PV**：按 `page_open` 的合法事件数；重放按 `_batchKey + _batchIndex` 去重。
2. **会话 UV**：按 session HLL/本地精确集合计算，不把账号级 DAU 混入产品 raw。
3. **DAU/MAU**：默认不在本能力包建设；如产品需要，必须由 user-service 的登录态投影单独提供，
   明确去重主体、时区、匿名用户策略和隐私授权，不能用 session UV 冒充。
4. **页面使用强度**：按 `pageName × action × result` 的小时矩阵，作为轻量“页面热力”，
   不收集坐标级点击热力，不记录输入内容。
5. **漏斗**：`journey -> action -> result`，入口、动作、结果必须带同一 session/feed/request 归因。
6. **QoE**：启动首屏、视频 ready/TTFF/rebuffer/seek、错误率，P95/P99 使用可合并 histogram。

### 明确不建设

- 坐标级 UI 点击热力图：采集面、隐私面、前端体积和解释成本高，当前页面级强度已足够运营决策。
- 用产品事件推导服务 RED：服务延迟、错误率、饱和度只认 Prometheus/服务端 instrumentation。
- 账号级 DAU/MAU 的第二套遥测计算：避免与 user-service 登录主体和隐私治理漂移。

### 北极星

交集转化仍是北极星：`交集曝光 -> 点击/访问 -> 互动或收藏`。PV、会话 UV、漏斗、
页面强度和 QoE 是诊断与增长基本盘，不替代交集转化。
