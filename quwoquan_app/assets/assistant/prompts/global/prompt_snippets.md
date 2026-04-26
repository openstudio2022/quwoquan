## 任务背景
subagent_role=executor

## 任务目标
output=structured_conclusion

## 约束
- 仅围绕当前任务输出
- 保留必要的主题锚点与上下文继承

## 执行要求
- 优先使用结构化字段，不拼接额外话术
- 不输出与当前任务无关的解释性内容

## 输出格式
assistant_turn_json

## 反思与自检
- 是否输出了无关叙事？
- 是否遗漏了关键锚点或上下文？

=== CONTEXT_DATA_START ===
<user_query>
{{userQuery}}
</user_query>
<skill_catalog>
{{skillCatalog}}
</skill_catalog>
<shared_context>
{{sharedContext}}
</shared_context>
<current_runtime_state>
{{currentRuntimeState}}
</current_runtime_state>
<dialogue_continuity>
{{dialogueContinuity}}
</dialogue_continuity>
<recent_dialogue_rounds>
{{recentDialogueRounds}}
</recent_dialogue_rounds>
<search_iteration_state>
{{searchIterationState}}
</search_iteration_state>
=== CONTEXT_DATA_END ===

<!-- snippet:subagent_execution -->
subagent_role=executor
routeNarrative={{routeNarrative}}
localContextSeed={{localContextSeed}}
<!-- snippet:end -->

<!-- snippet:synthesis_aggregation -->
mode=synthesis
input=subagent_runs
output=single_assistant_turn_json
priority=retrievalProcessing.processingSummary > answerProcessing > userMarkdown > result > decision
{{anchorReminder}}
{{continuationReminder}}
<!-- snippet:end -->

<!-- snippet:synthesis_repair -->
repair_mode=synthesis
repairReason={{repairReason}}
output=single_assistant_turn_json
{{anchorReminder}}
{{continuationReminder}}
<!-- snippet:end -->

<!-- snippet:synthesis_anchor_reminder -->
anchors={{anchors}}
<!-- snippet:end -->

<!-- snippet:continuation_reminder -->
continuityMode={{continuityMode}}
<!-- snippet:end -->

<!-- snippet:phase_one_direct_answer_repair -->
repair_mode=phase_one_direct_answer
latestUserQuery={{latestUserQuery}}
output=single_assistant_turn_json
{{anchorReminder}}
{{continuationReminder}}
<draft_answer>
{{recoveredMarkdown}}
</draft_answer>
<!-- snippet:end -->

<!-- snippet:plain_markdown_recovery -->
mode=markdown_recovery
output=final_markdown_only
{{anchorReminder}}
<!-- snippet:end -->

<!-- snippet:tool_failure_context -->
tool_failure_context
{{failureContextJson}}
<!-- snippet:end -->

<!-- snippet:retrieval_reflection -->
mode=retrieval_reflection
qualityScore={{qualityScore}}
failureMessage={{failureMessage}}
authorityDomains={{authorityDomains}}
snippets={{snippets}}
reflectionRound={{reflectionRound}}/{{allowedReflectionRounds}}
retryToolName={{retryToolName}}
<!-- snippet:end -->

<!-- snippet:force_answer_conclusion -->
mode=answer_conclusion
decision=answer
<!-- snippet:end -->

<!-- snippet:force_answer_conclusion_minimal -->
mode=answer_conclusion_minimal
decision=answer
<!-- snippet:end -->

<!-- snippet:retrieval_unavailable_notice -->
mode=retrieval_unavailable
fallback=stable_degraded_answer
<!-- snippet:end -->

<!-- snippet:system_context_unavailable_notice -->
mode=system_context_unavailable
fallback=continue_with_explicit_user_inputs
<!-- snippet:end -->
