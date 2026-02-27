# L2 特性：publish-comment-reaction

## 功能说明
- 内容发布、评论互动、反应计数与行为上报的端云协同能力。
- **子特性**：post-create-update（发布/更新/删除）、**comment-thread**（评论列表/发表/删除）、reaction-state-counter（点赞/收藏/计数）、行为上报（ReportBehaviors）。
- **评论端云一体化**：comment-thread 负责 ListComments、CreateComment、DeleteComment 的端到端打通；业务对象 Comment 已完备，缺口在契约修正、云侧实现与端侧 Repository 对接。详见 `comment-thread/spec.md` 与 `comment-thread/tasks.md`。

## 约束
- 契约与字段策略必须与 OpenAPI、service.yaml、metadata 保持一致。

## 验收标准
- A1：发布、评论、互动、行为上报功能路径可执行且输出稳定。
- A7：契约一致性校验通过。
- A8：对应自动化测试映射完整。
