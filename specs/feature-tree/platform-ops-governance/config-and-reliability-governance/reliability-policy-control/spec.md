# L3 Story：可靠性策略控制 (`reliability-policy-control`)

> 所属能力：[`config-and-reliability-governance`](../spec.md)

> Journey / Scenario：横切工程能力；由父 L2 spec 参与 AppRoot Journey。

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为平台运维、安全或审核角色，
我希望用 SLO、错误预算、kill-switch 和回滚阈值约束高风险配置与服务发布，
从而获得可审计且可回滚的平台治理结果。

## 2. 范围与非目标

### In Scope

- “可靠性策略控制”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 可靠性策略控制

- 用 SLO、错误预算、kill-switch 和回滚阈值约束高风险配置与服务发布。

<a id="req-002"></a>
### REQ-002 托管发布 receipt 与提升

- `prod-hosted` 的 apply、health、SLO、rollback 只能由托管 service-plane 的不可变 receipt 证明；本机输出仅可作 readback cache。
- receipt 必须绑定 release manifest、`campaignId`、image/config/ContractGraph/adapter candidate digest、`allocationKeyId`、`subjectKind`、audience 摘要、stage、post-check、last-good target 和 rollback outcome。
- Provider Conformance 的 last-good/rollback ref 必须经 hosted fetch 与上述 candidate digest 同源校验；缺失托管凭据、真实前置条件或审批时发布保持 blocked。

<a id="req-003"></a>
### REQ-003 固定阶段、稳定分桶与单调扩张

- 生产发布状态机固定为 `canary → 5 → 20 → 50 → 100`；各阶段均为可暂停、可恢复、可回滚的独立发布事务，不存在 `prod-gray` 环境。
- canary 只接收内部 account/device 白名单；5、20、50、100 阶段分别使用 500、2000、5000、10000 basis points。
- Android、iOS、Web 按可信安装级 `deviceActorId` 分平台独立确定性分桶；阶段比例以去重安装实例为统计单位，请求量和去重账号比例必须另列。
- 同一 campaign 内已进入 candidate 的安装实例必须保持 candidate；阈值只允许增加，平台、受支持 App Build、地域与运营商 audience 只能保持或扩大。修改 candidate digest、allocation key、subject kind、降低阈值或缩小过滤条件必须被配置门禁拒绝。
- 地域、运营商默认全选并仅作观测维度；定向过滤只影响尚未入组的安装实例，命中后的持久化 assignment 不因地域、网络或运营商变化而失效。

<a id="req-004"></a>
### REQ-004 阶段证据、失败与回滚

- canary 必须完成 120 次 synthetic，并由 Android、iPhone、Web 各至少 2 个真实安装实例通过核心 Query、Command 和 UAT。
- 5% 阶段至少持续 30 分钟，累计 1000 个 candidate 请求和 50 个去重安装实例，每个已选平台至少 10 个。
- 20% 阶段至少持续 2 小时，累计 5000 个请求和 200 个安装实例，每个平台至少 30 个。
- 50% 阶段至少持续 24 小时，累计 20000 个请求和 1000 个安装实例，每个平台至少 100 个。
- 100% 阶段必须恢复全平台、全地域、全运营商和全部受支持 App Build，生成 full hosted receipt，并完成 24 小时 post-check、last-good 与 rollback target 回读。
- 显式过滤的每个地域或运营商至少有 10 个安装实例和 100 个请求；样本不足或 warn 阈值只能暂停，critical SLO、assignment store 故障、assignment 数据丢失、candidate digest 漂移或默认平台样本缺失必须自动 rollback。
- rollback 只切换 stable/candidate 服务池和 campaign 状态，不撤销共享业务事实；candidate 在全部阶段必须保持对当前 stable 契约和共享存储的向后兼容读写能力。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 可靠性策略控制

- GIVEN 平台运维、安全或审核角色具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“可靠性策略控制”对应的公开行为。
- THEN 用 SLO、错误预算、kill-switch 和回滚阈值约束高风险配置与服务发布。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 Hosted release receipt 准出

- GIVEN 运维提交具有 immutable manifest 和 image/config/ContractGraph/adapter digest 的候选发布。
- WHEN `stackctl deploy --target prod-hosted` 依次执行 `canary`、`5`、`20`、`50`、`100` 或自动 rollback。
- THEN service-plane 为每个阶段写入并回读独立不可变 receipt，campaign/candidate/allocation/audience 摘要、CAS generation、stage、post-check、last-good target 与 rollback result 均可校验，且本机 cache 不参与 readiness 决定。
- AND Provider Conformance 只接受经 `stackctl hosted-release-receipt` hosted fetch 校验的 `receipt:hosted:<sha256>` last-good 与 rollback ref。
- AND rollback 成功与失败分别记录为 `rolled_back` 和 `rollback_failed`；任一读回、digest、SLO、health 或真实环境前置条件失败均不得提升 readiness。

<a id="gwt-003"></a>
### GWT-003 多平台固定比例与阶段证据准出

- GIVEN Android、iOS、Web 均为默认选中平台，活动 identity 和 audience 已随受审计发布包冻结。
- WHEN candidate 从 canary 提升到 5%、20%、50% 和 100%。
- THEN 每个平台分别达到该阶段 basis-point 比例和最小样本要求，安装实例、账号、请求及过滤后的 eligible/全体比例可分别回读；缺失任一默认平台、地域或运营商定向样本不足时阶段保持 paused。
- AND 100,000 个固定测试 subject 在每个平台的 5%、20%、50% 分布分别处于 4.5–5.5%、19–21%、49–51%，不能用总体请求占比替代该证明。

<a id="gwt-004"></a>
### GWT-004 Candidate assignment 单调性与故障回滚

- GIVEN 某安装实例已经在 campaign 中形成 candidate assignment。
- WHEN 阶段扩大、账号切换、地域变化或网络/运营商变化，或控制面尝试缩小 audience、降低阈值、替换 candidate digest/allocation key/subject kind。
- THEN 正常变化不改变该安装实例的 candidate target，非法配置在 apply 前被拒绝；只有显式或自动 rollback 使真实请求全部返回 stable。
- AND assignment store 不可用或丢失时 campaign 自动进入 `rolled_back` 并生成可校验 rollback receipt，不得随机重分桶或以内存 assignment 伪装继续。

## 6. 依赖

- 前置要求：[`config-and-reliability-governance`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 可靠性策略控制 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺少能够证明“可靠性策略控制”已满足当前规格的真实测试证据。
- 完成判定：`GWT-001`、`GWT-002`、`GWT-003`、`GWT-004` 对应行为满足且真实测试 `spec_ref` 有效。
