# L2 Design：商用就绪风险收口 (`commercial-readiness-risk-closure`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“运维运营平台只有在仓内风险已解决且外部前置条件真实满足时才能进入生产；不接受风险豁免或伪造证据”需要 `zero-risk-production-readiness` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：运维运营平台只有在仓内风险已解决且外部前置条件真实满足时才能进入生产；不接受风险豁免或伪造证据。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`zero-risk-production-readiness`](./zero-risk-production-readiness/spec.md)：缺失项逐一有稳定错误与修复指引，发布不能继续。

## 3. 端云与数据流

- 上游能力：[`platform-ops-governance`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- canonical 引用：`quwoquan_service/contracts/metadata/_shared/runtime_observability.yaml`、`quwoquan_service/services/product-ops-service/contracts/product_ops/event_record/event_catalog.yaml`、`quwoquan_service/contracts/metadata/_control_plane/portal_menu.yaml`、`quwoquan_service/contracts/metadata/_control_plane/platform/control_plane.yaml`、`quwoquan_service/contracts/metadata/_control_plane/product/control_plane.yaml`、`quwoquan_ops/policies/branch_policy.yaml`、`.github/workflows/service_pipeline.yml`、`.github/workflows/deploy-prod-auto.yml`、`quwoquan_ops/environments/prod/rollout/stages.yaml`、`quwoquan_ops/policies/config-release/slo_thresholds.yaml`、`quwoquan_ops/observability/monitoring/docker-compose.prod.yml`、`quwoquan_ops/observability/monitoring/alerts/quwoquan_alerts.yaml`、`quwoquan_ops/environments/prod/rollout/routing_policy.yaml`、`quwoquan_service/control-plane/platform-ops/contracts/platform_ops/config_snapshot/operations.yaml`
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 商用准出由可验证证据和阻断级 OPEN 共同裁决
- 决策：商用准出由可验证证据和阻断级 OPEN 共同裁决。
- 理由：运维运营平台只有在仓内风险已解决且外部前置条件真实满足时才能进入生产；不接受风险豁免或伪造证据。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`zero-risk-production-readiness`](./zero-risk-production-readiness/spec.md)
- 关联验收：`SIT-001`

<a id="dec-002"></a>
### DEC-002 灾备准出只信任 hosted 隔离恢复 receipt
- 决策：灾备准出只接受由受控 data-plane 工作流生成、并绑定计划摘要与恢复目标的
  hosted receipt；本机 dump、CI 合成文件和页面手工输入均不得作为生产证据。
- 理由：备份文件存在无法证明加密、异地副本、可恢复性和 RPO/RTO。release 必须对
  receipt 的内容摘要、KMS key version、远端副本状态、隔离恢复目标、恢复耗时和
  容量成本水位 fail-closed。
- 被否决方案：把 `/var/backups` 的 gzip dump、默认 localhost 连接或过期报告作为
  release green 条件。
- 约束与影响：receipt 仅保存引用、摘要和脱敏状态；签名或远端操作身份由 hosted
  authority 证明。缺少受控 data-plane/KMS/云存储权限时，production workflow 必须阻断。
- 关联要求：`REQ-005`
- 影响 Story：同 DEC-001，约束 [`zero-risk-production-readiness`](./zero-risk-production-readiness/spec.md) 的灾备准出。
- 关联验收：`SIT-005`

<a id="dec-003"></a>
### DEC-003 第一方容器预验证与正式 release transaction 物理分轨

