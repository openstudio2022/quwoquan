# L3 特性：comment-thread

## 功能说明
- 评论楼与楼中楼：按 post 维度的评论列表拉取（游标分页）、发表评论/回复、删除评论，与端侧 comment_system 组件对接，保证端云契约一致。
- 范围：ListComments（cursor + limit）、CreateComment（content、可选 replyToCommentId）、DeleteComment（postId + commentId）；不包含评论点赞计数（归属 reaction-state-counter）、评论审核/隐藏（归属 moderation-delete-audit-guard）。

## 约束
- 契约与字段策略必须与 OpenAPI、service.yaml、metadata（fields.yaml）保持一致。
- 删除评论路径以 service.yaml 为准：`DELETE /v1/content/posts/{postId}/comments/{commentId}`；OpenAPI 须与此一致。

## 验收标准
- A1：评论列表拉取、发表评论/回复、删除评论端到端可执行且输出稳定。
- A7：契约一致性校验通过（metadata、OpenAPI、endpoint_catalog、端侧 Repository 与 service.yaml 对齐）。
- A8：对应自动化测试映射完整（contract_test 中 comment_thread / comment_with_notification 可运行）。

## 业务对象完备性
Comment 为 Post 聚合成员（aggregate.yaml members），非独立实体。当前状态：

| 维度 | 状态 | 说明 |
|------|------|------|
| aggregate.yaml | ✅ | members 含 Comment，relation 1:N，cascade_delete |
| fields.yaml | ✅ | Comment 字段完整（_id, postId, authorId, personaId, content, replyToCommentId, replyToUserId, likeCount, status, createdAt） |
| storage.yaml | ✅ | comments 集合 + idx_comments_post_created 等索引 |
| events.yaml | ✅ | CommentCreated，payload_entity: Comment |
| service.yaml | ✅ | ListComments / CreateComment / DeleteComment 三条路由 |
| entity_catalog | ✅ | Comment 已注册 |

**结论**：业务对象与元数据完备，无需 S01/S02/S05 新建；缺口在**契约修正、实现与端侧对接**。

## 缺口与扩展路径

| 缺口 | 类型 | 扩展/命令 | 说明 |
|------|------|----------|------|
| OpenAPI Delete 路径错误 | 契约修正 | 手动编辑 `contracts/openapi/content-service.v1.yaml` | 改为 `DELETE /v1/content/posts/{postId}/comments/{commentId}` |
| Comment 持久化缺失 | 实现 | 手写或 `make codegen target=post`（若工具支持 member 持久化） | 参考 post_store 实现 comment_store |
| HTTP 层 NotImplemented | 实现 | 手写 handler 逻辑 | 替换 handleNotImplemented，调用应用层 |
| 应用层评论用例缺失 | 实现 | 手写 comment_service / 扩展现有用例 | ListComments / CreateComment / DeleteComment 编排 |
| ContentRepository 无评论接口 | 端侧 | `make codegen-app`（若从 service.yaml 生成）或手写 | Abstract + Mock + Remote 三方法 |
| contract_test 场景 | S20 | 更新 service.yaml contract_test → `make codegen-test` | comment_thread、comment_with_notification 已有定义，需实现后断言通过 |

**无需执行**：S01（新建聚合）、S02（新建成员）、S05（新建端点）——均已存在于 metadata。

## 探索结论（代码与元数据检查）
- **元数据**：完备。
- **契约不一致**：OpenAPI 中 Delete 为 `DELETE /v1/content/comments/{commentId}`，须统一为 service.yaml 路径。
- **云侧**：ListComments、CreateComment、DeleteComment 均为 handleNotImplemented；无 comment_store、无应用层评论用例。
- **端侧**：ContentRepository 无评论接口；CommentViewer 未接 Repository；无 Comment codegen DTO（可暂用 Map）。
