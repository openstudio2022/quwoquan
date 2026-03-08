# L3 特性：domain-onboarding-acceptance-governance

## 背景与动机

`runtime-control-plane-foundation` 已经冻结了统一门户、三类面、控制面元数据与统一集成验收的上位约束，但当前仓库仍缺少一套**可在一个统一实施会话中按模板域先行、再复制到所有垂直领域服务**、并在最终由同一会话完成集中收口的标准接入规范。

如果本阶段不冻结该规范，后续统一接入会出现以下问题：

- 各领域对“接入完成”的理解不一致，只补 API 或只补测试，无法形成统一验收口径
- `platform-ops` 与 `product-ops` 接入动作会退化为手写后台接口、手写检查清单和人工对表
- 三类面虽然在概念上存在，但缺少领域级元数据声明，无法做到低代码标准接入
- 当前 `deploy/shared/process_domain_mapping.yaml` 只表达 domain -> process，无法支撑 `user-plane / platform-control-plane / product-control-plane` 的任意部署组合
- 最终统一验收只能人工阅读大量领域产出，无法通过 metadata、gate 与门户聚合状态自动收口

本节点的目标，是冻结一套**领域统一接入验收矩阵**与其配套的 metadata / command / rule / gate / deploy 上位规格，使后续每个领域都能通过“补元数据 + codegen + 最小 glue code + 测试资产”的方式标准接入，而不是靠大量手写代码才能进入统一控制面体系。

## 目标用户

- 全局规范维护者：负责冻结统一控制面接入规则，并在同一会话中串行推进模板域与批量复制接入
- 各领域服务 owner：在统一实施会话中，按统一模板接入 `platform-ops` 与 `product-ops`
- 平台治理与发布责任人：通过统一 gate 与部署绑定，判断哪些领域达到可发布/可验收状态
- 门户与 codegen 维护者：消费统一的接入元数据，生成聚合状态、对象跳转与验收视图

## 核心目标

- 冻结 `domain_onboarding` 元数据 schema，作为每个领域接入统一控制面的唯一声明入口
- 冻结“领域最小接入包”，明确一个领域要被认定为“已接入统一控制面”至少需要哪些元数据、codegen 产物、测试层和门户能力
- 冻结 plane-aware deployment binding，支持 `domain-plane -> process` 的部署表达与门禁验证
- 冻结统一 gate 聚合口径，使各领域在同一接入会话中的状态可被统一统计、统一阻断、统一收口
- 冻结最终集中验收口径，使同一接入会话在所有领域接入完成后，可直接在本节点完成最终验收

## 功能范围

### R1：冻结 `domain_onboarding` 元数据真相源

统一接入矩阵必须首先落为 metadata，而不是文档表格。冻结以下真相源边界：

- 全局 schema：`quwoquan_service/contracts/metadata/_control_plane/domain_onboarding_schema.yaml`
- 分领域实例：`quwoquan_service/contracts/metadata/_control_plane/domains/<domain>.yaml`

该 schema 至少必须表达：

- `domain`
- `owner_service`
- `planes`
- `user_plane_object_types`
- `platform_control_plane_object_types`
- `product_control_plane_object_types`
- `required_metadata`
- `required_codegen_targets`
- `required_test_layers`
- `danger_actions`
- `approval_modes`
- `audit_events`
- `deployment_profiles`
- `portal_integration_targets`
- `acceptance_status`

约束：

- 每个领域独立维护自己的 `<domain>.yaml`，禁止集中维护一个巨大的人工表格
- 该元数据必须能被 `verify`、`codegen`、`gate` 与 `ops-portal` 聚合消费
- 控制面接入状态不得只存在于 spec/design 文档

### R2：冻结领域最小接入包

每个领域要被认定为“已接入统一控制面”，至少必须完成以下最小接入包：

1. 领域已有 `service.yaml`
2. 领域已有 `tests/e2e.yaml`
3. 领域已声明 `user-plane / platform-control-plane / product-control-plane`
4. 领域已声明最低对象集合与最低动作集合
5. 领域已声明危险动作、审批模式与审计事件
6. 领域至少有 1 条 `T3` API / contract 集成场景
7. 领域至少有 1 条 `T4` 真旅程或系统能力场景（实时/弱网/音视频等领域必须具备）
8. 领域已接入统一门户的搜索、对象跳转、审计或 dashboard 聚合入口

