# 四环境产品遥测 Elasticsearch Runbook

本 Runbook 只解释正式合同的执行与恢复方式，不拥有字段、索引或聚合语义。唯一业务真相位于 Product Ops `event_record/storage.yaml` 与 `rollups.yaml`；告警执行策略位于 `quwoquan_ops/observability/elasticsearch/product_telemetry_alerts.yaml`。

## 单轨约束

- Alpha、Beta、Gamma、Prod 均绑定 `ext.obs.elasticsearch` 和同一 `ObservabilityLogSinkPort`。
- Alpha/Beta/Gamma 使用各自本地拓扑中的独立 Elasticsearch 容器、索引和数据卷；Prod 使用受保护环境注入的正式 Elasticsearch endpoint 与 API key。
- 不允许 PostgreSQL、SLS、文件或内存作为环境运行时 log sink，也不允许双写、fallback 或运行时选择器。
- 本地 endpoint 只由 packaged runtime/port manifest 解析；Prod endpoint 和 `PRODUCT_OPS_ELASTICSEARCH_API_KEY` 只由受保护部署环境注入。

## 建设与验证顺序

1. `stackctl package` 固定四环境候选配置与镜像摘要。
2. `stackctl up` 启动候选；Alpha/Beta/Gamma 的 Elasticsearch 必须来自环境 package 声明的完整 workload。
3. `stackctl health` 验证集群、四个索引、写入权限、TTL/ILM 和 Product Ops health check。
4. 通过 Product Ops `/ops/events` 和 `/ops/runtime-logs` 写入；禁止测试直写索引。
5. 验证幂等 batch、raw/startup/runtime 隔离、rollup row identity、freshness waterline、Portal summary/drilldown 和权限负例。
6. `stackctl verify` 归档 target、baseline/package/image/runtime digest、Provider CaseResult 和脱敏 query receipt。
7. 本地环境执行 `stackctl down` 并证明资源释放；Prod 仅在受保护批准后进入 apply/rollout。

## 准出与回滚

- 三个本地环境必须分别产生真实 ES 网络/持久化读写证据；local_contract harness 不能替代环境证据。
- Prod prevalidate 只证明装配纯度，不是 hosted readiness。缺少正式 endpoint、API key、容量、备份恢复或 hosted receipt 时保持 `GATE_BLOCK`。
- 回滚 App/Service 制品时保留 ES 数据；rollup 变更以同一不可变候选回退。禁止以切回 PostgreSQL/SLS 作为恢复动作。
- 报告不得包含 API key、完整 sessionId、`_batchKey`、callStack 或可反查用户的原文。
