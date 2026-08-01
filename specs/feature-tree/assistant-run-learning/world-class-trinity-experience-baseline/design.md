# L2 Design：小趣统一体验 (`world-class-trinity-experience-baseline`)

> 对应规格：[L2 spec](./spec.md)

> 设计触发原因：公开网隔离、Skill Package、跨端语义展示与持久 Run 同时改变状态 owner、安全边界和恢复语义。

## 1. 背景、目标与非目标

- 设计目标：以统一 Agent 主线、不可变 Skill Package、受控自主探索、语义 Adaptive Presentation 与持久 Run，提供可持续扩展且可恢复的小趣体验。
- 非目标：复制字段 schema、实现任务、测试排列组合或执行历史。

## 2. Story 协作与状态流

- [`context-assembly-slot-filling`](./context-assembly-slot-filling/spec.md)：装配授权后的上下文与槽位状态，是本能力的入口。
- [`long-term-memory-compaction`](./long-term-memory-compaction/spec.md)：向装配提供事实型长期记忆与压缩后的会话历史。
- [`session-preference-memory-control`](./session-preference-memory-control/spec.md)：向装配提供结构化文风偏好。
- [`skill-progressive-disclosure-routing`](./skill-progressive-disclosure-routing/spec.md)：在策略允许集合内确定该次运行的领域技能与其工具策略。
- [`planner-aggregation-orchestration`](./planner-aggregation-orchestration/spec.md)：消费装配结果与技能策略，决定下一步动作并裁决答案边界。
- [`tool-fabric-runtime`](./tool-fabric-runtime/spec.md)：为编排执行工具调用并返回受预算与恢复策略约束的观察。
- [`native-tool-calling-model-routing`](./native-tool-calling-model-routing/spec.md)：为编排提供模型档位与原生工具调用协议。
- [`trajectory-replay-evaluation-gate`](./trajectory-replay-evaluation-gate/spec.md)：消费上述各 Story 的公开运行结果，以版本化回放语料持续验证完整 Agent 轨迹。
- [`autonomous-web-exploration`](./autonomous-web-exploration/spec.md)：为 Tool Fabric 提供隔离的公开网只读读取和来源账本。
- [`skill-context-proactive-runtime`](./skill-context-proactive-runtime/spec.md)：用同一 Skill/Context 管线承接用户请求与主动 Trigger。
- [`adaptive-presentation-runtime`](./adaptive-presentation-runtime/spec.md)：把 Skill 结构化输出解析为可持久化、可降级的语义展示事实。
- [`durable-agent-run-orchestration`](./durable-agent-run-orchestration/spec.md)：拥有长任务状态、TaskGraph、Checkpoint、控制命令与事件重放。

## 3. 端云与数据流

