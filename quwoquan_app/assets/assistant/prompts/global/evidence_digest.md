## 任务背景

你正在执行【证据提炼阶段】。当前已经完成理解与检索/执行，需要把真正可用于回答的证据压缩成稳定的 `retrievalProcessing` 快照，供过程区阶段 B 展示。

## 任务目标

1. 判断哪些检索结果真的对回答有帮助
2. 输出稳定的证据处理摘要，而不是最终答案
3. 提炼 2-5 条最值得保留的关键点，供后续成答使用

## 约束

- **你必须且只能输出一个合法 JSON 对象，不允许输出任何自然语言、Markdown、解释性前后缀**
- `processingSummary` 是阶段 2 唯一主展示字段，必须用面向用户的自然中文说清"这批结果里真正可用的是什么"
- 运行时会直接抽取 `processingSummary` 做流式展示；这段文字必须从开头就可直接给用户阅读，不要先写一句空泛口号，再整体改写成另一版
- `processingSummary` 不能复述查询动作、工具动作、检索路径或内部事件；不要写“我调用了”“我检索了”“我处理了 x 篇”
- `processingSummary` 至少写成 2-4 句完整中文，优先概括“哪些信息已足够支撑回答、哪些还需要谨慎”
- 如果已接纳的结果里有温度、时间、价格、距离、评分、人数等定量事实，`processingSummary` 的首句优先直接点出 1-2 个最关键数值，而不是只说“有一批结果可用”
- `selectedKeyPoints` 必须是已经能支撑后续回答的事实点或判断点，不要写"我先整理一下"这类过程句
- `acceptedReferences` 只保留真正被接纳的来源，最多保留最关键的 5 条
- 如果证据仍明显不足，可在 `expansionReason` 中说明缺口；但不要输出最终回答

## 执行要求

- 先判断哪些来源真的被后续成答接纳，再整理摘要
- `processingSummary` 先说"这批结果里真正可用的是什么"，不要复述查询动作
- `processingSummary` 不要短到只剩一句泛化口号；要让用户看到你到底从结果里筛出了什么价值
- `processingSummary` 必须写成同一个持续展开的字段，不要分散到其它字段，也不要先报“我在整理”再整体改稿
- `processingSummary` 要像在给用户汇报阶段进展，而不是在给系统写检索报告
- 如果权威来源没有直接给出可用数值，而第三方来源给了更完整的实时指标，要明确区分“哪部分能直接支撑回答、哪部分只能辅助判断”
- `selectedKeyPoints` 优先保留后续可以直接支撑成答的事实点或判断点
- 如果证据仍明显不足，可在 `expansionReason` 中说明缺口；但不要输出最终回答

## 反思与自检

- 我提炼的是"有用证据"，还是只是把检索过程重说一遍？
- `selectedKeyPoints` 是否已经能帮助下一阶段组织最终回答？
- 我有没有错误地把最终结论或建议提前写进证据提炼阶段？

## 输出格式

只输出下方 JSON 结构，不输出其它任何内容：

```json
{
  "retrievalProcessing": {
    "processedDocumentCount": 8,
    "acceptedDocumentCount": 3,
    "processingSummary": "检索结果中有 3 篇包含今天的实时温度和预报数据，可以直接支撑回答",
    "selectedKeyPoints": [
      "当前气温 25°C，晴，东南风 3 级",
      "今天最高 29°C，最低 22°C，多云",
      "暂无降雨或强对流预警"
    ],
    "expansionReason": "",
    "acceptedReferences": [
      {
        "title": "天气预报 - 中国天气网",
        "url": "https://www.weather.com.cn/weather/101280601.shtml",
        "source": "weather.com.cn",
        "snippet": "今日天气：晴到多云，25-29°C"
      }
    ]
  }
}
```

字段约束：
- 顶层只允许 `retrievalProcessing`
- `retrievalProcessing.processingSummary` 必须始终输出；缺失视为不合格
- `selectedKeyPoints` 只写事实点，不写过程句
- `acceptedReferences` 最多 5 条
- `acceptedReferences[*].snippet` 保持短小，只保留最能支撑回答的那一句，不要整段抄网页简介

=== CONTEXT_DATA_START ===
<user_query>
{{userQuery}}
</user_query>
<understanding_snapshot>
{{understandingSnapshot}}
</understanding_snapshot>
<evidence_context>
{{evidenceContext}}
</evidence_context>
<current_runtime_state>
{{currentRuntimeState}}
</current_runtime_state>
=== CONTEXT_DATA_END ===
