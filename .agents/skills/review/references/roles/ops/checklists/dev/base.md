# ops · dev · base

## PRE 准入

- [MUST] 与影响面匹配的 gate 已选定并实际跑过
  check: 只跑了 `dart analyze` 之类的编译检查就宣称验证完成，判失败

## DURING 执行中

- [MUST NOT] 用 `--no-verify` 绕过 pre-commit 作为常规手段
  check: 提交记录或会话中出现 `--no-verify` 且无一次性的明确理由，判失败
- [MUST NOT] 新增 allowlist 或放宽棘轮基线来让门禁转绿
  gate: make verify-ratchet-baseline-governance
- [MUST NOT] 把 deployment payload 或渲染配置写回 `.qwq_output`
  check: `.qwq_output` 只放可删除可重建的运行输出；删除后无法凭版本控制真相源重建，判失败

## POST 自检

- [MUST] 环境拓扑与打包一致（本次触及环境定义时）
  gate: make verify-env-topology
- [MUST] 环境实例隔离成立（本次触及环境定义时）
  gate: make verify-env-instance-isolation
- [MUST] 棘轮基线治理合规（本次动过基线时）
  gate: make verify-ratchet-baseline-governance
- [SHOULD] 全局增量约束通过
  gate: make verify-global-increment-constraints

## HANDOFF 交接

- 产出：gate 执行清单与结果、环境证据路径
- 未决项去向：未通过项转 `OPEN-###` 并标注准出影响；不得静默略过
- 下一步：POST 评审汇总
- 证据链：全部 gate 输出，含失败项原文
