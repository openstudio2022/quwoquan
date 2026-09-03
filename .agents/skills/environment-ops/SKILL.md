---
name: environment-ops
description: Use stackctl to package, start, verify, inspect, diagnose, repair, and deploy the alpha/beta/gamma/prod environment topology. Make sure to use this skill whenever the user mentions 环境启动, 打包, URL, 路由, 健康检查, 巡检, 部署, 灰度, 回滚, stackctl, gamma-local, prod-hosted, prod gray rollout, or any environment troubleshooting in this repository, even without an explicit command.
metadata:
  kind: workflow
---

# environment-ops

## 触发与输入

用于环境打包、启动、URL/路由、health、inspect、doctor、repair、部署、灰度与回滚。输入是环境/target、服务、操作意图与所需授权；角色交互只引用 `quwoquan_ops/policies/human_agent_delivery_contract.yaml#workflow_interaction_binding.bindings.environment-ops`，可见输出由 canonical projector 生成。

本轮若将产生、更新或恢复 registry 声明的送审交付件 `release-evidence`，PRE 必须从 canonical environment owner fact 唯一反解环境：所选 runtime target 必须只属于一个 `quwoquan_ops/environments/<env>/runtime.yaml` 的 `dataReleaseTarget`/`targets`，并以该 runtime manifest 的 repository-relative exact path 作为 exact target；缺 target、多环境命中或 owner fact 不一致时返回 typed `GATE_BLOCK`。随后运行 `make feature-context TARGET=<exact-path>`，保存 stdout 指向的 content-addressed immutable owner manifest exact ref，PRE 后不得重写或替换该 ref。

## 执行

唯一操作面是 `python3 quwoquan_ops/cli/stackctl.py`。按需执行 package/up/verify/health/inspect/doctor、白名单 repair 或 prod-hosted deploy；环境、URL、端口、拓扑与 rollout 参数只读 canonical manifests/readback，不手写第二事实。打包、启动、健康与巡检只加载 [environment-operator.md](references/roles/environment-operator.md)，候选验证、发布与灰度只加载 [release-operator.md](references/roles/release-operator.md)，诊断、白名单修复与回滚只加载 [recovery-operator.md](references/roles/recovery-operator.md)；组合操作按实际角色加载，不预载无关正文。

纯 `status`、`health`、`inspect` 或其他不产生送审交付件的只读操作不要求 Feature owner manifest；它们只以当前 readback、明确的 `read-only/no-review-deliverable` 或 typed blocker 终止，不得调用 POST Review，也不得声称产出 `release-evidence`。若任务需要修改源码、spec、design、contracts 或测试，立即停止该 mutation，并按目标归属交接 explore/prd/design/dev；环境 Skill 不代替 Feature workflow 的 target/manifest/Review 生命周期。

## 完成证据

分层报告 package、启动、health、runtime probe、发布/回滚与真实 UAT 的当前 receipt/readback；上游 PASS 不替代下游闭环。至少执行并报告 1–3 个适用入口：`python3 quwoquan_ops/cli/stackctl.py health --target <target> --scope <scope>`，其中 target 与 scope 均读取本轮 environment/workload owner facts；`python3 quwoquan_ops/cli/stackctl.py inspect --target <target> --kind <kind>`；`python3 quwoquan_ops/cli/stackctl.py verify --env <env> --kind all --profile <smoke|integration|release>`（无环境依赖时用 `--profile baseline` 且不传 `--env`）。

产生 `release-evidence` 时，POST 必须把 PRE 保存的同一个 owner manifest exact ref 原样作为 `--context-manifest` 传给 Review（workflow=`environment-ops`、segment=`POST`、deliverable=`release-evidence`、scope=`<exact-path>`）；先按 plan 去重执行命名 evidence，再派 registry 主审与至多一名专审。manifest ref 缺失、与 PRE 不同或 stale，required evidence/Reviewer 未完成，均不得完成。

## 失败与停止

生产授权、凭据、hosted identity、回滚目标、required readback、唯一 exact target 或送审 owner manifest 缺失时 fail closed；repair 超白名单或需破坏性动作时请求额外授权，不用旧 receipt 覆盖失败。

## 条件性交接

源码/spec mutation 只交 Feature workflow；外部阻断、环境/发布、跨会话或证据复用满足 canonical 触发时生成 handoff。送审交付的 handoff 必须携带 PRE 保存并在 POST 原样复用的 owner manifest exact ref；纯只读无送审交付不生成替代 manifest。
