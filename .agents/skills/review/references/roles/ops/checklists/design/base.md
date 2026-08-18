# ops · design · base

## PRE 准入

- [MUST] SLI/SLO 已声明：新增页面、API、行为信号、推荐策略或数据发布都有对应指标与目标值
  check: 读设计文档；存在新增对外能力但无 SLI/SLO 声明，判失败
- [MUST] 配置来源唯一：不手写端口、host、public URL、gateway/media base，统一读
  `quwoquan_ops/environments` manifests 与 stackctl 输出
  check: 设计中出现硬编码 URL 或第二套拓扑表述，判失败
- [MUST] 灰度与回滚路径已声明，且回滚不依赖重新构建
  check: 缺回滚路径，或回滚方式是「重新发一个版本」，判失败
- [SHOULD] 四环境差异只落在 endpoint、容量与发布阶段，不落在数据源或包结构
- [SHOULD] 回滚可在 5 分钟内完成，且旧配置仍在版本控制中可还原

## DURING 执行中

- [MUST NOT] 新增第二套环境脚本入口；环境装配、部署、巡检、修复统一走
  `python3 quwoquan_ops/cli/stackctl.py`
  check: 新增脚本直接操作环境拓扑而未经 stackctl 门面，判失败
- [MUST NOT] 用 allowlist 或棘轮基线掩盖新债
  gate: make verify-ratchet-baseline-governance
- [MUST NOT] 把部署产物写回 `.qwq_output`
  check: `.qwq_output` 只放可删除可重建的运行输出；删除后无法凭版本控制真相源重建，判失败

## POST 自检

- [MUST] 环境拓扑一致
  gate: make verify-env-topology
- [MUST] 环境打包纯度通过
  gate: make verify-env-packaging
- [MUST] 生产装配纯度通过
  gate: make verify-production-wiring-purity
- [SHOULD] gamma-local 与 prod 同构
  gate: make verify-gamma-local-prod-isomorphism

## HANDOFF 交接

- 产出：SLI/SLO 声明、配置来源清单、灰度与回滚步骤
- 未决项去向：缺容量数据的项转 `OPEN-###`，标注需要哪次压测或实测补齐
- 下一步：`dev`，其 PRE 需要本次的回滚路径
- 证据链：上述 gate 的实际输出
