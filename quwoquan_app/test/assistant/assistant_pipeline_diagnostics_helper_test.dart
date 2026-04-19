import 'package:quwoquan_app/assistant/contracts/assistant_subagent_run_record.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_tool_result_row.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_diagnostics_helper.dart';
import 'package:test/test.dart';

void main() {
  group('AssistantPipelineDiagnosticsHelper', () {
    test('builds typed tool observations and timeline entries', () {
      final helper = const AssistantPipelineDiagnosticsHelper();
      final record = AssistantSubagentRunRecord.fromJson(
        <String, dynamic>{
          'subagentId': 'sub-1',
          'domainId': 'content',
          'status': 'running',
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
          'answerReady': false,
          'references': <Map<String, dynamic>>[],
          'acceptedEvidence': <Map<String, dynamic>>[
            <String, dynamic>{
              'title': 'ref-1',
              'url': 'https://example.com/1',
            },
          ],
          'rejectedEvidence': <Map<String, dynamic>>[
            <String, dynamic>{
              'title': 'ref-2',
              'url': 'https://example.com/2',
            },
          ],
          'nextAction': 'answer',
          'missingSlots': <String>['topic'],
          'failureReason': '',
          'toolCallCount': 0,
          'modelCallCount': 0,
          'totalTokens': 0,
          'maxTokensPerCall': 0,
          'tokenSource': 'trace',
          'tokenSampleCount': 0,
          'inputTokens': 0,
          'outputTokens': 0,
          'usageLedger': <Map<String, dynamic>>[],
        },
      );
      final observations = helper.buildToolObservations(
        toolResults: <AssistantToolResultRow>[
          const AssistantToolResultRow(
            toolName: 'search',
            toolCallId: 'call-1',
            message: 'ok',
            data: <String, dynamic>{'hits': 2},
          ),
        ],
        toolErrors: <Map<String, dynamic>>[
          <String, dynamic>{
            'message': 'failed',
            'data': <String, dynamic>{'code': 'x'},
            'toolCallId': 'call-2',
          },
        ],
      );

      expect(observations, hasLength(2));
      expect(observations.first.ok, isTrue);
      expect(observations.first.toJson(), containsPair('toolCallId', 'call-1'));
      expect(observations.last.ok, isFalse);
      expect(observations.last.toJson(), containsPair('message', 'failed'));

      expect(record.toJson()['acceptedEvidence'], isNotEmpty);
      expect(record.toJson()['nextAction'], equals('answer'));

      final timeline = helper.buildUiTimeline(
        subagentRuns: <AssistantSubagentRunRecord>[record],
      );

      expect(timeline, hasLength(1));
      expect(timeline.single.toJson(), containsPair('status', 'running'));
      expect(timeline.single.summary, equals('summary'));
      expect(timeline.single.acceptedEvidenceCount, equals(1));
      expect(timeline.single.nextAction, equals('answer'));
    });

    test('builds typed quality metrics with freshness coercion', () {
      final helper = const AssistantPipelineDiagnosticsHelper();
      final metrics = helper.buildQualityMetrics(
        decisionParseSuccess: true,
        renderFallbackFlag: false,
        heuristicFallbackUsed: false,
        evidenceSufficient: true,
        freshnessSatisfied: false,
        freshnessRequired: false,
        criticalSlotsResolved: true,
        answerGateReady: true,
        answerGateReasonCode: 'ready',
      );

      expect(metrics.freshnessSatisfied, isTrue);
      expect(metrics.toJson(), containsPair('answerGateReasonCode', 'ready'));
      expect(metrics.toJson(), containsPair('decisionParseSuccess', isTrue));
    });
  });
}
