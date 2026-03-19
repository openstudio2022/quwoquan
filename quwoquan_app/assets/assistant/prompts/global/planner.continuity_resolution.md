## 任务背景

你要判断当前用户问题，是否应该承接上一轮对话上下文。

## 任务目标

1. 判断当前问题是在延续上一轮目标、改写上一轮条件，还是已经切换成新目标
2. 给出 `continuityMode`、`explicitContinuation` 与 `topicOverlap`
3. 判断历史摘要、长期记忆、位置线索是否真的有助于当前轮
4. 判断上一轮结构化理解与当前问题是否匹配
5. 只保留当前轮明确改写的 `overrideSlots`

## 约束

- 不要靠“有没有出现某几个跟进词”来判断连续追问
- 不要因为上一轮和这一轮都属于同一个垂类，就默认承接
- 不要机械继承所有历史槽位；只有当前问题仍依赖它们，或者用户明确在改写已有条件时才继承
- `fresh_topic`：当前问题已经换了目标，不应默认继承上一轮框架
- `same_topic`：目标一致或高度相关，且承接上下文有帮助，但不是在明确改写上一轮条件
- `explicit_follow_up`：当前问题明显沿用上一轮目标，并且在补充、缩小、改写或追问已有条件
- `overrideSlots` 只放当前问题明确改写的条件，例如时间、地点、预算、对象、排序要求；没有就输出空对象
- 只输出单个 JSON 对象，不要追加解释

## 执行要求

- 综合读取当前问题、最近几轮用户问题、历史摘要、上一轮结构化意图、上一轮理解快照、上一轮结果处理快照、上一轮槽位快照、上一轮答案摘要
- 基于语义判断当前问题真正想解决什么，而不是机械复用上轮主题词
- 若当前问题在缩小范围、替换条件、补充限制或追问上轮结论，优先考虑 `explicit_follow_up`
- 若上下文只是在背景层面有帮助，但目标并未明确改写，可用 `same_topic`
- 若当前问题已经转向新问题，应返回 `fresh_topic`
- `referenceQueries` 只保留当前轮仍然相关的历史用户问题
- `previousUnderstandingSnapshot` 与 `previousAnswerProcessing` 只能用于判断“理解方向是否延续 / 偏移 / 被纠正”，不是当前证据

## 输出格式

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
  }
}
```

## 反思与自检

- 我是否基于语义判断连续关系，而不是偷懒用关键词命中？
- 我是否只保留当前轮真正相关的历史上下文，而不是整包继承？
- 我是否判断了上一轮理解方向与当前问题是否仍然匹配？
- `overrideSlots` 是否只包含当前轮明确改写的条件？

=== CONTEXT_DATA_START ===
<currentQuery>
{{currentQuery}}
</currentQuery>
<referenceQueries>
{{referenceQueries}}
</referenceQueries>
<historySummary>
{{historySummary}}
</historySummary>
<previousIntentGraph>
{{previousIntentGraph}}
</previousIntentGraph>
<previousUnderstandingSnapshot>
{{previousUnderstandingSnapshot}}
</previousUnderstandingSnapshot>
<previousAnswerProcessing>
{{previousAnswerProcessing}}
</previousAnswerProcessing>
<previousSlotState>
{{previousSlotState}}
</previousSlotState>
<previousAnswerSummary>
{{previousAnswerSummary}}
</previousAnswerSummary>
=== CONTEXT_DATA_END ===
