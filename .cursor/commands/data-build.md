---
name: /data-build
id: data-build
category: Workflow
description: 数据工程 · 实体/标签/主页构建阶段
---

# data-build

## 命令目的
基于 catalog 生成标准化实体、标签层级树和实体主页。

## 输入
- `--task {taskId}` `--batch {batchId}`
- catalog.ndjson（来自 explore）

## 实体三层目录

实体按「领域/类型/名称」三层组织，与标签维度 `实体类型/{领域}/{类型}` 保持一致：

```
entities/
  地点/景区/峨眉山/
  地点/遗址/东风堰/
  地点/打卡地/成都太古里/
  地点/博物馆/三星堆博物馆/
  地点/美食街/锦里小吃街/
  地点/古镇/阆中古城/
  地点/餐厅/陈麻婆豆腐/
  机构/学校/四川大学/
  活动/赛事/成都马拉松/
```

## 三段式

### prepare
为每个实体生成 `inputs/normalize_extract/{entityName}.json`，写 `assistant_tasks/normalize_extract.json`。

### agent（模型执行）
1. 归一化名称（中文规范名）
2. 推导领域/类型分类（对应 `tags/实体类型/{领域}/{类型}`）
3. 推导 tagRefs（路径格式）、geoTagRef
4. 物化到 `entities/{领域}/{类型}/{名称}/`：
   - `_entity.json`：无 entityId/entityType（从目录推导），含 aliases/tagRefs/geoTagRef/description/createdAt/updatedAt
   - `page.md`：按 `sop/主页/{领域}/{类型}/template.md` 模板生成，>= 800 字，嵌入 /entity/ + /tag/ + asset:// 引用
   - `manifest.json`：含 tagRefs/assets/timestamps
5. 物化标签到 `tags/{dim}/{path}/_definition.json`：无 tagId，含 label/labelEn/description/timestamps

### validate
- 每个 entity 有 _entity.json + page.md + manifest.json
- page.md >= 800 字，含 /entity/ + /tag/ + asset:// 引用，无独立标签/相关实体章节
- 所有 tagRefs 指向存在的 tags 目录
- SOP 模板存在：`sop/主页/{领域}/{类型}/guide.md + template.md + example.md`
