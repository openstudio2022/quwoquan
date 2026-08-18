# 诊断与恢复

诊断一个已存在的 `.qwq_output/data/tasks/<executionId>/` 工作包时：

1. 先读 `execution_manifest.json`、各阶段结果与 `evidence/`。**不猜测失败原因。**
2. 同 ID 只允许 resume——用创建它的**同一门面与相同参数**再跑 `--stage run`。
3. 输入目标变化或需要新尝试时递增 sequence 并声明 `retryOf`：

```bash
python3 quwoquan_data/scripts/cli.py task execute \
  --execution-id YYYYMMDD--travel-homepage-coverage--cn-region-a--pilot-002 \
  --retry-of YYYYMMDD--travel-homepage-coverage--cn-region-a--pilot-001 \
  --family content/travel/homepage/homepage \
  --region-ref china/test-region-a \
  --selector priority \
  --count 1 --stage run
```

- [MUST NOT] 创建 stage runner、手写阶段产物或并行状态根。
- [MUST NOT] 补写缺失的 source、rights、review 或 release 证据。
- 失败必须保留明确的阶段与原因，不得迁移、兼容或伪造通过。

就绪与隔离核验：

```bash
python3 quwoquan_data/scripts/cli.py verify execution-readiness --execution-id <executionId>
python3 quwoquan_data/scripts/cli.py verify output-root-isolation
```
