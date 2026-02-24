---
name: /opsx-verify
id: opsx-verify
category: Workflow
description: 验证实现匹配制品 + 自动 G3 门禁
---

> 主线：`specs/00_MASTER_DEVELOPMENT_FLOW.md` — 阶段 4

验证特性实现匹配制品（specs、tasks、acceptance），并自动执行全量门禁。

## 步骤

### 1. 完成度检查

1) 读取目标特性的 `tasks.md`，逐项检查是否标记完成
2) 读取 `acceptance.yaml` A1~A8，逐项确认是否有对应实现
3) 生成完成度报告

### 2. 正确性检查

1) 确认实现符合 `spec.md` 的需求描述
2) 确认实现符合 `design.md` 的设计决策
3) 确认代码遵循 DDD 分层 + metadata-first + runtime 统一

### 3. 自动 G3 卡点：全量门禁

AI Agent **必须自动执行**：

```bash
make gate-full
```

包含：
- `make verify` — metadata 一致性
- `make build` — 全量编译（Go + Flutter analyze）
- `make test-contract` — 契约测试（真实数据库）
- 结构约束（DDD 导入、数据库隔离、codegen hash）
- 端侧语义（硬编码字面量、包引用）
- 特性树一致性

**任一失败 → 输出错误 + 修复建议 → 修复后重跑。**

### 4. 输出

```
验证报告：<feature-name>

| 维度 | 状态 |
|------|------|
| 完成度 | X/Y tasks, A1~A8 覆盖率 |
| 正确性 | spec/design 一致性 |
| 门禁 | make gate-full PASS/FAIL |

CRITICAL: ...
WARNING: ...
SUGGESTION: ...

结论：Ready for archive / 需修复 N 项
```
