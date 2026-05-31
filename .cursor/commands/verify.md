# /verify

目标：复核增量是否满足一棵树和测试覆盖。

检查：
- AppRoot UAT 是否受影响并有 T4/T3。
- 业务能力 SIT 是否闭环并有 T2/T3。
- Story GWT/contract 是否闭环并有 T1/T2。
- metadata、seed、mock、页面质量、runtime error、CR 是否同步。

输出：通过、缺口、需重跑命令。
