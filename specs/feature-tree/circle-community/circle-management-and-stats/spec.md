# L2 Business Capability：圈子管理与统计 (`circle-management-and-stats`)

> 所属领域：[`circle-community`](../spec.md)
>
> 设计归属：[L1 DEC-001](../design.md#dec-001)

## 1. 能力目标

为圈子治理与运营提供权限受控的处置、固定口径指标和可下钻运营视图。

## 2. 范围与非目标

### In Scope

- 由本目录 Story 组合交付“circle-management-and-stats”的独立业务结果。

### Out of Scope

- 其他 L2 的事实所有权、metadata schema 与实现施工步骤。

## 3. Journey / Scenario 贡献

- [`JNY-004 / SCN-001`](../../spec.md#scn-001)
  - 本能力接收：该 Scenario 进入本能力边界的已授权主体与 canonical 输入。
  - 本能力处理：为圈子治理与运营提供权限受控的处置、固定口径指标和可下钻运营视图。
  - 本能力输出：直属 Story 组合产生的可观察结果与明确失败终态。
  - 失败时终态：保留已确认事实，并返回可恢复的 canonical failure。

## 4. Story



- [`kpi-reporting`](./kpi-reporting/spec.md)：定义“KPI 报告”的可观察主路径、失败语义及父能力交接。
- [`moderation-governance`](./moderation-governance/spec.md)：定义“治理”的可观察主路径、失败语义及父能力交接。
- [`ops-dashboard`](./ops-dashboard/spec.md)：定义“运营看板”的可观察主路径、失败语义及父能力交接。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 circle management and stats 能力 SIT

- 本能力必须组合直属 Story 与公开契约，交付“为圈子治理与运营提供权限受控的处置、固定口径指标和可下钻运营视图”所定义的业务结果；失败终态必须可区分且不得伪造成功。

<a id="req-002"></a>
### REQ-002 跨边界字段、operation 与错误语义只引用所属服务 contracts

- 跨边界字段、operation 与错误语义只引用所属服务 contracts；本节点不得复制 wire 定义。
- 对象专属错误由产生该业务失败的 Circle 对象唯一拥有；同域通用错误保持单一 canonical owner，兄弟对象只通过完整 operation 身份显式引用，不得复制 code 定义或把兄弟对象错误聚合回 Circle 主对象。

<a id="req-003"></a>
### REQ-003 PersonaCircleSlice 保持 Circle canonical 类型语义

- `PersonaCircleSlice` 必须使用 canonical `status`，不得保留 `state` alias；`status`、`visibility`、`joinPolicy`、`kind`、`displaySubjectType` 与 `linkedHomepageType` 必须分别引用 Circle 聚合及共享主页类型所属的 canonical enum。
- App 契约枚举必须由 metadata 生成；`PersonaCircleSlice`、Circle 查询投影及页面只读模型不得重新声明字符串值域，未知枚举值必须失败关闭。
- metadata 校验必须比较 `PersonaCircleSlice` 与 Circle 聚合的同名 enum_ref；任何投影降级为裸 string 或改绑其他值域都阻断生成。

## 6. 契约与依赖

- 上游能力：[`circle-community`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 circle management and stats 能力 SIT

- GIVEN 执行“circle management and stats 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“circle management and stats 能力”对应动作。
- THEN 直属 Story 共同交付“为圈子治理与运营提供权限受控的处置、固定口径指标和可下钻运营视图”，失败终态可区分且不产生伪成功事实；每个对象专属错误可追溯到唯一 owner，同域共享错误仅由 canonical owner 定义并精确绑定实际 producer。

<a id="sit-002"></a>
### SIT-002 PersonaCircleSlice typed projection 单轨验收

- GIVEN Circle 聚合和 `PersonaCircleSlice` 声明 canonical enum_ref，且 App 仅消费 metadata 生成的枚举。
- WHEN `GET /personas/{personaId}/circles` 返回 canonical `status` 与其余 typed 字段。
- THEN 服务端、纯 Dart 契约和页面模型保持同一值域；旧 `state` alias、未知枚举值或投影 enum_ref 漂移均失败关闭，不得补默认值伪造成功分支。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 circle management and stats 能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺 SIT-001 t2 的对象专属错误唯一 owner 证据，不能用页面测试硬绑。t1（权限受控处置、固定口径指标、可下钻运营视图）可由 kpi-reporting 与 membership 覆盖。本能力不阻塞 SCN-014 商用主旅程。
- 完成判定：`SIT-001` 两条结果子句均由真实测试 `spec_ref` 绑定。

<a id="open-002"></a>
### OPEN-002 圈子类目缺可引用的 canonical 值域

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：当前 `quwoquan_service/services/circle-service/contracts/circle_management/circle_membership/fields.yaml` 的 `PersonaCircleSlice.category` 与 `subCategory` 仍是裸 string，端侧只能自行约定类目取值，未知值无法失败关闭。
- 根因是 `quwoquan_service/contracts/metadata/_shared/domain_taxonomy.yaml` 的自述已失效，它声称由 codegen 产出 Go 与 Dart 的领域标签类型，但仓库内既没有该生成器也没有这两个符号，唯一读取它的脚本只校验 `user_tag_ref`。
- 该文件的子类目是按 domain 分组的本地化标签文案且没有稳定 id，直接压成扁平枚举会把 locale 文案写进 wire 取值，形成不可演进的对外契约。
- 迭代七曾尝试启动 enum_ref 单轨收敛：工作树存在并行 cloud_contracts / search / assistant / content codegen 锁，按计划中止，禁止半截收敛。
- 裁决补充：类目一级 id 闭集事实上已稳定存在
  （`meet/campus/car/humanity/life/sports/tech/travel/food`），但散落为 App 页面
  私有 const（`circle_edit_settings_page_state.dart` 九项闭集、hub 页五垂类子集），
  且 `circle_category_tab_config_dto.dart` 注释仍指向已不存在的
  `CircleCategoryTabsLoader`/`ui_category_tabs.yaml`。收敛方向：把该 id 闭集提升为
  circle 契约 `enum_ref`（wire 只收稳定 id，不收 locale 文案），服务端过滤与写路径
  fail-closed，App 两处 const 改消费 codegen 枚举；变更横跨契约单轨、双端 codegen
  与存量数据核验，须以独立迭代整体完成，禁止双轨或半截收敛。
- 完成判定：`SIT-002` 与 `SIT-001` 对应行为满足且真实测试 `spec_ref` 有效
- 依赖：先让领域标签文件真正产出枚举并为子类目分配稳定 id，再同时改聚合与投影字段类型。
