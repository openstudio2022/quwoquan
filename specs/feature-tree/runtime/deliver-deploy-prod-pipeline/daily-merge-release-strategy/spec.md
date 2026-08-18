# L3 Story：每日合并发布策略 (`daily-merge-release-strategy`)

> 所属能力：[`deliver-deploy-prod-pipeline`](../spec.md)

> Journey / Scenario：横切工程能力；由父 L2 spec 参与应用交付与发布验收。

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，
我希望所有日常开发直接进入 `dev1.0` 稳定集成、`main` 承接唯一发布，并在 promotion 后由系统回同步，
从而获得可审计、可恢复且不会把未晋级代码送入 Prod 的交付结果。

## 2. 范围与非目标

### In Scope

- `dev1.0` 集成分支与 `main` 发布分支的唯一角色、唯一合法 PR 边以及任何其他分支的禁令。
- 人工 direct push、PR head/base、系统 fast-forward backsync 与 Prod source admission 的可观察准入结果。
- 非法边、非 fast-forward、远端状态不可证明与 SHA 不可达 `main` 时的 fail-closed 终态。
- GitHub 托管 refs、branch protection/ruleset 与 system actor 权限的只读 readback 和当前有效性证明。

### Out of Scope

- hook、workflow、GitHub ref 与发布脚本的具体实现；由本 Story 的验收约束实现，不在规格复制代码。
- GitHub 原生 branch protection/ruleset 与系统 App 权限的创建或变更。
- 历史分支迁移、真实环境部署、Prod rollout，以及 `quwoquan_data/**` 的任何代码、内容或发布工作。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 每日合并发布策略

- **分支角色**：本地与远端只允许 `dev1.0` 与 `main`；`dev1.0` 是唯一集成真相源并接受日常直接开发，`main` 是唯一发布真相源。任何临时分支或第三长期分支均非法。
- **工程归属**：本 Story 拥有集成、晋级、回同步与发布来源的可观察行为；`platform-ops-governance` 拥有 `quwoquan_ops/policies/branch_policy.yaml` 及其 gate/hook 的机器实现，机器实现不得改写本 Story 的行为语义。

<a id="req-002"></a>
### REQ-002 集成、晋级与回同步准入

- **集成主路径**：开发者只在 `dev1.0` 提交并直接推送；同一精确 SHA 的 required integration checks 全部成功后，`dev1.0` 成为该增量的集成终态。失败提交只能在 `dev1.0` 追加修复，不得创建临时旁路分支。
- **发布主路径**：release actor 只从 `dev1.0` 创建以 `main` 为 base 的 promotion PR；required promotion checks 全部成功并合入后，`main` 成为该增量的发布终态。
- **合法 PR 边**：只允许 `dev1.0 -> main`；任何其他 PR、人工 `main -> dev1.0`、缺失 head/base、临时分支和第三长期分支全部拒绝。
- **失败身份**：policy/schema 无效为 `OPS.BRANCH.POLICY_INVALID`，PR 边或 ref 非法为 `OPS.BRANCH.REF_NOT_ALLOWED`，人工 direct push 为 `OPS.BRANCH.DIRECT_PUSH_NOT_ALLOWED`，非 fast-forward 为 `OPS.BRANCH.BACKSYNC_NOT_FAST_FORWARD`，compare-and-swap 漂移为 `OPS.BRANCH.BACKSYNC_CAS_CONFLICT`，Hosted/Git authority 不可读为 `OPS.BRANCH.AUTHORITY_UNAVAILABLE`，Prod source 不可达 `main` 为 `OPS.BRANCH.SOURCE_NOT_MAIN_REACHABLE`；OID、ref、actor 与远端诊断只进入 string context。
- **direct push 边界**：人工/API token 只允许从匹配的本地 `dev1.0` 更新远端 `dev1.0`，该动作只取得 integration evidence，不具备 release eligibility。`main` direct push 始终拒绝；Actions 与 release governance 必须拒绝缺少合法 promotion 事实的 SHA，在缺少 GitHub 原生保护时不得声称远端 ref 一定未被先行修改。
- **系统回同步**：promotion 成功后，系统只能以 compare-and-swap 的无 force fast-forward 将 `main` 回同步到 `dev1.0`。两者相等时幂等成功。`dev1.0` 为 `main` ancestor 时允许推进。分叉、`main` 落后、采样后 ref 漂移或 ancestry 不可证明时返回 blocker，ref 保持采样后已确认状态且不得创建临时分支、force、自动 merge 或改写历史。
- **发布来源**：Prod source 必须是格式精确、可达可信 `origin/main` 且绑定唯一已合并 `dev1.0 -> main` promotion 的 Git SHA；只存在于 `dev1.0`、无法证明 ancestry 或 workflow definition 不来自 `refs/heads/main` 时不得进入发布门。
- **正式 Prod 边界**：`main` push 只生成发布验证，不执行正式 Prod apply；正式 apply 的 approval、凭据、rollout 与回滚由父 L2 和 `gray-release-to-prod` 拥有，本 Story 只拥有进入该发布门之前的 branch/source admission。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。
- 机器合同：`quwoquan_ops/policies/branch_policy.yaml`。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 集成与发布 PR 边

