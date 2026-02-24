---
name: /opsx-ff
id: opsx-ff
category: Workflow
description: 创建特性（Plan + Create + 自动 G0/G1 卡点）
---

> 主线：`specs/00_MASTER_DEVELOPMENT_FLOW.md` — 阶段 1+2

## 步骤

### 1. G0 卡点：Plan（需求澄清）

在创建任何文件之前，AI Agent 必须先完成以下检查：

```
✓ 需求已映射到特性树节点（查 specs/feature-tree/tree_index.yaml）
✓ 涉及的业务对象已识别（查 contracts/metadata/）
✓ 涉及的扩展场景已识别（S01~S20）
✓ 任务拆解遵循 metadata-first 顺序
```

如涉及新实体/字段/事件 → 任务首项必须是更新 metadata（先 `/qwq-extend` 再手写逻辑）。

### 2. 特性创建

1) 在特性树中定位或新增节点：
   - 查 `specs/feature-tree/tree_index.yaml`
   - 选择对应 L1 的 `tree.yaml`
2) 创建特性实例目录（如需要）：
   ```bash
   bash scripts/new_feature_fullstack.sh "<slug>"
   ```
3) 补齐特性制品：
   - `acceptance.yaml` — A1~A8 验收标准
   - `traceability.yaml` — 追溯映射
   - `tasks.md` — 任务拆解（**顺序：metadata → codegen → 业务逻辑 → 测试**）

### 3. G1 卡点：Verify + Codegen（自动执行）

特性创建完毕后，AI Agent **必须立即自动执行**：

```bash
make verify                    # metadata 内部一致性
make codegen                   # 云侧代码生成
make codegen-app               # 端侧代码生成
```

**任一失败 → 停止 + 输出错误 + 修复建议 + 修复后重跑。**

### 4. 输出

- 特性目录已创建，制品已补齐
- G0 约束检查通过
- G1 verify + codegen 通过
- 下一步：`/opsx-apply` 进入实施
