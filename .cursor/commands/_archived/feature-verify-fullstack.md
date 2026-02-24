---
name: /feature-verify-fullstack
id: feature-verify-fullstack
category: Quality
description: 校验特性映射、元数据契约与端云门禁状态
---

在仓库根目录执行：

```bash
make verify
make gate
```

若准备合入主分支或发版，再执行：

```bash
make gate-full
```

检查项：
- 特性台账与 traceability 完整性
- 特性树层级与父子关系合法性
- specs L1 目录层级与索引一致性
- feature-tree 重构索引与目录完整性
- 元数据契约完整性
- 云侧 contracts/specs 一致性
- 端侧分析通过（CI 中执行全量测试）

建议复用：
- 若特性已在 OpenSpec 变更流中，额外执行 `/opsx-verify`，避免重复实现但漏改 artifacts。

