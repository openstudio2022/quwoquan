---
name: content-production
description: Run the canonical quwoquan data content workflow from reusable inputs through one execution work package, immutable release, environment import, and App UAT, and diagnose or resume a failed execution. Make sure to use this skill whenever the user mentions 按区域生成主页, 跑内容任务, 内容生产, 生产内容并导入环境, 复核 execution, 恢复内容任务, 重试实体任务, immutable release, or 数据发布, even without an explicit command.
metadata:
  kind: workflow
---

# content-production

## 触发与输入

用于内容生产、execution 恢复、immutable release、环境 import 与 App UAT。输入是可复用运行输入、source digest、execution identity 和既有 receipt（如续跑）；角色交互只引用 `quwoquan_ops/policies/human_agent_delivery_contract.yaml#workflow_interaction_binding.bindings.content-production`，可见输出由 canonical projector 生成。

本轮若将产生、更新或恢复 registry 声明的送审交付件 `content-release`，PRE 必须先得到一个可唯一解析的 exact target：从当前 execution/release owner facts（优先 release UAT sample plan 的 `specRef`）取去掉 `#anchor` 后的 repository-relative canonical Feature `spec.md` 路径；全部引用必须归一为同一路径。缺失、多路径或无法解析到唯一 owner 时返回 typed `GATE_BLOCK`，不得进入 publish/release/ship 送审；多 owner 内容必须拆成分别送审的交付件。随后运行 `make feature-context TARGET=<exact-path>`，保存 stdout 指向的 content-addressed immutable owner manifest exact ref，PRE 后不得重写或替换该 ref。

## 执行

所有动作以 `python3 quwoquan_data/scripts/cli.py` 为 canonical 入口，按 0.plan、sources、1.download、2.quality、3.compose、4.draft、5.review、publish、release、ship 顺序只消费磁盘 owner facts；每阶段只创建一次 receipt，不手写执行状态，不用后续结果修饰旧证据。进入某阶段时只加载 `references/stage-contracts/<stage>.md`；失败或续跑才加载 [recovery.md](references/recovery.md)，需要 loop、并发或 fleet 才加载 [orchestration.md](references/orchestration.md)，不预载其他阶段与恢复正文。

内容运行本身不要求 Feature owner manifest，但该豁免只覆盖不产生送审交付件的纯只读查询/诊断。此类请求以 `fleet-status` 的只读结果、明确的 `report-only/no-review-deliverable` 或 typed blocker 终止，不得调用 POST Review，也不得声称 `content-release` 完成。若任务需要修改源码、spec、design、contracts、gate 或测试，立即停止该 mutation，并按 exact target 交接 explore/prd/design/dev；本 Skill 只继续内容执行/恢复链。

## 完成证据

同一 execution 的 receipt 链、immutable release、环境 import/readback 与 App UAT exact receipt 必须同时闭合；逐层报告未证明项，不用 publish/release PASS 替代设备 UAT。至少执行并报告 1–3 个适用入口：`python3 quwoquan_data/scripts/cli.py task fleet-status --execution-id <id> --json`；`python3 quwoquan_data/scripts/cli.py verify execution-readiness --execution-id <id> --mode <calibration|research|commercial>`，其中 `--mode` 必须读取当前 execution/readiness owner fact；`python3 quwoquan_data/scripts/cli.py verify release-lifecycle --release <releaseId>` 仅证明顶层 immutable release 的 release-only 局部证据，不证明任何环境 activation、import/readback 或 App UAT 闭合。环境激活的完整命令与 exact receipt 绑定以 [ship.md](references/stage-contracts/ship.md) 为准。

产生 `content-release` 时，POST 必须把 PRE 保存的同一个 owner manifest exact ref 原样作为 `--context-manifest` 传给 Review（workflow=`content-production`、segment=`POST`、deliverable=`content-release`、scope=`<exact-path>`）；先按 plan 去重执行命名 evidence，再派 registry 主审与至多一名专审。manifest ref 缺失、与 PRE 不同或 stale，required evidence/Reviewer 未完成，均不得完成。

## 失败与停止

禁止补造 source、rights、review、release、import/readback、owner manifest 或 UAT 证据。receipt/source/release identity 不一致，exact target 不能唯一解析，或 App UAT exact receipt 未绑定时保留首个 typed blocker，按 canonical recovery 返回唯一阶段。

## 条件性交接

源码/spec mutation 只交 Feature workflow；跨宿主接手、环境/发布、外部阻断或证据复用满足 canonical 触发时生成 handoff。送审交付的 handoff 必须携带 PRE 保存并在 POST 原样复用的 owner manifest exact ref；纯只读无送审交付不生成替代 manifest。
