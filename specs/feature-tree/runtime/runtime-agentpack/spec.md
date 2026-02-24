# L2 特性：runtime-agentpack

## 功能说明
- agent_task_pack.yaml schema：特性开发完成后的标准化归档格式。
- ScanFeatureTree：扫描特性树目录 → 自动构建 TreeIndex（含状态推断）。
- WriteIndex / ReadIndex：tree_index.yaml 序列化/反序列化。
- SearchFeatures：关键词搜索特性树（按 ID/名称/标签匹配）。
- IngestTaskPack：新特性自动归入特性树。

## 约束
- 状态推断基于 tasks.md 完成度（全部完成 → completed，部分 → in_progress）。
- tree_index.yaml 为自动生成，不手写。

## 验收标准
- A1：扫描目录 → 自动构建正确的特性树索引。
- A1：搜索特性树「推荐」→ 返回匹配的 recommendation 特性。
- A1：IngestTaskPack 后特性树自动更新。
- A8：全链路自动化测试（扫描/搜索/写入读取/归档）。
