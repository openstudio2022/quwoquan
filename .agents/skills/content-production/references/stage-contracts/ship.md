# 阶段契约：ship

AI 显式执行 Data-owned apply、readback/health 与所需 API consumer checks；不存在 gate registry、自动 terminal reducer 或 Data-owned `EnvironmentAcceptanceFact` writer。

## PRE

- `release` CLOSE 为 pass。
- OPEN 显式冻结 Data release identity（供 `ship` 命令消费的 releaseId/releaseDigest）、environment/target、import/verify run identities、所需环境 owner refs，以及可选的内容 consumer-check intent。
- `m1_api_consumer` 只允许作为选择 Alpha 服务/API consumer raw `ReadinessCaseResult` 的内容执行意图；它不是 EAF profile、EAF 字段或 writer 名称。
- 若调用方另需 EAF，OPEN 只冻结用于 HANDOFF 的同一 exact integration candidate Environment Ops scheduler request；Data ship 不据此签发 acceptance。

## DURING

AI 按顺序显式调用并记录 exact facts：

1. `ship apply` 导入同一 immutable release；
2. `ship verify` 和对应环境 readback/health；
3. 内容交付确有需要时 activate；
4. 逐 cell 执行本次内容 intent 要求的真实 API consumer checks，并保留 raw canonical `ReadinessCaseResult`；
5. 结束 Data ship，不调用任何 EAF builder、writer 或 append 接口。

`m1_api_consumer` intent 只选择 Alpha 服务/API consumer 的 entry surface × carrier 16-cell fresh raw facts；不得把它映射成 EAF profile，也不得用 fixture、旧 receipt、counts 或另一 candidate/release 的事实代替。

若下游要求 EAF，AI 仅向 Environment Ops HANDOFF 同 candidate request 与 current raw CaseResult exact refs。Environment Ops scheduler 是唯一 producer；它只为 `alpha|beta|gamma` 使用 canonical `profile=smoke|integration|release`，且不得从内容 intent 省略 v2 closure。

## POST

逐条运行当前 Data ship 与 consumer-check intent 适用的真实环境 verifier。基础环境动作使用：

```bash
python3 quwoquan_data/scripts/cli.py ship apply --release-id <releaseId> --env <env> \
  --run-id <importRunId> --import --full-sync
python3 quwoquan_data/scripts/cli.py ship verify --release-id <releaseId> --env <env> \
  --import-run-id <importRunId> --run-id <verifyRunId> --readiness-phase <phase>
```

`m1_api_consumer` intent 只附加 Alpha 服务/API consumer health 与 16-cell raw CaseResult。AI 逐条绑定真实 argv/exit/ref/digest，在 CLOSE 中显式提交 pass/blocked；内核只重验 facts，不派生 END、succeeded 或 EAF。

若另行请求 EAF，Environment Ops scheduler 必须基于同一 candidate request 验证非空且去重的 `caseResultRefs`，以及 8 个互异 exact named closure refs：`runtimeIdentity`、`dataLifecycle`、`providerReadiness`、`observabilityReadiness`、`inspectEvidence`、`doctorEvidence`、`cleanupEvidence`、`leaseClosureEvidence`；同时闭合 exact `candidate`、`impactPlanDigest`、Alpha/Beta/Gamma `predecessor`、`expiresAt`、`nonPromotable` 与 DSSE `signer` 后才能签发 `EnvironmentAcceptanceFact` v2。EAF v2 不携带 Data release identity、consumer sample/binding、raw-result 聚合或 Prod 字段。

## HANDOFF

- Data `resultRefs` 只包含：import、verify/readback/health、activation（适用时）与 API consumer raw CaseResult exact refs/digests。
- ship pass 后按 Skill 固定到 END；完成报告只说明 Data ship 与 consumer-check intent 的实际闭合，不声称 EAF、App UAT 或 Prod acceptance 已闭合。
- 需要 EAF 时另行交给 Environment Ops scheduler；其 acceptance exact ref 属于 Environment Ops 执行结果，不回写 Data ship receipt。Prod acceptance 走 RC Qualification package acceptance、`ReleaseTagAdmissionFact`、`ProdActivationAdmissionFact` 与 hosted rollout/readback facts，不走 EAF。
