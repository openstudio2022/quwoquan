# L2 Design：内容服务云端交付 (`content-service-cloud-production`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：“让经数据生产和审核的文章、图片、视频及主页内容以不可变发布物进入 content-service，并由 App 通过正式远端契约读取”需要 `remote-content-delivery` 共享状态 owner、契约或质量边界。

## 1. 背景、目标与非目标

- 设计目标：让经数据生产和审核的文章、图片、视频及主页内容以不可变发布物进入 content-service，并由 App 通过正式远端契约读取。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`remote-content-delivery`](./remote-content-delivery/spec.md)：缺 release、路径逃逸或悬挂引用必须拒绝导入；成功导入后 App 必须通过统一 gateway 读取，不得回退 fixture。

## 3. 端云与数据流

- 上游能力：数据生产和内容审核公开的 release/canonical objects。
- 下游能力：内容浏览、主页聚合、搜索和推荐读取面。
- 读取事实：immutable release、canonical content objects。
- 写入事实：content-service 拥有的内容聚合与导入证据。
- operation/event/object：引用 `quwoquan_service/services/content-service/contracts/`。
- 一致性要求：release create-once；服务导入和 App 读取不得接受旧 wire 键。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 存储必须持久化（MongoDB），不能继续用内存 PostStore
- 决策：存储必须持久化（MongoDB），不能继续用内存 PostStore。
- 理由：让经数据生产和审核的文章、图片、视频及主页内容以不可变发布物进入 content-service，并由 App 通过正式远端契约读取。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：[`remote-content-delivery`](./remote-content-delivery/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 配置只提供已选 adapter 的连接参数，不能在运行期按 metadata 或存储类型选择实现。
- 基础设施已就绪（redis.Router 支持 Pub/Sub），chat-service 已验证可靠性，零新增依赖。
