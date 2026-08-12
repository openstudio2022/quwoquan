# L3 Story：多环境波次部署 (`multi-environment-wave-deployment`)

> 所属能力：[`deliver-deploy-prod-pipeline`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，
我希望按 alpha、beta、gamma、prod 的准入顺序发布同一制品，任一波次失败即停止晋级，
从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- “多环境波次部署”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 多环境波次部署

- 同一 `ReleaseEvidenceManifest.candidateId` 必须贯穿 Alpha、Beta、Gamma-local 与 Prod，禁止在环境间重新生成候选身份。
- `candidate-ready` 必须由同一 Service component、四环境 configuration package、四环境 App 实际 payload、ContractGraph、真实 Provider readiness 和三层测试摘要共同派生；环境阶段不得重新打包或替换其中任一输入。
- Alpha、Beta、Gamma-local 可以在隔离 runner 并行执行 package/up/health/verify；准入聚合必须严格按 `alpha -> beta -> gamma` 接受回执，任一失败即停止晋级。
- Gamma-local 是正式阻断阶段，不由旧 nightly 或其他候选摘要的证据替代；仓库不新增 `gamma-hosted`。
- 三个前置环境全部通过后，Prod 才能进入同一个受审批事务 job，并按 `canary -> 5 -> 20 -> 50 -> 100` 晋级。
- Alpha/Beta/Gamma 回执必须从各自 raw package/up/health/verify（Beta 另含 Android/iOS 设备矩阵）生成并发布为不可变 OCI；Actions Artifact 只能保留诊断副本，不能作为环境间晋级输入。
- 主链软目标为 600 秒、硬门为 1800 秒；workflow 创建后达到 1500 秒时禁止开始下一波次，为恢复预留 300 秒。
- `CiTimingSummary` 必须从 GitHub job DAG 采集真实矩阵长尾和排队时间；证据缺失时返回 `historical_incomplete`，不得填零或假绿。

## 4. 契约引用

- environment：`quwoquan_ops/environments/alpha`
- environment：`quwoquan_ops/environments/beta`
- environment：`quwoquan_ops/environments/gamma`
- environment：`quwoquan_ops/environments/prod`
- canonical：`quwoquan_ops/environments/prod/rollout/stages.yaml`
- canonical：`quwoquan_ops/environments/gamma/validation_suites.json`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 多环境波次部署

- GIVEN 开发、测试或运维角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“多环境波次部署”对应的公开行为。
- THEN 按 alpha、beta、gamma、prod 的准入顺序发布同一制品，任一波次失败即停止晋级。
- AND Alpha、Beta、Gamma-local 的隔离并行执行不改变准入顺序，且每个回执均绑定同一 candidate digest。
- AND App 四个测试 shard 的实际最长 job 时长进入 Delivery Gate 关键路径。
- AND 达到 1500 秒后不会开始下一阶段，超过 1800 秒时发布门禁失败。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

## 6. 依赖

- 前置要求：[`deliver-deploy-prod-pipeline`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 多环境波次部署 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“多环境波次部署”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效。
