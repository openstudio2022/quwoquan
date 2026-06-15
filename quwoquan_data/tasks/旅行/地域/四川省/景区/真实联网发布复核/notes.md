# 真实联网发布复核（放大规模）

- 批次：`scaled_e2e_20260610`
- 规模：10 景区实体 × 20 攻略文章 × 20 画报
- 运行（现主线）：
  - `python3 quwoquan_data/scripts/cli.py task scaled-e2e prepare --task <taskId> --batch <batchId> --plan <planId>`
  - `python3 quwoquan_data/scripts/cli.py task scaled-e2e fanout-author --plan <planId> --concurrency <n>`
  - `python3 quwoquan_data/scripts/cli.py task scaled-e2e rollup --plan <planId>`
  - `python3 quwoquan_data/scripts/cli.py task scaled-e2e verify --task <taskId> --batch <batchId>`
- 清场后全新联网跑通 download → build → content_plan → produce → publish → 证据链门
