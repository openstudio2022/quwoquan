import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  group('runtime string governance', () {
    test('治理文档冻结 metadata 根路径与 generated-only 规则', () {
      final designDoc = _read(
        'assistant/docs/PERSONAL_ASSISTANT_DESIGN_AND_CONSTRAINTS.md',
      );
      final ssotDoc = _read('assistant/docs/canonical_truth_sources.md');
      final governance = _read(
        'lib/assistant/reasoning/runtime/runtime_string_governance.dart',
      );

      expect(
        designDoc,
        contains('quwoquan_service/contracts/metadata/assistant/'),
      );
      expect(designDoc, contains('quwoquan_app/lib/assistant/generated/'));
      expect(designDoc, contains('assistant_turn'));
      expect(designDoc, contains('禁止继续保留读取兼容'));

      expect(ssotDoc, contains('lib/assistant/generated/'));
      expect(ssotDoc, contains('当前运行时不再读取兼容'));

      expect(
        governance,
        contains('quwoquan_service/contracts/metadata/assistant/'),
      );
      expect(governance, contains('lib/assistant/generated/'));
      expect(governance, contains('assistant_turn'));
      expect(governance, contains('唯一允许的助理输出契约版本'));
    });

    test('narrative_engine 不再直接承载用户可见中文文案', () {
      final content = _read(
        'lib/assistant/reasoning/runtime/narrative_engine.dart',
      );

      expect(content, contains('DefaultProcessingCopyBank'));
      final chineseLiteral = RegExp(
        r'''['"][^'"\n]*[\u4e00-\u9fff][^'"\n]*['"]''',
      );
      expect(chineseLiteral.hasMatch(content), isFalse);
    });

    test('tool_result_assessor 不再直接承载用户可见中文文案', () {
      final content = _read(
        'lib/assistant/reasoning/runtime/tool_result_assessor.dart',
      );

      expect(content, contains('DefaultProcessingCopyBank'));
      final chineseLiteral = RegExp(
        r'''['"][^'"\n]*[\u4e00-\u9fff][^'"\n]*['"]''',
      );
      expect(chineseLiteral.hasMatch(content), isFalse);
    });

    test('tool_result_assessor 使用 enum 而不是字符串 message key', () {
      final content = _read(
        'lib/assistant/reasoning/runtime/tool_result_assessor.dart',
      );

      expect(content, contains('ToolAssessMessageKey.'));
      expect(content, isNot(contains("toolAssessMessage('")));
    });

    test('phase owner 不再使用 realtimeTokens 关键词数组做实时判断', () {
      final content = _read(
        'lib/assistant/orchestration/local_phase_execution_owner.dart',
      );

      expect(content, isNot(contains('const realtimeTokens')));
      expect(content, contains('freshnessHours'));
      expect(content, contains('authorityScore'));
      expect(content, contains('EvidenceSourceTier.authority'));
    });

    test('answer_composer 的兜底文案由 copy bank 提供', () {
      final content = _read(
        'lib/assistant/reasoning/runtime/answer_composer.dart',
      );

      expect(content, contains('DefaultProcessingCopyBank'));
      expect(content, isNot(contains('## 当前信息还不够稳')));
      expect(content, isNot(contains('## 先给你一个稳妥版本')));
      expect(content, isNot(contains('### 参考来源')));
      expect(content, isNot(contains('需要补齐关键信息后再继续')));
    });

    test('conversation_state_kernel 默认追问文案由 copy bank 提供', () {
      final content = _read(
        'lib/assistant/context/assembly/conversation_state_kernel.dart',
      );

      expect(
        content,
        contains(
          'DefaultProcessingCopyBank.conversationKernelAskPrompt(slotId)',
        ),
      );
      expect(content, isNot(contains('告诉我更具体的地点')));
      expect(content, isNot(contains('再告诉我预算范围')));
    });

    test('phase owner 使用 typed nextAction/messageKind 合同而非裸字符串比较', () {
      final content = _read(
        'lib/assistant/orchestration/local_phase_execution_owner.dart',
      );

      expect(content, contains('parseNextAction('));
      expect(content, contains('parseMessageKind('));
      expect(content, contains('AssistantNextAction.answer'));
      expect(content, contains('AssistantMessageKind.answer'));
      expect(content, isNot(contains("nextAction == 'answer'")));
      expect(content, isNot(contains("nextAction == 'ask_user'")));
      expect(content, isNot(contains("messageKind == 'answer'")));
    });

    test('assistant_turn_contract 提供 nextAction/messageKind wireName 映射', () {
      final content = _read(
        'lib/assistant/contracts/assistant_turn_contract.dart',
      );
      final enumContent = _read(
        'lib/assistant/generated/enums/assistant_runtime_enums.g.dart',
      );

      expect(enumContent, contains('extension AssistantNextActionX'));
      expect(enumContent, contains('extension AssistantMessageKindX'));
      expect(content, contains('AssistantNextAction get nextActionType'));
      expect(content, contains('AssistantMessageKind get messageKindType'));
    });

    test('assistant generated contracts 提供字段常量与 typed assistant_turn 子合同', () {
      final decisionContract = _read(
        'lib/assistant/generated/contracts/conversation_state_decision.g.dart',
      );
      final slotSchemaContract = _read(
        'lib/assistant/generated/contracts/slot_schema.g.dart',
      );
      final reactObservationContract = _read(
        'lib/assistant/generated/contracts/react_observation.g.dart',
      );
      final dialogueRoundScriptContract = _read(
        'lib/assistant/generated/contracts/dialogue_round_script.g.dart',
      );
      final assistantTurnContract = _read(
        'lib/assistant/generated/contracts/assistant_turn.g.dart',
      );

      expect(
        decisionContract,
        contains('class ConversationStateDecisionDtoFields'),
      );
      expect(slotSchemaContract, contains('class SlotSchemaDtoFields'));
      expect(
        reactObservationContract,
        contains('class ReactObservationDtoFields'),
      );
      expect(
        dialogueRoundScriptContract,
        contains('class DialogueRoundScriptDtoFields'),
      );
      expect(assistantTurnContract, contains('class AssistantTurnAskUser'));
      expect(
        assistantTurnContract,
        contains('class AssistantTurnDecisionPayload'),
      );
      expect(
        assistantTurnContract,
        contains('final AssistantTurnAskUser askUser;'),
      );
      expect(
        assistantTurnContract,
        contains('final AssistantTurnDecisionPayload decision;'),
      );
    });

    test(
      'planner_contracts 覆盖 phase/action/reason/assessment/slot typed enums',
      () {
        final content = _read('lib/assistant/contracts/planner_contracts.dart');

        expect(
          content,
          contains(
            "export 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';",
          ),
        );
        expect(
          content,
          contains("assistant/generated/contracts/planner_contracts.g.dart"),
        );
        expect(content, contains('SlotFillAction.askUser'));
        expect(content, contains('SlotSource.userQueryLlm'));
        expect(content, contains('class SlotFillPlan'));
        expect(content, contains('SlotFillEntry _slotFillEntryFromRaw'));
      },
    );

    test('phase owner 不再使用 fallbackFrame 回填 intent graph 关键字段', () {
      final content = _read(
        'lib/assistant/orchestration/local_phase_execution_owner.dart',
      );

      expect(content, isNot(contains('fallbackFrame.targetObject')));
      expect(content, isNot(contains('fallbackFrame.userJobToBeDone')));
      expect(content, isNot(contains('fallbackFrame.hardConstraints')));
      expect(content, isNot(contains('fallbackFrame.softConstraints')));
      expect(content, isNot(contains('fallbackFrame.entityAnchors')));
      expect(content, isNot(contains('_fallbackIntentQueryTasks(')));
    });

    test('skill executors 不再通过 skill.id 内建特判知识技能', () {
      final executor = _read(
        'lib/assistant/skill/execution/assistant_skill_executor.dart',
      );
      final simpleExecutor = _read(
        'lib/assistant/skill/execution/simple_skill_executor.dart',
      );
      final market = _read(
        'lib/assistant/skill/market/assistant_skill_market_service.dart',
      );

      expect(executor, isNot(contains("skill.id == 'knowledge_qa'")));
      expect(executor, isNot(contains("skill.id == 'web.quick_search'")));
      expect(simpleExecutor, isNot(contains("skill.id == 'knowledge_qa'")));
      expect(simpleExecutor, isNot(contains("skill.id == 'web.quick_search'")));
      expect(executor, contains('_usesKnowledgeQaPipeline('));
      expect(simpleExecutor, contains('_usesKnowledgeQaPipeline('));
      expect(market, isNot(contains("m.id == 'knowledge_qa'")));
      expect(market, isNot(contains("m.id == 'web.quick_search'")));
      expect(market, contains('m.defaultEnabled'));
    });

    test('tool catalog 不再维护域到技能的白名单矩阵', () {
      final catalog = _read(
        'assets/assistant/tools/catalog/tool_catalog.meta.json',
      );

      expect(catalog, isNot(contains('"supportedSkills"')));
      expect(catalog, contains('"domainToolMatrix"'));
    });

    test('conversation_state_kernel 优先消费 slotFillPlan 而非 regex 提取', () {
      final content = _read(
        'lib/assistant/context/assembly/conversation_state_kernel.dart',
      );

      expect(content, contains('SlotFillPlan.fromJson'));
      expect(content, contains("answerPayload['slotFillPlan']"));
      expect(content, contains("answerPayload['contextSlots']"));
      expect(content, isNot(contains('_compatibilityExtractSlots')));
      expect(content, isNot(contains('_extractSlotsFromQuery')));
      expect(content, contains('EvidenceStatus.unknown'));
      expect(content, contains('EvidenceStatus.full'));
      expect(content, contains('EvidenceStatus.bounded'));
      expect(content, isNot(contains("evidenceStatus == 'full'")));
      expect(content, isNot(contains("evidenceStatus == 'bounded'")));
      expect(content, isNot(contains("evidenceStatus == 'not_required'")));
    });

    test('context_orchestrator 不再内嵌长关键词表和自然语言补槽指令', () {
      final content = _read(
        'lib/assistant/context/assembly/context_orchestrator.dart',
      );
      final continuityContract = _read(
        'lib/assistant/contracts/context_continuity_policy.dart',
      );
      final assemblyContract = _read(
        'lib/assistant/contracts/context_assembly_result.dart',
      );
      final readinessContract = _read(
        'lib/assistant/contracts/synthesis_readiness_result.dart',
      );

      expect(content, contains("'slotFillPolicy': _buildSlotFillPolicy("));
      expect(content, contains("'preferredSignals'"));
      expect(content, contains("'missingSlotAction': 'ask_user'"));
      expect(content, contains('ContextContinuityPolicy('));
      expect(content, contains('ContextAssemblyResult('));
      expect(content, contains('SynthesisReadinessResult('));
      expect(content, contains('_continuityHintsFromHistory('));
      expect(content, isNot(contains('class ContextContinuityPolicy')));
      expect(content, isNot(contains('class ContextAssemblyResult')));
      expect(content, isNot(contains('class SynthesisReadinessResult')));
      expect(content, isNot(contains('_hasWeakAnchors(')));
      expect(content, isNot(contains('_hasFollowUpCue(')));
      expect(content, isNot(contains('_hasRealtimeCue(')));
      expect(content, isNot(contains('_hasLongtermCue(')));
      expect(content, isNot(contains('slotFillInstruction')));
      expect(
        content,
        isNot(contains('static const List<String> _realtimeKeywords')),
      );
      expect(
        content,
        isNot(contains('static const List<String> _longtermKeywords')),
      );
      expect(
        content,
        isNot(contains('static const List<String> _continuationSignals')),
      );
      expect(content, isNot(contains('gpsCity/gpsLat/gpsLng')));
      expect(content, isNot(contains('historySummarySnippet补全关键槽位')));
      expect(
        continuityContract,
        contains(
          'assistant/generated/contracts/context_continuity_policy.g.dart',
        ),
      );
      expect(
        assemblyContract,
        contains(
          'assistant/generated/contracts/context_assembly_result.g.dart',
        ),
      );
      expect(
        readinessContract,
        contains(
          'assistant/generated/contracts/synthesis_readiness_result.g.dart',
        ),
      );
    });

    test('assistant_journey_projector 使用 typed journey stage/kind 而非旧 explainable 流', () {
      final content = _read(
        'lib/assistant/application/assistant_journey_projector.dart',
      );

      expect(content, contains('JourneyStageId.analyze'));
      expect(content, contains('JourneyStageId.search'));
      expect(content, contains('JourneyStageId.verify'));
      expect(content, contains('JourneyStageId.answer'));
      expect(content, contains('JourneyEntryKind.referenceBundle'));
      expect(content, contains('JourneyEntryKind.narrative'));
      expect(content, isNot(contains('ExplainableFlowEvent')));
      expect(content, isNot(contains('processJournal')));
    });

    test('assistant_stream_projector 只消费 canonical journey 流', () {
      final content = _read(
        'lib/assistant/application/assistant_stream_projector.dart',
      );

      expect(content, contains('AssistantJourneyProjector('));
      expect(content, contains('resolveCompletedJourney'));
      expect(content, contains('AssistantRunStreamEvent.processTimeline'));
      expect(content, isNot(contains('emitRemoteProcessJournal')));
      expect(content, isNot(contains('processJournalEvent')));
      expect(content, isNot(contains('explainableFlowEvent')));
    });

    test('display_text_classifier 与 tool catalog 清理旧路径和查询泄漏模板', () {
      final classifier = _read(
        'lib/assistant/protocol/display_text_classifier.dart',
      );
      final catalog = _read('assets/assistant/tools/catalog/tool_catalog.meta.json');

      expect(
        classifier,
        contains('assets/assistant/config/progress_text_policy.json'),
      );
      expect(classifier, isNot(contains('assets/personal_assistant')));
      expect(catalog, isNot(contains('检索查询：{{query}}')));
      expect(catalog, isNot(contains('抓取：{{url}}')));
      expect(catalog, isNot(contains('检索：{{query}}')));
      expect(catalog, isNot(contains('打开 {{url}}')));
    });

    test('ui_text_constants 已清理旧 timeline 兼容常量', () {
      final content = _read('lib/core/constants/ui_text_constants.dart');

      expect(content, isNot(contains('assistantTimelineSearchProcess')));
      expect(content, isNot(contains('assistantTimelineThinking')));
      expect(content, isNot(contains('assistantPhaseWaiting')));
      expect(content, isNot(contains('assistantPhaseThinking')));
      expect(content, isNot(contains('assistantProcessThinking')));
    });

    test('retrieval_planner 使用 typed AnswerShape switch 而非字符串', () {
      final content = _read(
        'lib/assistant/reasoning/planner/retrieval_planner.dart',
      );

      expect(content, contains('frame.answerShapeKind'));
      expect(content, contains('AnswerShape.comparison'));
      expect(content, contains('AnswerShape.options'));
      expect(content, contains('AnswerShape.decisionReady'));
      expect(content, isNot(contains("case 'comparison':")));
      expect(content, isNot(contains("case 'options':")));
      expect(content, isNot(contains("case 'decision_ready':")));
    });

    test('compatibility fallbacks 已从主链清理，不再保留旧注释入口', () {
      final kernel = _read(
        'lib/assistant/context/assembly/conversation_state_kernel.dart',
      );
      expect(kernel, isNot(contains('DEPRECATED compatibility fallback')));
      expect(kernel, isNot(contains('_compatibilityExtractSlots')));

      final reactRuntime = _read(
        'lib/assistant/reasoning/runtime/react_runtime.dart',
      );
      expect(
        reactRuntime,
        isNot(contains('DEPRECATED compatibility fallback')),
      );

      final phaseOwner = _read(
        'lib/assistant/orchestration/local_phase_execution_owner.dart',
      );
      expect(phaseOwner, isNot(contains('DEPRECATED compatibility fallback')));
    });
  });
}

String _read(String relativePath) {
  final file = File(relativePath);
  expect(file.existsSync(), isTrue, reason: '文件不存在: $relativePath');
  return file.readAsStringSync();
}
