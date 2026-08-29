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

## 执行

1. PRE 由主会话确认 owner、scope、验收、OPEN、依赖和命名 evidence，自动 Reviewer 为零。
2. metadata/contract 变更先改 authoring source，再 verify/codegen；不手改生成物。实现按 Red/Green/Refactor 闭环，测试 `spec_ref` 绑定对应验收。
3. 尊守 manifest 加载的领域/技术设计；不从 Review 角色复制功能事实，不为错误实现保留 shim/fallback。
4. 执行影响面最小且足够的 `local_contract/api_integration/user_acceptance` 与 gate。POST 先运行 Review plan 中去重 evidence，再派 Developer 主审与最多一名专审。

## 完成证据

实现字节、生成物身份、测试/gate 命令与退出码、未执行验证、OPEN 变化和 POST Review 均绑定当前 HEAD+脏树指纹。源码 PASS、编译、runtime 与 UAT 分层报告。

## 失败与停止

spec/design/owner 未冻结时回 prd/design/explore。required evidence 失败时返回首个 typed blocker 且不启 Reviewer；required Reviewer incomplete 不自动重试。不因外域脏树红项伪称本 scope 成功。

## 条件性交接

普通闭环只交付文件、验证和未决项。跨会话未完成、多人并行、环境/发布、外部阻断或证据需复用时，才持久化 owner/scope、产物、指纹、typed blocker 和唯一下游。
