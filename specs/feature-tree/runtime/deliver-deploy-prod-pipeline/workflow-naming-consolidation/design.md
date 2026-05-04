# workflow-naming-consolidation 设计

## 设计动因

历史上同时存在 `05 / 05b`、`08b / 08b` 以及 `07` 定时合流等旧编号，导致 Actions UI 与文档理解成本高，也掩盖了 merge queue 与 post-main 的真实职责边界。

## 适用场景与约束

- **适用**：GitHub Actions 多 workflow 串联；deliver → deploy 端到端流程
- **约束**：编号唯一；同一职责只保留一个正式入口
- **局限性**：后续若继续扩展 workflow，需要同步维护文档编号与 repo required checks

## 命名规范


| 序号  | 命名                        | 环境 / 边界                   |
| --- | ------------------------- | ------------------------- |
| 01  | 01. App Pipeline          | Tag / Manual              |
| 02  | 02. Service Pipeline      | Post-main                 |
| 03  | 03. Delivery Gate         | Merge Queue               |
| 04  | 04. Pre-Release Gate      | Merge Queue / Integration |
| 05  | 05. App Env Device Matrix | Merge Queue / Self-hosted |
| 06  | 06. Deploy To Prod (Gray) | Manual                    |
| 07  | 07. Deploy To Prod (Auto) | Post-main                 |
| 08  | 08. Deploy Gamma ECS      | Manual / Gamma            |


## 去重决策

- **05 / 05b**：删除 wrapper，保留 `app-env-device-matrix-self-hosted.yml` 作为唯一 `05`
- **07 定时 merge**：删除，显式 PR + merge queue 取代
- **08b / 08b**：保留 `08b. Verify Chat Avatar Commercial Matrix Evidence`，将回滚改名为 `08c. ECS Onebox Rollback`

## 02/03 重复检查

- **02 Service Pipeline**：main 后 `make build`、Python 镜像、kustomize **aliyun-prod**
- **03 Delivery Gate**：merge queue 前 topology + L1 + L2
- **结论**：职责互补；一个是主干前质量门，一个是主干后构建 / prod 清单校验

## 未来演进

- 若新增 workflow，继续沿用 09、10… 序号
- 若 merge queue required checks 改动，需同步更新 `branch_strategy.md` 与 `ci_cd_end_to_end_design.md`