# Account-enforcement Gamma UAT

本 runbook 只说明如何消费仓内唯一验收入口，不定义第二套环境、对象或状态真相源。
领域验收事实来自：

- `specs/feature-tree/product-ops-growth/product-control-plane-foundation/account-moderation-and-appeal-enforcement/spec.md#gwt-003`
- `specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-003`
- `quwoquan_ops/tests/acceptance/user_acceptance/service_ops/product-ops-service/gamma/account_enforcement_gamma_uat_manifest.json`

## 前置条件

- 仅允许 `gamma-local` 的 production Remote composition；不得手写 URL、端口或服务直连入口。
- 使用正式 operator OIDC、manifest 声明的细粒度 scopes、Product Ops service identity、真实 PostgreSQL 与 User Remote。
- 使用一个可恢复的受控账号、两个不同 operator，以及同一 immutable candidate digest。
- Android 与 iPhone 都必须是真机。模拟器、dry-run、旧 receipt 或仅 HTTP 200 均不能形成通过证据。
- phase token、refresh token、owner/persona identity 只从受保护的执行环境注入；不得写入命令参数、receipt、日志或截图说明。
- 执行器读取 `QWQ_ACCOUNT_ENFORCEMENT_GAMMA_{SUSPENDED|RESTORED}_{ACCESS|REFRESH}_TOKEN`、`QWQ_ACCOUNT_ENFORCEMENT_GAMMA_OWNER_ID` 与 `QWQ_ACCOUNT_ENFORCEMENT_GAMMA_PERSONA_ID`；这些值只允许存在于 secret environment。

## 唯一执行序列

1. 通过正式 operator 面完成 authorization negative cases、双人 moderation、suspend delivery，并生成 manifest 要求的 candidate-bound 安全 JSON evidence envelopes 与 `journey-receipt.json`。原始凭据和 PII 不得进入 evidence。
2. 在暂停状态使用旧会话执行双真机阶段：

   ```bash
   python3 quwoquan_ops/cli/stackctl.py account-enforcement-uat \
     --action device-suspended \
     --candidate-digest "$QWQ_ACCOUNT_ENFORCEMENT_GAMMA_CANDIDATE_DIGEST" \
     --device-id "$QWQ_ACCOUNT_ENFORCEMENT_GAMMA_ANDROID_DEVICE_ID" \
     --device-id "$QWQ_ACCOUNT_ENFORCEMENT_GAMMA_IPHONE_DEVICE_ID" \
     --report-dir "$QWQ_ACCOUNT_ENFORCEMENT_GAMMA_REPORT_DIR"
   ```

3. 通过正式 appeal 双人审批恢复同一受控账号；旧 token 必须继续失效，随后只通过正式登录取得新 session。
4. 使用新 session 执行恢复后的双真机阶段：

   ```bash
   python3 quwoquan_ops/cli/stackctl.py account-enforcement-uat \
     --action device-restored \
     --candidate-digest "$QWQ_ACCOUNT_ENFORCEMENT_GAMMA_CANDIDATE_DIGEST" \
     --device-id "$QWQ_ACCOUNT_ENFORCEMENT_GAMMA_ANDROID_DEVICE_ID" \
     --device-id "$QWQ_ACCOUNT_ENFORCEMENT_GAMMA_IPHONE_DEVICE_ID" \
     --report-dir "$QWQ_ACCOUNT_ENFORCEMENT_GAMMA_REPORT_DIR"
   ```

5. 完成 recoverable failure、terminal DLQ、same-decision retry、readiness 与 observability readback，并确认账号 active、新 session 可用、DLQ 清零。然后聚合 CaseResult：

   ```bash
   python3 quwoquan_ops/cli/stackctl.py account-enforcement-uat \
     --action verify \
     --run-id "$QWQ_ACCOUNT_ENFORCEMENT_GAMMA_RUN_ID" \
     --candidate-digest "$QWQ_ACCOUNT_ENFORCEMENT_GAMMA_CANDIDATE_DIGEST" \
     --journey-receipt "$QWQ_ACCOUNT_ENFORCEMENT_GAMMA_JOURNEY_RECEIPT" \
     --suspended-device-report "$QWQ_ACCOUNT_ENFORCEMENT_GAMMA_SUSPENDED_DEVICE_REPORT" \
     --restored-device-report "$QWQ_ACCOUNT_ENFORCEMENT_GAMMA_RESTORED_DEVICE_REPORT" \
     --report-dir "$QWQ_ACCOUNT_ENFORCEMENT_GAMMA_REPORT_DIR"
   ```

同一目录内使用 canonical 文件名时，`verify` 会自动解析三份输入。Gamma release
profile 也会消费对应环境变量中的 receipt 路径；任一输入缺失或不一致时返回
`GATE_BLOCK`，且 `caseResults` 必须为空。

## 准出与失败处理

- 只有 12 个 manifest assertion 全部形成 `passed` CaseResult 才准出。
- 缺 OIDC/scope、service identity、真实存储、User Remote、故障注入、DLQ、readiness、观测、候选绑定、同一受控账号或双真机中的任何一项，均为 `GATE_BLOCK`。
- evidence 必须位于 `QWQ_OUTPUT_ROOT` 下、使用 `application/json` 安全投影、携带实际 SHA-256，并与同一 run/candidate 绑定。被改写、含 Bearer/JWT/PII 字段或超过安全大小的 evidence 一律拒绝。
- CaseResult 与设备报告 create-once；失败后必须新建 run/report 目录，禁止覆盖或把旧失败 receipt 改成通过。
- 本流程不执行 `up`、`deploy`、`repair`、rollout 或生产操作。
