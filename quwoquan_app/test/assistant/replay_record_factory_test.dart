import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/application/transcript/assistant_replay_record_factory.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';

void main() {
  group('buildAssistantReplayPayloadFromTraces', () {
    test('提取最新检索诊断与 replay payload', () {
      final now = DateTime.parse('2026-04-08T09:00:00.000Z');
      final traces = <AssistantTraceEvent>[
        AssistantTraceEvent(
          type: AssistantTraceEventType.toolError,
          message: 'older diagnostics',
          timestamp: now,
          data: const <String, dynamic>{
            'diagnostics': <String, dynamic>{'query': '旧诊断'},
          },
        ),
        AssistantTraceEvent(
          type: AssistantTraceEventType.toolResult,
          message: 'search result',
          timestamp: now.add(const Duration(seconds: 1)),
          data: const <String, dynamic>{
            'queryPlan': <String, dynamic>{
              'queriesUsed': <String>['2026-04-08 A股 大涨 原因'],
            },
            'policyDecision': <String, dynamic>{'webAccessMode': 'enabled'},
            'roundTraces': <Map<String, dynamic>>[
              <String, dynamic>{
                'round': 1,
                'queries': <String>['A股'],
              },
            ],
            'diagnostics': <String, dynamic>{'query': '最新诊断'},
          },
        ),
      ];

      final payload = buildAssistantReplayPayloadFromTraces(traces);

      expect(payload['queryPlan'], <String, dynamic>{
        'queriesUsed': <String>['2026-04-08 A股 大涨 原因'],
      });
      expect(payload['policyDecision'], <String, dynamic>{
        'webAccessMode': 'enabled',
      });
      expect(payload['roundTraces'], <Map<String, dynamic>>[
        <String, dynamic>{
          'round': 1,
          'queries': <String>['A股'],
        },
      ]);
      expect(payload['webSearchDiagnostics'], <String, dynamic>{
        'query': '最新诊断',
      });
    });

    test('无工具结果时仍返回稳定空结构', () {
      final payload =
          buildAssistantReplayPayloadFromTraces(<AssistantTraceEvent>[
            AssistantTraceEvent(
              type: AssistantTraceEventType.lifecycleStart,
              message: 'llm request iteration 1',
              timestamp: DateTime.parse('2026-04-08T09:00:00.000Z'),
            ),
          ]);

      expect(payload['queryPlan'], const <String, dynamic>{});
      expect(payload['policyDecision'], const <String, dynamic>{});
      expect(payload['roundTraces'], const <Map<String, dynamic>>[]);
      expect(payload['webSearchDiagnostics'], const <String, dynamic>{});
    });
  });
}
