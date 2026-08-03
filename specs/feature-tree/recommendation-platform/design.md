# L1 Design：推荐与模型平台 (`recommendation-platform`)

> 对应规格：[L1 spec](./spec.md)

## 1. 背景与设计目标

- 设计目标：以 recommendation-service 的单一 Python 运行时统一候选、特征、交集解释、对象卡选择、稳定窗口、训练、推理和评估；Content 只通过 typed HTTP 取序并执行当前权限 hydration。

## 2. 领域模型与所有权

- authoritative ownership：拥有 CandidateIndex、FeatureProfile、RankedRecommendationWindow、推荐隐私阻断、交集解释、对象卡候选、训练数据集引用、模型发布、评估结果与晋升决定。
- write boundary：只能通过本领域公开 command 修改其拥有事实。
- 非本域对象：不拥有 Post、Persona、Circle、Homepage、Tag 或 Experiment 的权威事实；跨域协作必须使用对方公开 command、query、projection 或 typed event。
- 非本域对象：不复制 metadata 中的字段、path、错误码和 wire 语义。

## 3. 上下文边界与协作

- [`JNY-011 / SCN-026`](../spec.md#scn-026) — 在“对象页交集行动深化（同趣围观到破冰升级）”中，基于行为、对象和模型版本生成排序或交集候选，并保留评估与回滚边界。
- [`JNY-011 / SCN-027`](../spec.md#scn-027) — 在“结伴同行与线下相聚”中，基于行为、对象和模型版本生成排序或交集候选，并保留评估与回滚边界。

## 4. 架构与数据流

- 上游 Post、PersonaRelationship、Circle placement、Homepage、Tag、Experiment 与账号关闭事实经 typed event 形成对象本地投影；禁止读取上游私有集合。
- 首刷由 RankedRecommendationWindow 一次性固化排序、对象卡候选和归因；续页只读同一不可滑动续期窗口。Content 对返回的 Post identity 做权限 hydration，成功追加 FeedDeliveryPage 后发布 FeedPageDelivered。
- 交集特征和可见解释由 FeatureProfile 的同源投影生成；Content/App 只呈现 typed 结果，不重算社交图谱或拼接第二理由。

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

<a id="dec-002"></a>
### DEC-002 推荐运行时与内容交付单轨
- 决策：候选、召回、特征、交集解释、对象卡选择、排序与稳定窗口只存在于 recommendation-service；content-service 仅通过 generated transport 取序、按 Post 当前权限 hydration 并记录交付事实。
- 理由：候选和特征与 Content 聚合具有不同生命周期、重建方式和隐私清理责任，放在 Content 会形成跨库读取与第二排序真相源。
- 被否决方案：Content 直读 `rm_*`、User/Circle/Entity 私有集合，在 Go 中保留等价推荐引擎，或用兼容 fallback/双写过渡。
- 约束与影响：切换冻结旧 writer，原子启用新 owner 后删除旧 reader/writer；不得保留双写窗口。Recommendation 失败返回 canonical failure，Content 不回退到本地推荐。
- 关联要求：`REQ-001`

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