### R3：冻结全局节点与领域实施批次边界

本节点负责冻结统一接入规范，并为后续在**同一 `/dev` 会话**内完成“模板域先行、其余领域复制”的统一实施提供边界。

职责划分如下：

- 本节点负责：
  - `domain_onboarding` schema
  - 领域最小接入包
  - plane-aware deployment binding 口径
  - gate 聚合规则
  - 最终集中验收口径
- 同一实施会话负责：
  - 先选一个模板域完成首轮接入
  - 再按统一模板复制到其余领域
  - 在同一会话内补本领域 `<domain>.yaml`、最小 glue code、`T1~T4` 证据与 `acceptance.yaml`
- 全部领域接入完成后，仍由本节点统一做最终集中验收

### R4：冻结命令、规则与流程增强边界

本节点必须定义后续要增强的命令与规则边界，确保统一实施会话按“模板域先行、批量复制”推进，而不是每个领域重新解释接入方法。

要求冻结以下命令增强方向：

- `/explore`
  - 自动识别目标领域是否已有 `domain_onboarding` 声明
  - 自动识别三类面缺项、metadata 缺项、测试缺项、部署缺项
- `/prd`
  - 必须先冻结领域接入 schema、最小接入包、集中验收状态机
- `/design`
  - 必须细化 `domain_onboarding_schema.yaml` 字段、codegen 消费边界、gate 聚合实现、deploy binding 方案
- `/dev`
  - 必须按“领域 onboarding metadata → verify → codegen → 最小实现 → 测试 → 回填 acceptance”的顺序实施
- `/extend`
  - 必须提供“已有领域接入统一控制面矩阵”的增量场景，而不是让每次扩展都回到泛化的 API/测试补充场景
- `/verify`
  - 必须支持统一接入矩阵复核
- `/deploy`
  - 必须以领域 onboarding 完成度和 plane-aware binding 作为部署准入条件

### R5：冻结统一 gate 聚合口径

统一 gate 必须覆盖四层：

- `L0 / verify`
  - 校验 `domain_onboarding_schema.yaml` 与各领域 `<domain>.yaml` 完整性
- `L1 / gate`
  - 校验 codegen 消费完整性、缺失对象/动作/route/schema
- `L2 / gate`
  - 校验领域是否具备最低 `T1 / T2 / T3`
- `L3 / gate-full`
  - 聚合所有目标领域的接入状态，判断是否进入最终集中验收

约束：

- gate 不能只检查文件是否存在，还必须检查矩阵字段、测试层、门户接入、部署绑定和 acceptance 状态
- 同一实施会话中所有领域的接入状态必须可被自动聚合，不能依赖人工逐域对表

### R6：冻结 plane-aware deployment binding

当前 `deploy/shared/process_domain_mapping.yaml` 只表达 `domain -> process`，不能支撑三类面任意组合部署。必须冻结一套面向三类面的部署绑定模型。

推荐目标态：

- 新增或演进为 `domain-plane -> process` 的部署真相源
- 至少表达：
  - `environment`
  - `domain`
  - `plane`
  - `process`
  - `container_mode`
  - `supports_independent_scaling`
  - `co_locatable_with`
  - `split_trigger`

必须支持以下部署形态：

- `user-plane` 独立扩缩容
- `platform-control-plane` 与 `product-control-plane` 同 `seed-box` 共 Pod
- `platform-control-plane` 与 `product-control-plane` 独立 Deployment
- `integration` 与 `prod` 的 plane 绑定保持一致

### R7：冻结最终集中验收口径

最终集中验收仍由本节点完成，且不再是人工汇总，而是统一依据以下聚合结果：

- 目标领域是否都存在 `<domain>.yaml`
- 目标领域是否都满足最小接入包
- 目标领域是否都通过统一 codegen 与 gate
- 目标领域是否都具备 plane-aware binding
- 目标领域是否都能进入 `ops-portal` 聚合视图
- 目标领域 `acceptance_status` 是否达到 `final_acceptance_ready`

