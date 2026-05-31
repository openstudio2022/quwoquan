# /obs

可观测专项入口。任何观测增量先执行全局入口检查：AppRoot Journey/Scenario、三层目录归属、UAT/SIT/GWT/contract、T1~T4。

专项必须补充：指标、日志、追踪、告警、SLO、看板、回滚触发条件。

缺业务验收映射或缺 SLO/告警证据时 `GATE_BLOCK`。
