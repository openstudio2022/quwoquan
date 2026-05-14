---
name: /data-reset-runtime
id: data-reset-runtime
category: Workflow
description: 应用数据生成工作流 · full runtime reset
---

## 目标

清空当前 `quwoquan_data/runtime/`，恢复 tracked baseline，重建目录布局。

## 真实实现

```bash
bash quwoquan_data/scripts/util/reset_quwoquan_data_runtime_full.sh
```

## 边界

- 该脚本会删除当前 runtime 下的 generated 数据
- baseline 恢复以当前工作树中的 tracked runtime 文件为准
