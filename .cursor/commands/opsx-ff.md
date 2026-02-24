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

**特性树文档标准**：仅使用四类文档，详见 `specs/feature-tree/00_FEATURE_TREE_STANDARD.md`。禁止在节点下生成 analysis-*.md、README、独立规划书等；所有需求/设计/任务/验收汇入 spec、design、tasks、acceptance。

1) 在特性树中定位或新增节点：
   - 查 `specs/feature-tree/tree_index.yaml`
   - 选择对应 L1 的 `tree.yaml`
2) 创建特性实例目录（如需要）：
   ```bash
   bash scripts/new_feature_fullstack.sh "<slug>"
   ```
3) 补齐特性制品（四类缺一不可，且足够详细）：
   - `spec.md` — 功能说明、范围、约束、验收重点（见标准 2.1）
   - `design.md` — 设计动因、决策、契约与迁移/演进说明；**须遵循设计原则**：业界对标与多方案对比、选最优或可演进到最优、轻量方案时在 design 与 tasks 中写清未来演进与规划任务（见标准 2.2）
   - `tasks.md` — 任务拆解（**顺序：metadata → codegen → 业务逻辑 → 测试**）；可选「规划任务」小节（见标准 2.3）
   - `acceptance.yaml` — A1~A8 验收标准、focus_groups、execution（见标准 2.4）
   - 若项目使用：`traceability.yaml` — 追溯映射

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
