# L2 Business Capability：三层测试模型 (`runtime-test-pyramid`)

> 所属领域：[`runtime`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

以 local_contract、api_integration、user_acceptance 形成唯一测试分层，使 App 与服务测试按生产对象身份同构，并让对象级覆盖率、结构证据和真实运行结果保持可区分。

## 2. 范围与非目标

### In Scope

- 三层测试命名、case ID、环境语义和执行入口
- App、Service、Data、Ops 测试路径到 domain/context/object owner 的反向关联
- support 边界、真实依赖分层、对象级分支覆盖率和运行报告计算
- 测试入口结构证据与 CaseResult、环境及用户验收结果证据的分离

### Out of Scope

- 单个业务 Story 的具体产品行为
- 远端环境和凭证供给
- prod 审批与放量决策

## 3. Journey / Scenario 贡献

- 横切工程能力：不直接拥有 AppRoot Scenario；调用本能力的业务领域仍承担对应 Journey 的产品责任。
  - 本能力处理：以 local_contract、api_integration、user_acceptance 形成唯一测试分层和环境证据模型。
  - 本能力输出：可供业务领域组合的公开结果与明确失败终态。

## 4. Story



- [`three-layer-evidence`](./three-layer-evidence/spec.md)：已支持验收至少有一个职责匹配且可执行的直接 `spec_ref`；被 OPEN 声明的未完成验收不得计为通过。
- [`branch-coverage-governance`](./branch-coverage-governance/spec.md)：对象级覆盖结果从真实绿测试派生，分支、未归属源码和覆盖回退不会被文件存在或人工基线掩盖。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 三层测试模型与门禁单轨收口

- 节点 spec 只登记稳定 UAT/DOM/SIT/GWT；测试或可执行治理门以 `spec_ref` 直接引用验收锚点。
- 已关闭验收至少有一个真实、职责匹配且可运行的 `spec_ref`；未闭合验收由同节点 OPEN 明确完成判定。
- App 三层测试按 `test/<layer>/service/<service>/<context>/<object>` 与 production 对象同构；服务 local_contract/api_integration 按 `tests/<layer>/<context>/<object>` 同构。
- App 跨对象 Journey 只有两种 canonical 边界：`test/local_contract/journeys/<journey>/` 只容纳使用测试树 typed double、Provider 或 Widget 的本地跨对象 Journey 契约，测试文件使用 `__local_contract_test.*` 后缀；`test/user_acceptance/journeys/<journey>/` 只容纳使用 production Remote composition 的真实 Journey，测试文件使用 `__user_acceptance_test.*` 后缀。禁止创建 `api_integration/journeys`。
- Journey 目录名必须为 `snake_case`，测试文件必须是 journey 目录的直接子文件，复用 helper 只能进入 `test/support`；路径存在只证明结构入口，不代表 Remote composition 已执行或通过。
- `support` 只承载共享 harness、fixture factory 与 typed double 定义，不承载测试用例、业务断言或环境 App 可达的生产实现；对象 support 必须位于 `test/support/service/<service>/<context>/<object>/`，真正横切的运行器、平台与边界 harness 只能位于 `test/support/runtime/`。
- support 禁止建立 `repository_mock_reexports`、按框架/类型聚合的 `fakes/fixtures/cloud_services` 等跨对象桶；消费者必须直接 import 唯一对象 owner。普通 fixture、typed double、adapter 与 golden 禁止用 `Alpha*`、`alpha_*` 等部署环境名伪装环境证据，真实 Alpha/Beta/Gamma/Prod 验收只能由相应结果层 runner 绑定候选、Provider 与可信回执。
- App、Service、Data、Ops 的 canonical 三层目录是唯一测试入口；旧 `ui/cloud/core/pages/patrol/quality` 测试大桶和其他迁移 allowance 不能成为长期合法路径。
- 运行报告从测试代码、执行结果、环境和制品摘要实时生成，不提交覆盖清单或证据索引。
- 测试入口路径、spec_ref 与内容摘要属于结构证据；runner 产生的通过/失败/跳过 CaseResult、环境摘要与用户验收回执属于结果证据，静态扫描不得把前者解释为后者。
- 视觉基线的 fixture 必须与执行日期无关；会跨越相对时间阈值的当前日期不得写入 golden 输入。

<a id="req-002"></a>
### REQ-002 禁止新增 T1-T4、L1-L4、contract-test 等第二套分层名称

- 禁止新增 `T1-T4`、`L1-L4`、`contract-test` 等第二套分层名称
- `spec_ref` 与验收锚点必须双向有效，禁止集中映射表或不存在的逻辑 case 冒充测试
- 缺少远端环境、凭证或当前报告时必须 `GATE_BLOCK`，不得以静态声明代替

<a id="req-003"></a>
### REQ-003 测试层由依赖真实度与用户可见边界决定

- local_contract 可使用进程内 typed double、fake 或内存实现，证明对象规则、mapper、Provider/Widget 状态、错误恢复与本地端口；任何测试 double 不得进入 api_integration、user_acceptance 或环境 artifact。
- api_integration 必须连接真实进程形态的 HTTP/WS、数据库副本集、缓存、消息或对象存储边界；把 fake 依赖包装成 HTTP 或把替身测试放入该目录仍按错层阻断。
- user_acceptance 必须使用 production Remote composition 验证 Journey、用户可见终态与恢复动作；文件存在、静态 path-UAT、动态 skip 或环境名不能充当执行结果。
- 覆盖率只描述真实测试触达的生产代码，不能替代 api_integration、user_acceptance、Provider、四环境或设备 CaseResult。

## 6. 契约与依赖

- 上游能力：[`runtime`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 三层测试模型与门禁单轨收口

- GIVEN 执行“三层测试模型与门禁单轨收口”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“三层测试模型与门禁单轨收口”对应动作。
- THEN 节点 spec 不包含测试文件、命令、通过率或历史证据，测试代码以 `spec_ref` 直接关联稳定验收锚点。
- THEN 每个已关闭验收都有真实测试或可执行治理门反向引用；OPEN 中的未完成验收不会被误报为通过。
- THEN App 与服务三层测试均可由物理路径精确反向定位 production 对象，support 不承载测试用例，旧测试大桶与迁移 allowance 不作为合法终态。
- THEN local_contract、api_integration、user_acceptance 按真实依赖和用户可见边界分类，fake HTTP、Memory 集成、path-UAT 与动态 skip 均不能提升证据等级。
- THEN 测试入口结构证据与 runner CaseResult、环境和用户验收结果证据分字段表达，文件存在不会被解释为执行通过。
- THEN golden fixture 使用固定、跨执行日期稳定的输入，不因相对时间阈值自动漂移。
- THEN 动态报告能从当前代码与运行结果定位实际测试、环境和制品摘要，不读取 tracked inventory。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 对象同构三层测试与结果证据准出

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`block`
- 影响或价值：当前测试树仍包含旧技术大桶和不完整的对象路径校验，静态 evidence 也尚未把 App、服务、Ops 的入口与 runner CaseResult 分侧承载，无法证明每个受影响对象的三层测试与真实结果完整。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效。
- 依赖：[`three-layer-evidence`](./three-layer-evidence/spec.md) 与 [`branch-coverage-governance`](./branch-coverage-governance/spec.md) 的开放事项关闭。
