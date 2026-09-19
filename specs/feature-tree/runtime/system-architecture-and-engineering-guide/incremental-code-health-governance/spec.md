# L3 Story：轻量增量代码健康治理 (`incremental-code-health-governance`)

> 所属能力：[系统架构与工程规范](../spec.md)
>
> Journey / Scenario：本 Story 为横切工程能力，不直接承接用户 Journey。
>
> 设计引用：[L2 DEC-031](../design.md#dec-031)

## 1. 用户价值

作为持续交付代码的开发者或 Agent，我希望每个 candidate 在数分钟内得到只针对新增或恶化维护债的可复现结论，从而在不让存量债拖死交付的前提下保持代码可理解、可复用、可验证。

## 2. 范围与非目标

### In Scope

- source 分类、复杂度、重复、可达性、文件规模与手写变更认知预算的 candidate delta。
- L0、L1、Delivery Gate 与 weekly report-only 的分层调度和 digest-bound receipt。
- Agent PRE/POST、Review named evidence、AI advisory 与热点 OPEN 的边界。

### Out of Scope

- 以总代码行数或提交数评价 Agent/个人，或要求一次清零全部存量债。
- 常驻质量服务、中央债务台账、路径豁免、AI 自动准出或自动删除可达性不确定代码。
- SBOM/许可证、Data JSON Schema 标准兼容和 release domain-model compatibility。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 candidate delta 只判新增或恶化事实

- 每个 changed path 必须互斥分类，generated/vendor/test 与手写生产代码使用不同判据。
- 首日 blocker 只来自确定性高置信新债；存量、无法证明的动态入口和 calibration 指标只报告。
- 删除、rename、codegen、fixture 与大迁移必须单列，不能仅按 churn 大小阻断。
- 手写生产文件规模由本 Story 的 canonical delta 单轨拥有：任何语言（含 Python 脚本治理）不得维护第二套行数预算、路径 allowlist 或机器派生豁免；测试类文件规模只进入 weekly 观测。
- 规模按同一逐文件事实派生语言、分类与模块汇总并保持守恒；物理行与 `cloc code` 分别命名，不能混算。源码目录恰名 `coverage` 不构成输出排除理由，内容发布目录按明确路径前缀分类，不用目录片段误匹配。
- generated 身份必须来自可信生成来源，不能凭任意文件自称 generated 绕过手写判罚。跨语言指标分别声明分析能力与未测状态，未测不得投影为零违规。
- 每条 finding 拥有稳定且可区分同文件同名成员的身份；candidate 身份绑定测量范围。债务变化区分新增、恶化、消除与持平，消除旧债不能抵消另一位置的新增 blocker。

<a id="req-002"></a>
### REQ-002 证据、调度与准出 authority 单轨

- delta receipt 必须绑定 exact Git range、changed paths、candidate exact bytes、policy、命令和 toolchain，输入漂移后不得复用。
- L0、L1、PR 与 scheduled 只改变执行深度，不复制指标阈值或建立第二策略。
- 确定性 terminal 不得被 AI、Reviewer、自然语言理由或旧 receipt 改写。
- 隔离 candidate 的健康子检查必须消费外层声明的 exact parent/head，而非从物化后的 `HEAD/dev1.0` 重新猜测基线。准出必须消费 full delta，并核对实际测量的 range、路径与 candidate；有源码增量却空扫描不构成 PASS。
- 评审裁决按 finding 身份绑定 current report，由 Review owner 契约拥有去向与退役闭包；缺失裁决或过期证据不能只因分析器退出 0 而获准出。替换仅在有消费者迁移与旧轨清理证据时称为退役完成；动态可达性不确定不授权自动删除。
- 交付链必须绑定自身完整准出范围的健康证据，不能用最后一次 push 的 report 代替整个 promotion 增量；集成后复算与 weekly 观察不签发发布 authority。

<a id="req-003"></a>
### REQ-003 calibration 与热点观测保持轻量

- advisory 指标只有达到最小时间/PR 样本、误报与耗时目标后，才能由显式策略版本人工升格；误报按 finding code 抽样评审判定（每个 code 至少 `minimum_reviewed_per_code` 条人工 verdict 且误报不超过上限），不要求评审全部 advisory。
- weekly 报告只输出容量趋势、churn、health 与 Top hotspots，不阻断 PR、不提交 snapshot。
- 连续出现且可行动的热点才进入最低 owner OPEN，不产生中央 backlog。
- 周报保存所有模块事实，Top N 仅为展示排序；结构复用 scope 不冒充已解析的 Feature context。未采集的架构、覆盖率或退役证据保持 unavailable，不能用规模和测试行数推导这些状态。
- 周报从 exact Git source 读取，当前工作树未提交字节不污染已提交统计。观察分支、head、策略、分析器与口径绑定历史比较；缺历史、跨分支或口径变化不得伪造改善。定时工作流部署和连续运行 readback 与本地实现分别报告。

## 4. 契约引用

- canonical policy：`quwoquan_ops/policies/code_health_policy.yaml`
- canonical impact：`quwoquan_ops/ci/impact_planner_core.py`
- canonical evidence：`quwoquan_ops/cli/lib/evidence_fingerprint.py`
- canonical entry：`make verify-code-health-delta`（本地 L1/L2，base 为 HEAD 与 dev1.0 的 merge-base）
- hosted 复算：`.github/workflows/lane-gate.yml`（lane PR required check，经 `verify_code_health_delivery.py`）与 `.github/workflows/code-health-integration.yml`（dev1.0 快进后 report-only fact，经 `quwoquan_ops/ci/verify_code_health_integration.py`）
- weekly 观测：`make report-code-health-weekly` / `.github/workflows/code-health-weekly.yml`，历史以 OCI fact 保存
- owner 热点视图：`make code-health-hotspots OWNER=<owner-scope>`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 changed-code 新债得到 typed terminal

- GIVEN candidate 同时包含手写、测试、generated、vendor、contract、config 与 docs 变更。
- WHEN 执行 canonical code-health delta。
- THEN 每个 path 恰好落入一种分类，只有手写生产代码参与复杂度、重复与认知预算判罚。
- THEN 新越过 2000 行、既有超限继续上升或新增无入口 private Python module 返回 `GATE_BLOCK`。
- THEN 复杂度、重复和 1000 行候选阈值在 calibration 阶段只返回 `PR_WARN`。
- THEN rename、delete、generated regeneration 与具备单一验收切片的大迁移不因原始 churn 单独阻断。

<a id="gwt-002"></a>
### GWT-002 receipt 对输入漂移 fail-closed

- GIVEN 一份已经生成的 code-health receipt。
- WHEN changed paths、base/head、candidate 字节、policy 或 toolchain 任一变化。
- THEN 新运行产生不同 EvidenceFingerprint，旧 receipt 不得充当该 candidate 的 PASS。
- THEN clean CI 独立重算 exact range，不信任本地脏树或旧 named evidence。
- THEN 未达到 calibration 的 14 天或 20 PR 与低于等于 10% confirmed false-positive 条件时，策略拒绝自动把 advisory 升为 blocker。

<a id="gwt-003"></a>
### GWT-003 本地、CI、Agent 与周报分责

- GIVEN Agent 正在实现一个唯一 owner 的 candidate。
- WHEN PRE、L0、L1、Review、Delivery 与 weekly 生命周期依次消费代码健康事实。
- THEN PRE 只加载本 owner 的紧凑阈值和热点，POST 生成 current delta receipt，Reviewer 与 AI 只消费命名证据。
- THEN L0 不安装网络工具且只做 changed-file 快判，L1/Delivery 执行完整 delta，weekly 全量报告不阻断 PR。
- THEN `PR_WARN` 只能被裁决为 candidate 内修复、最低 owner OPEN 或 out-of-scope，重复两次后才可 distill 为绑定 deterministic check 的规则候选。
- THEN weekly 报告对照上期给出每项棘轮指标的方向与每个 Top hotspot 的连续在榜周数；`plan-next` 只对连续两期在榜且可行动的 owner scope 热点裁决为最低 owner OPEN 或 out-of-scope，热点事实不可用时按无热点继续、不阻断。

<a id="gwt-004"></a>
### GWT-004 健康量尺可比较且不靠分类逃逸

- GIVEN 两个 exact Git 版本包含同名成员、生成物、真实 `coverage` 源码、内容发布资产和机械搬迁。
- WHEN 计算健康 delta 与模块规模。
- THEN finding 身份区分同文件不同成员，裁决不会因相同 `code/path` 合并；删除或简化可观察为消除，不掩盖其他 blocker。
- THEN 可信生成物独立分类，伪造生成声明不豁免手写债；各模块、语言与分类汇总来自同一明细且总量守恒。
- THEN 工作树脏字节不改变 exact commit 的统计，未测分析能力不输出无违规结论。

<a id="gwt-005"></a>
### GWT-005 准出必须检查真实增量并完整裁决

- GIVEN 已提交 candidate 相对 parent 新增确定性 blocker，且其隔离执行目录完全干净。
- WHEN acceptance 计算健康并尝试准出。
- THEN full report 覆盖真实 parent/head 的源码路径，不能因 capsule 的本地分支都指向 candidate 而获得空增量 PASS。
- THEN 错误范围、fast-only、缺失报告或未裁决 warning 不构成准出健康证据；原始 GATE_BLOCK 不被调用方 passed 标记或 OPEN 改写。
- THEN 合法无源码增量可明确报告不适用，日常 staged 快判仍保持其自身语义。
- THEN promotion 验证其完整 exact 范围；集成后最后一段健康 PASS 不代替完整准出增量。

<a id="gwt-006"></a>
### GWT-006 全模块投影与历史状态诚实

- GIVEN 仓库模块数超过五个，热点文件数超过二十个。
- WHEN 保存 weekly fact 并按任意模块读取健康视图。
- THEN 未进入 Top N 的模块仍有完整事实；缺失 coverage、架构、退役或历史证据显式标记未测，不显示为健康。
- THEN 报告标明观察分支、exact head、时间与测量口径，不把跨分支或异口径变化称为健康改善。
- THEN weekly 仍 report-only，不因报告可视化生成 release authority 或中央债务台账。

## 6. 依赖

- 前置要求：canonical impact planner 与 EvidenceFingerprint 可用。
- 上游事实：exact base/head、changed paths、context identity、candidate 字节与 policy/toolchain identity。
- 下游结果：typed report、named evidence、Delivery Gate 结论与 report-only hotspots。
- 父级设计：`DEC-031`。

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 健康量尺与准出证据闭环

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺验收证据：`GWT-004`、`GWT-005` 的完整子句绑定与入库/promotion 对合法告警裁决的联合验证。启发式指标、隔离 candidate 范围和告警裁决不可据上层回执冒充完整健康证明；既有 `GWT-001` 至 `GWT-003` 的规则仍生效，不以本 OPEN 豁免 blocker。
- 完成判定：`GWT-004`、`GWT-005` 的子句级真实负例及正例绑定完成，fresh full delta、readiness 与 promotion 的范围/结果消费通过；评审与发布 owner 的证据链分别闭合。

<a id="open-002"></a>
### OPEN-002 全模块观察与真实定时运行

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺验收证据：`GWT-006` 对应默认分支工作流的授权部署、真实运行与连续周度 readback，以及各业务 owner 的热点退役闭包。全模块投影与异口径历史识别的本地测试不替代上述证据；活跃 writer 持有的热点不得被其他 scope 抢写或据旧报告称已收敛。
- 完成判定：`GWT-006` 子句有真实测试与 exact source 报告；经授权发布后的周报工作流实际运行并完成连续周期 readback，未测模块及历史缺口显式展示；热点按其最低 owner 独立关闭。
