# 开发任务：publish-comment-reaction

- [ ] contracts-first
- [ ] metadata 对齐
- [ ] 实现
- [ ] 测试（mock/unit/contract/integration/uat）
- [ ] gate 验证

## 评论端云一体化（comment-thread）

**业务对象完备性**：Comment 已作为 Post 聚合成员存在于 metadata（S02 已完成）；ListComments/CreateComment/DeleteComment 路由已在 service.yaml（S05 已完成）。**无需** S01/S02/S05。

**缺口与扩展路径**：

| 缺口 | 操作 |
|------|------|
| OpenAPI Delete 路径错误 | 手动编辑 `contracts/openapi/content-service.v1.yaml` |
| Comment 持久化 + 应用层 + HTTP | 手写 + 可选 `make codegen target=post` |
| ContentRepository 评论接口 | `make codegen-app` 或手写 |
| contract_test | S20 若需 + 手写断言 |
| 门禁 | `make verify` → `make codegen` → `make gate` |

- [ ] 契约统一：OpenAPI Delete 评论路径与 service.yaml 一致（见 comment-thread/tasks.md）。
- [ ] 云侧：Comment 持久化 + 应用层 List/Create/Delete + HTTP 实现（替换 handleNotImplemented）。
- [ ] 端侧：ContentRepository 增加 listComments/createComment/deleteComment；CommentViewer 通过 Provider 对接真实 API。
- [ ] 契约测试：comment_thread、comment_with_notification 场景通过。
- 详细拆解、扩展场景映射见 `comment-thread/spec.md`、`comment-thread/tasks.md`、`comment-thread/design.md`。
