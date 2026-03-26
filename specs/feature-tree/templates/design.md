# templates 设计

## 设计动因

`templates` 目录承担的是规格作者模板，而不是产品功能本身。  
如果这个目录没有正式设计说明，后续容易出现两个问题：

1. 模板文件被当作“随手放的草稿”，长期失去维护；
2. gate 对 feature-tree 的结构要求无法同等作用到模板目录。

## 上游输入评审

- 规格树根规则：`specs/feature-tree/`
- 模板资产：`l2_journey_acceptance.yaml`、`l3_scenario_acceptance.yaml`、`plan.yaml`
- 仓库 gate：要求节点具备完整的 `spec / design / acceptance / plan`

## 方案对比

### 方案 A：把模板目录排除出 gate

优点：

- 实现简单。

缺点：

- 模板目录逐渐失控；
- 结构约束无法一体化；
- 作者难以理解模板资产的正式归属。

### 方案 B：把模板目录也建成正式 feature-tree 节点

优点：

- 模板资产自身也满足结构校验；
- 新作者可以通过标准节点理解模板用途；
- gate 规则不需要为模板分叉特殊逻辑。

缺点：

- 需要补齐最小规格文档。

### 选型

选择 **方案 B**。

## 关键设计决策

### D1：模板目录作为 authoring capability 存在

`templates` 不是线上能力，但仍是规格体系中的正式节点。  
它的用户是规格作者，而不是终端用户。

### D2：模板文件只提供结构骨架

模板文件包含：

- L2 acceptance 骨架
- L3 acceptance 骨架
- plan 骨架

它们定义格式，不定义任何具体业务事实。

### D3：模板目录同样遵守 gate 要求

目录必须具备：

- `spec.md`
- `design.md`
- `acceptance.yaml`
- `plan.yaml`

这样 gate 不需要为模板写例外。

## 演进策略

- 后续新增模板时，优先扩展现有模板而不是创建并行第二套骨架。
- 模板字段若因 gate 演进而变化，应先改模板，再推广到新增节点。
