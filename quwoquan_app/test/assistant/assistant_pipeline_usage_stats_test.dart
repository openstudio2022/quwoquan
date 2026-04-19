import 'package:quwoquan_app/assistant/contracts/assistant_subagent_run_record.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_usage_stats.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:test/test.dart';

void main() {
  group('AssistantPipelineUsageStats helpers', () {
    test('buildUsageStatsFromTraces prefers usage ledger and tracks totals', () {
      final stats = buildUsageStatsFromTraces(
        traces: <AssistantTraceEvent>[
          AssistantTraceEvent(
            type: AssistantTraceEventType.lifecycleStart,
            message: 'llm request synthesis 1',
            timestamp: DateTime.parse('2026-01-01T00:00:00Z'),
            data: <String, dynamic>{
              'usageEntries': <Map<String, dynamic>>[
                <String, dynamic>{
                  'totalTokens': 40,
                  'inputTokens': 10,
                  'outputTokens': 30,
                  'source': 'trace_a',
                },
              ],
            },
          ),
        ],
        fallbackInputText: 'abc',
        fallbackOutputText: 'xyz',
      );

      expect(stats.modelCallCount, 1);
      expect(stats.totalTokens, 40);
      expect(stats.inputTokens, 10);
      expect(stats.outputTokens, 30);
      expect(stats.tokenSource, 'trace_a');
    });

    test('buildUiUsageStats merges main and subagent usage', () {
      final request = AssistantRunRequest(
        messages: const <AssistantRunMessage>[
          AssistantRunMessage(role: 'user', content: '你好'),
        ],
      );
      final usage = buildUiUsageStats(
        traces: <AssistantTraceEvent>[
          AssistantTraceEvent(
            type: AssistantTraceEventType.lifecycleStart,
            message: 'llm request iteration 1',
            timestamp: DateTime.parse('2026-01-01T00:00:00Z'),
            data: <String, dynamic>{
              'usageEntries': <Map<String, dynamic>>[
                <String, dynamic>{
                  'totalTokens': 20,
                  'inputTokens': 5,
                  'outputTokens': 15,
                  'source': 'trace_main',
                },
              ],
            },
          ),
        ],
        request: request,
        subagentRuns: <AssistantSubagentRunRecord>[
          AssistantSubagentRunRecord.fromJson(<String, dynamic>{
            'subagentId': 'sub-1',
            'domainId': 'content',
            'status': 'success',
            'goal': 'goal',
            'mode': 'mode',
            'problemClass': 'general',
            'shell': <String, dynamic>{},
            'stopPolicy': 'policy',
            'searchIntensity': 'low',
            'providerPolicy': 'auto',
            'freshnessHoursMax': 24,
            'answerThreshold': 0.5,
            'summary': 'summary',
            'userMarkdown': '',
            'result': <String, dynamic>{},
            'answerReady': true,
            'references': <Map<String, dynamic>>[],
            'toolCallCount': 1,
            'modelCallCount': 2,
            'totalTokens': 30,
            'maxTokensPerCall': 18,
            'tokenSource': 'subagent',
            'tokenSampleCount': 2,
            'inputTokens': 12,
            'outputTokens': 18,
            'usageLedger': <Map<String, dynamic>>[
              <String, dynamic>{
                'totalTokens': 30,
                'inputTokens': 12,
                'outputTokens': 18,
                'source': 'subagent',
              },
            ],
          }),
        ],
        outputText: '回答',
      );

      expect(usage['modelCallCount'], 3);
      expect(usage['totalTokens'], 50);
      expect(usage['inputTokens'], 17);
      expect(usage['outputTokens'], 33);
      expect(usage['usageLedger'], isA<List>());
    });
  });
}
