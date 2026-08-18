# product · explore · base

explore 是只读的。你的任务是把「现在是什么样」说清楚，不是提方案。

## PRE 准入

- [MUST] 探索目标明确：要回答哪个具体问题
  check: 目标是「看看代码」这类无边界描述，判失败
- [SHOULD] 已确认目标区域的 owner 节点，或确认它缺 owner

## DURING 执行中

- [MUST NOT] 在 explore 写实现
  check: `git status --porcelain` 与本次 explore 开始时一致；出现新的改动，判失败
- [MUST NOT] 把推测写成事实。未验证的结论必须标注为待验证
  check: 每条结论要么带 `文件:行`，要么显式标「待验证」；两者都无，判失败
- [MUST NOT] 新建人工索引、清单或状态镜像来「整理」探索结果
  check: 新增文件里出现 registry / index / inventory / matrix 性质的台账，判失败

## POST 自检

- [MUST] 结论有路径级证据：每条事实指向具体文件与行
  check: 存在无出处的断言，判失败
- [MUST] 归属结论明确：目标区域是被某个 L1 唯一认领、被多个 L1 同优先级认领，还是无 owner
  gate: make feature-context TARGET=<目标路径>
- [SHOULD] 已识别出与探索目标相关的现存 `OPEN-###`

## HANDOFF 交接

- 产出：现状事实清单（每条带 `文件:行`）、owner 归属结论、相关 OPEN 清单
- 未决项去向：发现的归属冲突或无 owner 区域必须转 `OPEN-###`，因为它会阻断后续所有工作流
- 下一步：`prd`（要做需求）或 `design`（现状已清楚、直接进设计）
- 证据链：`make feature-context` 输出
