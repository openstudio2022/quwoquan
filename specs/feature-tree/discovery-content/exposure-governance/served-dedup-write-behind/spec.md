# L3 Story：served-dedup-write-behind

## 功能说明

服务端 feed 下发后写入 `served` 短窗口记忆，用于翻页和短时间刷新去重。`served` 只表示服务端已经下发，不等同用户真实看见，不能直接作为训练正样本。

## 范围

- `served` 与 `impressed` 双轨语义。
- 服务端 feed 下发即写 `served`，按 `user+day` 分桶（跨会话），write-behind 不阻塞主链路。
- feed 返回后 write-behind 写 served，避免阻塞主链路。
- 召回/过滤阶段下推 served exclude，过滤用候选集 `SISMEMBER` 批量点查或短 Bloom，禁止长窗口全量 `SMembers` 回读。
- cursor 候选集变化时仍控制跨页重复。

## 非目标

- 不把 P1/P2 的动态曝光预算、协同召回或 near-dup 一并塞入 served 去重链路。
- 不把 served 替代端侧真实曝光 tracker。

## 验收标准

- A1：`served` 和 `impressed` 在规格、指标和训练语义中分离；`served` 不作训练正样本。
- A2：下发即标记只用于短窗口去重，TTL 和窗口来自 recpolicy，按 `user+day` 分桶。
- A3：served 写失败不阻塞 feed，有降级和观测。
- A4：重复曝光率指标引用 `recommendation_slo.yaml#repeat_exposure_rate`。
- A5：过滤走 `SISMEMBER` 批量点查或短 Bloom，禁止长窗口全量 `SMembers`，单请求 payload 有上限报告。
