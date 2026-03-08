# platform-ops 任务列表

## 当前交付任务
- [x] T1: [metadata] 创建共享控制面元数据骨架：`portal_shell.yaml`、`portal_menu.yaml`、`control_plane.yaml`、`config_schema.yaml`、`workflow.yaml`、`audit_schema.yaml`
- [ ] T2: [codegen] 扩展 `runtime-codegen`，明确 Go / Python 控制面 schema 与 client/scaffold 生成
- [x] T3: [codegen] 扩展或新增门户 metadata codegen，生成 TS 菜单、对象 schema、dashboard schema 与 client
- [x] T4: [测试] 为控制面元数据补齐 T1 contract tests 与 codegen 输出测试骨架
- [ ] T5: [业务逻辑] 实现 `platform-ops` 的对象模型与在线控制 API
- [ ] T6: [业务逻辑] 实现后台 worker：依赖探测、灰度阶段检查、预算计算、审计归集
- [x] T7: [业务逻辑] 实现门户页面：服务目录、配置中心、治理策略、发布灰度、环境与依赖、可观测与 SLO、Runbook、CI/CD 门禁
- [ ] T8: [测试] 打通配置灰度、回滚、审计、SLO、部署组合与仪表盘验证链路

## 搁置任务（不在本次交付范围，但已识别，有重启条件）
- [ ] 引入微前端（重启条件：门户模块规模失控、单应用编译与发布成为瓶颈）
- [ ] 将 `platform-control-plane` 拆成多个独立平台服务（重启条件：模块化单体 + worker 无法满足容量或组织边界）
- [ ] 全量实时动态配置（重启条件：低风险热配置需求显著增长，且已有稳定审计/回滚保障）

## 未来演进任务
- [ ] 将 `domain-plane -> process` 正式纳入部署映射与门禁
- [ ] 将 Dashboard schema 全量纳入 metadata-first
- [ ] 将统一平台控制面验收接入 `make gate-full`
- [ ] 将 `seed-box` 过渡期策略升级为独立 `platform-control-plane` Deployment
