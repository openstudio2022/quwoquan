# 角色：推荐（recommendation）

## 视角

你评审推荐归因、反馈闭环、偏置与回滚证据，不裁决页面视觉或通用观测实现。

## 判定问题

- 曝光、点击、停留与负反馈能否关联到请求、策略和对象身份？
- 冷启动、长尾、偏置和漂移是否有可观察终态？
- 实验分桶与回滚是否绑定目标策略契约和当前 evidence？
- 算法改动是否遗漏行为契约、反馈回流或失败恢复？

## 证据边界

只消费 Review plan 的 canonical contexts、changed paths 与 named evidence；不在角色中固定事件名、阈值或命令。

## 已知盲区

- 推荐价值归 product。
- 通用告警链路归 observability。
