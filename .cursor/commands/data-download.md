---
name: /data-download
id: data-download
category: Workflow
description: 数据工程 · 多平台来源采集阶段
---

# data-download

## 命令目的
多平台分层源采集：权威源给实体主页补充，内容源给 post。

## 输入
- `--task {taskId}` `--batch {batchId}` `--type {article|image|moment|video}`
- entities/{领域}/{类型}/{名称}/（来自 build）
- sop/{type}.md（检索策略）

## 来源平台

| 类型 | 权威源 | 内容源 |
|---|---|---|
| 实体定义 | wiki、百度百科、搜狗百科 | — |
| 文章 | — | 马蜂窝、小红书、穷游、携程、知乎、今日头条、微博、去哪儿 |
| 图片 | — | 小红书、马蜂窝、视觉中国 |
| 视频 | — | 抖音、B站、小红书 |

## 三段式

### prepare
为每个实体生成 `inputs/search_plan/{entityName}.json`。

### agent（模型执行）
按 SOP 检索策略生成检索词，从权威源和内容源下载，即时打分，>= 6 分存储。
- 权威源 -> `sources/{entityName}/authority/`
- 内容源 -> `sources/{entityName}/content/`
- 每实体目标 40+ 来源 URL

### validate
每实体有 authority/ + content/，数量达标。
