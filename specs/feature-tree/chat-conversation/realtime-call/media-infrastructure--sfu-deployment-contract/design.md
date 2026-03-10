# sfu-deployment-contract 设计

> status: specified

## 目标

为 LiveKit SFU 与 coturn 的部署、容量、弱网恢复和灰度发布定义统一基线，使实时媒体基础设施具备可验证的生产门槛。

## 关键决策

- SFU 与 TURN 作为独立媒体基础设施部署，业务服务只依赖标准 token 和会话编排，不感知底层节点细节。
- 并发与房间容量指标以前置基准压测结果为准，`500 InitiateCall p99 < 200ms` 与 `32 人房间 CPU < 85%` 作为默认门槛。
- 弱网恢复依赖 Simulcast 降级和 ICE restart，恢复成功率、恢复时延进入灰度观测指标。
- prod 灰度按 `5% -> 20% -> 50% -> 100%` 逐步推进，每阶段都绑定回滚条件与 SLO 检查。

## 验证策略

- T3：集成环境验证 SFU/TURN 连接、重连和弱网退化行为。
- T4：真实网络条件下验证 ICE restart、音视频连续性与灰度回滚脚本。
