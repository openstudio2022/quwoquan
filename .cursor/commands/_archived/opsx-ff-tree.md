---
name: /opsx-ff-tree
id: opsx-ff-tree
category: Workflow
description: 基于特性目录树快速创建并补齐特性开发骨架
---

在仓库根目录执行：

1) 选择 L1 节点（`specs/feature-tree/tree_index.yaml`）
2) 选择对应 L1 的 `tree.yaml`（L2-L5）
3) 运行脚手架：

```bash
bash scripts/scaffold_feature_tree_from_yaml.sh "specs/feature-tree/<l1>/tree.yaml"
```

4) 生成特性实例目录：

```bash
bash scripts/new_feature_fullstack.sh "<slug>"
```

5) 绑定树上下文到 `acceptance.yaml` 与 `traceability.yaml`，并补齐 A1~A8。
6) 执行 `make verify`。

要求：
- 必须先树后实现（tree-first）
- 每个目录特性固定 `spec.md`
- 人工仅确认边界、风险、上线窗口

