---
name: /rec-audit
id: rec-audit
category: Recommendation
description: 推荐系统 · 全面自检评审（对标业界一流，识别断点、DDD/端云/类型/存储合规缺口）
---

# rec-audit

## 命令目的
以顶尖推荐算法专家、数据工程师、推荐运营总监和**代码评审专家**四重视角，对推荐系统做端到端自检评审。既识别业界差距和链路断点，也审计 DDD 分层、强类型、存储无关、端云一致、元数据驱动和四层测试的合规性。

## 输入
- `--scope {all|behavior|feature|recall|scoring|social|pipeline|metrics|compliance}` 审计范围（默认 all）
- `--benchmark {tiktok|xiaohongshu|wechat}` 对标对象（默认全部）
- `--depth {quick|standard|deep}` 审计深度（默认 standard）

## 四重专家视角

### 视角一：推荐算法专家
- 特征是否真实反映用户行为（等级化、差异化深度、来源归因）
- 四维标签体系（Topic/Audience/Format/Entity）利用程度
- 召回路数是否充分（标签/热门/作者/实体/社交/向量/协同）
- 排序维度是否完整（15 维 RuleScorer + 多目标模型）
- 重排策略是否有效（多样性、反茧房、冷启动）
- 模型迭代能力（双塔/序列/多目标、自动训练 DAG）

### 视角二：数据工程师
- 数据工程 release → 推荐特征管线的贯通性
- 行为采集端到端链路（端侧→API→HotPath→投影→特征库）
- 特征一致性（feature_registry.yaml vs Go struct vs Python extractor）
- 离线训练管线可用性（learning events → sample joiner → train → evaluate）
- 实体/标签/内容三者之间的关系索引完整性

### 视角三：推荐运营总监
- 运营指标是否实时可观测（CTR/深度消费率/互动率/负反馈率/社交转化率）
- AB 实验能力（正交分层、自动流量分配、统计显著性）
- 长期效应评估（留存、信息茧房、创作者覆盖）
- 冷启动策略是否商用就绪（新用户/新内容）
- 来源归因是否支持渠道 ROI 分析

### 视角四：代码评审专家（DevOps 合规）
- **DDD 分层**：推荐域代码是否遵循 `domain ← application ← adapters ← infrastructure` 单向依赖；`runtime/recommendation/` 是否存在跨层 import（如 domain 层直接引用 MongoDB driver）
- **强类型**：端侧 UI/Provider 是否直接操作 `Map<String, dynamic>`；Go 侧是否存在 `interface{}` 作为推荐特征传输；`BehaviorEvent` / `BehaviorSignal` 字段是否全部强类型
- **存储无关**：`FeatureStore` / `BehaviorEventStore` / `DiscoveryFeedProjector` 是否通过 interface 抽象、不泄漏 Mongo driver 到 application 层；切换存储引擎是否只需替换 infrastructure 实现
- **端云一致**：`BehaviorEvent`（Dart）字段 ↔ `BehaviorSignal`（Go）字段 ↔ `feature_registry.yaml` 是否一一对齐；序列化枚举值（如 `ReferralSource`）是否端云用同一字符串常量
- **元数据驱动**：推荐相关的 path、operation、error code 是否来自 metadata codegen；是否存在硬编码的 API 路径或错误码字符串
- **四层测试**：推荐引擎是否有 T1（单元）+ T2（契约/集成）+ T3（端云联调/gamma）+ T4（真机旅程）四层证据；现有 `engine_test.go` / `engagement_depth_test.go` 覆盖到哪一层
- **codegen 保护**：`// Code generated ... DO NOT EDIT.` 标记的文件是否被手改；推荐相关 DTO 是否走 codegen
- **特性树对齐**：推荐能力是否归属到 `L1_capability`，是否有对应的 `spec.md` / `acceptance.yaml` / `design.md` / `plan.yaml` 四件套

## 自检维度（10 维，含 2 个合规维度）

### D1–D8：与之前一致
D1 行为采集完整性 / D2 行为→特征贯通性 / D3 特征广度与等级化 / D4 召回与排序完整性 / D5 社交图谱利用 / D6 数据工程→推荐衔接 / D7 运营指标与 AB / D8 内容类型差异化

### D9. DDD / 强类型 / 存储无关合规
扫描推荐相关代码（`runtime/recommendation/`、`services/content-service/internal/`、`lib/cloud/services/behavior/`、`lib/core/trackers/`）：

- `runtime/recommendation/` 内是否有 `import "go.mongodb.org"` 或 `import "github.com/go-redis"`
- `internal/application/behavior_service.go` 是否直接操作 Mongo collection（应通过 interface）
- `UserFeatureVector` 是否有 `interface{}` 类型字段
- Dart 端 `BehaviorEvent.toJson()` 返回值是否被 UI 层直接 as Map 消费
- `FeatureStore` / `BulkImportStore` 是否是 interface（非 struct 直接暴露）
- 推荐相关的 Dart DTO 是否有 codegen 标记或手写强类型类

### D10. 四层测试与特性树合规
- 推荐域 T1（单元测试）文件列表与覆盖
- 推荐域 T2（契约/集成测试）文件列表与覆盖
- 推荐域 T3（端云联调）是否存在
- 推荐域 T4（真机旅程）是否存在
- 是否有 `spec.md` / `acceptance.yaml` / `design.md` / `plan.yaml` 四件套
- `acceptance.yaml` 中的验收项是否有 `tests` 证据回填
- 推荐功能归属的 `L1/L2/L3` 位置

## 输出格式

```
╔══════════════════════════════════════════════════╗
║       推荐系统自检评审报告（/rec-audit）           ║
╠══════════════════════════════════════════════════╣
║ D1. 行为采集完整性        ✓/✗  N 项缺口          ║
║ D2. 行为→特征贯通性       ✓/✗  N 项断点          ║
║ D3. 特征广度与等级化      ✓/✗  N 项缺失          ║
║ D4. 召回与排序完整性      ✓/✗  N 项未接入         ║
║ D5. 社交图谱利用          ✓/✗  N 项未挖掘         ║
║ D6. 数据工程→推荐衔接     ✓/✗  N 项断裂          ║
║ D7. 运营指标与AB          ✓/✗  N 项缺失          ║
║ D8. 内容类型差异化        ✓/✗  N 项未覆盖         ║
║ D9. DDD/强类型/存储无关   ✓/✗  N 项违规          ║
║ D10. 测试与特性树         ✓/✗  N 项缺失          ║
╠══════════════════════════════════════════════════╣
║ 断点修复优先级                                    ║
║   P0(BLOCKING): N 项                              ║
║   P1(高): N 项   P2(中): N 项   P3(低): N 项     ║
╚══════════════════════════════════════════════════╝
```

每个 ✗ 项附带：文件路径 + 断点描述 + 修复方案 + 对应规则引用（如 `01-arch-constraints §1.2`）

## 后续动作
- 自检完成后自动生成修复规划（等同 `/rec-plan` 输入）
- 合规项（D9/D10）若有 BLOCKING，必须标注 `GATE_BLOCK`，不允许绕过进入实施
