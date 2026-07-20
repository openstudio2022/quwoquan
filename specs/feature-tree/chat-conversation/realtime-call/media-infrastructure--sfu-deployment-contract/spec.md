# L3 Story：sfu-deployment-contract — LiveKit/TURN 运行合同

> **层级**：L3_story（隶属 L2 `realtime-call`）
> **状态**：specified；环境验收 pending

## 最小价值

每个受支持环境都能以同源配置启动 rtc-service、LiveKit SFU 与 coturn，完成 Room/token、
真实媒体、网络恢复、指标 readback 和安全回滚。

## Contract

- rtc-service、LiveKit、coturn 使用环境拓扑与受控 Secret 装配；App 不获得服务端密钥。
- Room 名、participant identity、grants、token TTL 与最大人数由 CallSession port 治理。
- 32 人容量、TURN fallback、网络切换与 reconnect 必须由真实运行制品验证。
- 发布证据记录 artifact/config digest、环境、设备、case、起止时间、原始 QoE 与失败原因。
- Gamma-local 证明设备和媒体；prod-hosted 只在 `gray_initial` 做最小高信号 canary。
- 回滚条件必须消费已存在的 series，不允许以文档阈值替代采集。

## 当前阻断

- Gamma full workload 缺受控 product telemetry SLS Secret，按预期 fail-closed。
- RTC media QoE 的生产 emitter、hourly rollup、SLS/LiveKit 告警与本地合同已落地；
  真实 series、查询面板和 Gamma/prod 触发/恢复/回滚演练仍缺，无法执行发布准出。
- 离线来电 provider 与设备注册未完成，不计入 SFU ready。

## Out of Scope

- 通话录制媒体管道、本期 E2EE、P2P 双路径。
- 把本地 fake media、容器能启动或 HTTP 2xx 作为商用媒体证据。

## 验收

见本节点 `acceptance.yaml`；没有 Gamma/Prod 真实 artifact 与 readback 时保持 pending。
