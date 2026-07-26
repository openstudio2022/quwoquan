---
name: /crawl-topic
id: crawl-topic
category: Workflow
description: quwoquan_data 单 execution 局部诊断与恢复入口
---

## 目标

诊断一个 `.qwq_output/data/tasks/<executionId>/` 工作包，并通过原始
`task execute` 命令 resume。禁止创建 stage runner、退役的双层运行身份、手写阶段产物
或并行状态根。

## 自然语言等价触发

用户说“复核这个 execution”“恢复这个内容任务”“重试这个实体任务”时，均按本命令语义执行。

## Spec Entry

- L1/L2/L3：沿用 execution manifest 绑定的特性树节点。
- 验收意图：`contract + SIT`，涉及环境消费时追加 `UAT`。
- 测试证据：`local_contract + api_integration`，涉及 App 时追加 `user_acceptance`。

## Pre-work Reflection

- 先读 `execution_manifest.json`、阶段结果和 `evidence/`，不猜测失败原因。
- 同 ID 只允许 resume；输入目标变化或需要新尝试时必须递增 sequence 并声明 `retryOf`。
- 不补写缺失 source、rights、review 或 release 证据。

## 恢复

使用创建该 execution 的同一门面与相同参数再次执行 `--stage run`。新尝试示例：

```bash
python3 quwoquan_data/scripts/cli.py task execute \
  --execution-id YYYYMMDD--travel-homepage-coverage--cn-region-a--pilot-002 \
  --retry-of YYYYMMDD--travel-homepage-coverage--cn-region-a--pilot-001 \
  --family content/travel/homepage/homepage \
  --region-ref china/test-region-a \
  --selector priority \
  --count 1 \
  --stage run
```

## Exit Review

```bash
python3 quwoquan_data/scripts/cli.py verify execution-readiness --execution-id <executionId>
python3 quwoquan_data/scripts/cli.py verify content-execution-layout
python3 quwoquan_data/scripts/cli.py verify output-root-isolation
```

输出只允许进入该 execution 工作包、对应 data release 或环境 run；失败必须保留
明确阶段与原因，不得迁移、兼容或伪造通过。
