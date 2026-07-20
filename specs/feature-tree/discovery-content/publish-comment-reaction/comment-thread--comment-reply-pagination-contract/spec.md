# L3 特性：comment-reply-pagination-contract

## 功能说明
- 评论列表游标分页契约与回复关联契约，保证端云协同一致。
- **游标契约**：ListComments 响应 `CommentPage` 含 `items` + `nextCursor`；cursor 为不透明字符串，仅用于下一页请求；与发现流 cursor 语义一致。
- **回复预览契约**：ListComments 对每条一级评论可返回 `replyPreview[]` 和 `replyNextCursor`；预览条数由云端 `sys.content.comment.reply_preview_count` 控制，端侧 fallback 为 1。
- **回复分页契约**：ListCommentReplies 使用 `postId + commentId + cursor + limit` 独立拉取二级回复；每次展开默认 limit 由 `sys.content.comment.reply_expand_page_size` 控制，端侧 fallback 为 10。
- **回复创建契约**：CreateComment 请求支持可选 `replyToCommentId`；服务端写入 `replyToCommentId`、`replyToUserId`，并规范化 `parentCommentId` 为一级评论 id，避免多级楼中楼。

## 适用范围与约束
- 依赖 comment-thread 云侧 ListComments / ListCommentReplies / CreateComment 实现；本节点验收为契约一致性，不单独实现业务逻辑。
- 不负责：三级及以上嵌套回复；所有回复都归一到一级评论下展示。

## 约束
- 契约与字段策略必须与 OpenAPI、service.yaml、metadata 保持一致。

## 验收标准
- A1：ListComments 返回 items + nextCursor；一级评论含 replyPreview + replyNextCursor；CreateComment 支持 replyToCommentId / parentCommentId；端云字段一致。
- A2：ListCommentReplies 按不透明 cursor 追加二级回复，limit 默认取 reply_expand_page_size，fallback 为 10。
- A3：reply_preview_count 默认 1、reply_expand_page_size 默认 10，二者都可由云端 App Config 覆盖。
- A7：OpenAPI schema、metadata、端侧 Repository 与 service.yaml 对齐。
- A8：contract_test 中 comment_thread 场景覆盖游标与回复契约。

## Folded current node `moderation-delete-audit-guard`

# L5 特性：moderation-delete-audit-guard

## 功能说明
- 评论删除的权限校验与审计守卫，保证删除可追溯。
- **删除权限**：仅评论作者或管理员可删除；非作者请求返回 403。
- **审计日志**：删除操作记录 traceId/requestId、操作者、commentId、postId、时间；供运营与安全审计使用。
- **软删语义**：可选用 status=deleted 软删，列表过滤 status!=deleted；或硬删，具体由 comment-thread 实现决定。

## 适用范围与约束
- 依赖 comment-thread 的 DeleteComment 实现；本节点在 DeleteComment 流程中注入权限校验与审计逻辑。
- 不负责：评论内容审核（发前/发后 moderation）、评论隐藏策略；后者可未来演进。

## 约束
- 契约与字段策略必须与 OpenAPI、service.yaml、metadata 保持一致。

## 验收标准
- A1：非作者删除返回 403；作者删除成功；删除操作写入审计日志。
- A7：契约一致性校验通过。
- A8：contract_test 覆盖删除权限与审计断言。
