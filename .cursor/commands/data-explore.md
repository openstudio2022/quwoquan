---
name: /data-explore
id: data-explore
category: Workflow
description: 应用数据生成工作流 · 数据规格探索阶段
---

## 目标

收敛本轮数据工程的：

- 地理范围
- 实体类型子集
- 合规边界
- 权威源可得性

## 真实实现

对应 CLI：

```bash
python3 quwoquan_data/tools/cli.py data explore --query "<query>" --regions "<省,市州>" --entity-types "<中文类型列表>"
```

## 工作流位置

`data explore` → **data baseline** → `data build-entities-tags` → ...

explore 之后**必须**执行 `data baseline` 冻结基线，才能进入后续阶段。

## 输出

- stage JSON 摘要
- 可进入 `/data-baseline` 的范围与待澄清项

## 边界

- 只做探索与收敛
- 不生成 runtime 数据
