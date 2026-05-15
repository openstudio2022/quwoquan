---
name: /data-publish
id: data-publish
category: Workflow
description: 数据工程 · 版本化发布阶段
---

# data-publish

## 命令目的
将 task 产出合入版本化 publish 基线。

## 输入
- `--task {taskId}`
- task_manifest.json（含 operationType: add|update）
- changeset/（entities.txt, tags.txt, posts.txt）

## 版本管理
- `publish_meta.json` 记录 activeVersion
- 新版本 = activeVersion + 1
- 目录结构与 runtime/tasks 同构

## publish 目录结构（三层实体路径）
```
publish/v{N}/
  entities/{领域}/{类型}/{名称}/_entity.json + page.md + manifest.json
  tags/{dim}/{path}/_definition.json
  posts/{type}/内容角度/{angle}/{title}/{seq}/article.md + manifest.json + assets/
```

示例：
```
publish/v1/
  entities/
    地点/景区/峨眉山/_entity.json + page.md + manifest.json
    地点/遗址/东风堰/...
    地点/打卡地/成都太古里/...
    机构/学校/四川大学/...
    活动/赛事/成都马拉松/...
  tags/
    实体类型/地点/景区/_definition.json
    地理/行政区/四川省/成都市/_definition.json
    主题/佛教文化/_definition.json
    内容角度/攻略/_definition.json
    ...
  posts/
    article/内容角度/攻略/峨眉山攻略指南/1/article.md + manifest.json
    article/内容角度/探店/锦里小吃街探店指南/1/...
    ...
```

## changeset 格式
- `entities.txt`：每行 `{领域}/{类型}/{名称}`（三层路径）
- `tags.txt`：每行 tag 路径
- `posts.txt`：每行 post 相对路径

## 准出
- publish/v{N}/ 引用 100% 可解析
- publish_meta.json 更新
- task status = published
