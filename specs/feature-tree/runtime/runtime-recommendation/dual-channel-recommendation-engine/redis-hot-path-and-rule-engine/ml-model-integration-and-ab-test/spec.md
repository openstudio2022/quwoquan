# L5 横切：ml-model-integration-and-ab-test

## 功能说明
- **ML 模型集成**：ModelScorer 抽象统一打分接口；支持 RuleScorer 基线 / RemoteModelScorer 远程 ML / CascadeScorer 容灾降级。
- **特征工程**：FeatureProvider 抽象用户特征供给；UserFeatureVector 包含 TagAffinities / AuthorAffinities / EngagementRate；FeatureStore 适配 MongoDB 读模型。
- **预排阶段**：PreRanker 抽象粗排截断；QualityPreRanker 实现时效过滤 + 互动密度排序。
- **Embedding 服务**：EmbeddingService 抽象向量生成；RemoteEmbeddingService 实现 HTTP 调用外部 API。
- **A/B 灰度**：推荐策略通过 runtime-experiments 灰度；支持规则引擎 vs ML 模型分组（权重层已完成，路由层待补）。

## 已实现架构

### 模型打分层
```
ModelScorer interface
├── RuleScorer          (增强基线: 6维特征公式)
├── RemoteModelScorer   (HTTP → ModelServiceClient → ML 模型)
└── CascadeScorer       (primary + fallback + timeout)
```

### 特征组装
```
FeatureProvider interface
├── NullFeatureProvider  (无特征 → 兜底)
└── FeatureStore         (MongoDB rm_recommend_feature → UserFeatureVector)
                          ├── TagAffinities      map[string]float64
                          ├── AuthorAffinities   map[string]float64
                          ├── TotalLikes/Views/Shares
                          └── EngagementRate      (likes+shares) / max(views, 1)
```

### 预排阶段
```
PreRanker interface
├── NullPreRanker       (透传)
└── QualityPreRanker    (MaxAge 时效过滤 + engagementDensity 粗排 + freshness 加成)
```

### CascadeScorer 容灾
- 主模型 (RemoteModelScorer) 超时或失败 → 自动降级到 fallback (RuleScorer)
- 降级日志包含原始错误信息 + 候选数量
- 超时可配置（WithTimeout option）

## 约束
- 实验配置与 experiments 元数据一致。
- ML 模型 fallback 到规则引擎（CascadeScorer 保证）。
- FeatureProvider 有独立超时（featureTimeout），超时不阻塞打分。

## 验收标准
- A1：ModelScorer 自定义注入 + 端到端打分正确。
- A3：CascadeScorer 容灾降级验证通过。A/B 路由待实现。
- A4：CTR/曝光/留存可监控（待实现 metric dashboard）。
- A8：ML 集成测试 + CascadeScorer 容灾测试 + 特征端到端测试 + PreRanker 测试。
