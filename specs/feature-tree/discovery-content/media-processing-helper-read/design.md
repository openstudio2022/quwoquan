# L2 Design：媒体处理与辅助阅读 (`media-processing-helper-read`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“图片/视频从上传完成事实到 ready/rejected 终态、归一化公开切片与可预览读取的商用闭环”需要 `helper-read-summary`、`image-delivery-variants`、`media-failure-recovery`、`media-status-pipeline` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：图片/视频从上传完成事实到 ready/rejected 终态、归一化公开切片与可预览读取的商用闭环。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`helper-read-summary`](./helper-read-summary/spec.md)：定义“辅助读取摘要”的可观察主路径、失败语义及父能力交接。
- [`image-delivery-variants`](./image-delivery-variants/spec.md)：损坏、超限、descriptor 缺字段或 CDN baseline 不可读全部进入 rejected 或保持 processing 重试，不能发布。
- [`media-failure-recovery`](./media-failure-recovery/spec.md)：checkpoint 保存失败后重放同一事实只产生一个有效 ready 结果。
- [`media-status-pipeline`](./media-status-pipeline/spec.md)：带音轨与无音轨输入均产生 H.264/AAC progressive fast-start MP4。

## 3. 端云与数据流

- 上游能力：[`discovery-content`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 media_not_ready 只在处理完成后解除
- 决策：media_not_ready 只在处理完成后解除。
- 理由：图片/视频从上传完成事实到 ready/rejected 终态、归一化公开切片与可预览读取的商用闭环。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`helper-read-summary`](./helper-read-summary/spec.md)、[`image-delivery-variants`](./image-delivery-variants/spec.md)、[`media-failure-recovery`](./media-failure-recovery/spec.md)、[`media-status-pipeline`](./media-status-pipeline/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 缺少 `eventId` 或 checkpoint 的 source cursor 不可安全跳过，Worker 必须 fail-closed 并保持 checkpoint 不推进。
