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
### REQ-001 exact candidate环境链与RC包接受

- 同一 integration candidate 必须绑定 source capsule、commit/tree、ContractGraph、ImpactPlan 与 toolchain；Alpha/Beta 在 ref 更新前消费该身份，Gamma 在 `dev1.0` 更新后只接受完全相同的 current head。
- Alpha必须先完成；Beta仅在typed高风险impact要求时执行，并在首个mutation前验证Alpha exact bytes。trusted publisher只消费Alpha/Beta，通过CAS后Gamma在首个mutation前验证dev CAS receipt与前驱事实。
- 三环境可并行进行无副作用的package预取与静态校验；任何Data mutation、activation、App UAT与passed fact必须按`alpha -> beta -> dev CAS -> gamma`执行。任一失败或superseded均安全teardown且不产生后继资格。
- 每个环境只写统一`EnvironmentAcceptanceFact`，绑定实际target CaseResult、runtime identity、Data lifecycle、Provider、observability、inspect/doctor、cleanup和lease closure；`workflow success`、App envelope、旧green matrix或并行后排序均不能替代。
- 只有RC tag才封存nonprod/prod App与Cloud组件、Web bundle及四环境配置composition并build/sign once；RC package acceptance只验证最终包特有风险和物理设备，不重跑Alpha/Beta/Gamma业务矩阵。
- Prod只消费stable tag AdmissionFact绑定的同一qualified RC digests，并在一次事务中完成rollout；stage推进不改变组件、配置composition、ContractGraph或release composition identity。

## 4. 契约引用

- environment：`quwoquan_ops/environments/alpha`
- environment：`quwoquan_ops/environments/beta`
- environment：`quwoquan_ops/environments/gamma`
- environment：`quwoquan_ops/environments/prod`
- canonical：`quwoquan_ops/environments/prod/rollout/stages.yaml`
- canonical：`quwoquan_ops/environments/gamma/validation_suites.json`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 exact candidate环境链与包复用

- GIVEN 一个尚未发布到dev的exact candidate及其typed ImpactPlan。
- WHEN 执行环境准入、dev CAS、Gamma、RC资格与Prod发布。
- THEN mutation与passed facts严格按Alpha、conditional Beta、dev CAS、Gamma推进，且每个后继验证前驱exact bytes；失败、漂移或superseded不会产生后继资格。
- AND RC只构建签名一次，最终包/物理设备接受与ABG不重复同一CaseResult；stable与Prod复用选中RC完全相同的build number和digests。
- AND 任一环境fact缺CaseResult、lifecycle、Provider、inspect/doctor、cleanup、lease closure或正确predecessor时fail closed，且不存在旧green matrix或workflow success替代。

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
