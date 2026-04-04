# L3 特性：analytics-metric-dictionary

## 功能说明

定义全链路埋点与反馈基础设施的统一指标字典，作为产品体验、用户行为、持续运营、在线学习与实验分析的唯一口径源。

字典覆盖全 App 域，并支持从领域服务 -> 页面表面 -> 内容/实体 -> 事件 -> 实验桶的下钻。

### 指标域

1. `experience`
   - 页面 `open / return`
   - 冷启动时长
   - 首帧时间
   - 页面错误率
   - 降级触发率
2. `qoe`
   - 视频首帧、解码失败率、卡顿率、播放进度分布
   - RTC 接通率、掉线率、弱网重试率
3. `behavior`
   - impression、有效曝光、click、dwell、scrollDepth、completion、replay
   - like/comment/favorite/share/dislike/report
4. `social`
   - 消息发送成功率、送达率、已读率、首回复时延、会话深度
5. `share`
   - 分享发起率、渠道分布、回流打开率、分享转化率
6. `entity`
   - 实体曝光率、实体点击率、绑定位置点击分布、实体转化结果
7. `learning`
   - InteractionEvent 上报成功率、Scorecard 完整率、反馈注入命中率、训练资格覆盖率
8. `experiment`
   - variant 覆盖率、uplift、回滚影响、收益/风险差异
9. `ops`
   - 漏斗完成率、留存、回流、类目/创作者/实体质量、策略收益

## 统一维度标准

### 公共维度
- `sessionId`
- `journeyId`
- `pageVisitId`
- `surfaceId`
- `routeId`
- `operationId`
- `requestId`
- `experimentBucket`
- `userIdHash`
- `appVersion`
- `platform`
- `networkClass`
- `occurredAt`

### 业务维度
- 内容：`contentId`、`contentType`、`authorId`、`circleId`
- 社交：`conversationId`、`messageId`、`rtcSessionId`
- 实体：`entityType`、`entityId`、`bindPosition`
- 学习：`runId`、`traceId`、`scorecardType`、`feedbackTarget`

## 指标定义原则

- 同一指标只能有一个主口径，不允许 dashboard、推荐、Assistant、BI 各自维护第二套定义。
- 指标必须声明：
  - 指标域；
  - 分子/分母；
  - 采样规则；
  - 默认时间粒度；
  - 支持的下钻维度；
  - 是否可用于训练/实验；
  - 数据延迟与 freshness 预期。
- 页级指标优先复用 `pageVisitId`；内容级指标优先复用 `contentId`；实体级指标优先复用 `entityType/entityId`。

## 对标吸收映射

- 微信：`messageDeliveryRate`、`messageReadRate`、`firstReplyLatencyMs`、`conversationDepth`
- 字节：`videoFirstFrameMs`、`completionRate`、`replayRate`、`negativeFeedbackRate`
- 今日头条：`effectiveImpressionRate`、`ctr`、`readingDepth`、`refreshQuality`
- 小红书：`shareOpenBackRate`、`entityExposureRate`、`entityClickRate`、`shareConversionRate`

## 约束

- 指标字典必须与 `event-schema-governance` 的字段与 envelope 兼容。
- 新增指标不得绕过字典直接进入 dashboard 或模型特征表。
- 用户可见体验指标与训练指标共享口径，但可有不同聚合层。
- 指标名称、分组与含义必须稳定，版本升级必须记录兼容策略。

## 验收标准

- A1：体验/行为/QoE/社交/分享/实体/学习/实验/运营九大指标域完整登记。
- A3：支持从领域到页面到内容/实体/实验桶的下钻分析。
- A4：推荐、Assistant、运营可基于同一指标口径消费数据。
- A7：新增指标必须经过字典治理与版本评审。
- A8：形成可支撑 baseline 的指标词典与维度标准文档。
