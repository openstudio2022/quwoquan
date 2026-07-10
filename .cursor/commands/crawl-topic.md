---
name: /crawl-topic
id: crawl-topic
category: Workflow
description: quwoquan_data 单任务/单批次局部复核入口
---

## 目标

`/crawl-topic` 仅用于把一个对象、一个任务或一个批次的缺口带回当前
`qwq-data task` 编排链。它不是第二套 worker，也不直接写旧
`quwoquan_data/runtime/**`。

## 自然语言等价触发

当用户说“处理这个 topic”“复核这个对象”“重跑这个批次的某阶段”等价于 `/crawl-topic`。

## Spec Entry

- AppRoot Journey/Scenario：`runtime/system-architecture-and-engineering-guide`
- L1/L2/L3：按当前数据任务或目录治理 Story 绑定。
- 验收意图：`SIT + contract`
- 测试证据：`local_contract + api_integration`

## Pre-work Reflection

- metadata-first：对象字段、错误码、服务路径来自 `quwoquan_service/contracts/metadata/**`。
- data CLI-first：只通过 `python3 quwoquan_data/scripts/cli.py task ...` 回到主编排链。
- mock 隔离：不得用 fixture 或手写 JSON 冒充真实批次证据。
- output-first：运行态只能写 `.qwq_output/**`。

## 当前入口

查看任务与批次：

```bash
python3 quwoquan_data/scripts/cli.py task show <task-id>
python3 quwoquan_data/scripts/cli.py task status <task-id> --batch <batch-id>
python3 quwoquan_data/scripts/cli.py task trace <task-id> --batch <batch-id>
```

重跑可恢复阶段：

```bash
python3 quwoquan_data/scripts/cli.py task retry-stage \
  --task <task-id> \
  --batch <batch-id> \
  --stage <stage>
```

补齐对象选择或批次审计：

```bash
python3 quwoquan_data/scripts/cli.py task select-targets --help
python3 quwoquan_data/scripts/cli.py task audit-batch --help
```

## 输出边界

- 运行态只允许在 `.qwq_output/local/data-runtime/**`。
- 发布真相源只允许在 `quwoquan_data/publish/**`。
- 摘要和报告只允许在 `.qwq_output/runs/data/**`。
- 禁止回写 `artifacts/**`、`.qwq_sandbox/**` 或顶层 `runtime/**`。

## Exit Review

- 规格达成：缺口已通过 `trace/status/audit-batch` 回指到当前任务和批次。
- 测试证据：至少完成 `verify output-root-isolation`，必要时补 `task lint`。
- 剩余风险：真实下载、创作、ship/import 未执行时必须如实列明。

## 输出

输出只允许是 `.qwq_output/**` 报告、当前任务状态摘要和必要的人工复核列表。
