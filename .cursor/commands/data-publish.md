---
name: /data-publish
id: data-publish
category: Workflow
description: 数据工程 · 发布真相源与发布包生成
---

# data-publish

## 命令目的

将当前 task/batch 产物组装为 data release，并保持 `quwoquan_data/publish/**`
作为唯一可提交发布真相源。

## 自然语言等价触发

用户说“发布这个数据批次”“把任务产物合入 publish”“生成 data release”时，按 `/data-publish` 语义执行。

## Spec Entry

- AppRoot Journey/Scenario：`runtime/system-architecture-and-engineering-guide`
- L1/L2/L3：按当前数据任务绑定。
- 验收意图：`SIT + contract`
- 测试证据：`local_contract + api_integration`

## Pre-work Reflection

- publish-first：发布真相源只写 `quwoquan_data/publish/**`。
- release output：发布包只写 `.qwq_output/release/data/**`。
- service import：只有显式 `--push-to-service` 时才触发服务导入。

## 当前实现

```bash
python3 quwoquan_data/scripts/cli.py data publish \
  --task "<task-id>" \
  --batch "<batch-id>" \
  --release-id "<release-id>"
```

可选服务导入：

```bash
python3 quwoquan_data/scripts/cli.py data publish \
  --task "<task-id>" \
  --batch "<batch-id>" \
  --release-id "<release-id>" \
  --push-to-service "http://localhost:18080"
```

## 输出

- `quwoquan_data/publish/**`
- `.qwq_output/release/data/<release-id>/**`

## 准出

- publish 引用 100% 可解析。
- release manifest 指向当前 task/batch。
- 如触发服务导入，必须补 importer 幂等性或 API integration 证据。

## Exit Review

- 说明 task、batch、releaseId、是否 push-to-service。
- 运行 `python3 quwoquan_data/scripts/cli.py verify output-root-isolation`。
- 未执行真实服务导入时如实说明，不冒充端到端完成。
