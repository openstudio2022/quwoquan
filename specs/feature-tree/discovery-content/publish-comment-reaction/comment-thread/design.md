# comment-thread 设计说明

## 设计动因与职责
- 评论能力由 content-service 以 Post 聚合内子实体 Comment 提供；端侧通过 Content 域 Repository 调用评论 API，CommentViewer 只负责 UI 与调用 Repository，不直接发 HTTP。
- 契约以 metadata（service.yaml + fields.yaml）为权威；OpenAPI、codegen、端侧 Abstract 接口与 path 须与 metadata 一致。

## 关键决策
- **删除评论路径**：采用带 postId 的路径 `DELETE /v1/content/posts/{postId}/comments/{commentId}`，与 service.yaml 一致；OpenAPI 需从当前 `DELETE /v1/content/comments/{commentId}` 改为上述路径并补充 postId 参数。
- **列表分页**：与发现流一致，使用 cursor + limit，响应 CommentPage（items + nextCursor）；Comment 字段与 fields.yaml 对齐（含 _id 暴露为 id、postId、authorId、personaId、content、replyToCommentId、replyToUserId、likeCount、status、createdAt）。
- **端侧**：在 ContentRepository 抽象中新增 listComments、createComment、deleteComment，Mock 用本地数据，Remote 用 CloudRuntimeConfig + CloudRequestHeaders 调用上述路径；CommentViewer 通过 Provider 注入 Repository，首屏与加载更多调用 listComments，提交/删除调用 createComment/deleteComment。

## 适用场景与约束
- 适用：单 post 下的评论列表、主评论与楼中楼回复、作者/权限方删除评论。
- 不负责：评论点赞计数（归属 reaction）、评论审核/隐藏策略（归属 moderation-delete-audit-guard）、评论搜索（未来可演进）。

## 未来演进
- 评论审核与删除审计：由子节点 comment-reply-pagination-contract/moderation-delete-audit-guard 承接。
- 评论列表可考虑二级分页（先主评论 cursor，再按 replyToCommentId 拉回复），当前采用扁平列表 + replyToCommentId 关联即可满足端侧楼中楼展示。
