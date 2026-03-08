# 开发任务：product-control-plane-foundation

## 当前交付任务
- [x] P1 规格：冻结 `product-ops` 的统一产品范围与一级菜单
- [x] P2 规格：冻结两大模块边界：`治理处置` 与 `增长 / 实验 / 推荐运营`
- [x] P3 规格：冻结各领域 `product-control-plane` 的统一接口约束与元数据对象基线
- [x] P4 规格：冻结核心对象模型与工作流模型
- [x] P5 规格：冻结推荐运营模型，覆盖召回 / 粗排 / 精排 / 重排的受控干预
- [x] P6 规格：冻结账号恢复模型，明确客服、证据、SLA、双签要求
- [x] P7 规格：冻结端侧 IA / 布局 / 体验配置与 `ops.*` 的边界
- [x] P8 规格：冻结控制面部署原则，明确短期 `seed-box` 同 Pod、长期独立 Deployment / Pod
- [x] P9 规格：输出后续 `/design` 的方案比较与任务拆解入口

## 本次 `/design` 已完成
- [x] D1 设计：细化统一产品信息架构、模块边界与全局工作台视图
- [x] D2 设计：细化 `ModerationCase`、`RecoveryCase`、`Experiment`、`RecommendationPolicy` 等对象的接入分层与领域映射
- [x] D3 设计：细化 `control_plane.yaml`、`workflow.yaml`、`audit_schema.yaml`、`config_schema.yaml` 的最小 schema 与关键字段
- [x] D4 设计：细化治理处置、申诉、恢复、实验、推荐策略的状态机与危险动作模型
- [x] D5 设计：细化推荐运营在召回 / 粗排 / 精排 / 重排的参数空间、guardrail 与回滚约束
- [x] D6 设计：明确 codegen 分工、手写边界与 Web / Go / Python / App 生成目标
- [x] D7 设计：明确短期同 Pod、长期独立 Pod 的部署演进约束与领域接入矩阵

## 后续 `/dev` 输入任务
- [x] V1 metadata：为 `product-ops` 建立首版 `control_plane.yaml`、`workflow.yaml`、`audit_schema.yaml`、`config_schema.yaml` 样例
- [ ] V2 codegen：补齐控制面 metadata 到 Go / Python / App 的最小生成链路
- [ ] V3 portal 契约：补齐 Web 侧 TS schema、workflow enum、对象详情与表单 schema 生成设计
- [ ] V4 领域接入：选择 `content` 作为首个治理接入域，验证举报 -> 审核 -> 处罚 -> 恢复链路
- [ ] V5 领域接入：选择 `ops` / experiment 作为首个增长接入域，验证实验 -> 放量 -> 回滚链路
- [ ] V6 审计：将高风险治理动作与推荐策略动作接入统一审计 envelope
- [ ] V7 测试：补齐 T1 metadata 契约测试、T2 workflow 交互测试、T3 领域联调测试样例

## 未来演进任务
- [ ] E1 拆分各领域的 `product-control-plane` metadata 模板与 codegen 模板
- [ ] E2 细化审核 / 申诉 / 恢复的权限模型、角色模型与 SLA 模型
- [ ] E3 细化推荐运营与实验平台的联合审计与放量机制
- [ ] E4 细化端侧 IA config 与 app route / page / surface metadata 的对齐模型
- [ ] E5 将统一治理动作、推荐运营动作与审计动作接入 `make gate-full`

## `/design` 重点比较主题
- [x] S1 统一产品 vs 分拆产品
- [x] S2 手写控制面接口 vs 元数据驱动 codegen
- [x] S3 轻量实验平台 vs 全量推荐运营平台
- [x] S4 简单恢复动作 vs 正式 case/workflow + SLA + 双签

## 与相邻节点的边界

### 交给 `event-ingestion-and-analytics`
- 事件 schema、指标字典、维度标准、报表一致性

### 交给 `experiment-bucketing-and-rollout`
- 分桶引擎、实验放量、实验审计与回滚

### 交给 `feedback-optimization-loop`
- 反馈采集、评估、优化发布闭环

### 由本节点统一约束
- 产品边界
- 共同对象模型
- 工作流上位模型
- `product-control-plane` 接口原则
- 推荐运营与治理处置的共同约束
