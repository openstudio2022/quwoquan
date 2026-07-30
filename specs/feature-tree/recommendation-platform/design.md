# L1 Design：推荐与模型平台 (`recommendation-platform`)

> 对应规格：[L1 spec](./spec.md)

## 1. 背景与设计目标

- 设计目标：为训练、推理和评估提供统一模型生命周期，使推荐策略能够基于真实反馈安全晋升或回滚，并通过 HTTP 或不可变离线产物与 Go 推荐引擎协作。

## 2. 领域模型与所有权

- authoritative ownership：拥有训练数据集引用、模型版本、评估结果、晋升决定和推理服务版本的生命周期与写入决定权。
- write boundary：只能通过本领域公开 command 修改其拥有事实。
- 非本域对象：不拥有其他 L1 的事实；跨域协作必须使用对方公开 command、query、projection 或 event。
- 非本域对象：不复制 metadata 中的字段、path、错误码和 wire 语义。

## 3. 上下文边界与协作

- [`JNY-011 / SCN-026`](../spec.md#scn-026) — 在“对象页交集行动深化（同趣围观到破冰升级）”中，基于行为、对象和模型版本生成排序或交集候选，并保留评估与回滚边界。
- [`JNY-011 / SCN-027`](../spec.md#scn-027) — 在“结伴同行与线下相聚”中，基于行为、对象和模型版本生成排序或交集候选，并保留评估与回滚边界。

## 4. 架构与数据流

- [`evaluation-and-flywheel`](./evaluation-and-flywheel/spec.md)：推荐准确性评估、在线 AB 和真实流量训练晋升闭环。
- [`rec-model-service`](./rec-model-service/spec.md)：**定位**：推荐平台下的模型推理服务，装载不同 scenario 的模型，对接 Go 业务服务（content-service 等）提供统一打分能力。
- [`rec-model-training`](./rec-model-training/spec.md)：**定位**：推荐平台下的训练工程服务，对接不同模型训练场景（content_feed / circle_discovery / friend_suggestion），产出模型与元信息写入 ModelRegistry + OSS/TOS，供模型服务加载。
- 工程边界由 spec 的“工程归属”声明；设计不复制具体实现文件。

## 5. 关键决策

<a id="dec-001"></a>
### DEC-001 训练、发布与推理解耦
- 决策：训练、发布与推理解耦。
- 理由：为训练、推理和评估提供统一模型生命周期，使推荐策略能够基于真实反馈安全晋升或回滚，并通过 HTTP 或不可变离线产物与 Go 推荐引擎协作。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 关联能力：[`evaluation-and-flywheel`](./evaluation-and-flywheel/spec.md)、[`rec-model-service`](./rec-model-service/spec.md)、[`rec-model-training`](./rec-model-training/spec.md)

## 6. 质量与运行约束

- 安全与隐私：训练和推理只消费获授权且去除非必要身份信息的特征。
- 性能与容量：推理超时和容量预算由 recommendation-service 配置与测试共同约束。
- 可观测性：记录模型版本、请求结果、延迟和失败原因，不记录原始敏感特征。
- 灰度与回滚：仅在 `prod` rollout stage 按模型版本灰度；回滚到最近一个满足门禁的版本。

## 7. 失败与恢复

- 失败类型：权限拒绝、依赖超时、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：按 canonical recovery action 重试、刷新或回滚到上一份已验证配置。
- 禁止 fallback：不得使用 Mock、旧 wire、双读双写或跨域直写伪造成功。
