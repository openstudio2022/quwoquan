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
