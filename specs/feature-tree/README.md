# 特性树写作、评审与门禁标准

本目录是产品规格与有效设计的唯一入口。目录结构就是树；父子 `spec.md` 就是导航；`design.md` 只记录当前有效的实现决策；所属服务 `contracts/**` 是业务对象与 wire 契约真相源，跨服务共享协议位于 `quwoquan_service/contracts/metadata/**`；代码与测试是实现和验收证据。

## 1. 目录模型

```text
specs/feature-tree/
├── README.md
├── spec.md
├── design.md
└── <l1>/
    ├── spec.md
    ├── design.md
    └── <l2>/
        ├── spec.md
        ├── design.md        # 仅达到设计门槛时存在
        └── <l3>/
            └── spec.md
```

- AppRoot：全应用目标、Journey、Scenario 和 UAT；`design.md` 保存全局架构与跨域约束。
- L1 Domain Service：稳定业务领域、事实所有权和领域边界；不等同于部署进程或代码模块。
- L2 Business Capability：多个 Story 组合成的独立业务结果。
- L3 Story：用户或平台调用方可观察、可独立验收的最小价值。
- Journey/Scenario 不是目录层；完整叙事只在 AppRoot `spec.md`，节点只写自身职责。

节点目录只允许 `spec.md`，以及 AppRoot/L1 必需、L2 按需的 `design.md`。禁止 `README.md`、`acceptance.yaml`、`tree.yaml`、`plan.md`、`tasks.md`、runbook、matrix、inventory、changelog、status、revision 和 L3 `design.md`。

模板位于 [`specs/templates/feature-tree`](../templates/feature-tree/)；7 份模板与实际节点使用同一章节门禁，模板占位符不得进入正式节点。

## 2. 层级内容要求

### AppRoot

- `spec.md`：产品目标、范围与非目标、术语、Journey/Scenario、跨域要求、UAT、开放事项。
- `design.md`：全局上下文、跨域数据流、全局 DEC、质量与运行约束、失败恢复、迁移回滚。
- Journey 必须写用户目标、起点、成功终态、失败恢复和参与 L1；Scenario 必须写领域交接并指向 UAT。

### L1

- `spec.md`：领域价值、拥有/不拥有的事实、上下游、Journey 职责、直接 L2、REQ、DOM、稳定工程归属和 OPEN。
- `design.md`：领域模型与所有权、上下文协作、架构数据流、DEC、特有质量约束、失败恢复与当前迁移。
- 工程归属只登记稳定目录根；业务域契约使用所属服务 `contracts/**`，`Metadata` 只允许 `_shared/_schemas/_vectors/_control_plane` 等跨服务定义；同一路径不得由多个 L1 无主次认领。

### L2

- `spec.md`：能力结果、范围、Journey 贡献、直接 L3、REQ、契约依赖、SIT 和 OPEN。
- 只有跨 L1/服务、外部依赖、状态或数据所有权变化、迁移、非平凡质量权衡、多方案或特有 rollout/rollback 时才创建 `design.md`。
- 不创建 design 时，spec 顶部必须指向父 L1 的 `DEC-###`。

### L3

- `spec.md`：独立用户价值、范围、可观察 REQ、canonical 契约引用、1～3 个 GWT、依赖和 OPEN。
- 不创建 `design.md`。非平凡设计决定上收到 L2；若单一 Story 复杂到需要独立设计文件，应拆分 Story 或上收能力责任。

## 3. 规格、设计与验收边界

- 规格说明系统应当做什么和不得做什么，不罗列类、函数、DTO 字段、施工步骤、测试命令或完成状态。
- 设计说明如何满足规格，只记录仍有效且会约束未来实现的架构决定，不复制规格或 metadata schema。
- AppRoot 使用 UAT，L1 使用 DOM，L2 使用 SIT，L3 使用 GWT。每项只保留会改变业务契约的代表性场景；排列组合、fixture、命令和执行证据留在测试代码与测试结果。
- 测试工程只使用三层：`local_contract` 证明本地规则与契约，`api_integration` 证明真实端云/存储/外部边界，`user_acceptance` 证明 Journey 与用户可见终态；测试直接以 `spec_ref` 绑定对应验收锚点。
- 字段、path、operation、surface、route、event、metric、错误码和恢复语义只引用 canonical metadata ID，不在 spec/design 复制定义。
- 已解决事项直接转为当前已支持的 REQ/设计事实；禁止保留完成日志或 resolved 清单。

## 4. 开放事项

未完成能力、外部阻断、当前风险和未来规划写在最低可独立关闭的节点 `## 开放事项` 中：

```markdown
### OPEN-001 标题

- 类型：`capability_gap | external_blocker | risk | future_plan`
- 优先级：`P0 | P1 | P2 | P3`
- 准出影响：`block | track`
- 影响或价值：……
- 完成判定：`GWT-###`、`SIT-###`、`DOM-###`、`UAT-###` 或其他可观察结果
- 依赖：……
```

OPEN 的存在就是未关闭；关闭时删除 OPEN，并把已支持行为写回 REQ/验收。禁止中央 backlog、成熟度矩阵或第二套风险登记。总览由工具动态扫描生成。

## 5. 增量与历史

不维护 changelog 或 change manifest。当前增量由会话目标与计划、spec/design/metadata/code/test 的 Git diff、测试结果和动态 change report 表达；历史使用 `git log --follow` 与 `git diff` 查询。动态报告只能写入 `.qwq_output`，不得提交。

## 6. Agent 最小阅读链

```text
最近的 AGENTS.md
  -> 本 README
  -> AppRoot spec/design
  -> 目标 L1 spec/design
  -> 目标 L2 spec/design（若存在）
  -> 目标 L3 spec
  -> spec 引用的 metadata
  -> spec_ref 对应测试
