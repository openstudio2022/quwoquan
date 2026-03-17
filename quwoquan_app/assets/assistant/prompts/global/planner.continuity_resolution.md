你要判断当前用户问题，是否应该承接上一轮对话上下文。

禁止做法：
- 不要靠“有没有出现某几个跟进词”来判断。
- 不要因为上一轮和这一轮都属于同一个垂类，就默认承接。
- 不要机械继承所有历史槽位；只有当前问题仍依赖它们，或者用户明确是在改写已有条件时才继承。

你要基于语义来判断：
- 当前问题是不是在延续上一轮目标。
- 当前问题是不是在改写上一轮约束或槽位。
- 当前问题是不是已经切换成了新目标。
- 历史摘要、长期记忆、位置线索分别会不会帮助当前轮判断。

## 当前问题
{{currentQuery}}

## 最近几轮用户问题
{{referenceQueries}}

## 历史摘要
{{historySummary}}

## 上一轮结构化意图
{{previousIntentGraph}}

## 上一轮槽位快照
{{previousSlotState}}

## 上一轮答案摘要
{{previousAnswerSummary}}

## 输出要求

只输出一个 JSON 对象，字段如下：

```json
{
  "queryIntent": "一句话描述当前问题真正要解决什么",
  "problemClass": "simple_qa | realtime_info | task_execution | complex_reasoning | general",
  "continuityMode": "fresh_topic | same_topic | explicit_follow_up",
  "explicitContinuation": true,
  "topicOverlap": 0.0,
  "allowHistorySummary": true,
  "allowLongtermMemory": false,
  "allowLocationHints": false,
  "referenceQueries": ["最近仍然相关的用户问题"],
  "overrideSlots": {
    "time_budget": "4天"
  },
  "reasonShort": "给用户看的简短说明"
}
```

判断标准：
- `fresh_topic`：当前问题已经换了目标，不应默认继承上一轮框架。
- `same_topic`：目标一致或高度相关，且承接上下文有帮助，但不是在明确改写上一轮条件。
- `explicit_follow_up`：当前问题明显是在沿用上一轮目标，并且在补充、缩小、改写或追问已有条件。

`overrideSlots` 只放当前问题明确改写的条件，例如时间、地点、预算、对象、排序要求；没有就输出空对象。

`reasonShort` 要自然、简短、面向用户，不要出现字段名、JSON、协议词或内部术语。

现在开始，只输出 JSON。
