---
name: dev
description: Implement a frozen Story, capability, or object-level extension and close the loop with real tests - metadata-first, then verify/codegen, then Red/Green/Refactor. Use when the user says 实现, 修复, 开始写代码, 加字段, 加接口, 加事件, 加查询, 加对象, 加存储 adapter, 新建服务, or asks for a code change whose spec and design are already settled.
metadata:
  kind: workflow
  command: /dev
---

# dev

## 触发与输入

用于实现已冻结 Story、能力、对象扩展或修复。输入是用户目标、plan/diff、已知路径、冻结验收与共享写点；调用前不要求 owner manifest。角色交互只引用 `quwoquan_ops/policies/human_agent_delivery_contract.yaml#workflow_interaction_binding.bindings.dev`，可见输出由 canonical projector 生成。

## 执行

1. PRE 从用户目标、plan/diff 与已知路径确定 exact target；读取最近子树 `AGENTS.md`，运行默认 compact `make feature-context TARGET=<exact-path>`，保存 stdout 的 immutable exact ref，再确认 owner、scope、验收、OPEN、依赖和命名 evidence。若 target 含手写源码，只以 `make code-health-hotspots OWNER=<owner-scope>` 加载该 owner 的紧凑阈值、热点与薄弱点（`unavailable` 时照常继续），不加载全仓报告。
2. metadata/contract 变更先改 authoring source，再 verify/codegen；实现按 Red/Green/Refactor 闭环。DURING 必须 search-before-create、采用最简单可测实现并在同一增量删除被替代旧轨；不因单次复用需求造框架，测试 `spec_ref` 绑定对应验收，不为错误实现保留 shim/fallback。
3. 执行影响面最小且足够的 `local_contract/api_integration/user_acceptance` 与 gate，分层报告源码、编译、runtime、release 与 UAT。
4. POST 复用 PRE owner identity ref，并从 current exact changed paths 生成 candidate evidence predecessor；手写源码 candidate 必须产出 current `code-health-delta` named evidence。报告命名 evidence 命令与退出码；默认零 Reviewer。只在用户显式 `/review`，或增量进入 lane→`dev1.0` PR、handoff、release 准出时，才按 review Skill 派 Developer 主审与最多一名专审。

## 完成证据

实现字节、生成物身份、测试/gate 命令与退出码、未执行验证与 OPEN 变化均绑定 current HEAD、脏树指纹与 immutable ref；未评审的增量如实标注"未评审"，不伪称已准出。

## 失败与停止

spec/design/owner 未冻结或 exact ref stale 时回 prd/design/explore。required evidence 失败时保留首个 typed blocker；不因外域脏树红项伪称本 scope 成功。

## 条件性交接

空 triggers 的普通闭环返回 `no_persistent_handoff`，不要求 artifact/Review/authority，也不创建 projection/store。canonical 六类 trigger 任一成立（包括 `cross_session_incomplete`、`multi_party_parallel`）都进入完整 owner/candidate/named evidence/Reviewer/consolidation 与 authoritative create-once store，不降级为临时 checkpoint。需要环境操作、内容发布或事故检视时交对应专用 Skill，但源码/spec mutation 仍回 Feature workflow。
