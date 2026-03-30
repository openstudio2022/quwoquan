# design：dual-theme-page-coverage（S6）

## 方案要点

1. **单一真相**：双色以 `AppTheme` / `CupertinoTheme` + `isDarkProvider`（或 `MediaQuery.platformBrightness` 与用户覆盖）为源；页面内 **少写三元分支**，多走 `AppColorsFunctional` / `CupertinoDynamicColor`。
2. **交付物**：`page-dual-theme-matrix.md`（或等价 CSV）放在本 feature 目录，CI 或 PR 模板引用「涉及页面是否已更新矩阵」。
3. **与门禁关系**：v1 以 **人工矩阵 + analyze + 语义脚本** 为主；v2 再评估 Golden 成本。
4. **豁免**：仅允许 **产品明确单模式** 或 **强制沉浸场景**；须在矩阵 `exemption_reason` 列登记。

## 风险

- 大文件页面（创作、编辑器）改动面广 → **按域切片**、每切片可独立验收。
- 第三方 WebView / 外链：仅要求 **壳与进度条** 双色，内页不保证。

## 与 app-theme-infrastructure 边界

| 项 | app-theme-infrastructure | dual-theme-page-coverage (S6) |
|----|--------------------------|-------------------------------|
| Theme/CupertinoTheme 接线 | 主责 | 消费 |
| 单页是否双色达标 | 辅责 | **主责** |
| 全页矩阵 | 否 | **是** |
