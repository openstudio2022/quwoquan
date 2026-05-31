# /deploy

目标：发布 release batch / CR 范围。

准入：
- UAT/SIT/GWT/contract 已闭环。
- T3/T4、SLO、观测、灰度、回滚演练完成。
- 生产包默认 Remote，无 mock 切换入口。

阻断：SLO 未达、回滚不清、生产数据或 seed 边界不清。