- GIVEN policy 声明仓库只允许 `integration=dev1.0`、`release=main`，短期前缀为空，且输入包含完整 event、actor、head/base 与 ref OID。
- WHEN gate 评估长期 refs、PR 或 direct push 的准入。
- THEN 只接受匹配的 `dev1.0` direct push 与 `dev1.0 -> main` PR，并只把 `dev1.0`、`main` 识别为仓库分支。
- AND 任何临时/第三分支、其他 PR 边、人工 `main -> dev1.0`、缺失 head/base、`main` direct push、非匹配来源对 `dev1.0` 的更新以及非受管 backsync 均返回 typed blocker；不得生成 promotion receipt、candidate 或 Prod apply 成功事实，`GWT-002` 的系统 backsync 是唯一额外 ref 同步例外且不产生 release eligibility。

<a id="gwt-002"></a>
### GWT-002 系统 fast-forward backsync

- GIVEN promotion 已成功，系统取得 `main`、`dev1.0` 的可信 before OID 与当前 readback。
- WHEN 受管系统身份请求 `main -> dev1.0` backsync。
- THEN 两 ref 相等时幂等完成，或仅在 `dev1.0` before OID 是 `main` OID 的 ancestor 且 CAS 未漂移时执行无 force fast-forward，并回读 exact after OID。
- AND 人工调用、错误 ref、force/non-fast-forward、分叉、ancestry 不可证明、权限/网络不可确认或 compare-and-swap 竞态全部 `GATE_BLOCK`，禁止覆盖、自动 merge 或伪造成功回执。

<a id="gwt-003"></a>
### GWT-003 Prod main reachability

- GIVEN 输入是精确 Git SHA、可信 `origin/main`、候选身份和已合并 promotion 事实。
- WHEN Prod source admission 在任何 Prod credential 或 canary 操作前评估候选。
- THEN 仅当 source SHA 可达 `origin/main`、绑定唯一已合并 `dev1.0 -> main` promotion 且 workflow definition 来自 `refs/heads/main` 时允许进入父能力发布门。
- AND dev1-only SHA、格式或对象类型错误、ancestry 不可证明、错误 workflow ref 或缺 promotion binding 时返回 `OPS.BRANCH.SOURCE_NOT_MAIN_REACHABLE` 或对应 branch blocker，不创建 candidate eligibility、部署或晋级成功事实。

## 6. 依赖

- 前置要求：[`deliver-deploy-prod-pipeline`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 每日合并发布策略 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：尚缺真实 `dev1.0` push checks、`dev1.0 -> main` PR/check、非法 ref/边负例、promotion 后系统 CAS fast-forward backsync、仅含两个 GitHub heads 的权威清单与干净 clone 复现回执。
- 完成判定：`GWT-001.t1..t2` 与 `GWT-002.t1..t2` 具备 decision-table local contract。真实 Git integration 证明退出类型、CAS 与 ref before/after。当前最终 SHA 的 hosted readback 证明 direct dev push checks、promotion PR/check、system actor 与 refs 精确为 `dev1.0/main`。

<a id="open-002"></a>
### OPEN-002 private-free GitHub 托管分支保护

- 类型：`external_blocker`
- 优先级：`P0`
- 准出影响：`block`
- 阻断边界：仅阻断 `formalProd` 与“GitHub 原生保护已闭合”声明；不阻断已由 Hosted API 精确证明的 promotion source validation。
- 影响或价值：仓内 hook/Actions 不能冒充服务端保护。当前 source admission 必须逐次从 Hosted API 证明 exact merge SHA、最终 `dev1.0` head、绑定该 head 的 approval、canonical required workflow run/attempt/check identity、当前 main reachability、repository default branch 与当前 workflow attempt；`dev1.0` direct push 因缺唯一 promotion binding固定不具备 release eligibility。托管 ruleset 的适用条件、bypass actor 与 required check readback 未精确闭合前，不能签发正式 Prod。
- 完成判定：`GWT-002.t1..t2` 与 `GWT-003.t1..t2` 的 GitHub refs、适用 ruleset/branch protection 与 system actor 权限均由托管 API readback 证明；在此之前 `hostedProtectionVerified=false / formalProd=false` 保持不变。
