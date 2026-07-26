# L1 Design：对象主页网络 (`object-homepage-network`)

> 对应规格：[L1 spec](./spec.md)

## 1. 背景与设计目标

- 设计目标：`object-homepage-network` 是用户主页、圈子/群组主页、共享主页三类对象页的跨域体验与契约收口层。

## 2. 领域模型与所有权

- authoritative ownership：拥有跨用户主页、圈子主页与共享主页的对象页呈现合同、交集解释、行动入口和跨页状态交接；底层对象事实仍由来源领域拥有。
- write boundary：只能通过本领域公开 command 修改其拥有事实。
- 非本域对象：不拥有其他 L1 的事实；跨域协作必须使用对方公开 command、query、projection 或 event。
- 非本域对象：不复制 metadata 中的字段、path、错误码和 wire 语义。

## 3. 上下文边界与协作

- [`JNY-011 / SCN-026`](../spec.md#scn-026) — 在“对象页交集行动深化（同趣围观到破冰升级）”中，组合对象关系与交集解释投影，向对象页交付可理解、可行动的交集结果。

## 4. 架构与数据流

- [`intersection-unified-experience`](./intersection-unified-experience/spec.md)：以统一的交集事实、置信度、保鲜期和展示契约驱动发现、对象主页、圈子、聊天、个人主页与助理场景
- 工程边界由 spec 的“工程归属”声明；设计不复制具体实现文件。

## 5. 关键决策

<a id="dec-001"></a>
### DEC-001 用户、圈子与共享主页共用对象页网络边界
- 决策：用户、圈子与共享主页共用对象页网络边界。
- 理由：`object-homepage-network` 是用户主页、圈子/群组主页、共享主页三类对象页的跨域体验与契约收口层。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 关联能力：[`intersection-unified-experience`](./intersection-unified-experience/spec.md)

## 6. 质量与运行约束

- D2：一次性全量开发，分 cohort 灰度发布。
- 灰度开关只控制展示与策略启用，不允许创建第二套 mock 数据或第二套路由。
- local_contract：metadata、DTO、route/surface/operation、fixture、灰度策略静态校验。
- local_contract：Widget/Provider/Repository mock，覆盖三页首屏、交集证据、小艺提示、空态、灰度分支。

## 7. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：按 canonical recovery action 重试、刷新或回滚到上一份已验证配置。
- 禁止 fallback：不得使用 Mock、旧 wire、双读双写或跨域直写伪造成功。
