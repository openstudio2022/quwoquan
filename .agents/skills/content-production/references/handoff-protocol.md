# 阶段交接协议

阶段间交接的唯一协议。工作包级主线共 10 个阶段（名字与磁盘目录一字不差）：

```text
0.plan -> sources -> 1.download -> 2.quality -> 3.compose -> 4.draft -> 5.review
-> publish -> release -> ship
```

每阶段的实例化契约见 [stage-contracts/](stage-contracts/)。

## 三段 authority 边界（每个阶段统一执行序）

宿主只提交 stage identity 与结构化 context；成功事实、命令退出码、artifact 摘要、
`verdict` 与 `next` 全部由确定性内核派生：

1. **OPEN**：`task stage-open --execution-id <id> --stage <stage>`。命令验证 receipt
   链的唯一合法 next、前驱 pass 与 `task init` 三文件 exact closure，并 create-once 冻结
   workflow contract digest。OPEN 不选择 candidate、不执行 stage、不推进状态。
2. **DURING**：`sources|2.quality|3.compose|4.draft|5.review` 先调用
   `task semantic-prepare --execution-id <id> --stage <stage>`；内核根据 registry 确定性发现
   输入闭包并冻结 canonical request，调用者不能自由传 input refs。宿主只基于该 request
   完成语义工作，随后把 `actor{host,sessionId,modelFamily,invocation{provider,model,runId}} + requestRef/requestDigest + resultRefs` 写入唯一结构化 JSON，
   调用 `task semantic-record --execution-id <id> --stage <stage> --input <json>`；record 校验
   stage allowlist、现有业务 schema/validator 与 exact bytes 后 create-once 写 canonical wrapper。
   结果 input 禁止包含 verdict、next、command 或 exitCode。
3. **GATE**：`task stage-gate --execution-id <id> --stage <stage> --context <json>`。
   内核只执行 stage registry 的 canonical argv，捕获真实 exitCode/stdout/stderr 摘要并冻结
   artifact exact refs。五个语义 stage 的 context 必须只把 canonical wrapper 作为
   `semanticResultRef + semanticResultDigest` 绑定，actor/语义结果不再从任意 artifact JSON 派生。
   release/ship context 必须绑定 `releaseId + releaseDigest`；ship 还必须
   绑定 canonical `EnvironmentAcceptanceFact` exact ref/digest，内核直接调用 Ops validator
   完整验证 required raw UAT closure。
4. **CLOSE**：`task stage-close --execution-id <id> --stage <stage> [--context <json>]`。
   close context 只允许结构化 `typedIssues`。内核重验 workflow/open/gate/artifact bytes，
   从 gate exits 与 typed issues 派生 `verdict` 和 `next`：pass 固定后继，ship pass 才
   `END`；blocked 只能回到 issue 指定且已完成/当前的 recovery stage。

Authority 文档路径固定为 `_shared/stage-authority/<seq>-<stage>/{open,gate}.json`；
current receipt schema 为 `quwoquan_data.stage_receipt`，其 `authority` 必须绑定
open/gate/workflow/artifacts/release/acceptance。公开 task parser 不再暴露 `stage-record`，
也不接受调用者自报 command/exitCode/next/actor/成功事实。CLI 退出码统一为：成功 `0`、
参数或协议拒绝 `2`、create-once 冲突 `3`。

`sources|2.quality|3.compose|4.draft|5.review` 的 actor 只从 machine gate 绑定的 canonical
semantic result wrapper 读取；`5.review` recorder 强制具名异族 modelFamily。其它阶段由
确定性 authority 标记机器身份。release receipt 必须绑定自身 release；ship open/gate/close
均重验该绑定与前驱 release receipt 的 `authority.releaseBinding` 完全相同。

## execution_state 合并方式（写入权移交，DEC-005）

- `_shared/execution_state.json` 是 receipt reducer 产生的只读最小投影；唯一写盘入口是
  `content.execution.receipt_state_reducer.reduce_receipt_projection`。`context.save_execution_state`
  永久拒绝业务写者；agent、skill 与其他命令一律不手写。
- `task stage-close` 先 create-once 写 receipt，再由全部 receipt 确定性重算 projection：
  - `stage=ship` 且 `verdict=pass` → `status=succeeded`（execution 终态的唯一合法来源）。
  - `verdict=blocked` → `status=manual_required`。
  - 其余 pass receipt → `status=running`。
- 终态（`succeeded`/`superseded`）受 layout/readiness 门保护，不可 resume；
  重试语义见 [recovery.md](recovery.md)。
