# 阶段契约：ship

AI 显式执行 apply、readback/health 与 `EnvironmentAcceptanceFact` 创建；不存在 gate registry 或自动 terminal reducer。

## PRE

- `release` CLOSE 为 pass。
- OPEN 显式冻结 releaseId/releaseDigest、environment/target、import/verify run identities、`acceptanceProfile` 与所需环境 owner refs。
- `acceptanceProfile` 仅为 `m1_api_consumer|environment_promotion`，不得从环境名猜测。

## DURING

AI 按顺序显式调用并记录 exact facts：

1. `ship apply` 导入同一 immutable release；
2. `ship verify` 和对应环境 readback/health；
3. 需要时 activate；
4. 逐 cell 执行该 profile 所要求的真实 consumer checks；
5. 调用 canonical writer 创建同 identity 的 EAF。

`m1_api_consumer` 只要求 Alpha 服务/API consumer 的 entry surface × carrier 16-cell fresh raw facts；不得生成/引用 App UAT、device/platform、`TargetUatBinding` 或 promotion predecessor。

`environment_promotion` 才要求 target-bound App UAT raw facts、target binding、predecessor/promotion closure。两分支均不得用 fixture、旧 receipt、counts 或另一 release 的事实代替。

## POST

逐条运行当前 profile 适用的真实环境 verifier。基础环境动作使用：

```bash
python3 quwoquan_data/scripts/cli.py ship apply --release-id <releaseId> --env <env> \
  --run-id <importRunId> --import --full-sync
python3 quwoquan_data/scripts/cli.py ship verify --release-id <releaseId> --env <env> \
  --import-run-id <importRunId> --run-id <verifyRunId> --readiness-phase <phase>
```

`m1_api_consumer` 只附加 Alpha 服务/API consumer health 与 16-cell raw facts，再由现有 Ops `environment-acceptance-append` writer 写 EAF；不得运行 promotion-only release lifecycle/rollback-replay Exit。`environment_promotion` 才运行其声明的 App UAT、predecessor 与 EAF validators。

AI 逐条绑定真实 argv/exit/ref/digest，在 CLOSE 中显式提交 pass/blocked。内核只重验 facts，不派生 END 或 succeeded。

## HANDOFF

- `resultRefs`：import、verify/readback/health、activation（适用时）、raw consumer facts、EAF exact refs/digests。
- ship pass 后按 Skill 固定到 END；完成报告必须说明 profile，且只在 `environment_promotion` 声称 App UAT 闭合。
