import 'dart:io';

import 'package:test/test.dart';

void main() {
  group('Assistant typed mainline architecture guard', () {
    test('execution pipeline does not expose legacy map bridge', () {
      final files = _dartFilesUnder('lib/assistant/orchestration');
      const bannedFragments = <String>[
        'executionBridgeSnapshot',
        'toLegacyMap(',
        'buildTypedOrchestratorStateFromLegacyDecision',
        'buildTypedTurnSynthesisStateFromLegacyDecision',
        'ConversationStateDecision',
        'conversation_state_decision',
        'typed_mainline_decision_adapter',
        'deriveLegacyConversationStateDecisionFromTypedState',
        "structured['conversationStateDecision']",
        'structured["conversationStateDecision"]',
      ];

      for (final file in files) {
        final content = file.readAsStringSync();
        for (final fragment in bannedFragments) {
          expect(
            content.contains(fragment),
            isFalse,
            reason:
                '${file.path} must not reintroduce legacy bridge: $fragment',
          );
        }
      }
    });

    test('legacy conversation decision files are removed', () {
      const removedPaths = <String>[
        'lib/assistant/contracts/conversation_state_decision.dart',
        'lib/assistant/generated/contracts/conversation_state_decision.g.dart',
        'lib/assistant/orchestration/typed_mainline_decision_adapter.dart',
      ];

      for (final path in removedPaths) {
        expect(
          File(path).existsSync(),
          isFalse,
          reason: '$path must stay deleted',
        );
      }
    });

    test('high-risk request context reads go through typed view', () {
      final checkedFiles = <File>[
        File(
          'lib/assistant/orchestration/pipelines/assistant_pipeline_engine.dart',
        ),
        File('lib/assistant/orchestration/phases/bootstrap_phase.dart'),
        File('lib/assistant/orchestration/phases/understand_phase.dart'),
      ];

      for (final file in checkedFiles) {
        final content = file.readAsStringSync();
        expect(
          content.contains('request.contextScopeHint['),
          isFalse,
          reason:
              '${file.path} must use AssistantPipelineContextScopeHintView for keyed request reads.',
        );
        expect(
          content.contains('AssistantPipelineContextScopeHintView'),
          isTrue,
          reason:
              '${file.path} should keep the contextScopeHint typed boundary.',
        );
      }
    });

    test('assistant controller reads structuredResponse through typed view', () {
      final file = File(
        'lib/ui/assistant/providers/assistant_conversation_controller.dart',
      );
      final content = file.readAsStringSync();

      expect(
        content.contains('response.structuredResponse['),
        isFalse,
        reason:
            'Controller must use AssistantStructuredRunResponseReadView for keyed reads.',
      );
    });

    test('assistant UI reads run response structure through typed view', () {
      final files = _dartFilesUnder('lib/ui/assistant')
          .where(
            (file) => !file.path.endsWith(
              'assistant_structured_run_response_read_view.dart',
            ),
          )
          .toList(growable: false);

      for (final file in files) {
        final content = file.readAsStringSync();
        expect(
          content.contains('structuredResponse['),
          isFalse,
          reason:
              '${file.path} must use AssistantStructuredRunResponseReadView for keyed response reads.',
        );
      }
    });

    test('assistant message widgets do not read runArtifacts map directly', () {
      final files = _dartFilesUnder('lib/ui/assistant/widgets/message')
          .where(
            (file) =>
                !file.path.endsWith('assistant_turn_message_resolver.dart'),
          )
          .toList(growable: false);

      for (final file in files) {
        final content = file.readAsStringSync();
        expect(
          content.contains('runArtifacts['),
          isFalse,
          reason:
              '${file.path} must use typed RunArtifacts or resolver helpers.',
        );
      }
    });

    test('assistant controller delegates protocol filtering helpers', () {
      final file = File(
        'lib/ui/assistant/providers/assistant_conversation_controller.dart',
      );
      final content = file.readAsStringSync();
      const bannedFragments = <String>[
        'LlmResponseParser.parse',
        'RegExp _xmlToolCall',
        'bool _isInternalChunk',
        'String _sanitizeAssistantHistoryContent',
        'String _assistantHistoryContentForModel',
        'int _usageInt',
        'String _assistantSourceToPageType',
      ];

      for (final fragment in bannedFragments) {
        expect(
          content.contains(fragment),
          isFalse,
          reason:
              'Controller must delegate protocol filtering/stat helpers: $fragment',
        );
      }
      expect(content.contains('isAssistantStreamInternalChunk'), isTrue);
      expect(
        content.contains('buildAssistantCumulativeUsageStatsProtocolMap'),
        isTrue,
      );
      expect(content.contains('assistantPageTypeForSource'), isTrue);
    });

    test('assistant runtime context does not forward precise coordinates', () {
      final checkedFiles = <File>[
        File(
          'lib/ui/assistant/providers/assistant_conversation_controller.dart',
        ),
        File('lib/assistant/context/assembly/context_orchestrator.dart'),
        File('lib/assistant/reasoning/geo/geo_scope_support.dart'),
      ];
      const bannedFragments = <String>[
        "location['latitude']",
        "location['longitude']",
        "gpsLocation['lat']",
        "gpsLocation['lng']",
        "slotFillHints['gpsLat']",
        "slotFillHints['gpsLng']",
        "gpsLocationEnvelope['lat']",
        "gpsLocationEnvelope['lng']",
        "'device_gps'",
      ];

      for (final file in checkedFiles) {
        final content = file.readAsStringSync();
        for (final fragment in bannedFragments) {
          expect(
            content.contains(fragment),
            isFalse,
            reason: '${file.path} must not forward precise location: $fragment',
          );
        }
      }
    });

    test('AgentExecutionState exposes only approved weak map fields', () {
      final file = File(
        'lib/assistant/orchestration/state/agent_execution_state.dart',
      );
      final lines = file.readAsLinesSync();
      final mapFieldPattern = RegExp(
        r'^\s*final\s+(?:List<)?Map<String, dynamic>',
      );
      const allowedFieldNames = <String>{
        'recentDialogueRounds',
        'continuityOverrideSlots',
      };

      for (final line in lines.where(
        (line) => mapFieldPattern.hasMatch(line),
      )) {
        final allowed = allowedFieldNames.any(line.contains);
        expect(
          allowed,
          isTrue,
          reason: 'Unexpected weak map field in AgentExecutionState: $line',
        );
      }
    });

    test(
      'ExecutionPhaseSuccess weak maps are explicit LLM serde boundaries',
      () {
        final file = File(
          'lib/assistant/orchestration/state/execution_phase_snapshot.dart',
        );
        final lines = file.readAsLinesSync();
        final mapFieldPattern = RegExp(
          r'^\s*final\s+(?:List<)?Map<String, dynamic>',
        );
        const allowedFieldNames = <String>{
          'retrievalPolicy',
          'understandingSnapshot',
          'templateVariables',
          'messages',
        };

        for (var i = 0; i < lines.length; i++) {
          final line = lines[i];
          if (!mapFieldPattern.hasMatch(line)) continue;

          final allowed = allowedFieldNames.any(line.contains);
          final precedingComment = lines
              .sublist(i >= 3 ? i - 3 : 0, i)
              .join('\n');
          expect(
            allowed,
            isTrue,
            reason: 'Unexpected weak map field in ExecutionPhaseSuccess: $line',
          );
          expect(
            precedingComment.contains('LLM serde boundary'),
            isTrue,
            reason: 'Weak map field must document its boundary: $line',
          );
        }
      },
    );

    test('M4 display path does not gate on natural-language snippets', () {
      final checkedFiles = <File, List<String>>{
        File(
          'lib/assistant/protocol/assistant_display_text_resolver.dart',
        ): const <String>[
          '_containsProcessOnlyMarkers',
          '_containsReportStyleMarkers',
          '模型调用',
          '中间结果',
          '处理了',
          '检索了',
          '信息已就位',
          '收拢到',
        ],
        File(
          'lib/assistant/protocol/assistant_display_state_projection.dart',
        ): const <String>[
          "['我会先', '我先', '先']",
          'normalizedCandidate.contains(normalizedExisting)',
          'normalizedExisting.contains(normalizedCandidate)',
        ],
        File('lib/assistant/session/assistant_session_store.dart'):
            const <String>['正在调用工具'],
        File('lib/assistant/session/session_summary_builder.dart'):
            const <String>['正在调用工具'],
        File('lib/assistant/infrastructure/llm/llm_provider.dart'):
            const <String>['[阶段提示：理解问题]'],
        File('lib/ui/assistant/widgets/message/assistant_answer_content.dart'):
            const <String>['_referenceBlockPattern', '参考资料', '来源'],
      };

      for (final entry in checkedFiles.entries) {
        final file = entry.key;
        final content = file.readAsStringSync();
        for (final fragment in entry.value) {
          expect(
            content.contains(fragment),
            isFalse,
            reason:
                '${file.path} must not use natural-language snippets as a display gate: $fragment',
          );
        }
      }
    });

    test('weather and stock replay do not use text answer matchers', () {
      final file = File('integration_test/assistant_manual_replay_test.dart');
      final content = file.readAsStringSync();
      const bannedFragments = <String>[
        'bool _matchesWeatherAnswer',
        'bool _matchesStockAnswer',
        'return _matchesWeatherAnswer(text)',
        'return _matchesStockAnswer(text)',
      ];

      for (final fragment in bannedFragments) {
        expect(
          content.contains(fragment),
          isFalse,
          reason:
              'Weather/stock replay acceptance must use structured fields, not answer text: $fragment',
        );
      }
    });

    test(
      'display classifier does not use natural-language progress lexicons',
      () {
        final file = File(
          'lib/assistant/protocol/display_text_classifier.dart',
        );
        final content = file.readAsStringSync();
        const bannedFragments = <String>[
          '_policy.progressLexicon',
          '_policy.degradedPrefixes',
          '_policy.degradedSubstrings',
        ];

        for (final fragment in bannedFragments) {
          expect(
            content.contains(fragment),
            isFalse,
            reason:
                'Display filtering must use structured state, not natural-language lexicons: $fragment',
          );
        }
      },
    );
  });
}

List<File> _dartFilesUnder(String path) {
  final root = Directory(path);
  if (!root.existsSync()) return const <File>[];
  return root
      .listSync(recursive: true)
      .whereType<File>()
      .where((file) => file.path.endsWith('.dart'))
      .toList(growable: false);
}
