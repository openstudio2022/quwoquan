---
name: content-production
description: Run or resume the six-step Data producer workflow - init, acquire, author, review, publish, release - from a topic to canonical 趣我圈 objects and an immutable milestone handoff.
metadata:
  kind: workflow
---

# content-production

目标只有一句：找到主题相关的公开原文（实体条目、文章、图片、视频），适度润色，加工成可在趣我圈展示的对象。宿主 Cursor/Codex Agent 是唯一语义主体；仓库脚本只做机械动作（抓取字节、算摘要、校 schema、原子写入、create-once 封存）。脚本不选来源、不判相关性、不创作、不评审、不推进步骤。

```text
init -> acquire -> author -> review -> publish -> release
```

每步的 AI 产出、脚本动作与唯一硬门见 [references/steps.md](references/steps.md)；四载体差异见 [references/carriers.md](references/carriers.md)；里程碑 handoff 见 [references/handoff.md](references/handoff.md)。

## 触发与输入

- 新任务：AI 按来源单一类型判定决定载体——可命名的地点/机构/景区/博物馆条目 → homepage（最优先）；非单一实体的主题、线路、事件、文化现象条目 → article；Commons 图片文件页 → image；Commons 视频文件页（webm/ogv）→ video。一个来源只产一个对象，不做数量推断、不做刻意剔重。随后写 `carrier_demand.json` 与 `candidate_bindings.json`，调用 `task init`。同一 execution 可批量承载多个 target；不同 execution 可并行。
- 恢复：只读 `_shared/receipts/` 找首个未闭合步骤继续；任一 receipt `blocked` 则新建 execution，不在原 execution 回退。已有 receipt 或 reviewer 产物的工作单元不得再次派发。
- 产生 `content-release` 时，PRE 运行 `make feature-context TARGET=<exact-path>` 保存 content-addressed immutable owner manifest exact ref；纯只读且无送审交付只允许 `report-only/no-review-deliverable`。

## 执行

两个 actor，不再多：

- **主会话**：直接完成 init、acquire、author、publish、release 与全部机械命令，不把任何步骤委托给通用子 Agent。
- **唯一 reviewer**：`review` 步骤由另一个真实会话执行，与 author 的 `host/sessionId` 与 `invocation.runId` 必须不同。全局同一时刻至多一个 reviewer 调用，始终前台，一次调用负责该 execution 全部对象；reviewer 只写 `content_review.json` 的判断字段，不派发子 Agent、不改产物、不 seal、不 publish。`starting up` 不是进度也不是失败，不得据此补发相同或替代调用；definitive failure 保留首个 typed blocker，由主会话停止重试。

机械命令闭集：`task init`、`task acquire`、`task seal`、`release publish-object`、`release finalize`、`release handoff-verify`。正文、caption、video script、评审、typed issue、verdict、cohort、milestone、来源是否切题、素材是否值得用、文章结构与作者人设一律由 AI 决定。

## 完成证据

硬门只有六条：来源 `https://` 可检索；bytes 与 sha256 精确；license 在白名单且权利六字段（`sourceUrl/license/termsUrl/authorizationProof/usageScope/rightsStatus`）在场；author 与 reviewer 是不同 session/runId；对象身份唯一且 create-once；显式 cohort 与里程碑计数。其余检查只写 advisory，不阻断。

producer 完成 = 三份 seal receipt 连续闭合 + 逐对象 publish 事务 + `release finalize` 产生的 immutable handoff（含 `producerBaselineRevision` 与 `producerContractDigest`）。M1/M10/M100/M1000 按累计唯一 finalized 对象计数，凡已完成 canonical publish 且 review approved 的对象都可进入 cohort。

## 失败与停止

任一硬门不闭合即停止并报告首个 typed blocker；不手改门禁、不伪造证据、不回写旧 receipt。环境 import/activate/readback、App/API UAT、EAF、promotion/rollback 全部 out of scope；下游 owner 是 Environment Ops scheduler（profile 闭集 `smoke|integration|release`），本 Skill 不调度也不记录任何 consumer facts。

## 条件性交接

产生 `content-release` 时，POST 把 PRE owner identity ref 原样作为 `--owner-identity`、current candidate evidence 作为 `--candidate-evidence` 调用 Review（workflow=`content-production`、deliverable=`content-release`），registry 只派一名 reviewer。`release finalize` 成功即 producer `END`，handoff 只含 release/cohort/canonical identity facts。源码/spec 变更走 Feature workflow。
