import 'dart:io';

import 'package:test/test.dart';

void main() {
  group('Assistant display architecture guard', () {
    const guardedFiles = <String>[
      'lib/assistant/protocol/assistant_display_text_resolver.dart',
      'lib/assistant/protocol/assistant_display_state_projection.dart',
      'lib/assistant/application/assistant_journey_projector.dart',
      'lib/assistant/application/assistant_stream_projector.dart',
      'lib/ui/assistant/widgets/message/assistant_journey_view_model.dart',
      'lib/ui/assistant/widgets/message/assistant_message_bubble.dart',
      'lib/ui/assistant/widgets/message/assistant_answer_content.dart',
      'lib/ui/assistant/providers/assistant_conversation_controller.dart',
    ];

    const bannedFragments = <String>[
      '方案',
      'Day',
      '为什么',
      '预算',
      '开始整理',
      '继续找',
      '资料筛选',
      '进入成答',
      '检索词',
      '关键词',
      '查询词',
    ];

    test('显示层不再保留业务话术型启发式词表', () {
      for (final path in guardedFiles) {
        final content = File(path).readAsStringSync();
        for (final fragment in bannedFragments) {
          expect(
            content.contains(fragment),
            isFalse,
            reason: '$path 仍包含受禁词片段: $fragment',
          );
        }
      }
    });

    const legacyHelperFiles = <String>[
      'lib/assistant/protocol/assistant_display_text_resolver.dart',
      'lib/assistant/application/assistant_journey_projector.dart',
      'lib/assistant/orchestration/local_phase_execution_owner.dart',
    ];

    const removedLegacyHelpers = <String>[
      'compactMarkdownForAnswerShape',
      'normalizeThreeSectionAnswerMarkdown',
      'normalizeThreeSectionResponseMarkdown',
      'rewriteRetrievalQueryLeakForDisplay',
      'hasThreeSectionAnswerShape',
      '_queryTaskLeadLine',
      '_isLowSignalSearchPlanningMessage',
      '_isLowSignalJourneyNarrative',
      '_looksLikeOverExpandedDisplayPlainText',
    ];

    test('显示链路不再保留旧字符串启发式 helper', () {
      for (final path in legacyHelperFiles) {
        final content = File(path).readAsStringSync();
        for (final helperName in removedLegacyHelpers) {
          expect(
            content.contains(helperName),
            isFalse,
            reason: '$path 仍包含已移除的旧 helper: $helperName',
          );
        }
      }
    });

    const inlineProtocolGuardFiles = <String>[
      'lib/assistant/application/assistant_journey_projector.dart',
      'lib/assistant/application/assistant_stream_projector.dart',
      'lib/assistant/protocol/persisted_assistant_turn.dart',
      'lib/ui/assistant/widgets/message/assistant_journey_view_model.dart',
      'lib/ui/assistant/providers/assistant_conversation_controller.dart',
    ];

    const inlineProtocolPatterns = <String>[
      r"contains\('assistant_turn'\)",
      r"contains\('contractId'\)",
      r"contains\('queryTasks'\)",
      r"contains\('queryVariants'\)",
      r"contains\('machineEnvelope'\)",
      r"contains\('tool_call'\)",
      r"contains\('正在调用工具'\)",
    ];

    test('显示链路的协议碎片过滤必须走统一入口', () {
      for (final path in inlineProtocolGuardFiles) {
        final content = File(path).readAsStringSync();
        for (final pattern in inlineProtocolPatterns) {
          expect(
            RegExp(pattern).hasMatch(content),
            isFalse,
            reason: '$path 仍存在内联协议过滤: $pattern',
          );
        }
      }
    });
  });
}
