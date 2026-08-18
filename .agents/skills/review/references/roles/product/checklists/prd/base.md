# product · prd · base

## PRE 准入

- [MUST] 能用一句话说清「谁 / 在什么场景下 / 得到什么」
  check: 读需求描述；说不清主体或场景，或只描述技术动作（如「重构 X」）而无用户结果，判失败
- [MUST] In Scope 与 Out of Scope 都显式写出
  check: 只写 In Scope 未写 Out of Scope 判失败——这是最高频漏项
- [MUST] 归属唯一：能定位到 `L1_domain_service / L2_business_capability / L3_story` 父链
  check: 无归属节点，或被多个 L1 同优先级认领，判失败并要求先修规格归属
- [MUST] 已挂到 AppRoot 的 Journey / Scenario
  check: 找不到承接的 Journey，判失败（横切工程能力可例外，但必须显式声明它是横切）
- [SHOULD] 验收意图已选定：`UAT / DOM / SIT / GWT / contract` 中的哪几类

## DURING 执行中

- [MUST NOT] 建中央 backlog、feature registry/index、changelog、成熟度矩阵或第二套状态台账
  check: 新增或改动的文件里出现跨节点汇总的状态台账，判失败
- [MUST NOT] 把未完成能力写成已实现的 REQ；未完成一律进 `OPEN-###`
  check: 逐条 REQ 找对应测试或实现；找不到落地证据却写成现行 REQ，判失败

## POST 自检

- [MUST] 特性树结构、链接与章节合规
  gate: make verify-feature-tree
- [SHOULD] 目标节点能生成最小完整上下文
  gate: make feature-context TARGET=<目标 spec 路径>

## HANDOFF 交接

- 产出：更新后的 `spec.md` 路径、REQ/GWT 编号、Journey/Scenario 归属
- 未决项去向：范围存疑的部分明确判 Out of Scope 或转最低可关闭节点 `OPEN-###`
- 下一步：`design`，其 PRE 需要本次的验收意图与父链归属
- 证据链：`make verify-feature-tree` 输出
