# L3 Story：媒体恢复、回滚与审计观测策略

## 恢复与回滚

- Worker 处理成功后才保存 checkpoint；checkpoint 保存失败允许安全重放。
- Worker 停止或回滚时保留 outbox、私有源对象和 processing 状态，恢复后继续消费。
- 派生物按资产版本写入，不覆盖已发布版本。
- FFmpeg/对象存储不可用时禁止降级为原始字节或伪造 ready。

## 审计与观测

- 记录每次 job 的 result、duration、eventId/assetId 的散列关联与错误类别。
- health 反映最近成功扫描时间；满批连续扫描用于识别积压。
- 告警覆盖 Worker 不可用、任务失败和 outbox lag。

## 验收标准

- checkpoint 故障注入后事实不丢失且仅产生一个终态结果。
- 运行态可区分 idle、success、content_rejected 与 infrastructure_failure。
- 回滚不破坏已发布 Post 和已存在 versioned slice。
