# L3 Story：dynamic-exposure-budget

## 功能说明

动态曝光预算把内容从“静态排序后自然获得曝光”升级为“按反馈和不确定性分配曝光”。它通过分级流量池赛马和 bandit 先验，让新内容小流量试投、反馈达标晋级、负反馈或低完成率淘汰。

## 范围

- 流量池：candidate、trial、rising、mature、evergreen、retired。
- bandit：Thompson Sampling 或等价非深度 bandit，先验与 reward 定义 metadata 化。
- 反馈：CTR、完成率、深度停留、正向互动、负反馈率共同决定晋级/淘汰。
- 预算：按内容、频道、用户 segment、生命周期状态分配。

## 非目标

- P1 先实现基于 recpolicy 的分级流量池曝光份额约束；真实 Thompson Sampling 与预算存储留给后续 `rm_exposure_state` 物化增强。
- 不引入深度排序模型或 IPS 反事实训练。

## 验收标准

- A1：动态预算不替代排序，只约束候选可获得的曝光份额。
- A2：reward、先验、晋级/淘汰阈值来自 recpolicy。
- A3：预算分配可按 `exposure_pool`、`lifecycle_state`、`experiment_bucket` 观测。
- A4：可通过回滚层 `disable_exposure_dynamic_budget` 关闭。
