---
name: /opsx-archive
id: opsx-archive
category: Workflow
description: 归档特性（自动 G3 全量门禁 + 归档）
---

> 主线：`specs/00_MASTER_DEVELOPMENT_FLOW.md` — 阶段 4

## 步骤

### 1. 完成度检查

1) 校验 `tasks.md` 所有任务已标记完成
2) 校验 `acceptance.yaml` A1~A8 均已映射到自动化

### 2. 自动 G3 卡点：全量门禁

AI Agent **必须自动执行**：

```bash
make gate-full
```

包含：
- metadata 一致性验证
- DDD 结构约束
- codegen hash 比对
- 端侧语义审计（flutter analyze + 硬编码检查）
- 云侧契约测试
- 特性树一致性

**任一失败 → 停止归档 → 输出错误 + 修复建议 → 修复后重跑。**

### 3. 归档

G3 通过后：
1) 标记特性为 `archived`
2) 生成复盘摘要（变更文件数、测试覆盖、耗时等）
3) 下一步：`/submit-with-gate` 提交
