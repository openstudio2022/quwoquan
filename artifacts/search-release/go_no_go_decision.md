# 搜索商用准出 · GO / NO-GO 发布判定

- 能力：`global-search-experience`（`search-provider-routing-and-storage-topology` + `cross-domain-search-journey`）
- 判定日期：2026-06-16
- 判定人：代理（按「搜索商用准出与零技术债收口计划」执行）
- **结论：NO-GO（不可宣称商用上线）**，唯一决定性阻断为「整套搜索增量 + 风险单一真相源 backlog 仍 git-untracked」（提交动作归属用户，本轮 `git_scope=verify_only`）。功能/质量/可观测/可重复性/回滚演练在工作树上已全绿，**一旦用户提交并在真集群复验通过即转 GO**。

---

## 1. 证据矩阵（工作树 · 本轮复验全绿）

| 层 | 验收意图 | 证据 | 结论 |
|---|---|---|---|
| T1 contract/static | GWT/contract | `make verify-metadata`、`runtime/search/*_test.go`、search-service `tests/*_contract_test.go`、`make codegen-app` 幂等、route/surface 对齐 | ✅ 绿 |
| T2 module | SIT/GWT | `flutter test test/ui/search/ + intersection_attribution` **50/50 通过**；search-service `go test ./... ` 全包通过（application/queryheat/http/searchsignals/tests） | ✅ 绿 |
| T3 integration | SIT | stackctl gamma `verify --env gamma --kind all` **10 checks passed**（`artifacts/stackctl/gamma/20260616T091314Z-verify-gamma-local`）；`/v1/search` 200 ES-backed、`/v1/search/feedback` 202；推荐信号真实 Redis 双服务 T3（`search_signal_t3_report.json`） | ✅ 绿（local-gamma） |
| T4 journey | UAT | `cross_domain_search_journey_test.dart`（suggest 本地两阶段 / result 云侧固定 Tab / 本地对象不进 result / 最近搜索水合 / 单域降级不阻塞整页 / 整页错误态可重试 / 默认页+结果页 `referralSource=search`+`feedRequestId` 归因链）**5/5 通过** | ✅ 绿 |
| Ops/Obs | — | SLO `search_slo.yaml`（含 load_shed_rate/inflight_saturation/related_terms_cache_hit_rate + AB control/term_heat 桶）；告警 `quwoquan_search` 组新增 `SearchLoadShedRateHigh`/`SearchInflightSaturationHigh`；`searchTermAffinity` 经 scorer 真实参与 Feed 排序（报告 `artifacts/search-obs/search_observability_ab_recommendation_report.md`） | ✅ 绿 |
| 高并发/性能 | — | 负载模型 `search_slo.yaml#load_model`（suggest/result/feedback/indexing × baseline/peak/spike）；背压 InflightLimiter + CachedTermHeat 实现+单测；压测/热路径报告 `artifacts/search-load/**` | ✅ 方法学+本地证据；真集群 measured 待补 |
| 可重复性 | — | 稳定全序 tie-break（`Score desc→Title→ObjectType→ObjectID`）+ AB bucket sticky + golden diff `artifacts/local-gamma/search_repeatability_golden_diff.json`（0 跳变） | ✅ 绿（单节点）；多副本 preference 待真集群 |
| 故障/回滚演练 | — | `artifacts/stackctl/gamma/search_rollback_rehearsal.md` + `search_rollback_rehearsal_report.json`：ES 宕机→typed 503 fail-fast→重启恢复；Redis 失败→best-effort 不阻塞；search-service 不可用→重启回滚 6.1s 恢复；演练后 8/8 healthy | ✅ 绿（local-gamma） |
| 触达范围门禁 | — | `verify_retired_terms_zero`/`verify_concept_naming`/`verify_dart_semantic`/`verify_ui_mock_isolation`/`verify_metadata_driven_ui_gate`/`verify_metadata_routes_vs_codegen_app`/`verify_page_horizontal_quality_matrix`/`verify_page_matrix_scan_complete`/`verify_acceptance_standard`/`verify_feature_tree_refactor` 全 **OK**；search-service module 可复现门禁见阻断 A | ✅ 绿（除 module 可复现） |

> 说明：上一轮 backlog R-IX07 记录的两处仓库级术语门禁红灯（`verify_retired_terms_zero`/`verify_concept_naming`）本轮复验均已 **OK**（其它会话已收敛），不再是发布阻断。

### 全量 gate 实跑结论

- **App 半**：触达范围 app 静态门禁全绿（dart_semantic / ui_mock_isolation / metadata_driven_ui_gate / metadata_routes_vs_codegen_app / page_horizontal_quality_matrix / page_matrix_scan_complete / 两术语门禁），搜索 Flutter 50/50 通过。注：另一会话并发跑 `gate_repo.sh --scope app` 在 flutter 阶段命中 build-hooks/sqlite3 prewarm 基础设施 flake（与搜索无关，非本能力）。
- **Service 半**：`gate_repo.sh --scope service` 在 `verify_config_pr_policy.sh` **FAIL（2 项）**——日志 `artifacts/search-release/service_gate_run.log`：
  1. `service configs changed but no releases/config version file changed`
  2. `high-risk config keys changed but risky-config-gray-release docs were not updated`
  其根因是搜索增量给 circle/content/entity/user 各环境 `configs/*/config.yaml` 新增 `es:` 段、并新增 `deploy/service/search-service/`，但 `releases/config/search-service/` **无版本文件**、风险灰度文档未更新。**这正是发布打包/版本落盘未完成的信号**（归属用户的 commit + release 打包动作），不是搜索功能缺陷。换言之：**全量 gate 在当前工作树上本就不可能全绿，恰恰因为增量尚未提交+发布打包——这本身即 NO-GO 证据。**

