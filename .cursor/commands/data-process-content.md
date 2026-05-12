---
name: /data-process-content
id: data-process-content
category: Workflow
description: 应用数据生成工作流 · 图文加工阶段
---

## 目标

对已下载来源完成：

- `content-review`
- 图文加工
- 生成前复核

## 真实实现

对应 CLI：

```bash
python3 quwoquan_data/tools/cli.py data process-content --spec "<runtime/spec>" --topics "<topic_ids>" --targets "alpha,gamma"
```

兼容别名：

```bash
python3 quwoquan_data/tools/cli.py data build-content ...
```

## 内部原语

- `crawl content-review`
- `crawl compose-post`
- `crawl review-generated`

## 门禁

- review schema 正确
- 图文标题 / 正文锚点命中实体 canonical 或 `label_zh`
- 不得引入第二套未回写的展示名
