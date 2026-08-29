# L3 Story：仓储布局 HYGIENE 与退役 (`repository-layout-hygiene-and-retirement`)

> 所属能力：[`system-architecture-and-engineering-guide`](../spec.md)
>
> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，我希望全仓路径分类、WIP 保护、可再生产输出清理和历史入口退役，从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- Git/ignored 全路径动态审计报告与候选证据。
- App、Service、Data、Ops 的目录/入口防回归门禁。
- 高置信二进制、失效脚本、重复文档和未注册入口的原子退役。
- Data CLI、stackctl、ML workflow 和设备脚本的唯一入口收敛。
- Fixture 媒体反向引用闭包、App 精确资产声明和无松弛棘轮基线。

### Out of Scope

- 当前 WIP、运行中的环境、vendor、商业 SDK、有效 fixture 和外部备份调度。
- 真实 beta/gamma/prod 远端发布或设备 UAT。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 inventory 能保护脏工作树并输出可复验证据

- 报告包含固定九类分类、WIP 清单、候选引用证据和最小验证命令。

<a id="req-002"></a>
### REQ-002 退役入口不会回流且唯一验证入口仍闭环

- 所有最小 gate 通过，且高置信退役路径无活动源码引用。

<a id="req-003"></a>
### REQ-003 可再生产输出的统一边界：`.qwq_output/`、Flutter/Gradle/Node/Python

- 可再生产输出的统一边界：`.qwq_output/`、Flutter/Gradle/Node/Python

## 4. 契约引用

- canonical：`specs/feature-tree/runtime/system-architecture-and-engineering-guide/repository-layout-hygiene-and-retirement/spec.md`
- canonical：`quwoquan_ops/cli/repo_hygiene_audit.py`
- canonical：`quwoquan_ops/gate/verify_service_architecture.py`
- canonical：`quwoquan_data/scripts/cli.py`
- canonical：`quwoquan_data/scripts/verify/handler.py`
- canonical：`.github/workflows/ml_training_pipeline.yml`
- canonical：`.github/workflows/verify-chat-avatar-commercial-matrix.yml`
- canonical：`quwoquan_ops/gate/verify_entrypoint_script_paths.py`
- canonical：`quwoquan_ops/gate/verify_markdown_local_links.py`
- canonical：`quwoquan_ops/gate/verify_media_delivery_contract.py`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 inventory 能保护脏工作树并输出可复验证据

- GIVEN 仓库同时存在 Git 跟踪、未跟踪、ignored、generated、vendor 和本地输出路径。
- GIVEN 工作树包含用户正在修改的文件和运行中的环境输出。
- WHEN 执行 python3 quwoquan_ops/cli/repo_hygiene_audit.py。
- THEN 报告写入 QWQ_OUTPUT_ROOT/env/repo/runs/，逐路径记录 Git 状态、大小、分类和哈希预算结果。
- THEN 当前 WIP 归入 protected_wip，且不进入自动删除候选。

<a id="gwt-002"></a>
### GWT-002 退役入口不会回流且唯一验证入口仍闭环

- GIVEN Service 根、Data verify、Makefile、活动 workflow 和发布计划存在历史路径漂移。
- WHEN 执行 Service layout gate、Data verify all、输出根 gate 和 repository hygiene local contract。
- THEN Service 根的 tracked *.test/Mach-O/ELF 构建产物被阻断，删除中的工作树文件不被误报。
- THEN Data 验证只经 cli.py verify all，历史 audit 入口和无效 Make target 不再注册。
- THEN ML workflow 使用 service-owned scripts，chat-avatar workflow 不默认读取 ignored manifest。
- THEN 活动 Make/Actions/gate 的脚本路径全部存在，第一方 Markdown 本地链接无断链。
- THEN 特性树不存在 tree/index/registry/changelog/backlog，目录与父子 spec 完整自解释。
- THEN 旧无 slice 与未引用 archived 媒体副本为零，全部权威媒体引用均有物理对象。
- THEN App 不打包无消费者配置，已清零语义基线不可通过 update-baseline 回流。

## 6. 依赖

