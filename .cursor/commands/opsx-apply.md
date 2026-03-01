---
name: /opsx-apply
id: opsx-apply
category: Workflow
description: 实施特性（逐 task 执行 + 每 task 自动 G2 卡点）
---

> 主线：`specs/00_MASTER_DEVELOPMENT_FLOW.md` — 阶段 3

## 前置条件检查（执行前必须满足）

执行本命令前，AI Agent **必须先检查**以下前置条件：

| # | 检查项 | 判定方式 |
|---|--------|----------|
| 1 | 目标特性已创建 | 目标节点目录存在，且包含 spec.md、design.md、tasks.md、acceptance.yaml |
| 2 | G0+G1 已通过 | 曾有 `/opsx-ff` 完成，且 make verify + codegen 已通过 |
| 3 | tasks.md 已就绪 | tasks.md 中有可执行任务列表，顺序为 metadata → codegen → 业务逻辑 → 测试 |
| 4 | 节点层级符合规范 | 目标节点层级符合 `01_FEATURE_TREE_LEVEL_DEFINITIONS.md`（L4 默认叶子，L5 仅 subtask 时存在） |

**若不满足**：不执行实施步骤；输出**补全列表**，引导用户按列表补全后再执行 `/opsx-apply`。

### 补全列表（前置不满足时输出）

```
前置条件不满足，请先完成以下项后再执行 /opsx-apply：

□ [ ] 特性已创建：目标节点目录存在，且具备 spec.md、design.md、tasks.md、acceptance.yaml（若未创建，先执行 /opsx-ff）
□ [ ] G1 已通过：make verify、make codegen、make codegen-app 均已通过
□ [ ] tasks 已就绪：tasks.md 中有明确的当前交付任务，顺序为 metadata → codegen → 业务逻辑 → 测试
□ [ ] 需求已澄清：若需求仍不清晰，先进行 ask 或 /opsx-explore 澄清后再创建/实施

补全后重新执行：/opsx-apply
```

---

## 步骤

### 1. 加载 tasks

读取目标特性的 `tasks.md`，按顺序逐项执行。实现须符合 `spec.md` 与 `design.md`。任务与节点对应：L4 节点下 task 对应 L4 范围；若该节点有 L5 子节点，子任务可在 tasks 中分组或由 L5 节点独立 tasks 承载（见 01_FEATURE_TREE_LEVEL_DEFINITIONS.md 八、8.3）。

**强制开发顺序**：
```
contracts/metadata → make verify → make codegen → 业务逻辑 → 测试
```

如某个 task 涉及扩展操作（新实体/字段/事件等），先执行 `/qwq-extend`。

### 2. 逐 task 执行 + 自动 G2 卡点

每完成一个 task，AI Agent **必须立即自动执行**：

```bash
make build                     # 编译通过（云侧）
make test-contract             # 契约测试通过（云侧）
# 若变更含 quwoquan_app/lib/**/*.dart，追加：
python3 scripts/verify_dart_semantic.py   # Dart 语义 token 检查
```

**失败 → 停止当前 task → 输出错误 + 修复建议 → 修复后重跑 → 通过后继续下一个 task。**

### 3. 约束（实时强制）

| 约束 | 规则 |
|------|------|
| Go DDD 层级依赖 | domain 禁止 import application/adapters/infrastructure |
| Go 数据库隔离 | 仅 infrastructure + tests 可 import 数据库驱动 |
| Go runtime 统一 | 必须用 runtime/errors、runtime/config、runtime/messaging |
| Go codegen 保护 | DO NOT EDIT 文件禁止手改 |
| Dart 设计系统 | 禁止硬编码视觉字面量 |
| Dart 包引用 | 禁止相对路径 import |
| Dart Feature 隔离 | Feature 禁止直接 import 其他 Feature |
| 错误码禁止硬编码 | 云侧用 generated.AppErrorFrom*；端侧用 *ErrorCode.fromCode().toDisplayMessage(l10n)；测试用枚举.code |

### 4. 全部 task 完成后

```bash
make gate                      # 本地门禁（verify + build + test-contract）
```

**通过 → 输出实施摘要 → 下一步：`/opsx-verify` 或 `/submit-with-gate`。**
