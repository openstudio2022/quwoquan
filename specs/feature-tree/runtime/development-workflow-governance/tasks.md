# development-workflow-governance 任务列表

## 当前交付任务

- [x] T1: [规格] 更新 `specs/00_MASTER_DEVELOPMENT_FLOW.md`，把治理口径收敛为 `L1_capability / L2_feature / L3_story`，并把 deploy 中的测试表述统一改为 `T1~T4`。
- [x] T2: [特性树标准] 重写 `specs/feature-tree/00_FEATURE_TREE_STANDARD.md`，明确目录到 `L3_story`，`Task` 不再作为目录层，旧层级零兼容。
- [x] T3: [层级定义] 重写 `specs/feature-tree/01_FEATURE_TREE_LEVEL_DEFINITIONS.md`，删除 Legacy L5、兼容映射和四层描述，建立三层唯一权威定义。
- [x] T4: [测试规则] 重写 `.cursor/rules/03-testing.mdc` 的治理口径，使测试只使用 `T1~T4`，不再用 `L3/L4` 表示测试层。
- [x] T5: [命令] 逐一改写 `.cursor/commands/explore.md`、`prd.md`、`design.md`、`dev.md`、`verify.md`、`commit.md`、`deliver.md`、`deploy.md`，统一围绕 `L3_story` 交付和 `Task` 执行。
- [x] T6: [脚手架] 重写 `scripts/new_feature_fullstack.sh`，改为直接生成 `specs/feature-tree/<L1>/<L2_feature>/<L3_story>/` 的三层目录结构。
- [x] T7: [索引/门禁] 重写 `quwoquan_service/runtime/agentpack/tree_index.go`、`quwoquan_service/tools/gen_tree_index/main.go`、`scripts/verify_feature_traceability.sh`、`scripts/verify_feature_tree_refactor.sh`，使其只接受三层模型并对旧层级直接失败。
- [x] T8: [存量迁移] 重建 `specs/feature-tree/tree_index.yaml`、重构 `specs/feature-tree/runtime/tree.yaml`，并批量迁移 `specs/feature-tree/` 下的旧层级节点与 `acceptance.yaml`。
- [x] T9: [测试] 为三层索引、门禁和迁移增加最小失败测试或校验样例，确保旧层级残留会被稳定拦截。
- [x] T10: [验证] 执行 tree index 重建、旧层级残留扫描、代表性样例节点抽样验证，并形成切换窗口与回滚检查清单。

## 搁置任务（带规划）

- [ ] P1: 将 `Task` 从 Markdown 清单升级为结构化 `tasks.yaml`（重启条件：三层模型稳定并完成首轮全量迁移后）。
- [ ] P2: 为 `/explore`、`/prd`、`/design` 提供结构化输入表单或模板片段（重启条件：命令文案三层化稳定后）。
- [ ] P3: 清理 `changes/` 目录及其相关文档的历史用途，明确仅保留归档价值还是彻底退出主流程（重启条件：新脚手架和 gate 已稳定运行）。

## 未来演进任务

- [ ] F1: 为 `acceptance.yaml` 增加更强的 `L2_feature` / `L3_story` / `Task` 结构校验。
- [ ] F2: 增加仓库级树迁移审计脚本，持续防止旧层级回流。
- [ ] F3: 提供一个完整三层样例节点，作为后续新增治理特性的模板。
- [ ] F4: 逐步清理 `specs/feature-tree/` 下与三层模型不一致的历史辅助文档。