- 前置要求：[`system-architecture-and-engineering-guide`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 超大实现文件持续收敛

- 类型：`risk`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：超过仓库行数预算的实现文件会混合多个职责，增加修改与审核风险。
- 完成判定：`GWT-002` 的最小门禁闭环子句在拆分后仍成立——动态文件预算门禁无超限项；拆分保持原 facade、契约和相关测试通过。

<a id="open-003"></a>
### OPEN-003 取证隔离区与输出布局门禁互斥，两者都无法同时成立

- 类型：`risk`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：`.qwq_output/data/quarantine/unauthorized-scale022-pids4167-5219-20260808/` 是一次未授权规模化执行事件的取证隔离区，其 `QUARANTINE.json` 判定为 `decision: GATE_BLOCK/WAIT_CONTENT`、`consumption: forbidden`、`recovery: retain_for_forensics_only`，必须永久保留。但它内含 `specs/`、`quwoquan_ops/policies`、各服务 `contracts/` 与 `quwoquan_data/schema` 的源真相副本，触发 `REQ-003` 的输出边界规则，使 `verify_output_layout.py` 与 `verify_root_layout.py` 永久 FAIL。现有豁免机制 `quwoquan_data/scripts/governance/protected_quarantine_evidence.py` 只认 `local/workspace/quarantine/<child>` 路径且必须绑定一份 output-layout migration apply receipt，是为布局迁移遗留树设计的，取证隔离拿不出这种 provenance。结果是取证保留与输出布局两条规则互斥：保留证据就永远红门，清掉红门就销毁证据。这类冲突不会自己暴露——它表现为一道"反正一直红"的门，久而久之没人再看它输出什么。
- 现状（时间线见 git 历史）：forensic provenance 机制闭合——`protected_quarantine_evidence.py` 的 `forensic` 类以 `QUARANTINE.json` 自身为凭据（要求 `recovery: retain_for_forensics_only`，整树摘要冻结含凭据本身），receipt schema 以 `oneOf` 承载 migration 与 forensic 两套互斥凭据集，forensic 分支的 `provenance`、marker 摘要与三项常量约束和校验器同源，两门与 Data 侧同源消费，8 个 local_contract 用例绑定 `GWT-002` 证明漂移即 BLOCK、未登记照拦。凭据集单轨由 schema 承载而非只由 Python 校验器承载，是这条判据能被机器裁定的前提。但该隔离区本体已在同日被发现从磁盘消失（容器目录 mtime 15:32 后为空，全仓无 `QUARANTINE.json` 残留，本机无 Time Machine 快照），「必须永久保留」的前提已被某次未归因操作破坏——这正是本 OPEN 警告的坏分支。
- 完成判定：`GWT-002` 对应行为满足——从备份恢复 `unauthorized-scale022-pids4167-5219-20260808` 隔离树后执行 `python3 quwoquan_data/scripts/cli.py governance protect-quarantine --provenance forensic --quarantine .qwq_output/data/quarantine/unauthorized-scale022-pids4167-5219-20260808` 完成登记，两门在保留该隔离区的前提下转绿；若确认无备份可恢复，由 owner 裁决以事件记录（含消失时间线与调查结论）替代原始证据后关闭本条。

<a id="open-004"></a>
### OPEN-004 输出布局门与对账工具对环境 runtime 目录的辖区认定互斥

- 类型：`risk`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：当前 `verify_output_layout.py` 对 `env/<env>/local/<target>/` 强制「只允许 `process/` 与 `cache/`」，`env/alpha/local/` 下的 `assistant-skill-package-publisher`、`elasticsearch-cjk-supply-chain`（含 OCI 镜像 tar 与 receipt）、`search-owner-backfill` 三个环境作业产物目录因此长期 FAIL；而修复工具 `stackctl repair --fix reconcile-output-layout` 把同一批路径判为「environment runtime and receipts are outside this operation」的 blocker，明确拒绝迁移。两条规则合起来是：门禁要求搬走、工具拒绝搬、人工删除又可能破坏环境 receipt 链——和取证隔离一样表现为一道「反正一直红」的门。
- 完成判定：`GWT-002` 对应行为满足——对环境作业产物目录的形态做出单一裁决并同源实现：要么 `verify_output_layout.py` 为「带 receipt 的环境作业产物」建立受约束豁免（登记形态 + 内容无 secret 材料），要么 `reconcile-output-layout` 接管此类目录的迁移；裁决后 `env/alpha/local/` 三个现存目录在门禁与工具下同时可判定，且真实测试 `spec_ref` 断言两者对同一路径不再互斥。
