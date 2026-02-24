---
name: /opsx-apply-tree
id: opsx-apply-tree
category: Workflow
description: 按特性目录树节点执行 contracts-first 开发与自动化验收
---

执行步骤：

1) 选择目标特性目录（L2/L3/L4/L5）
2) 先完成目录内：
- `spec.md`（功能说明/约束/验收重点）
- `tasks.md`（可执行任务）
- `acceptance.yaml`（A1~A8 + 测试映射）

3) 开发顺序（强制）：
- contracts/openapi + metadata
- mock
- 实现
- contract tests
- integration tests
- uat automation

4) 运行门禁：

```bash
make verify
make gate
```

5) CI/合入前：

```bash
make gate-full
```

