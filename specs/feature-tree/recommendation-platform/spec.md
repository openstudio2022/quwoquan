# L1 Domain Service：推荐与模型平台 (`recommendation-platform`)

> 一句话定位：将行为和内容特征转化为可版本化、可评估、可晋升并可回滚的推荐模型能力。

## 1. 目标与用户价值

为训练、推理和评估提供统一模型生命周期，使推荐策略能够基于真实反馈安全晋升或回滚，并通过 HTTP 或不可变离线产物与 Go 推荐引擎协作。

## 2. 领域边界

### 本领域拥有

- 拥有训练数据集引用、模型版本、评估结果、晋升决定和推理服务版本的生命周期与写入决定权。
- 只能通过本领域公开 command 修改其拥有事实。

### 本领域不拥有

- 不拥有其他 L1 的事实；跨域协作必须使用对方公开 command、query、projection 或 event。
- 不复制 metadata 中的字段、path、错误码和 wire 语义。

### 上下游协作

- 上游：AppRoot Journey 与公开输入事实。
- 下游：直接 L2 能力以及协作 L1 的公开结果。
- 跨域写入：目标领域公开 command；禁止直写目标存储。
- 跨域读取：目标领域公开 query/projection。

## 3. Journey / Scenario 职责

- [`JNY-011 / SCN-026`](../spec.md#scn-026)
  - 本领域负责：在“对象页交集行动深化（同趣围观到破冰升级）”中，基于行为、对象和模型版本生成排序或交集候选，并保留评估与回滚边界。
  - 进入条件：`object-homepage-network` 已交付其公开结果。
  - 交付给下游的结果：基于行为、对象和模型版本生成排序或交集候选，并保留评估与回滚边界，供 `chat-conversation` 继续处理。
  - 不负责：不写入内容、关系、圈子或会话事实，也不由模型结果绕过权限。
- [`JNY-011 / SCN-027`](../spec.md#scn-027)
  - 本领域负责：在“附近同趣·结伴同行·线下局”中，基于行为、对象和模型版本生成排序或交集候选，并保留评估与回滚边界。
  - 进入条件：`circle-community` 已交付其公开结果。
  - 交付给下游的结果：基于行为、对象和模型版本生成排序或交集候选，并保留评估与回滚边界，供 `user-identity-profile-relationship` 继续处理。
  - 不负责：不写入内容、关系、圈子或会话事实，也不由模型结果绕过权限。
- [`JNY-011 / SCN-028`](../spec.md#scn-028)
  - 本领域负责：在“派生称谓与联系人标签驱动连接”中，基于行为、对象和模型版本生成排序或交集候选，并保留评估与回滚边界。
  - 进入条件：`chat-conversation` 已交付其公开结果。
  - 交付给下游的结果：基于行为、对象和模型版本生成排序或交集候选，并保留评估与回滚边界，形成该场景中本领域负责的终态。
  - 不负责：不写入内容、关系、圈子或会话事实，也不由模型结果绕过权限。

## 4. 业务能力

- [`evaluation-and-flywheel`](./evaluation-and-flywheel/spec.md)：推荐准确性评估、在线 AB 和真实流量训练晋升闭环。
- [`rec-model-service`](./rec-model-service/spec.md)：**定位**：推荐平台下的模型推理服务，装载不同 scenario 的模型，对接 Go 业务服务（content-service 等）提供统一打分能力。
- [`rec-model-training`](./rec-model-training/spec.md)：**定位**：推荐平台下的训练工程服务，对接不同模型训练场景（content_feed / circle_discovery / friend_suggestion），产出模型与元信息写入 ModelRegistry + OSS/TOS，供模型服务加载。

## 5. 领域要求

<a id="req-001"></a>
### REQ-001 recommendation platform 领域边界验收

- 领域边界、上下游依赖、工程映射和服务治理清晰。
- evaluation-and-flywheel 的离线 replay、在线 AB 与真实训练晋升规格已登记，且不与训练/推理服务职责混淆。

## 6. 领域验收

<a id="dom-001"></a>
### DOM-001 recommendation platform 领域边界验收

- 条件：本领域收到有效输入且前置领域事实成立。
- 可观察结果：领域边界、上下游依赖、工程映射和服务治理清晰。；evaluation-and-flywheel 的离线 replay、在线 AB 与真实训练晋升规格已登记，且不与训练/推理服务职责混淆。
- 禁止结果：不得绕过本领域公开 command/query/event 写入其拥有事实。

## 7. 工程归属

- App（协作引用，不用于代码归属）：`quwoquan_app/lib/ui/discovery`
- Metadata：`quwoquan_service/contracts/metadata/_vectors`
- Contracts（协作引用，不用于代码归属）：`quwoquan_service/services/recommendation-service/contracts`
- Service：`quwoquan_service/services/recommendation-service`
- Service（协作引用，不用于代码归属）：`quwoquan_service/services/recommendation-service/internal/recommendation/recommendation_model_release/infrastructure/model_runtime`
- 测试：
  - `local_contract`：`quwoquan_service/services/recommendation-service/internal/recommendation/recommendation_model_release/infrastructure/model_runtime`
  - `api_integration`：`quwoquan_service/services/recommendation-service/tests`
  - `user_acceptance`：`quwoquan_ops/tests/acceptance/user_acceptance`

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 recommendation platform 领域边界验收

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：领域边界、上下游依赖、工程映射和服务治理清晰。
- 完成判定：`DOM-001` 对应行为满足且真实测试 `spec_ref` 有效
