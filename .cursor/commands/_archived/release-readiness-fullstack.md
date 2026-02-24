---
name: /release-readiness-fullstack
id: release-readiness-fullstack
category: Release
description: 按商用发布准入检查端云一体特性是否可发布
---

目标：从“端侧 mock 可用”升级到“可商用发布”。

执行顺序：

1. 特性准入检查  
- `changes/feature_catalog.yaml` 中目标特性状态为 `active` 或 `release_candidate`
- 特性目录的 `acceptance.yaml` 与 `traceability.yaml` 已完整

2. 契约与元数据检查  
```bash
make verify
```

3. 工程门禁  
```bash
make gate
make gate-full
```

4. 运维线检查（platform-ops）  
- 日志/指标/trace/告警模板已配置
- SLO 与回滚策略已声明
- 配置治理（sys.*）支持灰度与回滚

5. 运营线检查（product-ops）  
- 关键行为事件可采集
- 实验/灰度策略可审计
- 自动优化闭环（采集→评估→发布→回滚）可运行

