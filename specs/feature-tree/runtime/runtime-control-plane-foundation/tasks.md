# 开发任务：runtime-control-plane-foundation

## 当前交付任务
- [ ] P1 规格：冻结统一门户 `ops-portal` 的产品边界、一级/二级菜单、全局导航、权限、审计、通知、环境切换与搜索入口
- [ ] P2 规格：冻结三类面架构：`user-plane`、`platform-control-plane`、`product-control-plane`
- [ ] P3 规格：冻结控制面部署原则，明确短期 `seed-box` 同 Pod、长期独立 Deployment / Pod 与独立扩缩容
- [ ] P4 规格：冻结控制面元数据对象：`portal_shell.yaml`、`portal_menu.yaml`、`control_plane.yaml`、`config_schema.yaml`、`workflow.yaml`、`audit_schema.yaml`
- [ ] P5 规格：冻结 codegen 目标，明确 Web / Go / Python / App 的生成责任
- [ ] P6 规格：冻结配置分层边界，明确 `sys.*` / `ops.*` / IaC 的职责划分
- [ ] P7 规格：冻结端侧可配置边界，明确 IA / 布局 / 体验 flag 与运行时参数的归属差异
- [ ] P8 规格：输出统一集成验收口径，定义后续 `platform-ops` 与 `product-ops` 完成后的收口检查项

## 搁置任务（带规划）
- [ ] D1 延后到 `/design`：细化 `portal_shell.yaml` 与 `portal_menu.yaml` 的字段级 schema
  - 搁置原因：当前阶段先冻结产品与边界，不进入字段级设计
  - 重启条件：进入统一门户 `/design`
  - 承接节点：本节点后续 `/design`
- [ ] D2 延后到 `/design`：细化 `control_plane.yaml` 与 `config_schema.yaml` 的 codegen 模板与命名约定
  - 搁置原因：需与 `runtime-codegen`、`codegen_app_metadata` 的现状一起设计
  - 重启条件：进入控制面元数据 `/design`
  - 承接节点：本节点后续 `/design`
- [ ] D3 延后到 `/design`：定义 `process_domain_mapping` 向 `domain-plane -> process` 的演进模型
  - 搁置原因：涉及现有部署契约与验证脚本
  - 重启条件：进入部署与门禁设计
  - 承接节点：本节点后续 `/design`

## 未来演进任务
- [ ] E1 细化统一门户壳层的 RBAC、通知中心、全局搜索与环境上下文设计
- [ ] E2 细化 plane 级部署拓扑、HPA、资源画像与拆分触发条件
- [ ] E3 细化控制面元数据到 Web / Go / Python / App 的 codegen 模板
- [ ] E4 细化端侧 IA config 与 app route / surface / page metadata 的单一真相源模型
- [ ] E5 将统一集成验收链路纳入 `make gate-full`

## 与子会话的边界

### 交给 `platform-ops` 子会话
- `Platform Ops` 详细产品规格
- `sys.*` 配置模型
- 配置包、灰度、回滚、SLO、告警、CI/CD 门禁
- 面向 `platform-control-plane` 的详细对象与流程

### 交给 `product-ops` 子会话
- `Product Ops` 详细产品规格
- `ops.*` 业务策略模型
- 审核、处罚、申诉、恢复工作流
- 推荐运营与实验运营的详细对象与流程

### 回到本会话统一收口
- 门户壳层是否与两个子系统规格一致
- 元数据对象是否被双方共同消费
- codegen 目标是否统一
- 三类面是否在全部领域具备一致约束
- 部署组合与集成验收口径是否闭环
