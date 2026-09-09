---
name: dev
description: Implement a frozen Story, capability, or object-level extension with real tests - metadata-first, then verify/codegen, then Red/Green/Refactor. Use when the user says 实现, 修复, 开始写代码, 加字段, 加接口, 加事件, 加查询, 加对象, 加存储 adapter, 新建服务, or asks for a code change whose spec and design are settled.
metadata:
  kind: workflow
  command: /dev
---

# dev

## 触发与输入

用于实现已冻结 Story、能力、对象扩展或修复。输入是用户目标、plan/diff、已知路径、冻结验收与共享写点。

## 执行

1. PRE 从用户目标、plan/diff 与已知路径确定 exact target；读取最近子树 `AGENTS.md`，运行 `make feature-context TARGET=<exact-path>` 并保存 immutable exact ref（写入前必须持有），再确认 owner、scope、验收、OPEN、依赖和命名 evidence。lane 落后本地 `dev1.0` 超过 `worktree_policy.yaml#resync_reminder_behind_commits` 时先建议 `sync-lane-from-dev`，避免在过时基线上实现。target 含手写源码时只以 `make code-health-hotspots OWNER=<owner-scope>` 加载该 owner 的紧凑热点（`unavailable` 时照常继续），不加载全仓报告。
2. metadata/contract 变更先改 authoring source，再 verify/codegen；实现按 Red/Green/Refactor 闭环。DURING 必须 search-before-create、采用最简单可测实现并在同一增量删除被替代旧轨；不因单次复用需求造框架，测试 `spec_ref` 绑定对应验收，不为错误实现保留 shim/fallback。
3. 执行影响面最小且足够的 `local_contract/api_integration/user_acceptance` 与 gate，分层报告源码、编译、runtime、release 与 UAT。
4. POST 复用 PRE owner identity ref，从 current exact changed paths 生成 candidate evidence predecessor；手写源码 candidate 必须产出 current `code-health-delta` named evidence。报告命名 evidence 命令与退出码，默认零 Reviewer。

## 完成证据

实现字节、生成物身份、测试/gate 命令与退出码、未执行验证与 OPEN 变化均绑定 current HEAD、脏树指纹与 immutable ref；未评审的增量如实标注"未评审"，不伪称已准出。

## 失败与停止

spec/design/owner 未冻结或 exact ref stale 时回 prd/design/explore。required evidence 失败时保留首个 typed blocker；不因外域脏树红项伪称本 scope 成功。

## 条件性交接

需要环境操作、内容发布或事故检视时交对应专用 Skill，源码/spec mutation 仍回 Feature workflow。持久交接语义见 continue Skill。
