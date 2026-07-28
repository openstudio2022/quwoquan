# L3 Story：零风险风险生产就绪 (`zero-risk-production-readiness`)

> 所属能力：[`commercial-readiness-risk-closure`](../spec.md)
>
> Journey / Scenario：横切工程能力；由父 L2 spec 参与 AppRoot Journey。
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为平台运维、安全或审核角色，我希望执行 RP1-RP7；仓内风险全部解决、外部前置条件真实满足后才允许 production release，从而获得可审计且可回滚的平台治理结果。

## 2. 范围与非目标

### In Scope

- 身份双签、遥测日志、供应链、灰度回滚、观测灾备、配置数据和验收清零
- local_contract、api_integration、user_acceptance 与 stackctl release 证据

### Out of Scope

- 伪造外部凭据、法务主体、IdP、GitHub entitlement 或 prod-hosted 结果

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 任一未解决风险阻断生产发布

- 缺失项逐一有稳定错误与修复指引，发布不能继续。

<a id="req-002"></a>
### REQ-002 全部风险关闭后完成不可变灰度与恢复验证

- stackctl release report、health/inspect/doctor、rollback/restore receipt 均可复验。

<a id="req-003"></a>
### REQ-003 第一方容器预验证不可提升为生产发布证据

- `prod-hosted` 可在独立 namespace 消费 reviewed main 的 Service Pipeline digest 制品，验证第一方容器、隔离空数据栈和 rootless user systemd 持久运行。
- ReleaseManifest 配置包必须从 GHCR OCI digest 解包；Actions Artifact 配额不足不得诱发部署时重生、`latest` 或跳过制品门。
- 受限单机只能按清单回收未运行旧容器和未使用镜像；Buildah external working container 仅在 `storage`、`PID=0`、名称与最小年龄全部命中时可回收。必须保留恢复容器与所有 volume，并在镜像传输前重新证明真实可用空间。
- 预验证不得接受 rollout/SLO/rollback 参数，不得读取或写入正式 release ledger/receipt；容器部署结果与正式发布资格必须分别报告。
- 隔离投影不得继承正式 credentials；商业登录、Push、模型、SLS 与 RTC Provider 只能明确 unavailable，禁止切到非生产 fixture 或 Mock。
- 缺 Provider、SFU/TURN、正式数据、观测、灾备、DNS/TLS 或灰度回滚证据时，正式发布资格始终保持 `GATE_BLOCK`。

## 4. 契约引用

- canonical：`specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md`
- canonical：`specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/design.md`
- canonical：父能力 [`OPEN`](../spec.md#8-开放事项) 与动态 `make feature-tree-overview` 输出
- canonical：`quwoquan_ops/environments`
- canonical：`quwoquan_ops/environments/prod/access-isolation.yaml`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 任一未解决风险阻断生产发布

- GIVEN 风险门读取目标父链 OPEN、外部前置审计和真实测试结果。
- WHEN 任一 RP 未完成，或 IdP/GitHub protection/法务主体/prod 凭据不可验证。
- THEN pre-release 与 deploy workflow fail-closed。
- THEN 不存在 warn-only、skip、allowlist 或风险豁免参数。

<a id="gwt-002"></a>
### GWT-002 全部风险关闭后完成不可变灰度与恢复验证

- GIVEN RP1-RP7 全部完成，外部前置条件真实可用。
- WHEN 运行 gray-initial、carry-on、full、告警闭环和隔离恢复演练。
- THEN 三阶段使用同一 ReleaseManifest digest。
- THEN 真实 Prometheus SLO、锁/CAS、双签、config ACK、告警与恢复证据完整。
- THEN 本 Story 范围内所有阻断级 `OPEN` 均达到完成判定，且不存在未归属风险。

<a id="gwt-003"></a>
### GWT-003 不可提升的第一方容器预验证

- GIVEN reviewed main 的 deployable ReleaseManifest、GHCR digest、四平面 SSH key 与满足阈值的 prod-hosted 主机。
- WHEN 执行 `stackctl deploy --target prod-hosted --mode prevalidate --prevalidate-scope first-party`。
- THEN 镜像传输前硬校验账号隔离、CPU、内存、容器空间、架构与端口，任一不足即 `GATE_BLOCK`。
- THEN 当前可用空间、可回收空间和回收后实测空间分别可见；Buildah external working container 只有在 `storage`、`PID=0`、名称与最小年龄全部匹配时才进入回收范围，任何 volume、恢复容器或运行中容器都不进入回收范围。
- THEN `integration-service` 只校验镜像和配置而不启动，LiveKit SFU、Coturn 与外部 Provider 不进入运行投影。
- THEN service/edge user systemd unit 为 enabled/active，运行容器 digest 与 manifest 交付内容一致；隔离数据无 seed、无正式数据且不构成发布证据。
- THEN container runtime 与 Provider readiness 分轴输出；被排除的 SLS 等 readiness 保持 `GATE_BLOCK`，不得污染第一方镜像/进程部署结论。
- THEN 报告可将第一方容器部署标为 passed，但正式发布资格仍为 `GATE_BLOCK`，且 hosted release ledger/receipt 均未写入。

## 6. 依赖

- 前置要求：[`commercial-readiness-risk-closure`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 任一未解决风险阻断生产发布

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：缺失项逐一有稳定错误与修复指引，发布不能继续。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 全部风险关闭后完成不可变灰度与恢复验证

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：stackctl release report、health/inspect/doctor、rollback/restore receipt 均可复验。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效
