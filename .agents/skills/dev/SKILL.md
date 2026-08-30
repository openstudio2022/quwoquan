---
name: dev
description: Implement a frozen Story, capability, or object-level extension and close the loop with real tests - metadata-first, then verify/codegen, then Red/Green/Refactor. Use when the user says 实现, 修复, 开始写代码, 加字段, 加接口, 加事件, 加查询, 加对象, 加存储 adapter, 新建服务, or asks for a code change whose spec and design are already settled.
metadata:
  kind: workflow
  command: /dev
---

# dev

## 触发与输入

用于实现已冻结 Story/能力/对象扩展或修复。输入必须包含 owner manifest、当前 REQ/验收、必要 DEC/contracts、影响路径与共享写点状态。



自然语言触发与显式 Skill 调用同轨，字段、闭集与审计隔离只引用 `quwoquan_ops/policies/human_agent_delivery_contract.yaml#workflow_interaction_binding.dev`：

- PRE：`progress_update` / `agent_led_implementation` / `engineering_delivery_owner`。

## 执行

1. PRE 由主会话确认 owner、scope、验收、OPEN、依赖和命名 evidence，自动 Reviewer 为零。
2. metadata/contract 变更先改 authoring source，再 verify/codegen；不手改生成物。实现按 Red/Green/Refactor 闭环，测试 `spec_ref` 绑定对应验收。
3. 尊守 manifest 加载的领域/技术设计；不从 Review 角色复制功能事实，不为错误实现保留 shim/fallback。
4. 执行影响面最小且足够的 `local_contract/api_integration/user_acceptance` 与 gate。POST 先运行 Review plan 中去重 evidence，再派 Developer 主审与最多一名专审。

- 执行中：`exception_escalation` / `agent_led_implementation` / `$route`。

`$route` 表示按当前决定责任动态路由；Skill 不复制 envelope schema，所有可见输出统一由 canonical projector 生成。

## 完成证据

实现字节、生成物身份、测试/gate 命令与退出码、未执行验证、OPEN 变化和 POST Review 均绑定当前 HEAD+脏树指纹。源码 PASS、编译、runtime 与 UAT 分层报告。

- POST：`completion_report` / `agent_led_implementation` / `engineering_delivery_owner`。

## 失败与停止

spec/design/owner 未冻结时回 prd/design/explore。required evidence 失败时返回首个 typed blocker 且不启 Reviewer；required Reviewer incomplete 不自动重试。不因外域脏树红项伪称本 scope 成功。

## 条件性交接

六类触发（跨会话未完成、多人并行、环境/发布、外部阻断、证据复用、用户显式要求）统一调用 canonical handoff producer；普通闭环不落持久交接。

仅当路由结果要求真实人类责任时，使用统一 `$route`、project/card 与 hosted authority readback；routine execution 不新造 checkpoint。Reviewer PASS 只是评审证据，不能签发或替代 authority receipt。
