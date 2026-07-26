# L1 Design：共享主页网络 (`shared-homepage-network`)

> 对应规格：[L1 spec](./spec.md)

## 1. 背景与设计目标

- 设计目标：让用户发现具体事物的长期主页、挂载内容和评价，并让可信主体通过认领、维护、状态上报与软下线保持主页事实可靠。

## 2. 领域模型与所有权

- authoritative ownership：拥有 `Homepage`、主页候选、认领、基础资料维护、评价和状态报告的生命周期与写入决定权。
- write boundary：只能通过本领域公开 command 修改其拥有事实。
- 非本域对象：不拥有其他 L1 的事实；跨域协作必须使用对方公开 command、query、projection 或 event。
- 非本域对象：不复制 metadata 中的字段、path、错误码和 wire 语义。

## 3. 上下文边界与协作

- [`JNY-003 / SCN-009`](../spec.md#scn-009) — 在“内容详情跳转作者主页”中，维护 Homepage 及其聚合读模型，解析稳定主页引用并交付可导航对象页。
- [`JNY-005 / SCN-011`](../spec.md#scn-011) — 在“全局搜索查询与筛选”中，维护 Homepage 及其聚合读模型，解析稳定主页引用并交付可导航对象页。
- [`JNY-007 / SCN-013`](../spec.md#scn-013) — 在“私建群、圈子群、组织节点群与主页相关群入口”中，维护 Homepage 及其聚合读模型，解析稳定主页引用并交付可导航对象页。
- [`JNY-008 / SCN-014`](../spec.md#scn-014) — 在“实体主页到圈子、组织节点、群单元与会话协作”中，维护 Homepage 及其聚合读模型，解析稳定主页引用并交付可导航对象页。
- [`JNY-009 / SCN-019`](../spec.md#scn-019) — 在“搜索 handoff 与统一 grounding”中，维护 Homepage 及其聚合读模型，解析稳定主页引用并交付可导航对象页。
- [`JNY-010 / SCN-023`](../spec.md#scn-023) — 在“对象对外分享分发”中，维护 Homepage 及其聚合读模型，解析稳定主页引用并交付可导航对象页。

## 4. 架构与数据流

- [`homepage-claim-maintain-and-offline`](./homepage-claim-maintain-and-offline/spec.md)：提供主页从候选、发布、认领维护到现实对象消亡后软下线并保留记录的完整治理链路。
- [`homepage-discovery-and-attach`](./homepage-discovery-and-attach/spec.md)：让用户发现具体事物的主页，并在发布内容时以单一引用把内容挂接到该主页。
- [`homepage-review-and-content`](./homepage-review-and-content/spec.md)：让用户围绕共享主页完成理解、比较、浏览内容、查看评价与继续贡献内容。
- 工程边界由 spec 的“工程归属”声明；设计不复制具体实现文件。

## 5. 关键决策

<a id="dec-001"></a>
### DEC-001 具体事物统一为可长期维护的共享主页对象
- 决策：具体事物统一为可长期维护的共享主页对象。
- 理由：让用户发现具体事物的长期主页、挂载内容和评价，并让可信主体通过认领、维护、状态上报与软下线保持主页事实可靠。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 关联能力：[`homepage-claim-maintain-and-offline`](./homepage-claim-maintain-and-offline/spec.md)、[`homepage-discovery-and-attach`](./homepage-discovery-and-attach/spec.md)、[`homepage-review-and-content`](./homepage-review-and-content/spec.md)

## 6. 质量与运行约束

- 沿用 AppRoot 全局质量约束并保持 metadata/code/test 单轨。

## 7. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：按 canonical recovery action 重试、刷新或回滚到上一份已验证配置。
- 禁止 fallback：不得使用 Mock、旧 wire、双读双写或跨域直写伪造成功。
