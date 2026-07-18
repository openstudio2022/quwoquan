# L3 Story: search-risky-config-gray-release

## 节点定位

- `L1_domain_service`: `global-search-experience`
- `L2_business_capability`: `search-provider-routing-and-storage-topology`
- `L3_story`: `search-risky-config-gray-release`

## 背景

搜索商用化引入独立 `search-service`，以及 content/entity/circle/user 等写侧服务的 `es:` 索引投影配置。`enabled / endpoints / addrs / password / tls` 等配置会影响 ES/OpenSearch、Redis、写时投影和搜索主路径可用性，属于高风险配置，必须经过版本快照、灰度和回滚演练，不能只改环境 yaml。

## 范围

In Scope:

- `quwoquan_service/services/search-service/v*.yaml` 版本快照。
- `search-service` 的 ES/Redis 配置灰度与回滚门槛。
- 写侧服务 `es:` 配置接入共享 `quwoquan_objects` 的灰度风险说明。
- prod rollout stage（gray-initial / carry-on / full）中的 SLO gate、回滚粒度和证据。

Out of Scope:

- ES/OpenSearch 业务主存储迁移。
- 修改真实 prod-hosted 凭据或手工部署。
- 未经用户确认执行 prod rollout。

## 配置合同

1. 发布配置必须有 `quwoquan_service/services/<service>/v*.yaml` 版本文件，并声明 `config.version / min_image_version / max_image_version`。
2. 提交的配置不得包含真实 endpoint、password、token 或证书；端点和凭据仅由部署环境变量/secret 注入。
3. `es.enabled=true` 只允许在 gamma/prod-sim/prod rollout stage 中通过 stackctl 验证后生效。
4. Redis publish 是 best-effort，Redis 配置故障不得反压 `/search` result 主路径。
5. 高风险配置变更必须配套 acceptance 证据：package、health、verify、search smoke、feedback 202、故障/回滚演练。

## 灰度与回滚

- 灰度由 `stackctl deploy --target prod-hosted` 的 prod rollout stage 驱动，不存在 `prod-gray` 环境。
- 回滚粒度：
  - config rollback：回退到上一 `quwoquan_service/services/search-service/v*.yaml`。
  - service rollback：回退 search-service image/config 组合。
  - dependency restore：ES/Redis 恢复或切回 native fallback。
- 回滚触发：
  - result P95/P99 超 SLO；
  - `search_retrieve_load_shed_total` 或 `search_retrieve_inflight` 持续高位；
  - ES error / timeout / threadpool queue 持续超阈值；
  - Redis lag 超阈值影响推荐 freshness；
  - `/search` 结构化 5xx 或 degrade rate 超阈值。

## 验收重点

1. config release version mapping、image compatibility 与 config PR policy 全绿。
2. `search-service` release config 可被干净检出复现，且不含秘密。
3. gamma/prod-sim stackctl verify 和 search smoke 证明配置有效。
4. 故障/回滚演练证明 ES/Redis/search-service 配置错误时可恢复。
