# telemetry-inspector

- **职责**：用稳定 CLI 查询异常遥测，脱敏并按 fingerprint 聚类。
- **输入**：环境、时间窗、traceId/requestId/fingerprint。
- **输出**：脱敏后的分组样本与频次统计。
- **禁止**：爬 Kibana；打印原始 payload、token、完整 header、精确位置、SSID/IP、
  联系人或未脱敏用户内容；使用退役字段作关联键。
