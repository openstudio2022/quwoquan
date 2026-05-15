---
name: /data-produce
id: data-produce
category: Workflow
description: 数据工程 · 内容润色生成阶段
---

# data-produce

## 命令目的
基于下载源润色生成可发布内容。单命令完成 compose + review。

## 输入
- `--task {taskId}` `--batch {batchId}` `--type {article|image|moment|video}`
- sources/{entityName}/（来自 download）
- entities/{领域}/{类型}/{名称}/（来自 build，作为全局上下文）
- sop/{type}.md + sop/主页/{领域}/{类型}/（内容策略）

## 目录结构

posts 按内容角度标签分类，标题命名目录，编号子目录：
```
posts/article/内容角度/攻略/峨眉山攻略指南/1/
  article.md
  manifest.json
  assets/
```

## 内容角度与实体类型对应

| 实体类型 | 建议内容角度 |
|---|---|
| 景区/遗址/古镇 | 攻略/体验/文化 |
| 打卡地 | 攻略/日记 |
| 博物馆 | 文化/体验 |
| 美食街/餐厅 | 探店/攻略 |
| 学校 | 攻略/体验 |
| 赛事 | 体验/攻略 |

## agent 执行

### compose
1. 基于 sop 模板 + 高质量源润色生成 article.md
2. 含 asset:// 图片引用（fullWidth / wrapLeft / wrapRight）
3. 含 /entity/{领域}/{类型}/{名称} 引用（三层路径）
4. 含 /tag/{tagPath} 引用

### review
交叉校验内容质量和引用一致性。

## manifest.json（无 topicId）
```json
{
  "contentType": "article",
  "title": "峨眉山攻略指南",
  "entityRefs": ["地点/景区/峨眉山"],
  "tagRefs": ["主题/佛教文化", "内容角度/攻略"],
  "sourcePaths": ["sources/峨眉山/content/source_01.md"],
  "assets": ["峨眉山_攻略_cover.jpg"],
  "createdAt": "...",
  "updatedAt": "..."
}
```

## 准出
- 每篇 > 600 字
- 含 asset:// + /entity/ + /tag/
- entityRefs 格式 `{领域}/{类型}/{名称}`（三层）
- manifest 无 topicId
