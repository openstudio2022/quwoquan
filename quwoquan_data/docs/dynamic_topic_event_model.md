# 动态话题与事件实例模型

> 这份规范只描述“时效对象”的运行时模型，不改静态标签树。  
> 核心原则：`Topic/事件` 与 `Topic/话题` 负责稳定分类，日更热词、热搜、挑战、新闻事件实例统一走 `tag_runtime/`，不把时效对象硬塞进物理实体树。

## 设计目标

- 把“每日热话题 / 热搜 / 挑战 / 新闻事件”从静态标签中剥离出来。
- 保留事件事实和话题簇之间的可追溯关系。
- 让推荐系统可以消费时效热度、传播速度、平台来源和归档状态，而不是只认死标签。
- 允许同一热话题跨平台合并，也允许一个新闻事件派生多个话题实例。

## 目标对象

### 1) 事件实例

事件实例是“可指称的事实对象”，例如新闻事件、历史事件、社会事件、赛事事件、城市突发事件。

建议字段：

| 字段 | 说明 |
| --- | --- |
| `eventId` | 稳定事件 ID |
| `title` | 事件标题 |
| `eventType` | 事件类型，如 `新闻事件`、`历史事件`、`社会事件`、`赛事事件` |
| `sourceRefs` | 事件事实来源链接或引用 |
| `startedAt` | 首次出现时间 |
| `endedAt` | 事实收束时间 |
| `status` | `active` / `closed` / `archived` |
| `entityRefs` | 关联实体，如人物、地点、机构、作品 |
| `topicRefs` | 关联到的稳定话题标签 |
| `contentRefs` | 相关内容引用 |
| `confidence` | 事实置信度 |

### 2) 话题实例

话题实例是“时效传播对象”，例如微博热搜、小红书挑战、今日头条热点、百度热榜、平台专题话题。

建议字段：

| 字段 | 说明 |
| --- | --- |
| `topicInstanceId` | 稳定话题实例 ID |
| `title` | 话题标题 |
| `aliases` | 别名、平台话题名、近义写法 |
| `sourcePlatform` | 来源平台，可多值 |
| `sourceType` | `social_hot` / `news_hot` / `search_trend` / `topic_tag` |
| `startsAt` | 首次进入热度窗口的时间 |
| `peaksAt` | 峰值时间 |
| `expiresAt` | 预计或实际过期时间 |
| `status` | `emerging` / `rising` / `peaked` / `cooling` / `expired` / `archived` |
| `trendScore` | 当前热度分 |
| `growthRate` | 近窗口增长率 |
| `derivedFromEventRefs` | 派生自哪些事件实例 |
| `sameClusterRefs` | 同簇实例互引 |
| `relatedTopicInstanceRefs` | 相关话题实例 |
| `contentRefs` | 内容引用 |
| `tagRefs` | 绑定的稳定标签，如 `Topic/事件`、`Topic/话题`、`Topic/摄影` |

## 生命周期

推荐统一使用以下状态流转：

`emerging -> rising -> peaked -> cooling -> expired -> archived`

补充说明：

- `emerging`：刚被发现，热度还未稳定。
- `rising`：热度快速上升。
- `peaked`：进入峰值窗口。
- `cooling`：热度回落，但仍有消费价值。
- `expired`：热度已过窗口，不再参与强推荐。
- `archived`：历史归档，仅用于检索和回放。

## 来源平台

建议把来源平台分成三类：

| 类别 | 示例 | 用途 |
| --- | --- | --- |
| 社交热榜 | 微博、小红书、抖音、快手、B站 | 发现话题传播速度和社区热度 |
| 资讯热榜 | 今日头条、网易新闻、腾讯新闻、澎湃、央视新闻 | 发现新闻事件和公共讨论 |
| 搜索热榜 | 百度热搜、平台搜索趋势 | 发现即时意图和外部需求 |

同一话题实例可以来自多个平台，`sourcePlatform` 只记录来源，不决定 canonical 归属。

## 事件与话题的关系

- `事件实例` 是事实源，回答“发生了什么”。
- `话题实例` 是传播源，回答“大家在谈什么”。
- 一个事件可以派生多个话题实例，例如新闻事件、地域话题、文娱话题。
- 多个平台的同名热词可以归并到一个话题实例，但每个平台都保留来源痕迹。
- 稳定分类仍由 `Topic/事件` 与 `Topic/话题` 承接，实例层不创建静态标签节点。

## 推荐回流信号

推荐系统只消费“实例 + 关联 + 热度 + 时效”四类信号：

- `trendScore`
- `growthRate`
- `status`
- `sourcePlatform`
- `derivedFromEventRefs`
- `sameClusterRefs`
- `relatedTopicInstanceRefs`
- `contentRefs`

推荐回流建议写成聚合事件，而不是直接改静态标签：

- 点击、收藏、分享、评论、停留、跳出
- 搜索命中、关注、屏蔽、纠错
- 事件簇合并、话题簇合并、实例过期

## 落盘建议

建议的 runtime 文件如下：

```text
tag_runtime/
├── topic_instances.ndjson
├── event_instances.ndjson
├── topic_cluster_edges.ndjson
├── topic_hotness.ndjson
├── tag_weight_overlay.ndjson
└── tag_metrics.ndjson
```

其中：

- `topic_instances.ndjson`：话题实例主表。
- `event_instances.ndjson`：事件实例主表。
- `topic_cluster_edges.ndjson`：实例间合并和关联边。
- `topic_hotness.ndjson`：当前热度快照。
- `tag_weight_overlay.ndjson`：推荐权重覆盖层。
- `tag_metrics.ndjson`：用户反馈和统计回流。

## 示例

```json
{
  "topicInstanceId": "topic:weibo:成都暴雨救援:2026-05-17",
  "title": "成都暴雨救援",
  "aliases": ["成都暴雨", "成都救援"],
  "sourcePlatform": ["微博", "今日头条"],
  "sourceType": "social_hot",
  "startsAt": "2026-05-17T08:00:00+08:00",
  "peaksAt": "2026-05-17T12:30:00+08:00",
  "expiresAt": "2026-05-19T00:00:00+08:00",
  "status": "rising",
  "trendScore": 82.4,
  "growthRate": 1.36,
  "derivedFromEventRefs": ["event:chengdu_rainstorm_2026"],
  "sameClusterRefs": ["topic:weibo:成都暴雨:2026-05-17"],
  "relatedTopicInstanceRefs": ["topic:weibo:城市救援:2026-05-17"],
  "contentRefs": ["post:abc123", "post:def456"],
  "tagRefs": ["Topic/事件", "Topic/话题", "Topic/地理/行政区/中国/四川省/成都市"]
}
```

## 与静态标签树的边界

- 静态标签树只定义稳定分类，不保存 `startDate`、`endDate`、`trendScore` 之类动态字段。
- 动态实例不进入 `publish/tags/`，只进入 `tag_runtime/`。
- 如果一个动态热词最终沉淀为长期语义，再由人工或半自动流程迁移为静态标签。
- 事件实例与话题实例都不替代 `Entity/地点`、`Entity/人物`、`Entity/活动` 这些实体骨架，只通过引用关联。

