{{> checkpoint_agent_role.md}}

<constraints>
  <always>
    - 必须用文件写入/编辑工具真实覆盖任务区指定的两个写入路径，并在最终回复前重新读取确认文件存在。
    - 若对象 5.review/repair_report.json 存在，必须先逐项修复其中问题。
    - 逐条覆盖 prompt/author_job_packet 的 mustIncludeFacts；article 载体必须有连贯散文段落和至少三个结构层次。
    - 正文必须显式落下 review 可识别的编辑信号：首段用所选 openingStrategy 的真实钩子开场（例如 conclusion_first 用“先说结论/直接说/一句话”，question_hook 用真实问题，scene_immersion 用具体时间/天气/动作）。
    - 正文必须分别出现具体喜欢/打动点，以及不足/遗憾/劝退/不建议/失望/踩雷等负向取舍表达，并至少写 2 处“如果你…建议…”式决策判断。
    - 收尾必须从本篇素材的一个具体细节自然落下。
    - 只引用 prompt/author_job_packet 中的 assetId 和 sourcePath。draft_meta 必须 generator=agent，记录 model、citedSourcePaths、coveredFacts、styleFamily、openingStrategy、creativePlan、selfCritique。
    - creativePlan 必须先列 2-3 个候选构思并说明 selectedPlanId/selectionReason；selfCritique 必须覆盖 readerPromise、titlePromise、informationDensity、evidenceBoundary、personaBoundary。
    - 完成后做自检。
  </always>
  <never>
    - 不得只在回复中声称已写入，也不得把正文贴在回复里替代落盘。
    - 禁止把取舍判断写成固定小标题，尤其不要使用“它到底适合谁/这条线适合谁/这趟适合谁/到底适合谁/适合谁”。
    - 不得使用同批通用总结句、口号式劝行、固定适配人群段或统一结论模板收尾。
    - 除非 prompt 明确证明为允许公开的官方号码，否则正文不得写电话号码。
    - 不要运行批次发布。
  </never>
</constraints>
