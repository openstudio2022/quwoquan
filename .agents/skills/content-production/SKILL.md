---
name: content-production
description: Run the canonical quwoquan data content workflow from reusable inputs through one execution work package, immutable release, environment import, and App UAT, and diagnose or resume a failed execution. Make sure to use this skill whenever the user mentions 按区域生成主页, 跑内容任务, 内容生产, 生产内容并导入环境, 复核 execution, 恢复内容任务, 重试实体任务, immutable release, or 数据发布, even without an explicit command.
metadata:
  kind: workflow
---

# content-production

从可复用输入到 execution 工作包、immutable release、环境导入与 App UAT 的
内容生产主线。五段执行契约见根 `AGENTS.md`。

## 触发

- 自然语言：按区域生成主页、跑内容任务、内容生产、生产内容并导入环境、
  复核 execution、恢复内容任务、重试实体任务、immutable release、数据发布。
- 由模型按 `description` 自动匹配，用户是否输入斜杠命令都不改变本契约。

## 输入

- 可复用运行输入（区域、载体、生成家族），归属由 `verify runtime-input-ownership` 判定。
- 来源素材及其 CAS 摘要，由 `verify source-digest --execution-id` 冻结。
- 续跑或跨宿主接手时，既有 receipt 链与 `execution_state.json` 只读消费，
  断点判定见 [references/recovery.md](references/recovery.md)。

## 边界宣言（详见 [references/boundary.md](references/boundary.md)）

- **宿主 agent 是唯一执行主体**：调研、创作、评审、推进决策、读校验报错自修产物。
- **skill 只写契约**：阶段序、产物位置/结构、完成判据绑定、恢复语义；零代码。
- **脚本只做检查与确定性 IO**：verify 门禁、下载/CAS、publish/release/ship
  原子操作、receipt 记录；永不驱动或等待 agent。

## 角色

主会话扮演 **content producer**（内容生产宿主）：按阶段契约调研、创作、评审、
推进决策，并读校验报错自修产物。阶段角色人设（独立会话派发）见
[references/roles/](references/roles/)。

## 执行

自由度：低（阶段序、产物位置与完成判据固定，创作内容自由）。

### 主线阶段

每阶段按四段生命周期执行（[references/handoff-protocol.md](references/handoff-protocol.md)），
收尾以 `task stage-record` 落 receipt。验收命令简写 `verify … ` =
`python3 quwoquan_data/scripts/cli.py verify …`，退出码 0 为过。

| 阶段 | 产物根 | 契约 | 完成判据 |
| --- | --- | --- | --- |
| `0.plan` | `0.plan/` + manifest | [0.plan.md](references/stage-contracts/0.plan.md) | `verify runtime-input-ownership` + `verify content-execution-layout` |
| `sources` | `sources/` | [sources.md](references/stage-contracts/sources.md) | `verify source-digest --execution-id` |
| `1.download` | 对象 `1.download/` + CAS | [1.download.md](references/stage-contracts/1.download.md) | 按 lane 绑定（见契约 POST 栏） |
| `2.quality` | 对象 `2.quality/` | [2.quality.md](references/stage-contracts/2.quality.md) | `verify stage-artifacts --execution-id` |
| `3.compose` | 对象 `3.compose/` | [3.compose.md](references/stage-contracts/3.compose.md) | `verify stage-artifacts --execution-id` |
| `4.draft` | 对象 `4.draft/` | [4.draft.md](references/stage-contracts/4.draft.md) | 按 lane 绑定（见契约 POST 栏） |
| `5.review` | 对象 `5.review/` | [5.review.md](references/stage-contracts/5.review.md) | `verify rubric --file --generation-family` |
| `publish` | `quwoquan_data/publish/` | [publish.md](references/stage-contracts/publish.md) | `verify publish-purity` + `verify publish-closure` |
| `release` | `.qwq_output/data/releases/<rid>/` | [release.md](references/stage-contracts/release.md) | `verify release-integrity --release` + `verify media-release-contract` |
| `ship` | 环境 run + UAT 证据 | [ship.md](references/stage-contracts/ship.md) | `verify release-lifecycle` + `stackctl verify --env gamma` |

角色人设（独立会话派发）见 [references/roles/](references/roles/)；
载体差异判据（article/homepage/image/video）见
[references/carriers/](references/carriers/)。

### 入口三分支

1. **新任务**：`python3 quwoquan_data/scripts/cli.py task preflight --json` →
   读 [0.plan.md](references/stage-contracts/0.plan.md) 开始。
2. **续跑 / 跨宿主接手**：读 [references/recovery.md](references/recovery.md)
   判定表，从 receipt 链定位断点。
3. **loop / 并发 / fleet 运行**：读 [references/orchestration.md](references/orchestration.md)
   （运行档位 A/B/D、single-writer claim、模型策略；正式并发唯一实现是
   fleet_dispatcher + loop_driver，宿主命令经 `HOST_CMD` 参数注入，零宿主分叉）。

工作包布局与命名约束见 [references/execution-layout.md](references/execution-layout.md)；
验收失败的自修循环见 [references/self-repair.md](references/self-repair.md)。

## 交付件

**immutable release 与环境导入证据**：release 目录、环境 run 与 App UAT 收据，
经由 receipt 链绑定到 execution。

送审前自检：

- 每个已推进阶段都有 create-once receipt，且 `execution_state` 与 receipt 链一致；
- release 通过 `verify release-integrity --release` 与 `verify media-release-contract`；
- 环境侧通过 `verify release-lifecycle` 与 `stackctl verify --env gamma`。

## 凭证与安全

- 凭证只来自仓外 `0600` 的 `~/.config/quwoquan/cursor_api_key`；
  任何输出不得包含 key、片段或指纹。

## 内置评审

- publish 前 POST 调 `review`（workflow=`content-production`，segment=POST，
  deliverable=`content-release`），角色 data-quality + data-legal——板外复核，
  独立于 `5.review` 执行角色的自查。

## 失败与停止

- [MUST NOT] 手改 verify/schema/门禁参数；[MUST NOT] 手写 receipt 或
  `execution_state.json`；[MUST NOT] 补写缺失的 source、rights、review 或
  release 证据。
- 失败必须保留明确的阶段与原因，不得把未过的门禁包装为通过。
- 证据缺失一律带 `executionId` 返回 `GATE_BLOCK`，由 recovery 判定表决定回到哪个阶段。

## HANDOFF

- **完成判据**：见 [completion-criteria](../review/references/completion-criteria.md) 本工作流段；证据链条目带命令+退出码+时间戳+SHA，下游过期即复跑。
- **产出物**：release 与 UAT 证据（receipt 链 + 环境 run 路径），报告给用户。
- **未决项去向**：blocked receipt 的 `openItems` 已落 `return_to_stage` /
  `gate_block` / `out_of_scope` 三者之一；恢复入口 [recovery.md](references/recovery.md)。
- **唯一合法下游**：App 侧问题交接 `dev`；其余报告给用户结束。
- **证据链**：`.qwq_output/data/tasks/<executionId>/_shared/receipts/`、
  `.qwq_output/data/releases/<releaseId>/`、
  `.qwq_output/env/<env>/runs/data-release/<releaseId>/<runId>/`。
