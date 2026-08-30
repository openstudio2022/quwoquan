# L3 Story：多环境波次部署 (`multi-environment-wave-deployment`)

> 所属能力：[`deliver-deploy-prod-pipeline`](../spec.md)

> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，
我希望同一 source release train 先封存按 nonprod/prod 信任域构建的不可变组件，再为 alpha、beta、gamma、prod 组合各自配置并按准入顺序验证，任一波次失败即停止晋级，
从而确保未变字节按 digest 复用、环境差异在装配期可审计，且维护者能以精确组件与环境配置定位和恢复失败。

## 2. 范围与非目标

### In Scope

- “多环境波次部署”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 多环境波次部署

- 同一 `releaseTrainId` 必须贯穿 Alpha、Beta、Gamma-local 与 Prod，并绑定同一 source capsule、ContractGraph 和 toolchain。每个环境拥有独立 `environmentArtifactDigest`，其投影由兼容信任域的组件 digest 与本环境 configuration、Provider binding、endpoint authority、runtime topology 摘要组成。
- `candidate-ready` 必须在环境验证前一次性封存 Android nonprod/prod、iOS nonprod/prod、单一 Web bundle 与 Cloud nonprod/prod 组件，并为四环境封存配置 composition。Alpha、Beta、Gamma 必须引用同一 nonprod App bytes 及同一 owner 的 nonprod Cloud digest，Prod 引用 prod digest。进入波次后不得重新构建、codegen 或替换其中任一输入。
- Alpha、Beta、Gamma-local 可以在隔离 runner 并行执行配置 package、镜像预取与静态校验。任何 Data mutation、activation、App UAT 或 passed acceptance receipt 必须严格按 `alpha -> beta -> gamma -> prod` 执行，任一失败即停止下一环境首个 mutation。
- Gamma-local 是正式阻断阶段，不由旧 nightly 或其他候选摘要的证据替代；仓库不新增 `gamma-hosted`。
- 三个前置环境全部通过后，Prod 才能进入同一个受审批事务 job，并按 `canary -> 5 -> 20 -> 50 -> 100` 晋级。
- 每个环境 acceptance receipt 必须同时绑定 Data release tuple、runtime candidate tuple、实际 target-scoped App CaseResult、lifecycle Exit、Provider、观测、inspect/doctor 与 cleanup。Beta、Gamma、Prod receipt 必须额外绑定前一环境 acceptance receipt 的 exact-byte digest；`appUatEnvelopeDigest`、workflow job success 或并行运行后的排序拼接均不能替代。
- 四环境回执从各自 raw package/up/health/verify/import/readback/UAT/cleanup 生成并发布为不可变 OCI；Actions Artifact 只能保留诊断副本，不能作为环境间晋级输入。
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
- THEN 按 alpha、beta、gamma、prod 的准入顺序验证同一 release train 下的环境 composition，任一波次失败即停止晋级。
- AND 配置 package、镜像预取与静态校验可并行，但环境 mutation、App UAT 和 passed receipt 严格串行。每个回执同时绑定共同 `releaseTrainId`、自身 `environmentArtifactDigest`、组件 build profile 与配置摘要。
- AND Alpha、Beta、Gamma 回执引用相同 nonprod App bytes digest 与同一 owner 的 nonprod Cloud digest，Prod 引用独立 prod digest。交换 profile、配置或 binding 必须在 mutation 前 fail closed。
- AND 四份 acceptance receipt 绑定同一 release train 与同一 Data release 身份，Beta、Gamma、Prod 分别绑定前一环境 receipt 的 exact-byte digest。
- AND App 五个真实 build-profile shard 的实际最长 job 时长进入 Delivery Gate 关键路径，四环境 UAT 不触发重复 App 编译。
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
- 影响或价值：尚缺四环境 acceptance receipt 的 predecessor、Data lifecycle、实际 App CaseResult、Provider、观测与 cleanup 单轨实现及真实顺序证据；当前并行环境 job 后排序接纳不能证明 mutation 严格串行。
- 完成判定：`GWT-001` 由 receipt/schema 的 `local_contract`、真实四环境 lifecycle/import/readback 的 `api_integration` 与同一 candidate/release 的顺序 App `user_acceptance` 直接覆盖，任一前驱或 exact-byte digest 漂移均在下一环境 mutation 前 fail closed。
