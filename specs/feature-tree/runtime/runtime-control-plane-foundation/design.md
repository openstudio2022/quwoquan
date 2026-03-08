# Design：runtime-control-plane-foundation

## 设计动因

当前仓库已经分别存在 `platform-ops-governance` 与 `product-ops-growth` 两条横切能力线，但缺少一个共同上位规格来统一以下问题：
- 统一 Web 门户 `ops-portal` 的壳层与菜单
- 各领域三类面的共同契约基线
- 控制面元数据对象的统一定义
- codegen 的统一输出目标
- 短期同 Pod / 长期独立 Pod 的部署演进约束

如果没有共同上位规格，后续很容易出现：
- `platform-ops` 与 `product-ops` 分别定义两套门户壳层与菜单模型
- 各领域控制面接口各自手写、各自命名
- 三类面在逻辑上混合，后续拆分 Deployment 返工
- App / Go / Python / Web 各自维护第二份控制面契约

## 上游评审结论

当前 `spec.md` 与本节点 `acceptance.yaml` 已足以支撑设计基线冻结，满足 `/prd` 阶段进入条件。后续 `/design` 阶段需重点补齐：
- 元数据字段详细 schema
- codegen 模板落点与命名约定
- 门户前端模块拆分与工程组织
- plane 级部署映射模型

## 方案对比

### 方案 A：两个独立门户，分别服务 Platform/Product

优点：
- 各自边界清晰
- 前端实现可独立节奏推进

缺点：
- 门户壳层、权限、审计、搜索、通知、环境切换重复建设
- 用户心智割裂
- 两条控制面更容易演化出两套元数据和两套交互规范

结论：
- 不选。适合组织规模更大、角色更明确的团队，不适合当前全栈共担模式。

### 方案 B：统一门户壳层，后端按域分离

优点：
- 登录、权限、审计、搜索、通知、环境切换统一
- 便于建立共同的控制面元数据和 codegen 体系
- 更符合“一个团队维护、多域协作”的现状
- 后端仍能按 `platform-ops` / `product-ops` 保持清晰边界

缺点：
- 门户壳层需要更强的菜单、权限、环境上下文治理
- 需要提前设计跨域导航与审计口径

结论：
- 选择此方案。

## 关键决策

### 1. 门户形态
- 统一门户命名为 `ops-portal`
- 门户前端技术栈冻结为 `React + TypeScript`
- 初期采用单前端应用 + 域模块化，不提前引入微前端

### 2. 三类面架构
- 每个领域必须具备三类面：
  - `user-plane`
  - `platform-control-plane`
  - `product-control-plane`
- 三类面在契约层独立
- 控制面动作不得混入面向 App 的用户接口

### 3. 部署组合原则
- 逻辑服务边界独立
- 部署形态可任意组合
- 短期允许 `seed-box` 容器与领域处置服务同 Pod
- 长期必须支持独立 Deployment / Pod
- 契约设计不得依赖当前同 Pod 组合

### 4. 控制面元数据对象
本节点冻结以下元数据对象作为共同基线：
- `portal_shell.yaml`
- `portal_menu.yaml`
- `control_plane.yaml`
- `config_schema.yaml`
- `workflow.yaml`
- `audit_schema.yaml`

### 5. codegen 目标
codegen 必须统一生成：
- Web：TS types、API client、菜单 schema、表单 schema、表格列 schema、workflow 枚举
- Go：handler scaffold、DTO、config schema struct、workflow 状态机骨架、审计 envelope
- Python：Pydantic model、API client、策略与事件 schema
- App：IA config DTO、route/surface/page metadata、feature flag / ops config DTO

### 6. 配置分层
- `platform-ops` 管理 `sys.*`
- `product-ops` 管理 `ops.*`
- IaC / K8s / HPA / 证书 / 组网 / 连接串不进入业务配置中心

### 7. 端侧可配置范围
允许进入 `ops.*` 的范围：
- 一级 tab、二级 tab、栏目顺序
- 页面布局、版式、卡片样式
- 体验类 feature flag
- 面向用户/人群/实验的 IA 配置

必须留在 `sys.*` 的范围：
- long-polling 周期
- 超时、限流、采样率
- worker 并发、批处理大小
- 熔断、降级、回退参数

## 与现有系统/契约的对应

已存在基础：
- `contracts/configuration.md`：`sys.*` / `ops.*` 分层
- `contracts/service_governance.md`：系统治理基线
- `contracts/metadata/*/ui_config.yaml`：端侧 IA 可配置雏形
- `runtime-codegen` / `codegen_app_metadata`：已有 metadata → Go / Dart 的基础生成能力
- `platform-ops-governance` 与 `product-ops-growth`：两条领域线已存在

本节点的作用：
- 不是替代上述节点
- 而是给它们提供统一的共同上位约束与交付基线

## 适用场景与约束

适用场景：
- 多领域、多控制面、全栈共担的单仓体系
- 需要短期快速落地、长期可拆分演进的控制面架构
- 需要 metadata-first 与 codegen-first 的控制面交付模式

约束与局限：
- 当前阶段只冻结共同上位规格，不展开到每个控制面对象的字段级设计
- 门户前端虽然冻结为 React + TypeScript，但具体组件库与目录结构留到 `/design`
- plane 级部署映射需要后续扩展现有 `process_domain_mapping` 表达能力

## 未来演进

目标态：
- 统一门户壳层稳定
- 控制面元数据对象成为一级真相源
- plane 级部署映射可验证
- Web / Go / Python / App 四端契约自动同步

未来演进方向：
- 从当前 `domain -> process` 扩展到 `domain-plane -> process`
- 从单前端域模块化演进到可插拔模块体系
- 从 IA config 扩展到完整的 app shell / route / surface metadata single source
- 将统一集成验收接入 `make gate-full`
