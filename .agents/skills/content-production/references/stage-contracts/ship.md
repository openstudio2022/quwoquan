# 阶段契约：ship

把 immutable release 幂等导入目标环境并完成消费侧核验。execution `succeeded`
终态的唯一合法来源是本阶段 pass receipt。

## 身份

- stage：`ship`（与磁盘目录一字不差）
- 前置阶段：`release`
- 合法 next：`END`（终态）
- 角色人设：[release-operator](../roles/release-operator.md)
- 写目录 allowlist：`.qwq_output/env/<env>/runs/data-release/<releaseId>/<runId>/`
  （只经 ship 命令与核验流程）

## 做前（PRE）

- `release` receipt `verdict=pass`，并读取其 `authority.releaseBinding`；ship open/gate/close 都必须重验当前 `releaseId + releaseDigest` 与该前驱绑定完全相同，另一份即使合法且有 acceptance 的 release 也不得借此 execution ship；复跑：

```bash
python3 quwoquan_data/scripts/cli.py verify release-integrity --release <releaseId>
python3 quwoquan_data/scripts/cli.py verify media-release-contract
```

- ship gate context 必须显式携带 `acceptanceProfile`，且只能为
  `environment_promotion|m1_api_consumer`；该值必须与 exact
  `EnvironmentAcceptanceFact.acceptanceProfile` 相等，不得从环境、target、设备字段缺席或
  `requiredTargetProfiles` 猜测，也不接受旧字段回退。
- 从 `quwoquan_ops/environments/<env>/runtime.yaml` 读取当前 environment owner fact：
  `dataReleaseTarget` 必须唯一给出 `<target>`，当前 workload/readiness owner fact 必须给出
  `<scope>`；缺失、冲突或靠猜测得到任一值时 `GATE_BLOCK`。
- `environment_promotion` 保持 `requiredTargetProfiles` 非空及既有 release/promotion 规则，
  canonical 环境门仍是：

```bash
python3 quwoquan_ops/cli/stackctl.py verify \
  --env <env> --kind all --profile release \
  --data-release-id <releaseId> --data-import-run-id <importRunId> \
  --data-verify-run-id <verifyRunId>
```

- `m1_api_consumer` 只允许 `environment=alpha,target=alpha-local`，并要求
  `requiredTargetProfiles=[]`。它不绑定 device/App authority；canonical 环境门只证明当前
  内容 API consumer workload 的服务、active release 与 exact query 健康：

```bash
python3 quwoquan_ops/cli/stackctl.py health \
  --target alpha-local --scope content-consumer
```

  `content-consumer` 仍严格要求命令退出码为 0，并保持 API、内容服务、active release、
  exact query 与 release-bound content feed 判据；仅 `device_bound`、`content_live_passed`
  不参与该 scope 的退出判定。不得以 warn-only、忽略退出码或删除环境核验替代。

- 涉及环境操作时同步加载 `quwoquan_ops/AGENTS.md`。

## 做中（DURING）

- 导入 run 与 verify run 都是 append-only 且身份分离：

```bash
python3 quwoquan_data/scripts/cli.py ship apply \
  --release-id <releaseId> --env <env> --run-id <importRunId> --import --full-sync
python3 quwoquan_data/scripts/cli.py ship verify \
  --release-id <releaseId> --env <env> --import-run-id <importRunId> \
  --run-id <verifyRunId> --readiness-phase <research|consumer|commercial>
```

- 回执、API 核验、回滚与重放证据只写对应环境 run
  （`.qwq_output/env/<env>/runs/data-release/<releaseId>/<runId>/`）。
- `environment_promotion` 的 App UAT 必须由消费侧公开入口显式绑定同一
  release/import/verify identity；Gamma content release 使用 import run 产生的 exact cases
  与 verify run id：

```bash
python3 quwoquan_ops/cli/stackctl.py content-uat \
  --target <target> \
  --release-uat-cases <output-root>/env/gamma/runs/data-release/<releaseId>/<importRunId>/homepage_verification_cases.json \
  --data-verify-run-id <verifyRunId> --acceptance-lease-id <leaseId> \
  --platform <android|ios|all> --device-id <deviceId> \
  --report-dir <output-root>/env/gamma/runs/data-release/<releaseId>/<verifyRunId>/app-uat
```

  完成时保存且引用 exact App UAT receipt
  `<output-root>/env/gamma/runs/data-release/<releaseId>/<verifyRunId>/app-uat/report.json`；
  receipt 必须为本次命令产出、`status=ok`，并通过 cases path、lease 与
  `dataVerifyRunId` 绑定当前 `<releaseId>/<importRunId>/<verifyRunId>`。非 Gamma 环境使用
  对应 environment acceptance/App UAT owner fact 指定的公开入口与 exact receipt，不得套用
  Gamma 路径或从 latest 推断。
- `m1_api_consumer` 不运行或引用上述 App UAT；它的 EAF 必须由 Ops canonical validator
  直接验证同一 M1 Research release/import/verify identity 的 16 个 fresh
  `producer=service,layer=api_integration` raw `ReadinessCaseResult` exact bytes，且拒绝
  `TargetUatBinding`、App/device/platform refs。其 canonical public writer 模板为：

