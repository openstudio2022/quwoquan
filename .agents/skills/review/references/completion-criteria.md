# workflow×deliverable 完成判据表

每个工作流的「完成」只有一个定义：本表列出的 verify 判据全部通过（命令退出 0，或 check 谓词客观成立）。
禁止用计数、抽样、日志观感等代理指标冒充准出；写不出判据 = RESOLVE 未完成，不许开工。
各 SKILL.md 的 HANDOFF 段引用本表；证据链条目必须带「命令 + 退出码 + 时间戳 + 工作树 SHA」，
下游 RESOLVE 消费时证据过期即复跑，不得转抄结论。

## explore

- deliverable：RESOLVE 报告。
- verify: `make feature-context TARGET=<目标路径>` 退出 0 且 owner 唯一（GATE_BLOCK 即未完成）。
- check: 报告含唯一 `(workflow, deliverable, scope)`、完整父链、In/Out Scope、验收意图与证据层、下游 PRE 输入全部必需项；纯查询任务直接答复，无交付判据。

## prd

- deliverable：spec 增量。
- verify: `make verify-feature-tree` 退出 0（含新增验收锚点与 OPEN 的结构校验）。
- check: 每条新增验收锚点可被真实测试绑定或由同节点 OPEN 挂账；无占位符、无自相矛盾。

## design

- deliverable：DEC 集。
- verify: `make verify-feature-tree` 退出 0。
- check: 每条 DEC 有可测试观察面与受影响 metadata 路径；不复述 spec。

## dev

- deliverable：实现增量。
- verify: 变更域 local_contract 测试全绿；关联 gate（按 changed_paths 派生）退出 0；动了规格时 `make verify-feature-tree` 退出 0。
- check: 失败门禁不得包装为成功；域外已知红按并行协议登记而非静默吞掉。

## continue

- deliverable：推进结果与诚实汇报。
- verify: 与被续跑轮次相同的判据（继承原 workflow 的本表条目）。
- check: 每个「已完成」都有验证证据而非记忆；未完成项与阻塞点无一遗漏。

## plan-next

- deliverable：闭环裁决 + 下一轮计划。
- verify: 上一轮声明的全部 verify 判据已复核（过期证据复跑）。
- check: 每个缺口落到「修复 / OPEN-### / Out of Scope」三者之一，零悬空；下一轮计划覆盖下游 PRE 输入。

## review

- deliverable：评审报告。
- verify: 去重 gate 证据计划全部执行完毕（每个 gate 退出码如实记录）。
- check: 全部派发角色返回结论；有 GATE_BLOCK 时整体判 GATE_BLOCK，不得降级。

## commit

- deliverable：提交回执。
- verify: `quwoquan_ops/gate/commit_gate.sh` 退出 0；提交后 `git status` 确认目标文件已入库。
- check: 提交内容与 HANDOFF 产出物清单一致；无秘密文件、无无关改动混入。

## environment-ops

- deliverable：环境操作回执。
- verify: `python3 quwoquan_ops/cli/stackctl.py verify --kind all --profile <按证明边界选定>` 退出 0。
- check: 回执引用 `.qwq_output/env/<env>/runs/<run-id>/` 真实运行证据，不引用记忆。

## content-production

- deliverable：immutable release 与环境导入证据。
- verify: 各阶段 verify 门禁退出 0；stage receipt 链完整（create-once，无跳段）。
- check: release 目录、环境 run 与 App UAT 收据经 receipt 链绑定到 execution。

## incident-inspection

- deliverable：脱敏巡检报告。
- verify: 只读工作流，无变更判据；报告生成命令退出 0。
- check: 每个 fingerprint 有优先级、owner 与 `report-only / handoff-dev` 结论；无复现证据不进入修复。
