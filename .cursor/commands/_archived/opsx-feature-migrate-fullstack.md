---
name: /opsx-feature-migrate-fullstack
id: opsx-feature-migrate-fullstack
category: Workflow
description: 按 OpsX 规格驱动执行特性迁移/新建并串联端云自动化测试
---

在仓库根目录执行（推荐先走树驱动命令）：

- `/opsx-ff-tree`
- `/opsx-apply-tree`
- `/opsx-archive-tree`

若需要兼容旧流程，再按以下步骤执行：

0) 复用优先（禁止重复造流程）
- 优先复用已有 OpsX 命令：
  - `/opsx-ff`：创建/补齐 OpenSpec 变更与 artifacts
  - `/opsx-apply`：按任务实现
  - `/opsx-verify`：按变更校验完整性与一致性
- 优先复用根脚本：
  - `scripts/new_feature_fullstack.sh`
  - `scripts/verify_feature_traceability.sh`
  - `scripts/verify_contract_metadata.sh`
  - `scripts/verify_acceptance_standard.sh`
  - `scripts/gate_repo.sh`

1) 初始化特性目录
```bash
bash scripts/new_feature_fullstack.sh "<slug>"
```

2) 先绑定特性树节点（必填）
- 在 `changes/feature_tree.yaml` 选择目标 `feature_path`
- 通过 `parent_path` 指向父节点（目录层级，不靠 parent_id 语义）
- 规范：`specs/feature_tree_and_acceptance_standard.md`
- 同步更新 `specs/l1_index.yaml` 与对应 `specs/l1-*` 目录 README/子特性文档

3) 更新特性台账（兼容索引）
- `changes/feature_catalog.yaml` 中补齐：
  - `level`、`parent_id`（按特性树规则）
  - `opsx_change_id`
  - `opsx_specs`
  - `delivery_profile`（ddd/metadata_driven/contract_driven 全 true）

4) 完成特性映射（必填）
- `changes/<date>-<slug>/traceability.yaml` 补齐：
  - `opsx`
  - `test_automation`（mock/contract/integration/uat）
- `changes/<date>-<slug>/acceptance.yaml` 补齐 A1~A8 统一验收模板
 - `acceptance.yaml` 额外补齐分层信息：
   - `tree_context.feature_level/feature_path/parent_path/acceptance_inherits_from`
   - `level_acceptance.focus_groups`

5) 端云实现顺序
- 先 contracts + metadata
- 再端云 mock
- 再契约测试
- 再集成测试与 UAT 自动化

6) 校验与门禁
```bash
make verify
make gate
make gate-full
```

