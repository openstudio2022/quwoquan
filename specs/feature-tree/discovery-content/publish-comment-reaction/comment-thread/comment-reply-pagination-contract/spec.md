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