- 上游能力：[`assistant-run-learning`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果；Runtime 主动订阅只消费标准 Trigger/Run 和投递结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 4. 关键决策

<a id="dec-001"></a>
### DEC-001 小趣采用统一 Agent 主线、Skill 中心与轨迹回放准入
- 决策：小趣采用统一 Agent 主线与 Skill 中心；提示、策略或技能目录变更必须通过同一主线的版本化轨迹回放后才能合入。
- 理由：以统一 Agent 主线、Skill 中心、Markdown-first 输出、可解释折叠过程与偏好事实回注，提供可持续扩展且可回退的小趣体验。
- 被否决方案：由调用方、页面或脚本复制本层状态并绕过公开契约。
- 约束与影响：实现只能细化对应规格与 canonical contract；冲突时先修正规格或契约。
- 关联要求：`REQ-001`
- 影响 Story：本目录全部直属 Story。
- 关联验收：`SIT-001`

<a id="dec-002"></a>
### DEC-002 公开 URL 进入隔离读取边界而非模型裸 HTTP
- 决策：`web_open` 接受用户或模型给出的公开 HTTPS URL、搜索来源与文档链接，但统一经隔离读取边界完成 DNS/IP/重定向复核、凭证剥离、响应预算和来源记账。
- 理由：只允许既有来源会阻断自主探索；裸 HTTP 又会把服务信任区暴露为 SSRF、数据外泄和无界抓取入口。
- 被否决方案：仅允许 `referenceId`；向模型开放任意方法、请求头、请求体或服务网络访问。
- 约束与影响：认证与私有内容只经 Connector 或领域 Reader；网页内容始终是不可信证据，不能修改指令和权限。
- 关联要求：`REQ-003`
- 影响 Story：[`autonomous-web-exploration`](./autonomous-web-exploration/spec.md)、[`tool-fabric-runtime`](./tool-fabric-runtime/spec.md)
- 关联验收：`SIT-001`

<a id="dec-003"></a>
### DEC-003 Skill 以不可变资产包渐进披露上下文与展示能力
- 决策：Skill Manifest 只保存身份、路由与各 Profile 引用；选中 Skill 后才加载 Context、Capability、Presentation 和 Evaluation 资产。主动触发与用户请求共用同一管线。
- 理由：垂类扩展应以新增资产和领域 Reader 为主，不能继续扩大常驻上下文或增加 Skill 专用编排分支。
- 被否决方案：把全部提示、工具 schema、上下文值和 UI 定义塞入单个 Manifest；为主动运行维护第二套文案和执行器。
- 约束与影响：隐私上限由平台策略决定，Skill 不得扩大；资产用 release digest 固定，不增加双轨版本信封。
- 关联要求：`REQ-001`、`REQ-003`
- 影响 Story：[`skill-context-proactive-runtime`](./skill-context-proactive-runtime/spec.md)、[`skill-progressive-disclosure-routing`](./skill-progressive-disclosure-routing/spec.md)、[`context-assembly-slot-filling`](./context-assembly-slot-filling/spec.md)
- 关联验收：`SIT-001`

<a id="dec-004"></a>
### DEC-004 云端只下发安全语义展示树
- 决策：Skill 选择已发布模板并填充结构化数据；服务端解析和持久化语义展示文档，Flutter 用设计系统组件注册表渲染，未知能力确定性降级到 Markdown 或纯文本。
- 理由：语义树可表达图文、时间线、比较表、来源和确认动作，同时保持跨端安全、无障碍和视觉一致性。
- 被否决方案：云端下发 Flutter、HTML、JavaScript、任意 CSS/像素布局或客户端路由回调。
- 约束与影响：样式只使用语义 token，图片和动作必须引用 canonical asset/operation。模板发布需满足最低客户端能力。
- 关联要求：`REQ-003`
- 影响 Story：[`adaptive-presentation-runtime`](./adaptive-presentation-runtime/spec.md)
- 关联验收：`SIT-001`

<a id="dec-005"></a>
### DEC-005 AssistantRun 是后台任务与公开终态的唯一 owner
- 决策：Run 持久化状态机、RunItem journal、TaskGraph、Checkpoint 和 Definition of Done；Session 只拥有会话生命周期与摘要，Subscription 只拥有调度和投递策略。
- 理由：进程内 ReAct 无法证明断线恢复、重启恢复、暂停、调整、级联取消和诚实完成。
- 被否决方案：依赖 SSE 连接或单服务实例存活；用会话对象继续承载 Run、Tool、Presentation 和订阅事实。
- 约束与影响：内部推理不进入公开事件，公开过程只包含进度、决策摘要和证据。终态由 Verifier 门禁。
- 关联要求：`REQ-003`
- 影响 Story：[`durable-agent-run-orchestration`](./durable-agent-run-orchestration/spec.md)、[`planner-aggregation-orchestration`](./planner-aggregation-orchestration/spec.md)、[`long-term-memory-compaction`](./long-term-memory-compaction/spec.md)
- 关联验收：`SIT-001`

## 5. 失败与恢复

- 失败类型：权限拒绝、公开网策略拒绝、依赖超时、模板校验失败、等待用户/外部条件、版本冲突或持久化失败。
- 可见结果：调用方收到可区分的 canonical failure 或规格明确允许的降级结果；任何失败均不写入成功事实。
- 恢复动作：调用方按 canonical recovery action 重试、刷新或停止；不得自行合成成功结果。
- 禁止 fallback：不得回退到 Mock、旧 wire、双读双写或页面本地写副本。

## 6. 质量与观测

- 观测统一关联 Run、Skill、Trigger、Context Snapshot、Tool Use、Source、Presentation 与 terminal outcome。
- 信息不足且无法安全假设时进入等待输入；预算耗尽或完成门失败时返回可解释阻断。
- 质量门覆盖公开网安全拒绝、来源质量、上下文压缩、模板降级、Run 恢复、工具有效率和 Verifier 拒绝完成。
