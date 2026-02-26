# 开发任务：comment-thread

## 扩展场景与命令映射

| 阶段 | 命令/操作 | 说明 |
|------|----------|------|
| ① 契约 | 编辑 `contracts/openapi/content-service.v1.yaml` | Delete 路径与 service.yaml 统一 |
| ② 验证 | `make verify` | metadata + OpenAPI 一致性 |
| ③ 云侧 codegen | `make codegen target=post` 或等价 | 若工具生成 Comment 持久化骨架；否则手写 |
| ④ 端侧 codegen | `make codegen-app` | 若从 service.yaml 生成 ContentRepository 评论方法 |
| ⑤ 实现 | 手写 | comment_store、comment_service、HTTP handler、ContentRepository 三方法、CommentViewer 对接 |
| ⑥ 测试 | S20 若需 | `make codegen-test` 生成/更新 contract 骨架；手写断言 |
| ⑦ 门禁 | `make gate` | 全量通过 |

**不适用**：S01/S02/S05（业务对象与路由已存在）。

---

## 当前交付任务

顺序：metadata/契约 → codegen（若需）→ 云侧实现 → 端侧对接 → 测试。

### 契约与元数据
- [ ] **契约统一**：OpenAPI 中 Delete 评论路径改为 `DELETE /v1/content/posts/{postId}/comments/{commentId}`，并补充 path 参数 postId；与 service.yaml、generated_routes 一致。
- [ ] 确认 ListComments 响应 CommentPage（items + nextCursor）及 Comment 字段与 fields.yaml 一致（id、postId、authorId、personaId、content、replyToCommentId、replyToUserId、likeCount、status、createdAt）；CreateComment 请求/响应与 metadata writable_fields 一致。

### 云侧（content-service）
- [ ] **Comment 持久化**：在 infrastructure/persistence 增加 comments 存储（如 comment_store.go），实现按 postId + cursor + limit 查询、插入、按 commentId 删除；与 storage.yaml 中 comments 集合及索引一致。
- [ ] **应用层**：新增评论用例（如 comment_service 或扩展现有 post 用例），实现 ListComments（游标分页）、CreateComment（写 comment、发 CommentCreated、更新 Post.commentCount）、DeleteComment（权限校验后软删或硬删、更新 commentCount）。
- [ ] **HTTP 层**：将 ListComments、CreateComment、DeleteComment 从 handleNotImplemented 改为调用上述应用层；路径参数 postId/commentId 从 request 解析并传递。

### 端侧（quwoquan_app）
- [ ] **ContentRepository**：在 Abstract 中新增 `listComments(postId, {cursor, limit})`、`createComment(postId, {content, replyToCommentId})`、`deleteComment(postId, commentId)`；Mock 实现返回本地数据且不发 HTTP；Remote 实现使用 CloudRuntimeConfig.gatewayBaseUrl + CloudRequestHeaders，路径与 service.yaml 一致，统一错误解码。
- [ ] **CommentViewer 对接**：评论弹窗打开时通过 ref.read(contentRepositoryProvider) 调用 listComments(postId) 作为首屏数据；onLoadMoreComments 用 nextCursor 再调 listComments；onSubmit 调 createComment（回复时带 replyToCommentId）；删除动线调 deleteComment。将 API 返回的 Map 转为 CommentModel 或直接使用 DTO（若已有 codegen Comment）。
- [ ] 若 codegen-app 支持 Comment：生成 Comment 相关 DTO/字段策略后，端侧优先使用生成类型；否则暂时用 Map<String, dynamic> 与 metadata 字段约定对齐。

### 测试与门禁
- [ ] 云侧 contract_test：comment_thread（CreateComment + ListComments）、comment_with_notification（CreateComment 后 DB 与 CommentCreated 断言）可运行并通过。
- [ ] 端侧：Mock 模式下评论列表/发表/删除可走通；Remote 模式下与 content-service 联调通过。
- [ ] `make verify`、`make codegen`、`make gate` 通过。

---

## 搁置任务（带规划）

- **评论点赞**：评论 like 计数与状态归属 reaction-state-counter；comment-thread 仅展示 likeCount，不实现评论点赞接口，待 reaction 能力扩展时再接。
- **Comment 端侧 codegen**：若当前 codegen-app 未生成 Comment DTO，可暂用 Map 与约定字段名；待 codegen 支持 Comment 实体后补齐生成与替换。

---

## 未来演进任务

- 与 comment-reply-pagination-contract 对齐：游标稳定性、回复分页策略（先主评论后回复页）。
- 与 moderation-delete-audit-guard 对齐：删除权限、审核状态、审计日志。
