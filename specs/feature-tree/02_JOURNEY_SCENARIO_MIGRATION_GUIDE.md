# Journey / Scenario 迁移指南

本指南用于把存量 `L2_business_capability / L3_story / 树内任务文档` 节点迁移到新的 `L2_business_capability / L3_story / 树内计划文档` 治理模型。

## 迁移目标

- `L2_business_capability` 改义为 `L2_business_capability`
- `L3_story` 改义为 `L3_story`
- `树内任务文档` 退出正式治理链路，改为 `树内计划文档`
- 增量规格变更统一记录到 `specs/changelog/CR-*.yaml`

## 迁移顺序

1. 先冻结 `L2_business_capability` 的旅程边界与组合验收，不先搬工程任务。
2. 再冻结 `L3_story` 的单环节目标、异常边界与路径覆盖。
3. 将 `树内任务文档` 中稳定实施切片提炼到 `树内计划文档`。
4. 将设计补丁、范围修订、兼容决策迁移到 `design.md` 或 `CR`。
5. 将任务级测试列表收束成 `acceptance.yaml` 的 `tests.planned / tests.recorded`。
6. 最后删除 `树内任务文档`，并补齐 `CR`。

## 文档搬运规则

### 从 `L2/树内任务文档` 移走

- 文件级任务
- 组件实现细节
- 具体测试 case 数量

去向：

- `L3_story/树内计划文档`
- 上层 `design.md`，或 `L3_story/spec.md` / `L3_story/acceptance.yaml`
- `L3_story/acceptance.yaml`

### 从 `L3/树内任务文档` 移走

- 设计补丁
- schema 草案
- 回滚与观测策略

去向：

- `design.md`
- `acceptance.yaml`
- `specs/changelog/CR-*.yaml`

## 迁移样例

推荐先用以下节点作为样板：

- `specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/`

建议重构映射：

```text
旧:
L2_business_capability: profile-homepage-redesign
  └── L3_story: owner-subaccount-homepage-unification

新:
L2_business_capability: profile-homepage-redesign
  ├── L3_story: owner-subaccount-homepage-unification
  ├── L3_story: profile-shell-ui-unification
  └── L3_story: profile-motion-and-sticky-coordination
```

迁移判断：

- Journey 层保留统一主页的端到端用户旅程、跨场景 IA 与发布 guardrails。
- Scenario 层拆出主体模型、统一 UI 壳层、滚动/动效等可独立实施与验收的环节。
- `树内任务文档` 中的 `T01~Txx` 转为各 Scenario 的 `树内计划文档.slices[]`。
- `L2 acceptance` 中直接写实现细节的部分，下沉到对应 `L3 scenario_acceptance`。

## 完成定义

一个节点完成迁移，至少满足：

- 目录语义已改成 Journey / Scenario
- `树内计划文档` 已替代 `树内任务文档`
- `acceptance.yaml` 已采用新 schema
- `CR` 已记录此次迁移 delta
- 命令、规则、脚手架不再把该节点识别为旧模型
