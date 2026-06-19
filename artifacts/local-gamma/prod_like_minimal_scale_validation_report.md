# Local Gamma 生产镜像最小规格验证报告

- 环境：`local-gamma`
- 生成时间：`2026-06-16T16:40:00Z`
- 结论：**通过 local-gamma 生产镜像最小规格验证**

## 验证原则

本轮验证按“生产镜像、知识规模最小级”执行：

- 生产镜像：验证 gamma/prod 一致性、拓扑映射、包布局、API/media edge 路由、服务健康、只读集成探针，以及 `search-service + Elasticsearch + Redis` 搜索主链路。
- 最小知识规模：使用 local-gamma 最小可证明数据规模，包含单机 compose 栈、单 ES data node、单搜索索引、contract/gamma seed fixtures、最小 media slice registry、短时本地压测与重复查询探针。
- 边界：local-gamma 不能替代真集群 measured 容量，不关闭 R-S06-S-1 的真集群阻断。

## 已通过证据

| 项目 | 命令 / 报告 | 结论 |
|---|---|---|
| gamma/prod 一致性 | `python3 quwoquan_service/scripts/deploy/verify_gamma_local_prod_consistency.py` | PASS |
| 拓扑与模块映射 | `verify_environment_topology_manifest.py`、`verify_workload_topology_inventory.py`、`verify_module_package_mapping.py` | PASS |
| gamma package | `python3 agent_ops/deploy/stackctl.py package --env gamma --include-services` | PASS，含 `search-service/gamma` |
| full health | `python3 agent_ops/deploy/stackctl.py health --target gamma-local --scope full` | PASS，`17/17 healthy` |
| gamma verify | `python3 agent_ops/deploy/stackctl.py verify --env gamma --kind all --tier all` | PASS，`15 checks` |
| search local-gamma capacity | `python3 quwoquan_service/scripts/search/verify_search_local_gamma_capacity.py --duration 5 --concurrency 10 --repeat 25` | PASS |

关键报告：

- `artifacts/stackctl/gamma/20260616T163359Z-package-gamma-local`
- `artifacts/stackctl/gamma/20260616T163409Z-verify-gamma-local`
- `artifacts/stackctl/gamma/20260616T163709Z-health-gamma-local`
- `artifacts/local-gamma/search_r_s06_s1_local_gamma_report.json`
- `artifacts/search-load/local-gamma/search_load_all_20260616T163632Z.json`

## 镜像范围

已镜像并验证：

- gamma/prod 环境一致性合同。
- 生产式 edge route 与端口清单。
- app/service 环境包布局。
- gamma remote 数据源姿态。
- API edge、media edge、media origin、服务健康、配置读取与只读集成探针。
- `search-service` 通过 local Elasticsearch 与 Redis 跑通。
- 搜索 baseline query、短时本地 load probe、单节点 repeatability。

按最小规格收敛：

- 单宿主机 docker compose 栈。
- 单 ES data node；`quwoquan_objects` 为 1 primary + 1 unassigned replica，因此 local-gamma ES health 为 yellow，读路径正常。
- 使用 contract/gamma seed fixtures，而不是生产规模知识库。
- 压测为短时 methodology proof，不作为商用容量曲线。

## 仍不能本地关闭

R-S06-S-1 仍需真集群 / prod-sim 原生 ES/OpenSearch 关闭：

- 多 data node 的 shard/replica sizing。
- 多副本 `preference` 对重复搜索不跳变的收益验证。
- 真实 RPS/P95/P99 容量曲线、最大稳定 RPS 与饱和点。
- 生产 heap/page cache/GC/search threadpool/circuit breaker 阈值。
- 云 ingress/LB/secret/managed observability/rollout 行为。

## 判定

`local-gamma` 已按生产镜像最小知识规模完成验证并通过。它可以作为提交前 T1-T4 左移与搜索主链路 local-gamma 准出证据；但不能宣称关闭真集群容量阻断，`R-S06-S-1` 的真实集群 measured capacity 仍保持打开。
