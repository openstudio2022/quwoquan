# 开发任务：comment-reply-pagination-contract

- [ ] contracts-first
- [ ] metadata 对齐
- [ ] 实现
- [ ] 测试（mock/unit/contract/integration/uat）
- [ ] gate 验证

## 与 comment-thread 实现对齐

- [ ] **游标契约**：ListComments 响应含 items + nextCursor；cursor 语义与发现流一致（不透明、仅用于下一页），端侧按 nextCursor 调用 onLoadMoreComments。
- [ ] **回复契约**：CreateComment 请求支持 replyToCommentId（可选）；服务端写入 replyToCommentId、replyToUserId；列表返回中回复与主评论通过 replyToCommentId 关联，端侧楼中楼展示依赖此字段。
- [ ] 上述契约由 comment-thread 的云侧 ListComments/CreateComment 实现与端侧 ContentRepository + CommentViewer 共同满足；本节点验收为契约一致性（OpenAPI/schema 与 metadata、端云字段一致）。
