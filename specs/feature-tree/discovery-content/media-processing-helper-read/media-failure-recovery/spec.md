# L3 Story：媒体处理失败恢复

## 用户故事

作为发布媒体内容的创作者，我希望网络、对象存储或处理进程暂时故障后任务能自动恢复，
而损坏文件得到明确终态，以免作品永久卡在处理中或误发布不可播放内容。

## 恢复语义

- 对象存储、FFmpeg 启动、checkpoint 与结果持久化失败属于可重试基础设施故障：
  不推进 checkpoint，不伪造聚合终态。
- 无视频流、不可解码或违反媒体约束属于内容性失败：幂等写入 `rejected` 与稳定原因，
  然后推进 checkpoint。
- 已 `ready/rejected/deleted` 的资产在重放时 no-op。
- 处理中的发布请求返回 metadata 定义的 `media_not_ready` 与 `recovery.action=retry`；
  未授权返回 `reauthenticate`，不得进入自动重试循环。

## 验收标准

- checkpoint 首次保存失败后，同一事实可重放且最终只形成一个有效 ready 结果。
- 进程重启后从持久 checkpoint 继续，不遗漏尚未处理事实。
- 损坏媒体进入 `rejected`，不生成任何可发布主 slice。
- 端侧发布意图对 `media_not_ready` 排队，对未授权永久阻断并提示重新认证。