```

只读取目标父链和直接依赖。决策优先级是 AppRoot spec → L1 spec → L2 spec → L3 spec → design → metadata → code/tests。下层只能细化上层；发生冲突时先修规格。

## 7. 动态工具

```bash
make feature-context TARGET=<spec-or-code-path>
make feature-tree-overview
make feature-tree-change-report
make feature-tree-content-review
make verify-feature-tree
```

- `feature-context`：输出目标父链、要求/验收/DEC/OPEN、Journey、工程归属、metadata 与测试引用；代码路径必须唯一定位到 L1。
- `feature-tree-overview`：实时输出领域、能力、Story，并按 OPEN 类型、优先级、准出影响、完成判定与 L1/L2 子树聚合开放事项。
- `feature-tree-change-report`：从 Git diff 推导受影响父链、锚点变化和未归属变更。
- `feature-tree-content-review`：逐文件检查实际节点与模板的章节、参与者与价值、非占位要求、GWT/DOM/SIT/UAT、DEC、服务本地契约、工程引用、真实 `spec_ref` 与 OPEN 一致性，并阻断历史编号、迁移病句、通用治理占位和中心业务域 metadata 回潮。
- `verify-feature-tree`：直接扫描目录和 Markdown，阻断结构、链接、归属、设计、验收与测试/可执行门追踪漂移。

所有输出位于 `.qwq_output/env/repo/runs/feature-tree/`。

## 8. 人工评审清单

### L1

- 五分钟内能否说清领域价值、拥有/不拥有的事实和上下游边界？
- 每个 L2 是否是可组合业务能力，而非页面组、服务名或技术任务？
- 工程归属是否唯一定位 App、metadata、Service/Data/Ops 和三层测试？
- DOM 是否验证所有权和不变量，而非复述测试命令？

### L2

- 是否有独立业务结果、清晰 Scope，且 Story 共同构成该能力？
- SIT 是否验证跨 Story 或端云组合？
- design 是否达到创建门槛；不存在时是否有明确父级 DEC？

### L3

- 是否提供独立可观察价值，REQ 是否无实现细节？
- GWT 是否简洁覆盖主路径与关键契约边界？
- 是否只引用 metadata，而没有复制 DTO、path 和错误文本？
- 是否错误承担了能力级设计？

## 9. 自动门禁

门禁至少检查：目录层级与父子链接一致；Markdown 链接/锚点有效；AppRoot Journey 与参与 L1 双向引用；工程归属存在且无未裁决重叠；L2 设计归属有效；禁止文件不回潮；REQ/UAT/DOM/SIT/GWT/DEC/OPEN 在文件内唯一；测试或可执行门的 `spec_ref` 指向现存验收锚点；OPEN `block` 对对应范围准出可见；Git diff 不出现未归属的业务变更。

验收追踪采用双向门禁，不维护 tracked coverage map：已支持的 UAT/DOM/SIT/GWT 必须被真实测试直接 `spec_ref`；尚未支持的验收必须出现在同一节点 OPEN 的“完成判定”中。代码治理类验收可以由可执行 gate 作为证据，产品行为验收必须由测试证明。

复合验收（含两条及以上结果子句）另受子句级覆盖判据约束。子句 ID 由锚点正文自身派生：第 N 条结果子句即 `tN`。**一个顶层结果 bullet 就是一条子句**：`GIVEN`/`WHEN`/`条件：`是前置条件，`AND` 不表达独立性、只继承最近一条角色 bullet 的角色，因此 `GIVEN` 后的 `AND` 仍是前置条件，`THEN` 后的 `AND` 是另一条结果。判据只看行首关键字，不读标点、不推断语义，所以同一段正文任何时候都得到同一个数，也不存在「把独立结果折叠进 `AND` 以规避子句级绑定」的写法；确实属于同一条结果的补充说明写成该 bullet 内的缩进续行。不存在与正文并列的数量声明字段。测试以 `spec_ref: <spec>.md#gwt-001.t3` 精确绑定单条结果，同一测试文件可携带多条子句引用，无需为满足门禁拆分测试文件。三条规则：

- 悬空子句引用（锚点不存在或 `tN` 越界）直接阻断，结果子句增删会立即暴露失配的绑定。
- 精度不可半途：锚点一旦出现任一子句级绑定，其全部结果子句必须都被绑定，禁止只绑定容易验证的那条却对外表现为精确覆盖。
- 闭合即需精度：本次 Git 增量中开始声称已闭合的复合验收（认领它的 OPEN 被删除、新增不挂 OPEN 的锚点、改写已闭合锚点正文）必须逐条绑定。存量不被追溯，代价只由真正做出闭合声称的改动承担；`verify-feature-tree` 输出 `RATCHET` 残量，该残量只减不增，没有豁免名单。

OPEN 的“完成判定”必须引用至少一个本节点存在的验收锚点（必要时含子句 `.tN`），否则该 OPEN 结构上不可裁定：没有任何证据能证明它关闭，也不会被双向门禁看见。若 OPEN 主张的缺口没有对应锚点，说明规格缺验收表达，应先补锚点而不是让 OPEN 继续悬空；若它其实没主张任何事实（纯占位或逐字复制 REQ 正文），应删除。该规则同样按 Git 增量棘轮生效：只有本次新增或改写的 OPEN 必须补齐，存量以 `RATCHET` 残量出现在门禁输出里，没有豁免名单。
