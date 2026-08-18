# product · dev · base

对象级扩展最容易发生的产品问题是**加了没人要的东西**：字段、接口、事件
在契约里各自看都合理，合起来没有对应任何已声明的用户价值。

## PRE 准入

- [MUST] 本次扩展能追到已声明的 REQ 或 GWT；不是「顺手加上以后可能用」
  check: 每个新增字段/接口/事件都要指出它服务哪条 REQ；指不出，判失败
- [MUST] 归属唯一：扩展的对象有明确 owner 节点
  gate: make feature-context TARGET=<目标路径>
- [SHOULD] 已确认现有字段或接口确实无法承载该需求，而不是重复建设

## DURING 执行中

- [MUST NOT] 顺带扩大范围：本次未在规格中声明的字段、状态或入口不得夹带进来
  check: 对比 `contracts/**` diff 与 prd 的 In Scope；存在范围外新增，判失败
- [MUST NOT] 把未定的产品决策以「先留个字段」的方式固化进契约
  check: 新增字段无明确语义或无消费方，判失败——契约里的字段删起来比加起来贵得多

## POST 自检

- [MUST] 特性树结构与链接合规
  gate: make verify-feature-tree
- [MUST] 契约与 metadata 一致
  gate: make verify-metadata
- [SHOULD] 变更影响面与预期一致
  gate: make feature-tree-change-report

## HANDOFF 交接

- 产出：本次扩展到 REQ 的对应关系、`contracts/**` diff 范围
- 未决项去向：范围外的想法转 `OPEN-###` 或明确判 Out of Scope，不要留在契约里占位
- 下一步：POST 评审汇总
- 证据链：上述 gate 的实际输出
