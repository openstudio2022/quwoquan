# architect · plan-next · base

## POST 自检

- [MUST] 本轮引入的架构妥协（临时实现、绕过契约、棘轮升水）都已转 `OPEN-###` 或列入下一轮计划
  check: 对照本轮 dev HANDOFF 的未决项；存在既未挂 OPEN 也未进计划的架构残量，判失败
- [MUST] 下一轮计划中的实现任务都有稳定的对象边界与契约基线，或显式声明先走 `design`
  check: 计划任务触及未裁决对象却直接标注为实现任务，判失败
- [SHOULD] 受影响棘轮基线已列出当前值与收敛方向

## HANDOFF 交接

- 产出：架构残量核对结论
- 未决项去向：全部落 OPEN / Out of Scope / 下一轮计划
- 下一步：POST 评审汇总
- 证据链：棘轮基线与 OPEN diff
