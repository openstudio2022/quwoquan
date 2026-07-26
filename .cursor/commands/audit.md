---
name: /audit
id: audit
category: Quality
description: 以正式规格、metadata 和可执行 gate 审计仓库级一致性
---

# /audit

目标：在不复制 gate 实现的前提下，审计特性树、metadata/codegen、App、Service、Data 与 Ops 的当前一致性。

## Spec Entry

- 读取根 `AGENTS.md`、`specs/feature-tree/README.md` 和审计目标的最小父链。
- 明确审计范围对应的 AppRoot Journey、L1/L2/L3、UAT/DOM/SIT/GWT 与三层测试。
- 运行 `make feature-context TARGET=<target>`；无法定位唯一 owner 时先返回 `GATE_BLOCK`。

## 执行

按影响面调用仓库现有门面，不在命令文档内重写扫描脚本：

```bash
make verify-feature-tree
python3 quwoquan_ops/gate/verify_single_track_contracts.py
python3 quwoquan_ops/gate/verify_service_architecture.py
python3 quwoquan_ops/cli/repo_hygiene_audit.py --hash-mode none
```

- App：按改动范围执行 `flutter analyze`、对应 `local_contract` 和必要 `user_acceptance`。
- Service/metadata：执行相关 codegen check、对象级 `local_contract` 与真实 `api_integration`。
- Data：统一经 `python3 quwoquan_data/scripts/cli.py verify all`；需要环境时追加 release/import 证据。
- Ops/环境：统一经 `stackctl verify/health/inspect`，不得用静态配置存在性代替运行证据。
- 全栈变更追加 `make feature-tree-change-report`，未归属变更直接阻断。

## 输出

- 按产品、架构、代码、测试、用户、运维、运营视角列出 finding、文件/锚点和严重级别。
- 明确区分代码缺陷、规格漂移、环境/凭证阻断、并发 WIP 与派生产物漂移。
- 只引用 gate 和测试的真实结果；不创建审计台账、成熟度矩阵、changelog 或归档报告。
- 需要长期跟踪的未完成事项写入最低 owner 节点 `OPEN`；已解决事项直接成为当前规格或删除。

自然语言等价触发：“全仓审计”“检查端云一致性”“代码库健康检查”。
