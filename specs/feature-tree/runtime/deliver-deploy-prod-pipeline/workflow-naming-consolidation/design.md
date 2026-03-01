# workflow-naming-consolidation 设计

## 设计动因

6 个 workflow 名称不统一（delivery-gate、pre-release-gate 小写；Deploy to Prod 部分大写），缺少执行序号与环境标注，不利于在 Actions UI 中排序与理解执行上下文。同时需确认 02 Service Pipeline 与 03 Delivery Gate 无重复执行。

## 适用场景与约束

- **适用**：GitHub Actions 多 workflow 串联；deliver → deploy 端到端流程
- **约束**：workflow_run 的 workflows 数组必须与 name 字段精确匹配
- **局限性**：序号前缀在 name 中，若重排需同步更新 workflow_run 引用

## 命名规范

| 序号 | 命名 | 环境 |
|------|------|------|
| 01 | 01. App Pipeline | Main Branch |
| 02 | 02. Service Pipeline | Main Branch |
| 03 | 03. Delivery Gate | Main Branch |
| 04 | 04. Pre-Release Gate | Integration |
| 05 | 05. Deploy To Prod (Gray) | Production — Gray |
| 06 | 06. Deploy To Prod (Auto) | Production — Full |

## 02/03 重复检查

- **02 Service Pipeline**：make build、Python 镜像、kustomize **aliyun-prod**
- **03 Delivery Gate**：topology + L1 + L2（含 go test）、kustomize **integration** × 3 云
- **结论**：职责互补，Kustomize 目标不同（prod vs integration），无重复。

## 未来演进

- 若新增 workflow，延续 07、08… 序号；更新 workflow_consolidation_plan。
