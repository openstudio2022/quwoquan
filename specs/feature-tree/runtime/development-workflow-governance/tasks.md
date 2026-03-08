# development-workflow-governance 任务列表

## 当前交付任务

- [x] D1: [规格/流程] 更新 `specs/00_MASTER_DEVELOPMENT_FLOW.md`，统一 explore/prd/design/dev 的职责、Gate 与四层测试视图。
- [x] D2: [特性树] 更新 `specs/feature-tree/00_FEATURE_TREE_STANDARD.md`，明确四件套中的 Story、对标输入机制、四层测试映射与 L1 架构交付要求。
- [x] D3: [特性树] 更新 `specs/feature-tree/01_FEATURE_TREE_LEVEL_DEFINITIONS.md`，将治理视图收敛为“关键能力 / 功能特性 / 子功能或组件 / Story”，并定义历史 L5 兼容策略。
- [x] D4: [规则] 更新 `.cursor/rules/03-testing.mdc`，补充 `T1~T4` 与现有执行桶 `L1a/L1b/L1c/L2/L3/L4` 的映射关系，并要求验收项与测试层绑定。
- [x] D5: [命令] 更新 `.cursor/commands/explore.md`，加入批判性澄清、对标输入机制、EXPLORE_READY/GATE_BLOCK 输出要求。
- [x] D6: [命令] 更新 `.cursor/commands/prd.md`，加入上游澄清质量评审、Story 化建模、四层测试验收基线与对标输入沉淀要求。
- [x] D7: [命令] 更新 `.cursor/commands/design.md`，加入上游规格评审、对标方案吸收、两方案对比、可测试性评审、Story 与测试层映射要求。
- [x] D8: [命令] 更新 `.cursor/commands/dev.md`，将“按 task 实施”升级为“按 Story 交付”，保留 tasks.md 作为实施清单。
- [x] D9: [命令] 更新 `.cursor/commands/try.md`，把对标输入、验证目标、成功标准、`/land` 吸收路径纳入统一治理模型。
- [x] D10: [命令] 更新 `.cursor/commands/land.md`、`.cursor/commands/archive.md`、`.cursor/commands/commit.md`，补齐原型落地、归档、提交流程与 Story / `T1~T4` 视图的一致性。
- [x] D11: [命令] 更新 `.cursor/commands/verify.md` 与 `.cursor/commands/deliver.md`，使验收、漂移检查、归档和交付流程统一基于 Story 与 `T1~T4` 视图。
- [x] D12: [特性树] 更新 `runtime/tree.yaml`、`tree_index.yaml` 与本节点四件套，确保新治理节点完整挂载。

## 搁置任务（带规划）

- [ ] P1: 用一个真实样例特性验证“对标输入 → explore/try → 规格 → 设计 → Story → 四层测试”的贯通性，并沉淀为后续演练基线（重启条件：本轮文档口径统一稳定后，选择 1 个真实业务特性试点）。
- [ ] P2: 将 `L4_story`、`T1~T4` 和 Story 覆盖规则真正落入 gate 脚本（重启条件：完成 1 个真实样例试点后）。
- [ ] P3: 全量迁移历史 `L5_leaf / L5_cross_cutting` 节点到新治理视图（重启条件：兼容映射脚本稳定后，由 runtime 治理专项承接）。
- [ ] P4: 为 `/explore`、`/prd`、`/design` 增加结构化表单或模板片段采集“标杆产品 / 原型 / 公开代码 / 公开文档”输入（重启条件：命令文案更新稳定后）。

## 未来演进任务

- [ ] F1: 在 `acceptance.yaml` 中引入更强的 Story ID、Trace、`test_layers` 结构校验。
- [ ] F2: 提供一个仓库级“样例特性模板”，让新特性可直接从四件套脚手架启动。
- [ ] F3: 将 explore/prd/design 的对标输入分析结果沉淀到可复用的最佳实践目录或知识库。
- [ ] F4: 逐步清理 `specs/feature-tree/` 下四件套之外的历史文档残留，减少口径分叉。
