# config-rollout-slo-gate 设计

## 设计动因

将灰度单步执行（状态更新、SLO 决策、回滚）封装为可复用脚本，供 workflow 与 runbook 调用。

## 适用场景与约束

- **适用**：config-release 灰度流程；与 gray_rollout_stages 配合
- **约束**：STEP 固定 5/25/50/100；SLO 阈值来自 slo_thresholds.yaml

## 关键决策

- **State 存储**：`.release-state/<service>.state` 记录 last_step、版本等
- **SLO 决策**：exit code 0=continue, 10=pause, 20=rollback；rollback 时脚本内调用 config_release_rollback
- **与 workflow 衔接**：workflow 传入 STEP、版本、SLO 参数，调用 make config-gray-rollout / config-slo-gate

## 未来演进

- SLO 自动拉取（Prometheus）集成到 slo-gate
- state 持久化到外部存储（当前为本地文件）
