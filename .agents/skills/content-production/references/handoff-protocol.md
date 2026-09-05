# 阶段交接协议

本协议只定义 producer 九阶段共用的 OPEN → AI DURING → AI POST → CLOSE 边界；阶段顺序与后继只由 `SKILL.md` 固定，不由代码状态机、registry 或 receipt reducer 派生。

## OPEN：AI 点名输入，内核冻结

宿主 AI 从前一阶段 receipt 与业务产物中选择本阶段所需 exact input refs，并显式调用：

```bash
python3 quwoquan_data/scripts/cli.py task stage-open \
  --execution-id <id> --stage <stage> --input <stage-open-input.json>
```

`stage-open-input.json` 只包含 `inputRefs[]`，每项只写 `scope` 与 `ref`；摘要由内核按实际文件字节计算。内核只允许验证 execution/stage identity、前一阶段 create-once receipt、输入路径边界、摘要与 schema，并 create-once 写入 `data/tasks/<executionId>/_shared/stage-open/<sequence>-<stage>.json` 冻结 exact bytes。内核不得发现语义输入、选择 candidate、运行 verifier、推进阶段或填写业务字段。

同 stage 的相同 OPEN 可幂等读取；OPEN 已存在且输入不同必须冲突。OPEN 后未产生 CLOSE，接手者读取同一 OPEN 并重做本阶段，不创建恢复状态或修改输入。

## DURING：AI 直接完成业务工作

宿主 AI 只读 OPEN 冻结输入，按当前 stage contract 直接写对象级业务结果。AI 承担选源、质量判断、compose、正文/image caption/video script、self-check、独立 review、verdict/typed issues、approved 对象与 explicit cohort/milestone；需要下载/CAS 或原子 I/O 时只调用契约点名的窄命令。

禁止 `semantic-prepare`、`semantic-record`、stage-gate、canonical argv registry、runner/fleet/lane claim、自动重试/rewind 与 execution-state 写入。批量并发、限流与 reviewer session 编排是宿主 runtime 责任，不写仓内状态。

## POST：机械 verifier + AI self-check

宿主 AI：

1. 检查每份结果是否忠实消费 OPEN 输入；
2. 逐条运行当前 stage contract 显式点名且当前真实存在的 verifier；
3. 保存每条真实 verifier fact，至少绑定 verifier identity、argv、`passed|failed`、exit code、observedAt 与 evidence ref/digest；
4. 完成当前契约列出的 AI self-check；
5. 决定 `pass|blocked`，并逐条写 typed issue。业务语义失败不得被脚本改写为 pass。

`verifierFacts` 是宿主对“已执行显式 verifier”的 attestation，不是内核执行证明。内核不会运行 command，也无法证明 command 真的执行；它只冻结宿主提交的 command/status/exit/observedAt，并从同一个 no-follow 打开的 regular-file fd 重算 evidence bytes digest。任何不能信任宿主的消费者都必须重跑当前 stage contract 点名的 verifier，不能仅凭 receipt 接受其事实。

verifier 只判断 schema、exact bytes、引用闭包与媒体/原子 I/O 硬事实；不得生成正文、review、verdict、typed issues、后继或环境结论。

## CLOSE：AI 提交结论，内核 create-once

```bash
python3 quwoquan_data/scripts/cli.py task stage-close \
  --execution-id <id> --stage <stage> --input <agent-result.json>
```

`agent-result.json` 必须显式包含：

- `actor`：宿主、session、实际 invocation/model 事实；
- `verdict`：`pass|blocked`；
- `typedIssues[]`：可为空，blocked 时非空；
- `resultRefs[]`：本阶段业务结果 exact refs/digests；
- `verifierFacts[]`：POST 逐条运行的宿主 attestations；`pass` 时每项必须 `status=passed`、`exitCode=0`，且 evidence ref/digest 必填。

内核只重验 OPEN exact bytes、结果 schema、result refs、verifier attestation 结构与 evidence bytes、严格 receipt 前缀/hash predecessor 链及 create-once 冲突，并写入 `data/tasks/<executionId>/_shared/receipts/<sequence>-<stage>.json`；不运行隐藏 gate，不改写 actor/verdict/issues，不计算后继，不投影 execution state。

CLOSE 后，`pass` 按 `SKILL.md` 固定顺序进入后继；所有 release header 绑定 execution 都有 sequence-009/pass 后，还必须 create-once 物化并复核 terminal immutable handoff，成功后才固定进入 `END`。`blocked` 终止该 execution，新尝试必须经 `task init` 创建新 execution，并从 `0.plan` 开始。producer receipt 与 release handoff facts 是跨会话唯一交接；环境事实属于下游 owner，不进入 producer receipt 链。
