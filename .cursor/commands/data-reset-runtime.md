---
name: /data-reset-runtime
id: data-reset-runtime
category: Workflow
description: 应用数据生成工作流 · full runtime reset
---

## 目标

清空当前 `quwoquan_data/runtime/`，并恢复 tracked baseline，再重建目录布局。

## 真实实现

```bash
bash scripts/reset_quwoquan_data_runtime_full.sh
```

## 输出

- baseline 恢复后的 `runtime/`
- 清空所有 generated 数据
---
name: /data-reset-runtime
id: data-reset-runtime
category: Workflow
description: 应用数据生成工作流 · full runtime reset
---

## 目标

按当前已确认口径执行 **full runtime reset**：

- 清空当前 `quwoquan_data/runtime/`
- 恢复 tracked baseline
- 重建 runtime 目录布局

## 真实实现

对应脚本：

```bash
bash scripts/reset_quwoquan_data_runtime_full.sh
```

## 边界

- 该脚本会删除当前 runtime 下的 generated 数据
- baseline 恢复以当前工作树中的 tracked runtime 文件为准
