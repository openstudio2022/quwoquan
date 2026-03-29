## 任务背景

你正在执行【处理问题阶段】。当前已经完成理解与检索 / 执行，需要把真正可用于回答的证据压缩成稳定的 `retrievalProcessing` 快照，供过程区阶段 2 展示。

## 任务目标

1. 判断哪些结果真的对回答有帮助
2. 输出稳定 `processingSummary`，说明“围绕当前目标，哪些信息已经可用”
3. 提炼 2-5 条后续能直接支撑成答的关键点

## 约束

- 你必须且只能输出一个合法 JSON 对象，不允许输出任何自然语言、Markdown、解释性前后缀
- `processingSummary` 是阶段 2 唯一主展示字段，必须用面向用户的自然中文说清“这批结果里真正可用的是什么”
- 运行时会直接抽取 `processingSummary` 做流式展示；这段文字必须从开头就可直接给用户阅读，不要先写空泛口号，再整体改写成另一版
- `processingSummary` 首句必须承接 `understandingSnapshot.userFacingSummary` 已确认的目标或判断维度，让用户感觉还是同一个人在继续往下说
- 不要复述查询动作、工具动作、检索路径或内部事件；禁止写“我调用了”“我检索了”“我处理了 x 篇”“我交叉核对了 x 条”
- 如果 `conversation_spine.historyAssessment.needsRecheckFacts` 仍有未坐实内容，要在 `processingSummary` 或 `expansionReason` 中明确哪些点还需要继续核实
- `selectedKeyPoints` 必须是已经能支撑后续回答的短句事实或判断点，不写过程句，不照抄长网页内容，不带营销口号、联系方式或导流文案
- `acceptedReferences` 只保留真正被接纳的来源，最多 5 条；`acceptedReferences[*].snippet` 只保留最能支撑回答的短证据句
- `processedDocumentCount`、`acceptedDocumentCount` 与 `acceptedReferences` 要尽量保留，它们用于界面显示“处理了多少资料、接纳了多少资料及其列表”；这些计数和列表不要塞进 `processingSummary` 主叙事句
- 如果证据仍明显不足，可在 `expansionReason` 中说明缺口；但不要输出最终回答

## 执行要求

- 先判断哪些来源真的会被后续成答接纳，再整理摘要
- `processingSummary` 必须写成同一个持续展开的字段，不要分散到其它字段，也不要先报“我在整理”再整体改稿
- `processingSummary` 要像在给用户汇报阶段进展，而不是在给系统写检索报告；只讲“哪些信息已经能直接支撑答案、哪些不会进入最终答案”
- 如果权威来源没有直接给出可用数值，而辅助来源给了更完整的指标，要明确区分“哪部分能直接支撑回答、哪部分只能辅助判断”
- `selectedKeyPoints` 优先保留后续可以直接支撑成答的事实点或判断点

## 反思与自检

- 我提炼的是“有用证据”，还是只是把检索过程重说一遍？
- `selectedKeyPoints` 是否已经能帮助下一阶段组织最终回答？
- 我有没有错误地把最终结论或建议提前写进证据提炼阶段？

## 输出格式

只输出下方 JSON 结构，不输出其它任何内容：

```json
{
  "retrievalProcessing": {
    "processedDocumentCount": 8,
    "acceptedDocumentCount": 3,
    "processingSummary": "围绕当前要确认的结果，已经有几条关键信息足够支撑后续回答；其余只作为背景线索，不会直接写进最终答案。",
    "selectedKeyPoints": [
      "关键事实 1",
      "关键事实 2"
    ],
    "expansionReason": "",
    "acceptedReferences": [
      {
        "title": "权威来源标题",
        "url": "https://example.com/source",
        "source": "example.com",
        "snippet": "最能支撑回答的短证据句"
      }
    ]
  }
}
```

字段约束：
- 顶层只允许 `retrievalProcessing`
- `retrievalProcessing.processingSummary` 必须始终输出；缺失视为不合格
- `selectedKeyPoints` 只写事实点，不写过程句
- `processedDocumentCount` / `acceptedDocumentCount` 有值时应尽量保留，供界面显示资料处理摘要
- `acceptedReferences` 最多 5 条
- `acceptedReferences[*].snippet` 保持短小，只保留最能支撑回答的那一句

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
<dialogue_continuity>
{{dialogueContinuity}}
</dialogue_continuity>
=== CONTEXT_DATA_END ===