- 决策：预验证与正式 release transaction 使用物理隔离的运行面和证据链。
  - 预验证只使用独立 Compose project、远端目录和 rootless user systemd unit。
  - 预验证只消费 Service Pipeline 发布到 GHCR 的 OCI digest 制品。
  - 预验证不得进入 rollout lock、SLO、正式 release ledger 或 receipt。
  - 受限单机使用声明式容器内存和 PID 上限。空间门同时校验当前可用量、可回收量与回收后实测量。
  - Actions Artifact 只保存短生命周期失败诊断，且诊断上传不得影响原始门禁结论。
  - Actions cache 不是发布输入：PR 只读默认分支的依赖缓存，不得写入按 PR ref 隔离的副本；历史或未来遗留的 PR merge-ref 缓存在 PR 关闭时按精确 ref 自动删除；Service Pipeline 继续审计成功运行中的意外 Build Record。
  - main 只触发 OCI 制品生产，不自动启动正式 rollout；正式 rollout 必须由人工 dispatch 绑定成功 main Service Pipeline run，且默认 dry-run。第一方 prevalidate 继续只经 stackctl deploy mode=prevalidate 执行。
  - SSH 管理 endpoint 只在 `access-isolation.yaml.management` 声明；`runtime.yaml` 及其 App package 投影只含 canonical HTTPS/WSS public base，禁止携带管理 IP。
  - 主线 Service Pipeline 固定使用仓库注册的 `self-hosted/macOS/ARM64` runner；Go builder 基镜像固定为多架构 OCI index digest，以 `BUILDPLATFORM` 原生执行工具链并显式向 `TARGETOS/TARGETARCH` 交叉编译，QEMU 只执行 linux/amd64 最终运行层装配，避免模拟 Go runtime 的不稳定性。GitHub-hosted 预算不可用不得改变 GHCR digest、SBOM、provenance 或 manifest 契约；每个 Go job 在 runner 启动后的 step 使用 `RUNNER_TEMP` 设置可变 cache，禁止在 job-level `env` 引用尚不可用的 `runner` context，checkout 不清理未受版本控制的运行输出。Docker 凭据与构建状态按 job 隔离时，先从宿主当前 context 保存并校验 daemon endpoint，再切换隔离 `DOCKER_CONFIG`，禁止回退到未运行的默认 socket。Delivery Gate 校验受控宿主 Python 版本后，为 Service 与 Data job 分别在 `RUNNER_TEMP` 创建隔离 venv，避免 macOS `setup-python` 子安装器回落到不可写的 `/Users/runner` 或改写系统 framework，也不保留长期工具缓存。
  - Prod runtime 基镜像固定为仍受支持的 Alpine 3.22 digest，依赖安装必须保留包索引签名校验；不得以 `--allow-untrusted` 绕过供应链失败。
  - Recommendation 使用固定 digest 的官方 Python 3.11 slim-bookworm 多架构索引；Dockerfile 已显式安装唯一缺失的 `libgomp1`，不需要携带完整 Python 开发基镜像及其 236 MB 单层。
- 理由：在 Provider、SFU、真实数据和公网入口尚未就绪时，仍需验证第一方容器可部署性，但该结果不能被误用为生产准出。
- 被否决方案：使用 `latest`、远端临时构建、旧容器、裸 IP public base，或把容器启动成功写成正式发布成功。
- 约束与影响如下。
  - 隔离数据使用重新摘要的不可提升配置投影和独立随机认证材料。unit 不得继承正式 credentials。
  - ReleaseManifest 配置包和镜像均以 GHCR digest 消费。Actions Artifact 不是成功 job 间传递或正式发布证据。
  - 旧运行面回收只允许匹配声明前缀且处于 `Created/Exited` 的容器和未使用镜像。禁止删除任何 volume 或恢复容器。
  - prod-hosted 当前系统 Python 3.6 是远端预检脚本的最低运行基线；inline 脚本使用 `universal_newlines` 等兼容接口，宿主侧编排可继续使用受控本机 Python。
  - 报告必须并列输出 container runtime、Provider readiness 与 release eligibility。后两者在完整生产证据前固定为 `GATE_BLOCK`。
- 制品生命周期约束如下。
  - Actions Artifact 只可保存有明确保留期的失败诊断。路径只能包含需要复验的 `summary.json`、`report.json` 或失败日志。
  - 取消运行不得上传。成功对象须由受控生命周期任务在完成后立即删除，失败对象超过诊断窗口后逐个删除。
  - `docker/build-push-action` 的自动 build record 上传必须显式关闭；受控清理发现历史 `.dockerbuild` record 时必须立即删除。未声明容量与回收策略的 Buildx GHA layer cache 不得启用。它们都不是 release evidence，不能取代 GHCR digest。
  - 不可变发布包、SBOM、provenance 与回滚所需镜像保持 GHCR digest 引用，并按已引用 release manifest 保留。
- 关联要求：`REQ-009`
- 影响 Story：在 [`zero-risk-production-readiness`](./zero-risk-production-readiness/spec.md) 中约束预验证与正式准出分轨。
- 关联验收：`SIT-008`、`GWT-003`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 准出结果必须同时绑定主体、危险动作审批、供应链摘要、配置 revision、验收证据和受影响范围。
- 外部前置缺失以 `external_blocker` OPEN 表达并阻断对应 production workflow；不得用豁免或合成证据放行。
- 证据至少包含最后一份 SLO snapshot、approval receipt 与 rollback receipt，且只保存引用、摘要和脱敏状态。
- 生产观测通过 Prometheus、Alertmanager、OTel 及声明的节点、容器和数据存储 exporter 提供真实数据。