## 不做什么（Out Of Scope）

- 本次 PRD 不直接实现 `domain_onboarding_schema.yaml` 的字段级校验器、codegen 逻辑与脚本
- 本次 PRD 不直接改写所有命令、规则、gate 脚本与 deploy 脚本
- 本次 PRD 不直接让所有领域在本会话中完成接入
- 本次 PRD 不一次性迁移全部历史部署 mapping 文件
- 本次 PRD 不展开各领域自身业务对象字段级设计和工作流实现细节

## 对标输入与吸收结论

对标输入：

- `Backstage + Score / 服务目录治理思路`：服务接入声明、所有权、环境与依赖画像
- `Argo Rollouts / GitOps 配置治理思路`：灰度、回滚、阶段 gate 与环境准入
- `LaunchDarkly / Statsig`：策略/实验的 rollout、审批、审计与统一状态聚合
- `Trust & Safety Console`：跨领域 case/workflow/evidence/dual-approval 的统一收口

吸收结论：

- 借鉴点：统一声明式接入、按域分散维护、集中聚合展示、按阶段阻断
- 不借鉴点：不引入重型服务目录平台或微前端化多门户拆分
- 适用边界：适合当前“统一控制面 + 多领域并行接入 + 最终统一收口”的组织方式
- 成本约束：优先通过 metadata 驱动降低接入成本，不允许先靠大量手写 glue code 再回补规范

## 适用范围与约束

适用范围：

- 作为后续所有垂直领域接入 `platform-ops` 与 `product-ops` 的统一 PRD 基线
- 作为同一 `/dev` 会话内按模板域复制接入所有领域的共同输入
- 作为最终集中验收的统一口径

约束：

- 必须遵从 metadata-first、contracts-first、codegen-first、DDD 分层与 runtime 统一能力
- 不允许通过手写第二套 admin / ops API 来规避 `domain_onboarding` 接入声明
- 不允许把部署拓扑写死在领域契约中
- 不允许只补某一层测试就宣称“领域已接入统一控制面”
- 统一门户、统一 gate、统一 deploy 与统一 acceptance 必须共享同一接入状态真相源

## 非功能目标

- 统一接入扩展性：
  - 任一新领域接入统一控制面时，新增手写代码应以“最小 glue code”为目标，不应成为主要成本
  - 同一实施会话应支持“先完成一个模板域，再复制到所有领域”的高复用方式
- 一致性：
  - 最终集中验收不依赖人工对表，统一状态可由 gate 与门户聚合读取
- 可演进性：
  - 允许先用 `seed-box` 承载控制面，再演进到独立 Deployment / Pod，而不修改领域控制面契约
- 可观测性：
  - 统一 gate 聚合结果与最终验收状态必须可进入门户 dashboard / audit / workbench

## 四层验收视图

- `T1`
  - `domain_onboarding` schema、领域实例、三类面、对象类型、审批模式、审计事件、deployment profile 的静态完整性
- `T2`
  - 门户中领域接入状态可见、对象可跳转、风险动作可识别、接入缺项可读
- `T3`
  - 各领域真实控制面 contract、API contract、Go contract 与 staging 集成闭环
- `T4`
  - 高风险领域的真实旅程：恢复、推荐放量、弱网、音视频、通知、实时恢复等系统能力

## 验收标准概要

- A1：`domain_onboarding` 元数据 schema 与分领域实例真相源被冻结
- A2：领域最小接入包被明确冻结，并能作为统一实施会话中所有领域的完成定义
- A3：本节点与同一实施会话的职责边界被冻结，支持“先做模板域、后复制到所有领域、最后统一收口”
- A4：命令、规则、流程增强边界被冻结，后续可在 `/design` 细化
- A5：统一 gate 聚合口径被冻结，可形成自动阻断与自动聚合
- A6：plane-aware deployment binding 被冻结，可支撑三类面任意部署组合
- A7：最终集中验收口径被冻结，不依赖人工对表
- A8：该规范可作为同一实施会话中所有领域增量开发的标准接入模板，而不要求大量手写代码
