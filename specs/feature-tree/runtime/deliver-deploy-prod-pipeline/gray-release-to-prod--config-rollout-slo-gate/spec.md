# L4 特性：config-rollout-slo-gate

## 功能说明

单步灰度执行的底层能力：rollout 状态管理、SLO 卡点决策、异常回滚。为 gray-release-to-prod 提供可复用脚本与 state 管理。

## 范围

- **config_release_gray_rollout.sh**：校验 step 顺序、写 `.release-state/<service>.state`
- **config_release_slo_gate.sh**：输入 SLO 指标，输出 continue(0) / pause(10) / rollback(20)
- **config_release_rollback.sh**：回滚到指定版本
- **config_release_apply_stage.sh**：单步 = rollout + slo-gate + 可选回滚

## 适用范围与约束

- **适用**：与 gray-release-to-prod 父节点配合；STEP ∈ {5, 25, 50, 100}
- **约束**：依赖 releases/config、slo_thresholds.yaml
- **不适用**：非 config-release 流程的部署

## 与父节点关系

**父节点**：gray-release-to-prod（L3）— 编排多阶段灰度；本节点提供单步执行能力。

## 验收标准概要

- A1：config_release_gray_rollout.sh 支持 STEP 5/25/50/100，校验顺序
- A2：config_release_slo_gate.sh 可执行，返回正确 exit code
- A3：config_release_rollback.sh 可回滚到指定 config 版本