---

## 2. 发布阻断项

### GATE_BLOCK-A（决定性）：整套搜索增量 + backlog 仍 git-untracked → CI 干净检出不可复现

`git status` 证实以下发布关键文件**全部 untracked**（节选）：

- 整个 `quwoquan_service/services/search-service/`（含 `go.mod`/`go.sum`/`cmd/api/main.go`/`Dockerfile` 经 `deploy/service/search-service/`）
- `quwoquan_service/contracts/metadata/search/`、`quwoquan_service/runtime/search/es/*` 与 `runtime/search/{query_first,sort_stable,retrieve_location,retrieve_near}*`
- 各域投影与写时索引：`{content,entity,circle,user}-service/internal/application/*_search_projection.go` + `internal/infrastructure/searchindex/` + `cmd/search-backfill/`
- `content-service/internal/infrastructure/recommendation/search_signal_consumer.go`
- App 端 `lib/core/services/remote_search_repository.dart`、`lib/cloud/runtime/generated/search/*.g.dart`、`lib/ui/search/pages/location_place_landing_page.dart`、`test/ui/search/journeys/`、`location_place_landing_page_widget_test.dart`
- `deploy/service/search-service/`、`releases/config/search-service/`
- **`docs/outstanding_risks_backlog.md` 自身（风险单一真相源）仍 untracked**

证据门禁：`bash quwoquan_service/scripts/search/verify_search_service_module.sh` 当前 **FAIL（设计内红灯）**——以干净检出视角断言 go.mod/go.sum/main.go/Dockerfile 必须 git-tracked。

发布打包未完成（同族）：`gate_repo.sh --scope service` 的 `verify_config_pr_policy.sh` FAIL——各服务 `es:` 配置变更 + 新增 `deploy/service/search-service/` 但 `releases/config/search-service/` 无版本文件、风险灰度文档未更新。

- 影响：CI 干净检出无法构建 search-service（缺 `go.sum`），无法复现整套搜索链路；风险清单未版本落盘；config 未做 release 版本绑定 → 全量 gate 不可全绿。
- 处置：**提交 + 发布打包动作归属用户**（本轮 `git_scope=verify_only`，依 AGENTS.md「仅在用户要求时提交」）。用户 `git add/commit` 上述文件 + 补 `releases/config/search-service/vX.yaml` 版本绑定与风险灰度文档后，重跑 module 门禁与 service gate 转绿，本阻断即解除。

### GATE_BLOCK-B：真集群 measured 容量/性能未采集（R-S06-S-1）

- 已冻结：四类流量负载模型 + 容量校准方法学 + 按数据规模的 ES 拓扑推荐（shard 10–50GB、≥半内存留 page cache、refresh 30s、bulk 校准、query cost guard）。
- 未闭合：measured RPS/P95/P99、饱和点、最大稳定 RPS、推荐 shard/replica/节点规格与 refresh/bulk/circuit 实测阈值必须在真集群/prod-sim 原生 ES/OpenSearch 采集；本地 Apple Silicon `linux/amd64` 模拟单节点不能代表商用高并发。
- 多副本可重复性 `preference` 兜底需真集群验证（local 单节点无副本）。

### 长稳残留（不阻断稳定性准出，发布后/真集群观察）

- R-S06-S-2：写时增量常驻投影器长 soak、backfill 幂等再跑收敛（ES 重启恢复 + 索引持久分项已证）。
- R-S07-5：`searchTermAffinity` 计入 Feed 排序的**线上 A/B 收益显著性**未度量（消费链路已证真实参与排序）。
- Redis stream consumer lag 告警接线：应在 broker 侧 `redis_exporter` 的 `redis_stream_group_lag` 落地（app 侧 `rtredis.Client` 接口不暴露 XPENDING/XINFO）。

---

## 3. 判定

| 维度 | 判定 |
|---|---|
| 功能链路可商用（local-gamma） | ✅ 是 |
| 质量/测试证据（T1~T4 工作树） | ✅ 全绿 |
| 可观测/SLO/告警/AB/回滚演练 | ✅ 齐备 |
| 可重复性（单节点） | ✅ 0 跳变 |
| **CI 干净检出可复现** | ❌ 否（增量 untracked，commit 用户owned） |
| **真集群 measured 容量** | ❌ 否（无真集群，方法学已冻结） |
| **最终发布判定** | **NO-GO（待 2 项阻断闭合）** |

## 4. 转 GO 的最小闭合路径

1. 用户提交整套搜索增量 + `docs/outstanding_risks_backlog.md`，并补 `releases/config/search-service/vX.yaml` 版本绑定 + 风险灰度文档 → 重跑 `verify_search_service_module.sh` 与 `gate_repo.sh --scope service` 转绿（关闭 R-S06-S-3 + config-pr-policy，解除 GATE_BLOCK-A）。
2. 在真集群/prod-sim 原生 ES/OpenSearch 采集 measured 容量并写回 `search_slo.yaml`/`spec.md#容量校准`（关闭 R-S06-S-1，解除 GATE_BLOCK-B）。
3. （发布后观察）R-S06-S-2 长 soak、R-S07-5 线上 AB 收益、Redis lag 告警接线。

闭合 1+2 后即可判定 GO；3 为发布后持续观察项，不阻断上线。
