# product-ops 任务列表

## 当前交付任务
- [x] T1: [metadata] 冻结 `_control_plane/product/control_plane.yaml`、`workflow.yaml`、`audit_schema.yaml`、`config_schema.yaml` 首版样例基线
- [x] T2: [design] 冻结统一产品形态、信息架构、仪表盘、对象模型、workflow 与推荐运营 guardrail
- [ ] T3: [codegen] 扩展 `runtime-codegen`，生成 `product-control-plane` 的 Go DTO、handler scaffold、Python schema / client 与 workflow / audit 常量
- [ ] T4: [codegen] 补齐现有 `codegen_ops_portal_metadata`，生成更完整的 TS types、表单 schema、对象详情 schema、dashboard schema 与 API client
- [ ] T5: [测试] 为控制面 metadata 补齐 T1 contract tests 与 codegen snapshot tests
- [ ] T6: [业务逻辑] 以 `content` 作为首个治理接入域，打通举报 -> 审核 -> 处罚 -> 恢复链路
- [ ] T7: [业务逻辑] 以 `ops` / experiment 作为首个增长接入域，打通实验 -> 放量 -> guardrail -> 回滚链路
- [ ] T8: [业务逻辑] 实现 `Product Ops` 门户页面、工作台、总览大盘、对象详情、时间线与审批交互
- [ ] T9: [测试] 补齐治理、推荐运营、实验、审计、仪表盘与部署组合的统一验收证据

## 搁置任务（不在本次交付范围，但已识别，有重启条件）
- [ ] 拆分成两个独立门户产品（重启条件：组织职责与容量明确分化）
- [ ] 引入复杂组织树与多租户模型（重启条件：统一能力级 scope 无法承载权限治理）
- [ ] 将运营推荐参数开放到更宽泛的自定义脚本空间（重启条件：受限参数空间不足以满足场景，但仍能保留审计与回滚）

## 未来演进任务
- [ ] 细化各领域的 `product-control-plane` metadata 模板
- [ ] 将仪表盘 schema 正式纳入 metadata-first
- [ ] 将统一治理动作、推荐运营动作与审计动作接入 `make gate-full`
- [ ] 细化客服工作台、附件预览、检索与证据管理
