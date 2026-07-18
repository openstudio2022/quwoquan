# 产品遥测 SLS 单轨切换 Runbook

本 Runbook 只定义受版本控制的资源和验证契约。实际创建、部署、放量与回滚必须由 `stackctl` 对应环境命令承载；禁止从开发机直接执行临时云脚本。

## 前置条件

- `PRODUCT_OPS_SLS_REGION`、`PRODUCT_OPS_SLS_ENDPOINT`、`PRODUCT_OPS_SLS_PROJECT` 已由环境清单注入，endpoint 为 VPC 地址。
- `ALIBABA_CLOUD_ACCESS_KEY_ID`、`ALIBABA_CLOUD_ACCESS_KEY_SECRET`、`ALIBABA_CLOUD_SECURITY_TOKEN` 仅来自部署 Secret。
- 资源声明以 `quwoquan_ops/environments/cloud-providers/aliyun/sls/product_telemetry.yaml` 为唯一真相源。
- RAM 仅覆盖声明中的 Project、三个 Logstore 与必要的写入/查询动作。

## 建设顺序

1. 创建 raw、startup diagnostic、hourly 三个 Logstore，核对保留期为 3/3/90 天。
2. 创建字段索引；`callStack` 只存储不索引，`sessionId` 仅允许 product-ops 服务端精确查询。
3. 创建三项 Scheduled SQL，启用 Exactly-Once、120 秒延迟及按接收时间窗口执行。
4. 创建 Scheduled SQL 失败、聚合 freshness 和保留期漂移告警。
5. 注入 Secret 并部署 product-ops；确认 `/healthz` 的 SLS 检查通过后再发布 App。

## beta/gamma 验证

通过 `python3 quwoquan_ops/cli/stackctl.py verify --env <env> --kind all --tier t3` 汇总协议测试；有真机后运行 T4。真实 SLS 验收必须证明：

- 同一规范化请求体重放后，`_batchKey` 对应记录数不增加。
- raw 公共字段与强类型扩展一致，startup diagnostic 不含身份或产品页面字段。
- Scheduled SQL 结果不含 `sessionId/userId/callStack/_batchKey`；目标 `__time__` 显式使用 `businessHour`，跨接收窗口的会话数使用 `sessionHll` 合并后再计算，不允许直接相加 UV。
- Portal summary P95 不超过 2 秒，raw drilldown P95 不超过 3 秒；闭合小时在整点后 10 分钟内可见。

缺少 Project、RAM、Secret 或真实设备时，自动化协议测试可以继续，但 gamma/生产 acceptance 必须保持 `partial / GATE_BLOCK`。

## Alpha / Beta / Gamma 执行顺序

本节是 `event-ingestion-and-analytics/design.md` 的可执行摘要；三环境必须串行，不得用定向测试替代
上游环境的全门。

1. **alpha（local_contract）**：不读取 `PRODUCT_OPS_SLS_*` 或任何阿里云 Secret。执行
   `python3 quwoquan_ops/cli/stackctl.py verify --env alpha --kind all --tier t3`；确认 metadata/codegen、
   App outbox/session、fake-SLS 幂等/超时协议和“没有真实 SLS writer”断言均绿。当前 fixture 基线红时，
   先修 fixture，不能跳 beta。
2. **beta（真实 api_integration）**：在能访问 VPC endpoint 的受控 runner 创建 beta 专属 Project/三 Logstore/
   Scheduled SQL/RAM/告警，部署 Secret 仅注入 product-ops。验证 runner 使用独立只读 `TEST_SLS_*` Secret；
   它仅查询资源和结果，不能写 Logstore。运行 `stackctl` beta T3 后执行统一 telemetry probe：重复 batch、
   raw/diagnostic 隔离、TTL/索引/RAM、小时聚合去重/脱敏与 Portal 30 次 P95。
3. **gamma（真机 user_acceptance）**：`gamma` 只有 `gamma-local` target。先启动 mirror，再在同一 VPC 或获批
   私网连通 runner 注入 gamma 专属 Secret；执行真机冷启动、页面访问、后台恢复、断网补传、异常和推荐反馈旅程。
   无真机或无私网连通时，只能留下 `partial / GATE_BLOCK`，不能以本机 fake 或 ES 证明真实 SLS。

测试报告只写入 `.qwq_output/env/<env>/runs/<run-id>/`，并删除/掩码完整 sessionId、_batchKey、callStack、
用户键和任何 Secret。测试事件仍从 `/ops/events` 进入，不允许 probe 绕过 product-ops 直写 raw Logstore。

## 发布与回滚

- 单轨顺序：SLS 资源 → product-ops → App；不启用 Mongo/ES 双写或 fallback。
- prod 仅使用 `5% → 25% → 50% → 100%` rollout stage，不创建 `prod-gray`。
- 回滚 App/服务制品时保留 SLS 资源；App 在服务不可用期间继续使用 actor-scoped 加密 outbox。
- beta 证据闭合后，才允许按受控数据库变更流程删除遗留 `event_records` 集合。删除是破坏性动作，必须单独人工确认。
