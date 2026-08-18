# product · plan-next · base

plan-next 是收口，不是开新坑。你要保证上一轮的每一个未决项都有明确去向。

## PRE 准入

- [MUST] 上一工作流的 HANDOFF 存在且可读
  check: 无 HANDOFF 或未决项段为空但实际有遗留，判失败——断链必须阻断
- [MUST] 上一工作流每个未决项都已落到「转 `OPEN-###`」「判 Out of Scope」
  「下一工作流承接」三者之一
  check: 存在既未关闭也未转 OPEN 的悬空项，判失败

## DURING 执行中

- [MUST NOT] 创建任务清单、changelog、成熟度矩阵或中央风险台账
  check: 新增文件里出现跨节点的任务或风险台账，判失败；计划只允许留在当前会话
- [MUST NOT] 把已完成事项留在 `OPEN` 里当日志；解决后必须删除 OPEN 并转为当前 REQ/设计事实
  check: 逐条 OPEN 核对是否已有落地证据；已完成却仍在 OPEN，判失败
- [MUST NOT] 把 OPEN 挂到高于必要层级的节点；必须挂最低可关闭节点
  check: 对每条 OPEN 找能独立关闭它的最低节点；挂点高于该节点，判失败

## POST 自检

- [MUST] 特性树合规，无 OPEN 悬挂错层
  gate: make verify-feature-tree
- [SHOULD] 变更影响报告已生成
  gate: make feature-tree-change-report

## HANDOFF 交接

- 产出：本轮 OPEN 变化（新增/关闭各哪些）、下一步建议的 workflow 与 deliverable
- 未决项去向：全部已分派完毕，此段应为空。不为空说明 plan-next 没做完
- 下一步：新一轮 `RESOLVE`
- 证据链：`make verify-feature-tree` 输出
