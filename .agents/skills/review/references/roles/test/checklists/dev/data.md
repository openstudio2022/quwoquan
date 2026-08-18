# test · dev · data

适用：改动触及 `quwoquan_data/**` 的管道、schema 或发布流。

## DURING 执行中

- [MUST NOT] 用手工拼装的产物代替 CLI 执行结果作为测试输入
  check: 测试输入不能由 `quwoquan_data/scripts/cli.py` 重建，判失败
- [MUST NOT] 用抽样通过掩盖 schema 全量校验失败
  gate: python3 quwoquan_data/scripts/cli.py verify all

## POST 自检

- [MUST] 数据契约与复用输入校验通过
  gate: make verify-quwoquan-data
- [MUST] release 一致性成立（本次触及发布流时）
  gate: make verify-data-release-consistency

## HANDOFF 交接

- 产出：数据侧测试与校验结果
- 未决项去向：未覆盖的管道环节转 `OPEN-###`
- 下一步：POST 评审汇总
- 证据链：CLI 与 gate 的实际输出
