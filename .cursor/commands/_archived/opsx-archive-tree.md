---
name: /opsx-archive-tree
id: opsx-archive-tree
category: Workflow
description: 基于特性目录树归档完成特性并输出复盘
---

执行步骤：

1) 校验目标特性目录的 `tasks.md` 是否全部完成
2) 校验 `acceptance.yaml` 的 A1~A8 是否均有自动化映射
3) 执行：

```bash
make verify
make gate-full
```

4) 将特性实例迁移到归档目录（或标记 archived）
5) 生成复盘摘要（问题、收益、回滚记录、后续优化）

人工确认点：
- 是否允许带风险项归档
- 是否进入下一批 L2/L3 开发

