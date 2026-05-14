---
name: /data-publish
id: data-publish
category: Workflow
description: 应用数据生成工作流 · 发布与反馈阶段
---

## 目标

完成：

- package 发布
- feedback 抽取与校验
- authenticity / package gate

## 真实实现

对应 CLI：

```bash
python3 quwoquan_data/tools/cli.py data publish --spec "<runtime/spec>" --topics "<topic_ids>"
```

## 内部原语

- `crawl publish-approved`
- `crawl feedback-extract`
- `crawl feedback-verify`
- `quwoquan_data/scripts/verify/verify_quwoquan_data_source_authenticity.py`
- `quwoquan_data/scripts/verify/verify_quwoquan_data_post_packages.py`

## 门禁

- authenticity 通过
- package 通过
- 若有反馈回写，必须产出 diff 提案
