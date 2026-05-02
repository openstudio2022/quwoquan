# L4 特性：comment-reply-pagination-contract

## 功能说明
- 评论列表游标分页契约与回复关联契约，保证端云协同一致。
- **游标契约**：ListComments 响应 `CommentPage` 含 `items` + `nextCursor`；cursor 为不透明字符串，仅用于下一页请求；与发现流 cursor 语义一致。
- **回复契约**：CreateComment 请求支持可选 `replyToCommentId`；服务端写入 `replyToCommentId`、`replyToUserId`；列表返回中回复与主评论通过 `replyToCommentId` 关联；端侧楼中楼展示依赖此字段。

## 适用范围与约束
- 依赖 comment-thread 云侧 ListComments / CreateComment 实现；本节点验收为契约一致性，不单独实现业务逻辑。
- 不负责：回复二级分页（先主评论 cursor 再按 replyToCommentId 分页拉取），当前采用扁平列表 + replyToCommentId 关联即可。

## 约束
- 契约与字段策略必须与 OpenAPI、service.yaml、metadata 保持一致。

## 验收标准
- A1：ListComments 返回 items + nextCursor；CreateComment 支持 replyToCommentId；端云字段一致。
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
