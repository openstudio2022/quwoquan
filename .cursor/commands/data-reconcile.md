---
name: /data-reconcile
id: data-reconcile
category: Workflow
description: 数据工程 · 引用一致性校验阶段
---

# data-reconcile

## 命令目的
从已生成 post 中反向抽取实体和标签引用，与 entities/tags 做一致性校验。

## 输入
- `--task {taskId}` `--batch {batchId}`
- posts/（来自 produce）
- entities/{领域}/{类型}/{名称}/（来自 build）
- tags/（来自 build）

## 三段式

### prepare
遍历 posts/，为每篇生成 `inputs/reverse_extract/{ref}.json`。

### agent（模型执行）
读取 article.md，提取 /entity/ 和 /tag/ 引用：
- `/entity/{领域}/{类型}/{名称}` -> 检查 `entities/{领域}/{类型}/{名称}/` 存在
- `/tag/{path}` -> 检查 `tags/{path}/_definition.json` 存在
- 检查 entityRefs 三层格式一致性
- 反向提取新的实体和标签候选

### validate
allRefsResolved: true，missingEntities: []，missingTags: []。
