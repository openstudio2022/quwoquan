# ops · incident-inspection · base

## DURING 执行中

- [MUST NOT] 在无可复现失败测试或 replay 前尝试自动修复线上问题
  check: 修复动作缺少复现证据链接，判失败
- [MUST NOT] 把用户隐私字段（token、手机号、精确位置）原样写入报告或工单
  check: 报告中出现未脱敏的敏感字段，判失败

## POST 自检

- [MUST] 每个定级结论（P0-P3）有影响面与频次数据支撑
  check: 定级只有主观描述、无 fingerprint 频次或影响用户数，判失败
- [MUST] 需要环境操作（重启、回滚、扩容）的处置走 `stackctl`，留有命令与输出
  check: 手工处置无记录，判失败

## HANDOFF 交接

- 产出：定级结论、处置记录与复现证据
- 未决项去向：未定位的 fingerprint 转 `OPEN-###` 或工单
- 下一步：修复走 `dev` 工作流，其 PRE 需要复现证据
- 证据链：ES 查询与 stackctl 输出
