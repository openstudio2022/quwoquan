# 开发任务：config-and-reliability-governance

## 当前交付任务
- [x] PRD：承接 `platform-ops` 的产品范围，冻结配置中心、治理策略、发布灰度、环境与依赖四类平台能力边界
- [x] PRD：冻结 `sys.*` / `ops.*` 分层与高风险配置治理边界
- [x] PRD：冻结各领域 `platform-control-plane` 最低接入对象集合要求
- [x] Design：细化配置包、配置发布、治理策略、依赖画像与发布灰度的对象模型
- [x] Design：细化 `control_plane.yaml` 与 `config_schema.yaml` 的字段级 schema
- [x] Design：细化 `seed-box` 同 Pod 到独立 Deployment 的演进模型
- [x] Design：细化 Web / Go / Python codegen 的目标与命名规范
- [x] Design：细化配置灰度、回滚、审计、SLO、门禁与部署组合的验收链路

## 搁置任务（带规划）
- [ ] 后续实施：补齐领域接入矩阵的具体字段与动作清单
  - 搁置原因：当前阶段先冻结 PRD 与设计入口
  - 重启条件：进入 `/design`
  - 承接节点：本节点后续设计与实施

## 未来演进任务
- [ ] 将 plane 级部署拓扑纳入现有部署映射与门禁校验
- [ ] 将统一平台控制面验收接入 `make gate-full`