```bash
python3 quwoquan_ops/cli/stackctl.py environment-acceptance-append \
  --acceptance-profile m1_api_consumer \
  --evidence-root <evidenceRoot> --acceptance-root <acceptanceFactRoot> \
  --environment alpha --target alpha-local \
  --release-id <releaseId> --release-digest <releaseDigest> \
  --import-run-id <importRunId> --verify-run-id <verifyRunId> \
  --sample-plan-ref <samplePlanRef> --sample-plan-digest <samplePlanDigest> \
  --data-readiness-ref <dataReadinessRef> --data-readiness-digest <dataReadinessDigest> \
  --active-cas-ref <activeCasRef> --active-cas-digest <activeCasDigest> \
  --active-cas-readback-ref <activeCasReadbackRef> \
  --active-cas-readback-digest <activeCasReadbackDigest> \
  --lifecycle-exit-ref <lifecycleExitRef> --lifecycle-exit-digest <lifecycleExitDigest> \
  --provider-readiness-ref <providerReadinessRef> \
  --provider-readiness-digest <providerReadinessDigest> \
  --observability-readiness-ref <observabilityReadinessRef> \
  --observability-readiness-digest <observabilityReadinessDigest> \
  --rollback-readiness-ref <rollbackReadinessRef> \
  --rollback-readiness-digest <rollbackReadinessDigest> \
  --lease-revocation <leaseRevocationRef>=<leaseRevocationDigest> \
  --lock-release <lockReleaseRef>=<lockReleaseDigest> \
  --gc-protection <gcProtectionRef>=<gcProtectionDigest> \
  --created-at <createdAt> --source-fingerprint <sourceFingerprint> \
  --required-raw <slotId>=passed=<rawRef>=<rawDigest> # 精确重复 16 次
```

  该 profile 不传 `--target-binding`、`--required-profile`、predecessor 或
  `--prod-release-facts`；public command 不从缺席字段猜 profile。
- [MUST NOT] 修改 canonical 或 release；[MUST NOT] 用 fixture、seed、旧回执或仅 API
  readback 顶替 `environment_promotion` 的 App UAT exact receipt。

## 做后（POST）

交付件按 profile 分轨：`environment_promotion` 为导入回执 + verify/readback + App UAT
exact receipt；`m1_api_consumer` 为导入回执 + verify/readback + 16 个 API raw exact results。
两轨都必须完成 activated lifecycle：

```bash
python3 quwoquan_data/scripts/cli.py verify release-lifecycle \
  --release <releaseId> --environment <env> \
  --import-run <importRunId> --verify-run <verifyRunId> --prod-mode activated
# environment_promotion：沿用 PRE 中 stackctl verify --profile release
# m1_api_consumer：沿用 PRE 中 stackctl health --target alpha-local --scope content-consumer
```

`verify release-lifecycle --release <releaseId>` 这种顶层 release-only 命令只证明 immutable
release 局部完整性；即使 PASS 也不得声称环境 activation、import/readback 或 App UAT 闭合。
`--import-run`、`--verify-run`、activated lifecycle PASS、本 profile canonical 环境命令
PASS 与本 profile required raw exact closure 任一缺失/不匹配，ship 都保持未完成，禁止调用者
自报 ship pass/END。ship gate context 必须显式绑定当前 `releaseId + releaseDigest +
acceptanceProfile` 与 canonical `EnvironmentAcceptanceFact` exact ref/digest；内核复用 Ops 同一
validator 验证 profile 分支后，close 才能派生 pass/END。

常见 issue → 修复：

- 导入计数不等（Manifest/导入/active/Search/Recommendation） → 按 issue 定位断链环节
  重跑幂等导入，不手补投影。
- 环境不健康 → 走 `environment-ops` 工作流修环境，本阶段保持未完成。

### verify 失败重试 SOP

verify run 是 append-only 证据：失败的 run 目录原样保留，禁止改写或删除。失败重入的固定
操作序，逐条依次判断：

1. **换新 run-id 重跑 verify，不重导入**：`ship apply` 导入是幂等的且证据独立于
   verify；只要 release、导入结果与环境 runtime 没变，重试只发生在 verify 层。新
   `<verifyRunId>` 必须贯穿 lifecycle 与新的 App UAT exact receipt，旧 UAT 不得复用。
2. **research isolation proof 自动复用**：runtime proof 效度域为
   `releaseId + manifestDigest + runtime 策略快照 + 24 小时时效`（DEC-034），不绑 verify
   run。同一 release 的后续 verify run 会自动发现并复用最近一次未超龄 PASS proof
   （重绑当前 run-id、`reusedFromVerifyRunId` 写明来源后落盘），无需重跑完整 probe。
   release 内容、导入或 runtime 策略变更，或 proof 超过 24 小时时效时，必须重新执行
   `stackctl research-isolation-probe`。
3. **需要重导入的唯一情形**：release 本身变更（新 releaseId 或 manifest digest
   漂移），此时从 `ship apply` 重新开始，旧 run 证据保留。
4. **环境卡点不在本阶段修**：`stackctl down` 对孤儿 compose 网络幂等回收；若 down/up
   仍不收敛，走 `stackctl doctor` → `repair`（environment-ops），不得手工 `docker`
   清理后继续本阶段。

按 [handoff-protocol.md](../handoff-protocol.md) 执行 `task stage-open` → `task stage-gate` → `task stage-close`；宿主不填写 command 退出码、verdict 或 next；只有上述 activated lifecycle 与 canonical `EnvironmentAcceptanceFact` required raw closure 同时闭合时，`task stage-close` 才派生 `verdict=pass,next=END`，receipt reducer 随后确定性投影 `execution_state.status=succeeded`。

## 交接（HANDOFF）

- 终态 receipt：`next=END`，并绑定 App UAT exact receipt ref。
- HANDOFF 报告用户或交 `plan-next`：release/import/verify/App UAT exact evidence refs、
  OPEN 变化、剩余阻断。
