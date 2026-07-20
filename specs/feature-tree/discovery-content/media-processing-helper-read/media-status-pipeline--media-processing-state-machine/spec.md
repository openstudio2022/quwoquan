# L3 Story：媒体处理状态机与失败重试守卫

## 领域契约

- `MediaAsset` 只允许 `processing → ready|rejected|deleted`；终态不可逆。
- `ready` 必须同时具备主视频 slice、封面 slice、有效尺寸/时长和探测 descriptor。
- 视频必须为 H.264/AAC、progressive MP4、fast-start、最长关键帧间隔 2 秒。
- `RecordProcessingResult` 以 outbox event id 形成稳定幂等键。

## 失败重试守卫

- 基础设施失败返回错误，不写终态、不推进 checkpoint。
- 内容性失败写 `rejected`，清除可发布 slice，并允许 checkpoint 前进。
- 重复事实读取到终态资产时 no-op，防止重转码和覆盖。

## 验收标准

- 单元/本地契约覆盖所有合法与非法状态跃迁、ready descriptor 不变量和重复事实。
- api_integration 证明数据库终态与对象存储派生物一致。
