# L2 Business Capability：小趣统一体验 (`world-class-trinity-experience-baseline`)

> 所属领域：[`assistant-run-learning`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

以统一 Agent 主线、Skill Package、可验证的自主探索、语义化 Adaptive Presentation、可解释过程与可恢复长任务，提供可持续扩展且可回退的小趣体验。

## 2. 范围与非目标

### In Scope

- 由本目录 Story 组合交付“world-class-trinity-experience-baseline”的独立业务结果。

### Out of Scope

- 其他 L2 的事实所有权、metadata schema 与实现施工步骤。

## 3. Journey / Scenario 贡献

- [`JNY-009 / SCN-017`](../../spec.md#scn-017)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：以统一 Agent 主线、Skill 中心、Markdown-first 输出、可解释折叠过程与显式偏好回注提供一致的小趣体验，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。

## 4. Story


- [`session-preference-memory-control`](./session-preference-memory-control/spec.md)：结构化文风偏好的即时注入、可见、遗忘与撤销恢复。
- [`native-tool-calling-model-routing`](./native-tool-calling-model-routing/spec.md)：以提供方原生工具调用协议选择工具，并按运行阶段与问题类型路由模型档位及降级。
- [`tool-fabric-runtime`](./tool-fabric-runtime/spec.md)：统一执行工具的时限、重试、循环检测与失败恢复，并保证策略允许工具真实可用。
- [`skill-progressive-disclosure-routing`](./skill-progressive-disclosure-routing/spec.md)：在策略允许集合内选择领域技能，并按需加载技能提示正文。
- [`planner-aggregation-orchestration`](./planner-aggregation-orchestration/spec.md)：决定下一步动作含向用户反问，统一单技能与多技能编排并裁决答案边界。
- [`context-assembly-slot-filling`](./context-assembly-slot-filling/spec.md)：运行前装配授权后的上下文与槽位状态，并以统一渠道声明约束公开场合记忆边界。
- [`long-term-memory-compaction`](./long-term-memory-compaction/spec.md)：记录可撤销的事实型长期记忆，并以滚动摘要压缩长会话历史。
- [`trajectory-replay-evaluation-gate`](./trajectory-replay-evaluation-gate/spec.md)：以覆盖全部技能的可重复轨迹回放阻断工具、澄清、引用和答案边界的静默回归。
- [`autonomous-web-exploration`](./autonomous-web-exploration/spec.md)：允许用户或模型从任意公开 HTTPS URL 开始只读探索，同时阻断内网探测、凭证继承和无界抓取。
- [`skill-context-proactive-runtime`](./skill-context-proactive-runtime/spec.md)：以不可变 Skill Package 和按需 Context Profile 统一响应式与主动触发运行。
- [`adaptive-presentation-runtime`](./adaptive-presentation-runtime/spec.md)：由 Skill 选择云端语义模板并填充结构化数据，App 按能力自适应渲染并安全降级。
- [`durable-agent-run-orchestration`](./durable-agent-run-orchestration/spec.md)：将长任务持久化为可暂停、恢复、调整、取消和断线重放的 AssistantRun。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 小趣统一体验能力组合结果

- 本能力必须组合直属 Story 与公开契约，交付统一的响应式、主动式与后台长任务体验；公开网证据、上下文、工具、展示与完成判定均可追踪，失败终态必须可区分且不得伪造成功。

<a id="req-002"></a>
### REQ-002 统一 `run / runStream / skills / invoke` 能力面

- 统一能力面，而不是本地/远端/渠道各说一套协议。
- Tool Fabric 和安全守卫在模型之外统一治理。
- 不把兜底能力做成低质模板回复，fallback 也必须是高水准通用能力。
- 第三方 Skill 商店化运营不属于本能力范围；Skill 自带的安全语义模板属于本能力范围。
- 正式编排面统一以 `skillRuns[]` 执行单 skill 与多 skill 问题，并由 `AggregationState` 裁决最终答案。
- `Tool Fabric` 统一工具元数据、参数 schema、权限、预算、结果截断、循环检测与恢复动作。
- `CapabilityGateway`：统一 `localOnly / remotePreferred / hybrid`，并对齐 `run / runStream / skills / invoke` 能力面。
- 统一本地和远端的结果质量门控，远端不满足商用品质时稳定回退。

<a id="req-003"></a>
### REQ-003 自主探索、Adaptive Presentation 与后台长任务使用同一运行事实

- 用户可直接提供公开 HTTPS URL，模型也可沿搜索结果或已读文档链接继续探索；所有内容都必须保留来源血缘和引用边界。
- Skill 只提交其允许的模板引用与结构化数据，服务端验证后形成终态展示事实；App 不执行云端代码。
- 长任务在 App 断连或服务实例重启后仍可恢复，用户可暂停、继续、补充约束或取消，并只能在完成条件通过后进入成功终态。

## 6. 契约与依赖

- 上游能力：[`assistant-run-learning`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 world class trinity experience baseline 能力 SIT

- GIVEN 执行“world class trinity experience baseline 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“world class trinity experience baseline 能力”对应动作。
- THEN 直属 Story 共同交付统一的响应式、主动式与后台长任务体验，公开网来源、上下文、工具、语义展示和完成判定均可追踪，失败终态可区分且不产生伪成功事实。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 world class trinity experience baseline 能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：尚缺受管 Provider、真实 Mongo/Redis、三环境同候选、双端物理真机和 Prod 发布证据，源码与本地门禁不能替代商业准出。
  - 缺真实 Mongo/Redis Assistant API integration 全包执行收据；包可编译以及 `AssistantRun`、TaskGraph、Checkpoint、Presentation、主动 Trigger、公开网、原生工具调用和恢复状态机的 direct local contract 不能替代该收据。
  - 缺绑定最终冻结 snapshot 的唯一 immutable candidate，以及 Alpha/Beta/Gamma 对同一 active Skill package digest 的 activation、Provider、Run/Tool/Presentation 与 rollback readback。
  - 缺公开 URL、主动 Skill、Adaptive Presentation 和后台恢复的 Android/iPhone 物理真机 Remote UAT。
  - 缺 Prod 法务真值、受保护审批、`canary→5→20→50→100` rollout 与 ≤300 秒 rollback readback；模拟器、本地测试、未绑定最终 snapshot 的 package 或未执行的 Patrol 均不能替代。
- 完成判定：`SIT-001` 对应行为满足，冻结 current source 后重新通过 ContractGraph、Assistant local contract、真实 Mongo/Redis API integration 与 service architecture。生成唯一 immutable candidate，并在 Alpha/Beta/Gamma 取得同 digest 的 package activation、Provider、Run/Tool/Presentation 与 rollback receipts。随后在 Android/iPhone 物理真机执行 Remote UAT，补齐 Prod 法务真值并完成受保护的 `canary→5→20→50→100` rollout 与 ≤300 秒 rollback readback。全部直属 Story 的阻断 OPEN 满足各自完成判定后方可删除本 OPEN。
