# Strangler Fig 拆分手册（modular-monolith → 独立 workload）

> 把热点领域从 `seed-box`（Go Modular Monolith 单 Deployment）按 Strangler Fig Pattern 平滑抽成同集群独立 Deployment，对外契约始终不变、可逆回滚。
> 真相源：`quwoquan_ops/environments/process_domain_mapping.yaml`（domain 归属）、`quwoquan_ops/environments/module_package_mapping.yaml`（包→模块）、`quwoquan_ops/environments/workload_topology_inventory.yaml`（部署形态三态）。
> 关联规则：`.cursor/rules/01-arch-constraints.mdc` §4、`specs/feature-tree/runtime/deliver-deploy-prod-pipeline/design.md`「Strangler Fig 拆分机制」。

## 1. 原则

- 逻辑边界（领域服务）不变；改变的只是部署单元（Deployment）数量：`多域共享一个 Deployment → 一域一个 Deployment`。
- 拆分是标准 K8s 演进，不引入定制结构：每个抽出的域成为标准 `Deployment + Service + HPA + PDB + probe + resources`。
- 物理仍共享单 ACK 集群 + 共享节点池，靠 bin-packing / cluster-autoscaler 复用资源。
- 跨技术栈服务（如 Python recommendation）从第一天即独立 workload，不退化为 sidecar——`quwoquan_service/services/recommendation-service/deploy/kustomize/**` 是已落地的标准参考模板。

## 2. 三态与拆分方向

| 三态（`deploy_kind`） | 含义 | 示例 |
|---|---|---|
| `modular-monolith-unit` | 单 Deployment 聚合多 Go 领域 | `seed-box` |
| `standalone-workload` | 第一天即独立 Deployment/StatefulSet，或已按本手册从 seed-box 抽出 | `recommendation-service`、`search-service`、`product-ops-service`、`realtime-gateway`、`rtc-service`、`livekit-sfu`、`coturn` |
| `split-candidate` | 当前并入 seed-box，将来按本手册抽出 | `content`、`chat`、`user`、`circle`、`integration`、`notification`、`entity`、`tag`、`assistant` |

拆分方向：`split-candidate` 域 → 新的 `standalone-workload`（从 `seed-box` 模块集合移出，独立成 Deployment）。

## 3. 拆分触发阈值（满足任一即可拆）

- 域级 CPU/内存长期高占用，或与其他域在 seed-box 内明显资源争用。
- 域级请求量/延迟 SLO 需要独立伸缩曲线（独立 HPA target）。
- 域级发布频率显著高于其他域（需要独立发布窗口 / 独立 rollout/rollback）。
- 域级故障需要独立故障域隔离（避免一域 OOM 牵连整个 monolith）。
- 域级安全/合规需要独立边界（独立 Secret/网络策略）。

阈值数据来源：seed-box 各域 `service.name` 维度的指标（CPU/内存/QPS/P95/错误率/发布次数），以及 reliable-task backlog/outbox/DLQ 指标（见 runbook §6）。

## 4. 契约不变量（拆分前后必须完全一致）

| 不变量 | 说明 | 守护门禁 |
|---|---|---|
| 域级 API path / route | 对外仍 `/v1/<domain>/*`，不变 | `verify_topology_contract_regression.sh` |
| Service DNS 名 | 集群内 `<service>` 短名 / `/v1/<domain>/*` 上游不变 | `verify_workload_topology_inventory.py` |
| domain 唯一归属 + beta=gamma=prod 一致 | 一域只属一个进程；三环境映射一致 | `verify_deployment_domain_mapping.sh` |
| 端侧 runtime 注入 | App 的 `gatewayBaseUrl` / surface / operation 不变，App 端零改动 | `verify_environment_topology_manifest.py` + 端侧 metadata 门禁 |
| 数据面归属 | 拆分后仍连同一托管 DB、同一归属、同一 ExternalName/DSN 抽象 | repository 接口 + Secret 注入（无硬编码、无跨域直连） |

## 5. 拆分步骤（metadata-first，可逆）

