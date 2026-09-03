# architect · distill

- [MUST] 每条规则候选有唯一 owner、触发条件和可执行判据。
  check: 逐条读取候选；缺 owner/trigger/evidence-or-check 任一字段时判失败。
- [MUST NOT] 把功能事实沉淀到全局规则或角色 checklist。
  check: 对照候选 owner 与落点；功能局部事实进入全局载体时判失败。
- [MUST NOT] 未经用户确认直接落长期规则资产。
  check: 对照用户确认范围与 diff；出现范围外规则资产时判失败。
