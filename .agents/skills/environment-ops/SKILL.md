---
name: environment-ops
description: Use stackctl to package, start, verify, inspect, diagnose, repair, and deploy the alpha/beta/gamma/prod environment topology. Make sure to use this skill whenever the user mentions 环境启动, 打包, URL, 路由, 健康检查, 巡检, 部署, 灰度, 回滚, stackctl, gamma-local, prod-hosted, prod gray rollout, or any environment troubleshooting in this repository, even without an explicit command.
metadata:
  kind: workflow
---

# environment-ops

## 触发与输入

在环境打包、启动、URL/路由、health、inspect、doctor、repair、部署、灰度、回滚或
任何 `stackctl` 故障排查时使用。取得目标环境/target、服务和操作意图；发布另需不可变
image/config/manifest、SLO 与审批状态，恢复另需当前诊断证据和白名单内修复动作。

环境操作者、发布操作者和恢复操作者的特殊步骤只在对应模式下读取
[roles/](references/roles/)；普通查询不预载发布或恢复约束。



自然语言触发与显式 Skill 调用同轨，字段、闭集与审计隔离只引用 `quwoquan_ops/policies/human_agent_delivery_contract.yaml#workflow_interaction_binding.environment-ops`：

- PRE：`progress_update` / `nonproduction_validation` / `environment_reliability_owner`。

## 执行

唯一操作面是 `python3 quwoquan_ops/cli/stackctl.py`（`make dev-up` 只是受控入口）：

- 构建/启动：`package --env <alpha|beta|gamma|prod>`，然后
  `up --env <alpha|beta|gamma|prod-sim|prod> [--device-id <id>]`。
- 验证：`verify --kind all --profile <baseline|smoke|integration|release>`；无环境依赖选
  `baseline`，四环境 Remote 启动和 release 只读探针选 `smoke`，Alpha/Beta/Gamma
  内容数据平面选 `integration`，Gamma 商业观测和 Prod 选 `release`。
- 诊断固定为 `health --target <target> --scope <scope>` →
  `inspect --target <target> --kind <kind>` → `doctor --target <target>`；仅白名单问题才
  `repair --target <target> --fix <rebuild-packages|restart-stack|reclaim-ports>`。
- 生产发布只用 `deploy --target prod-hosted ...`，按 `canary / 5 / 20 / 50 / 100`
  rollout stage 推进；完整参数和停止点从
  [release-operator.md](references/roles/release-operator.md) 按需加载。
- 第一方容器预验证只用 `deploy --target prod-hosted --mode prevalidate ...`，且必须传入
  `--ssh-host`、`--data-mode`、`--prevalidate-scope first-party` 和
  `--release-manifest`；它不接受 rollout/SLO/rollback 参数，不可提升，也不写正式
  release ledger/receipt。

`prod-gray` 不是环境；生产灰度属于 `prod` rollout。`gamma` 只表示本地
`gamma-local`，远端目标只有 `prod-hosted`。端口从
`quwoquan_ops/environments/local_env_port_manifest.yaml` 读取，拓扑从目标环境
`runtime.yaml` 读取，禁止手写或把 `--ssh-host` 写入 runtime public base。

- 执行中：`exception_escalation` / `production_campaign` / `$route`。

`$route` 表示按当前决定责任动态路由；Skill 不复制 envelope schema，所有可见输出统一由 canonical projector 生成。

## 完成证据

分别报告 package、启动、health、运行探针、发布/回滚和真实 UAT 的实际结果，并引用：

- `.qwq_output/env/<env>/runs/<run-id>/report.json` 与 `summary.md`
- `.qwq_output/env/gamma/local/gamma-local/process/report.json`
- `QWQ_OUTPUT_ROOT/env/prod/local/prod-hosted/process/release-state/<service>.state`

涉及 prod rollout/rollback 的 POST Review 先由主会话按 Review registry 解析并执行一次
去重的命名 evidence，再调用 `review`（workflow=`environment-ops`、segment=`POST`、
deliverable=`release-evidence`）。主审是 `ops`，命中环境发布 profile 时至多增加一个
`infra-capacity` 专审。Reviewer 不运行 gate。纯 `health`、`inspect`、只读 `verify` 不自动
派审；required evidence 或 required Reviewer 未完成即返回 typed `GATE_BLOCK`。

- POST：`completion_report` / `production_campaign` / `$route`。

## 失败与停止

以下情况 fail closed，并保留首个 typed blocker：

- 生产审批、放量范围或回滚目标不明确；缺少 credential、hosted base URL 或发布必填
  service/image/config/step/SLO。
- prevalidate 缺 OCI digest manifest、来源不是 clean reviewed `main`、主机低于资源门或
  端口冲突；prevalidate 永远不能作为 release eligibility。
- `prod-hosted inspect/doctor` 未同时证明 user systemd enabled/active、容器状态和镜像
  identity；`--ssh-host` 只用于隔离账号巡检。
- health/inspect/doctor 暴露配置、artifact、host 或 identity 污染；不得用旧 receipt
  覆盖当前失败。
- repair 超出白名单或需要破坏性动作；停止并向用户取得额外授权。

## 条件性交接

六类触发（跨会话未完成、多人并行、环境/发布、外部阻断、证据复用、用户显式要求）统一调用 canonical handoff producer；普通闭环不落持久交接。

仅当路由结果要求真实人类责任时，使用统一 `$route`、project/card 与 hosted authority readback；routine execution 不新造 checkpoint。Reviewer PASS 只是评审证据，不能签发或替代 authority receipt。