1. **触发评估**：用第 3 节阈值 + 指标证据确认要拆的域 `D`。
2. **改真相源（先 metadata）**：
   - `process_domain_mapping.yaml`：从 `seed-box.domains` 移出 `D`，新增 `D-service.domains: [D]`（beta/gamma/prod 同步）。
   - `module_package_mapping.yaml`：把 `D.*` 模块从 `seed-box` package 移到新 `D-service` package。
   - `workload_topology_inventory.yaml`：把 `D` 从 `seed-box.domains` 与 `split_candidates` 移出，新增 `D-service` workload（`deploy_kind: standalone-workload`，`required_primitives: [Deployment, Service, HPA, PDB]`，初期 `wired_to_prod_root: false`）。
3. **建独立 kustomize**（照搬模板，见第 6 节）：`quwoquan_service/services/D-service/deploy/kustomize/{base,overlays/{dev,integration,beta,prod}}`，保持 Service 名与 `/v1/<domain>/*` 上游不变。
4. **wire 进 root**：把 `D-service` prod overlay 加入 `quwoquan_ops/environments/kustomization/{cloud}-prod`，inventory 置 `wired_to_prod_root: true`。
5. **切流量**：把 Ingress/gateway upstream 或 Service selector 切到新 Deployment（对外 path/Service 名不变）。
6. **从 monolith 移除**：seed-box 发布单元移除 `D` 模块；dispatcher/worker 通过可靠任务租约接管，不双写、不重复 ACK。
7. **独立 rollout**：`D-service` 用与 seed-box 同一参数模型（`CONFIG_VERSION/IMAGE_VERSION/replicas/HPA`）独立灰度/回滚。
8. **门禁验证**：第 8 节命令全绿。

## 6. 标准独立 workload 模板

新 `D-service` 直接复制 `recommendation-service` 的标准结构（已通过门禁）：

- `quwoquan_service/services/D-service/deploy/kustomize/base/deployment.yaml` —— 单业务容器 + 标准 probe（readiness/liveness/startup）+ requests/limits + topologySpreadConstraints。
- `quwoquan_service/services/D-service/deploy/kustomize/base/service.yaml` —— `metadata.name: D-service`（对外稳定标识）。
- `quwoquan_service/services/D-service/deploy/kustomize/base/hpa.yaml` —— `scaleTargetRef` 指向同名 Deployment，CPU/内存 target。
- `quwoquan_service/services/D-service/deploy/kustomize/base/pdb.yaml` —— `minAvailable: 1`。
- `quwoquan_service/services/D-service/deploy/kustomize/base/kustomization.yaml` —— 聚合上面四件。
- `quwoquan_service/services/D-service/deploy/kustomize/overlays/<env>/kustomization.yaml` —— 独立 `configMapGenerator`（命名 `D-deploy-params`，避免与 seed-box `deploy-params` 冲突）+ `images.newTag` + `replacements`（APP_ENV/CONFIG_VERSION/IMAGE_VERSION/REPLICAS/HPA 阈值）。

约束：
- 每个 Deployment 只允许 1 个业务容器；领域职责禁止以 sidecar 承载（仅允许 `*-config-bootstrap` 等 init 辅助容器）。
- 跨服务调用走集群 Service DNS（如 `http://D-service:<port>`），禁止 Pod 内 `127.0.0.1`。

## 7. 回滚

- 拆分回滚：inventory 置 `wired_to_prod_root: false` + root 移除该 overlay，真相源把 `D` 退回 `seed-box.domains` 与 module package，流量切回 seed-box；App 端无需改环境注入（契约不变保证）。
- 发布回滚：`D-service` 独立 rollout 失败时按域独立回退到上一稳定 `image/config`，不牵连 seed-box 与其他独立 workload（独立故障域）。

## 8. 门禁清单（本地）

```bash
# 域归属唯一 + beta=gamma=prod 一致
bash quwoquan_ops/environments/verify/verify_deployment_domain_mapping.sh
# 路由/契约不漂移
bash quwoquan_ops/environments/verify/verify_topology_contract_regression.sh
# 包→模块映射一致
python3 quwoquan_app/scripts/runtime/verify_module_package_mapping.py
# 三态 inventory + 标准原语 + 反模式（多业务容器共享 Pod / sidecar 承载领域职责）
python3 quwoquan_ops/environments/verify/verify_workload_topology_inventory.py
# prod root 可渲染（多云）
bash quwoquan_ops/environments/verify/verify_deploy_kustomization.sh
```
