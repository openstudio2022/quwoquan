# AppRoot Design：应用根规格

> 对应规格：[AppRoot spec](./spec.md)

## 1. 背景、设计目标与非目标

- 设计目标：趣我圈是一套以“遇见同趣，绽放热爱”为品牌表达、以“别人帮你刷内容，我们帮你遇到对的人”为产品主轴的端云一体社交应用。它通过内容、对象主页、交集、关系、圈子、会话、搜索和小趣助手，把内容消费转化为可证、安全、可沉淀的同趣连接；AppRoot 统一用户旅程、跨领域场景、全局术语、边界和 UAT。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. 全局上下文与所有权

- [`assistant-run-learning`](./assistant-run-learning/spec.md)：让用户获得可恢复、可解释且上下文一致的小趣回答；让平台以版本化策略、学习事件、反馈聚合和用户确认的画像提案持续改进助手行为。
- [`chat-conversation`](./chat-conversation/spec.md)：让用户在 1v1 与大群会话中可靠发送、接收、同步和治理消息，并在同一会话上下文完成实时通话；容量、权限和失败恢复均保持可观察。
- [`circle-community`](./circle-community/spec.md)：让用户以清晰的圈子、组织节点与群组边界完成发现、加入、内容参与和成员协作，并保持圈子主页、默认群与共享主页之间的唯一关系语义。
- [`discovery-content`](./discovery-content/spec.md)：发现流、推荐排序、内容发布、评论互动、媒体处理与帮读能力。
- [`gateway-orchestrator-foundation`](./gateway-orchestrator-foundation/spec.md)：提供网关统一入口、鉴权限流、防护策略与跨服务编排基础能力。
- [`global-search-experience`](./global-search-experience/spec.md)：统一搜索覆盖联系人、会话、内容、圈子、主页、地点和网络结果，在本地联想与云侧最终结果之间保持清晰合同，并将反馈归因到搜索和推荐。
- [`object-homepage-network`](./object-homepage-network/spec.md)：`object-homepage-network` 是用户主页、圈子/群组主页、共享主页三类对象页的跨域体验与契约收口层。
- [`platform-ops-governance`](./platform-ops-governance/spec.md)：建立平台侧可观测、配置治理、服务治理、安全隐私、发布回滚的统一治理能力。
- [`product-ops-growth`](./product-ops-growth/spec.md)：建立产品运营侧的事件采集、实验分桶、反馈评估与策略优化闭环。
- [`recommendation-platform`](./recommendation-platform/spec.md)：为训练、推理和评估提供统一模型生命周期，使推荐策略能够基于真实反馈安全晋升或回滚，并通过 HTTP 或不可变离线产物与 Go 推荐引擎协作。
- [`runtime`](./runtime/spec.md)：runtime 作为跨端云机制领域服务，治理共享 runtime 包和 integration-service 等独立机制 进程；部署边界不形成新的 L1，业务对象与 Vendor SDK 不得穿透。
- [`shared-homepage-network`](./shared-homepage-network/spec.md)：让用户发现具体事物的长期主页、挂载内容和评价，并让可信主体通过认领、维护、状态上报与软下线保持主页事实可靠。
- [`user-identity-profile-relationship`](./user-identity-profile-relationship/spec.md)：让用户以默认账号或明确选择的 Persona 安全进入应用、维护公开资料和设置、建立或解除关系，并在所有业务领域获得一致的主体与权限语义。

## 3. 跨域协作与数据流

- AppRoot Journey 只编排参与 L1 的公开结果；写事实始终由所属 L1 的 command 完成。
- 跨域读取使用公开 query/projection，异步变化使用公开 event，任何缓存都不得成为写真相源。

## 4. 全局架构

- App 通过生成契约访问服务；服务本地 contracts 拥有业务 wire，中心 metadata 只保留跨服务共享 schema。
- 目录结构与父子 spec 表达特性树，运行时扫描生成上下文和变更报告，不提交人工索引。

## 5. 关键决策

<a id="dec-001"></a>
### DEC-001 每个领域声明唯一且可验证的工程归属
- 决策：每个领域声明唯一且可验证的工程归属。
- 理由：趣我圈是一套以“遇见同趣，绽放热爱”为品牌表达、以“别人帮你刷内容，我们帮你遇到对的人”为产品主轴的端云一体社交应用。它通过内容、对象主页、交集、关系、圈子、会话、搜索和小趣助手，把内容消费转化为可证、安全、可沉淀的同趣连接；AppRoot 统一用户旅程、跨领域场景、全局术语、边界和 UAT。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`

## 6. 质量与运行约束

- 应用根负责跨领域编排、UAT、全局架构、技术约束、观测、灰度和回滚。
- `UserAccount` 只承担账号、认证和安全；`Persona` 是公开业务主体。

## 7. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：游客关闭登录回安全首页不循环，登录成功继续进入写文字。
- 恢复动作：按 canonical recovery action 重试、刷新或回滚到上一份已验证配置。
- 禁止 fallback：不得使用 Mock、旧 wire、双读双写或跨域直写伪造成功。
