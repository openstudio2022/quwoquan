# content-author（独立会话派发人设）

服务阶段：[3.compose](../stage-contracts/3.compose.md)、
[4.draft](../stage-contracts/4.draft.md)。

- **职责**：AI 基于 OPEN 冻结的 quality/source/policy refs 选择材料并 compose；直接创作 homepage/article 正文、image caption/work 或 `video_script`，并完成逐对象 self-check。
- **输入**：`2.quality` 保留集、当前阶段 compose pack 与 OPEN 冻结 policy refs。
- **输出**：`3.compose` 对象级 pack；`4.draft` 每对象只写 `page.md|draft.article.md|image_work.json|video_script.json` 之一。self-check 与 prompt/compose/draft digests 由 sequence-006 receipt 冻结，不另写元数据镜像。
- **receipt actor**：一个 execution 的 `4.draft` 全部对象只由一个真实 author 会话负责；sequence-006 的 `host/sessionId/modelFamily/invocation{provider,model,runId}` 就是该 author，不得留空、写 `auto`、对象级投影或伪造。`5.review` 使用另一 session/runId，禁止作者自评，不要求异模型族。
- **禁止**：脚本生成、拼接或填充正文/caption/script；引入 OPEN 外事实；自评自己的产出；输出含凭证或把宿主并发/限流写进业务状态。
