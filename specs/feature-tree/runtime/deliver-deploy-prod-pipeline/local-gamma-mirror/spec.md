# L3 Story：本地 Gamma 镜像 (`local-gamma-mirror`)

> 所属能力：[`deliver-deploy-prod-pipeline`](../spec.md)
>
> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，我希望gamma-local 作为开发与提交前左移主验证链（gamma 仅本地，无远端 gamma）；真实远端复验由 prod gray-initial rollout stage 承接，从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- 本地 gamma 语义镜像栈（DB/Redis/核心服务/media/TLS 反代）启停与健康前置检查
- 本地 local_contract->user_acceptance 左移：真实 HTTP API、存储副作用、错误码、RemoteRepository 解码与模拟器/真机 Patrol 核心旅程
- 提交前报告 artifacts/local-gamma/report.json，指向 quwoquan_ops/environments/gamma/validation_suites.json
- 与 prod 同构的工作负载图谱解释（同 Service 名、路由前缀、数据面 Service 名/DSN 变量）

### Out of Scope

- 替代云侧 gamma 的 K8s/Ingress/Secret/云观测/多云 overlay
- 替代云侧 prod 灰度流量、SLO 卡点、审批与回滚演练
- 新增 local-gamma 环境枚举、APP_ENV 枚举或第四份 seed manifest
- 在生产包引入 test fixture / seed reset / 本地 mirror URL

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 gamma-local 提交前左移主验证链

- gamma-local 是开发与提交前的主验证链，统一本机模拟器/浏览器接入同一组域级入口。
- gamma-local 通过仅证明提交前左移质量，不替代也不成为 main required check。
- 不新增运行环境枚举或第二套 seed manifest。
- gamma-local 从各服务 `deploy/compose.yaml` 与 Ops external/infra Compose 扫描装配，不维护服务名册；recommendation 各环境统一以 `recommendation-service:8000` 调用。
- edge-media（realtime-gateway/rtc-service/livekit-sfu/coturn）统一在本 compose 以 profile 按需组装；realtime-gateway 实现未就绪以 edge-media-pending 显式占位收敛。
- full 镜像栈使用唯一的 Caddy 路由真相源与各服务声明的内部监听端口；非生产环境不会因生产 operator OIDC 前提阻塞健康检查。
- 以已有 package provenance image 启动时必须先验证本地 image 可用，缺镜像为可诊断的 GATE_BLOCK，禁止通过手工重标记、拉取 localhost tag 或旧 Caddyfile 路径绕开。

<a id="req-002"></a>
### REQ-002 远端复验只在 prod gray-initial 执行

- 仓库不定义 hosted gamma 环境；真实远端复验只在 prod `gray-initial` rollout stage 执行，与 gamma-local 本地左移验证职责不重叠。

<a id="req-003"></a>
### REQ-003 本地左移验证与远端准出边界

- gamma-local 必须覆盖 `local_contract -> api_integration -> user_acceptance` 的本地可验证链路，但不得替代 prod gray-initial 的远端准出证据。
- 本地 `user_acceptance` runner 统一 App 与测试进程 endpoint，至少在一台模拟器或真机完成 Patrol 核心旅程。
- gamma-local 服务名册与 prod `runtime.yaml` 及各服务真实环境部署目录一致。
- recommendation 对外 DNS 名各环境统一为 `recommendation-service:8000`
- 由统一架构门禁守护。
- `realtime-gateway` 作为第一方 workload 纳入 topology 与 `edge-media` 验证链，禁止 pending/registered-only 占位进入 gamma/prod。
- gamma-local 由 Ops infra/external Compose 与各第一方服务自治 Compose 片段共同承载；`profiles` 只表达按需运行能力，不承担服务注册。
- 对外 DNS 名与 prod 对齐：recommendation 服务在各环境统一以 `http://recommendation-service:8000` 被调用。
- edge-media 名册与 prod 目录扫描结果一致：`realtime-gateway / rtc-service / livekit / coturn` 必须由真实 compose/Kustomize 入口承载。

## 4. 契约引用

- canonical：`quwoquan_ops/environments/gamma/validation_suites.json`
- canonical：`quwoquan_app/scripts/gamma/verify_local_gamma_mirror.py`
- canonical：`quwoquan_service/contracts/metadata/_shared/test_fixtures/app_gamma_seed_manifest.json`
- canonical：`quwoquan_ops/environments/compose/docker-compose.gamma-local.yaml` 与 `quwoquan_service/services/*/deploy/compose.yaml`
- canonical：`quwoquan_ops/environments`
- canonical：`quwoquan_ops/gate/verify_service_architecture.py`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 gamma-local 提交前左移主验证链

- GIVEN 开发机具备 Docker mirror 栈与至少一台模拟器/浏览器 runner。
- GIVEN 服务以 APP_ENV=gamma 启动，端侧以 APP_RUNTIME_ENV=gamma、APP_DATA_SOURCE=remote 接入本地 mirror endpoint。
- GIVEN 测试数据仅来自 app_gamma_seed_manifest.json 与 metadata fixtures。
- WHEN 提交前运行 make gate-local-gamma。
- THEN 启动 gamma 语义镜像栈并完成 CONFIG_VERSION/依赖/health/DNS/TLS/media 前置检查。
- THEN 依次执行 local_contract->user_acceptance 并生成 artifacts/local-gamma/report.json；缺 DNS/TLS/设备/服务依赖时状态为 GATE_BLOCK。
- THEN full health 覆盖 platform-ops、content、user、Elasticsearch 与 proxy；受保护 user route 经 canonical Caddy 上游抵达 user-service。
- THEN 复用 package 时的 image 缺失在启动前失败并给出修复动作，而非运行时拉取或人工 image tag 修补。

<a id="gwt-002"></a>
### GWT-002 远端复验只在 prod gray-initial 执行

- GIVEN gamma-local 已作为提交前主验证链，gamma 仅本地、无远端 gamma。
- WHEN 需要云侧手动复验、nightly 或发布前高置信度回归时，统一在 prod gray-initial rollout stage 执行。
- THEN prod gray-initial 执行 hosted deploy、readiness、api_integration API contract、assistant/chat-avatar probe。
- THEN 远端复验不承担提交前左移职责，也不与 gamma-local 重复维护第二套验证逻辑。

## 6. 依赖

- 前置要求：[`deliver-deploy-prod-pipeline`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 gamma-local 提交前左移主验证链

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：gamma-local 是开发与提交前的主验证链，统一本机模拟器/浏览器接入同一组域级入口。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 prod gray-initial 远端复验证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：真实远端复验只允许在 prod `gray-initial` rollout stage 产生，不能用 gamma-local 证据替代。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效
