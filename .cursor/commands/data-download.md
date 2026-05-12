---
name: /data-download
id: data-download
category: Workflow
description: 应用数据生成工作流 · 下载与来源发现阶段
---

## 目标

生成并落盘：

- `instruction_profile.json`
- `runtime/specs/*.yaml`
- `authority_pool.ndjson`
- `source_pool.ndjson`
- `pages/**/source.md`

## 真实实现

对应 CLI：

```bash
python3 quwoquan_data/tools/cli.py data download --spec "<runtime/spec>" [--seed <content-seed>] [--fetch-seed <real fetch seed>] [--skip-pool-bootstrap] [--skip-content-discover]
```

## 内部原语

- `crawl authority-sync`
- `crawl authority-review`
- `crawl pool-bootstrap`
- `crawl spec-discovery`
- `crawl fetch-source`
- `crawl content-discover`
- `crawl content-hydrate`

## 门禁

- `validate_crawl_spec`
- hydrate 失败率低于阈值
- 标题 / URL / snippet 与实体锚点同源
