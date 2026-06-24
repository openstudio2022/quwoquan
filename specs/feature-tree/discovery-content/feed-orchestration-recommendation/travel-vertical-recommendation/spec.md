# L3 Story：travel-vertical-recommendation

## 功能说明

`travel-vertical-recommendation` 负责把首页推荐中的旅行频道从 `subCategory=travel` 归一为 `vertical=travel_photography`，并让召回、排序、fallback 和行为观测都按同一垂类口径过滤与归因。

## 范围

- `GET /v1/content/feed` 中 `type/subCategory=travel|旅行|旅游` 归一为 `vertical=travel_photography`。
- Tag/Hot/Explore/Author/Mongo/PostRepo/Social/Collaborative/Vector 召回必须遵守 vertical 过滤或在候选回传后过滤。
- repository fallback 不得混入非旅行内容。
- 行为事件和推荐指标按 `channelId=travel_photography`、`vertical=travel_photography`、`recallPath` 分桶。

## 非目标

- 不新建旅行专用深排模型。
- 不新建第二套旅行 feed API。
- 不绕过全局负反馈、下架、频控、near-dup 和曝光治理。

## 验收标准

- A1：旅行频道请求向 runtime recommendation 下传 `Surface=travel_photography` 与 `Vertical=travel_photography`。
- A2：召回不足进入 fallback 时仍只返回合格旅行内容。
- A3：协同召回、社交召回和向量召回不得绕过旅行垂类过滤。
- A4：行为回流保留 feedRequestId/channelId/vertical/recallPath/rankingVersion/reasonVersion。
