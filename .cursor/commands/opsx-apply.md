---
name: /opsx-apply
id: opsx-apply
category: Workflow
description: 实施特性（逐 task 执行 + 每 task 自动 G2 卡点）
---

> 主线：`specs/00_MASTER_DEVELOPMENT_FLOW.md` — 阶段 3

## 前置条件

- `/opsx-ff` 已完成（G0 + G1 已通过）
- `tasks.md` 已就绪

## 步骤

### 1. 加载 tasks

读取目标特性的 `tasks.md`，按顺序逐项执行。

**强制开发顺序**：
```
contracts/metadata → make verify → make codegen → 业务逻辑 → 测试
```

如某个 task 涉及扩展操作（新实体/字段/事件等），先执行 `/qwq-extend`。

### 2. 逐 task 执行 + 自动 G2 卡点

每完成一个 task，AI Agent **必须立即自动执行**：

```bash
make build                     # 编译通过
make test-contract             # 契约测试通过
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

### 4. 全部 task 完成后

```bash
make gate                      # 本地门禁（verify + build + test-contract）
```

**通过 → 输出实施摘要 → 下一步：`/opsx-verify` 或 `/submit-with-gate`。**
