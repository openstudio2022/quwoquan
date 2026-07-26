# L1 Domain Service：共享主页网络 (`shared-homepage-network`)

> 一句话定位：为地点、学校、公司等具体事物提供可发现、可认领、可评价并可持续维护的长期主页。

## 1. 目标与用户价值

让用户发现具体事物的长期主页、挂载内容和评价，并让可信主体通过认领、维护、状态上报与软下线保持主页事实可靠。

## 2. 领域边界

### 本领域拥有

- 拥有 `Homepage`、主页候选、认领、基础资料维护、评价和状态报告的生命周期与写入决定权。
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

- [`JNY-003 / SCN-009`](../spec.md#scn-009)
  - 本领域负责：在“内容详情跳转作者主页”中，维护 Homepage 及其聚合读模型，解析稳定主页引用并交付可导航对象页。
  - 进入条件：`user-identity-profile-relationship` 已交付其公开结果。
  - 交付给下游的结果：维护 Homepage 及其聚合读模型，解析稳定主页引用并交付可导航对象页，形成该场景中本领域负责的终态。
  - 不负责：不拥有内容正文、圈子、账号或聊天会话事实。
- [`JNY-005 / SCN-011`](../spec.md#scn-011)
  - 本领域负责：在“全局搜索查询与筛选”中，维护 Homepage 及其聚合读模型，解析稳定主页引用并交付可导航对象页。
  - 进入条件：`chat-conversation` 已交付其公开结果。
  - 交付给下游的结果：维护 Homepage 及其聚合读模型，解析稳定主页引用并交付可导航对象页，形成该场景中本领域负责的终态。
  - 不负责：不拥有内容正文、圈子、账号或聊天会话事实。
- [`JNY-007 / SCN-013`](../spec.md#scn-013)
  - 本领域负责：在“私建群、圈子群、组织节点群与主页相关群入口”中，维护 Homepage 及其聚合读模型，解析稳定主页引用并交付可导航对象页。
  - 进入条件：`circle-community` 已交付其公开结果。
  - 交付给下游的结果：维护 Homepage 及其聚合读模型，解析稳定主页引用并交付可导航对象页，形成该场景中本领域负责的终态。
  - 不负责：不拥有内容正文、圈子、账号或聊天会话事实。
- [`JNY-008 / SCN-014`](../spec.md#scn-014)
  - 本领域负责：在“实体主页到圈子、组织节点、群单元与会话协作”中，维护 Homepage 及其聚合读模型，解析稳定主页引用并交付可导航对象页。
  - 进入条件：`circle-community` 已交付其公开结果。
  - 交付给下游的结果：维护 Homepage 及其聚合读模型，解析稳定主页引用并交付可导航对象页，供 `chat-conversation` 继续处理。
  - 不负责：不拥有内容正文、圈子、账号或聊天会话事实。
- [`JNY-009 / SCN-019`](../spec.md#scn-019)
  - 本领域负责：在“搜索 handoff 与统一 grounding”中，维护 Homepage 及其聚合读模型，解析稳定主页引用并交付可导航对象页。
  - 进入条件：`chat-conversation` 已交付其公开结果。
  - 交付给下游的结果：维护 Homepage 及其聚合读模型，解析稳定主页引用并交付可导航对象页，形成该场景中本领域负责的终态。
  - 不负责：不拥有内容正文、圈子、账号或聊天会话事实。
- [`JNY-010 / SCN-023`](../spec.md#scn-023)
  - 本领域负责：在“对象对外分享分发”中，维护 Homepage 及其聚合读模型，解析稳定主页引用并交付可导航对象页。
  - 进入条件：`circle-community` 已交付其公开结果。
  - 交付给下游的结果：维护 Homepage 及其聚合读模型，解析稳定主页引用并交付可导航对象页，形成该场景中本领域负责的终态。
  - 不负责：不拥有内容正文、圈子、账号或聊天会话事实。

## 4. 业务能力

- [`homepage-claim-maintain-and-offline`](./homepage-claim-maintain-and-offline/spec.md)：提供主页从候选、发布、认领维护到现实对象消亡后软下线并保留记录的完整治理链路。
- [`homepage-discovery-and-attach`](./homepage-discovery-and-attach/spec.md)：让用户发现具体事物的主页，并在发布内容时以单一引用把内容挂接到该主页。
- [`homepage-review-and-content`](./homepage-review-and-content/spec.md)：让用户围绕共享主页完成理解、比较、浏览内容、查看评价与继续贡献内容。

## 5. 领域要求

<a id="req-001"></a>
### REQ-001 shared homepage network 领域边界验收

- 领域边界、上下游依赖、工程映射和服务治理清晰。

<a id="req-002"></a>
### REQ-002 前台统一让用户看到“具体事物的主页”

- 前台统一让用户看到“具体事物的主页”
- 产品层统一把这套能力称为 `共享主页`
- 主页成为内容挂载、口碑沉淀、搜索发现和后续商业承接的统一锚点
- **内容挂载与口碑沉淀的统一锚点**
- 主页与内容、群组、搜索之间的统一集成契约。
- R1.3：主页统一包含 `总览 / 口碑 / 内容 / 问答 / 相关群组 / 官方或服务信息` 六个模块。
- R1.4：不同类目在统一骨架下允许使用不同的字段模板和模块权重。
- R2.1：主页来源统一支持 `网络抓取建档 / 用户补充 / 内容反向抽取 / 运营导入` 四条路径。
- R2.2：抓取与抽取产物必须先进入候选或待校验状态，不能直接跳过治理发布。
- R2.3：AI 可以参与摘要、标签、结构化字段补全与展示配置建议，但不能直接替代事实校验。

## 6. 领域验收

<a id="dom-001"></a>
### DOM-001 shared homepage network 领域边界验收

- 条件：本领域收到有效输入且前置领域事实成立。
- 可观察结果：领域边界、上下游依赖、工程映射和服务治理清晰。
- 禁止结果：不得绕过本领域公开 command/query/event 写入其拥有事实。

## 7. 工程归属

- App：`quwoquan_app/lib/ui/entity`
- App（协作引用，不用于代码归属）：`quwoquan_app/lib/ui/content`
- Contracts：`quwoquan_service/services/entity-service/contracts`
- Contracts（协作引用，不用于代码归属）：`quwoquan_service/services/content-service/contracts`
- Service：`quwoquan_service/services/entity-service`
- Service（协作引用，不用于代码归属）：`quwoquan_service/services/content-service`、`quwoquan_service/services/circle-service`
- 测试：
  - `local_contract`：`quwoquan_service/services/entity-service/tests`
  - `api_integration`：`quwoquan_service/services/entity-service/tests`
  - `user_acceptance`：`quwoquan_ops/tests/acceptance/user_acceptance`

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 shared homepage network 领域边界验收

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：领域边界、上下游依赖、工程映射和服务治理清晰。
- 完成判定：`DOM-001` 对应行为满足且真实测试 `spec_ref` 有效
