import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/public/assistant_ui_usage_stats_view_data.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/assistant_display_state_projection.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/assistant_journey.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/run_artifacts.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/assistant_citation.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/persisted_assistant_timeline_payload.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/persisted_timeline_turn_codec.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/assistant_transcript_timeline_row.dart';
import 'package:test/test.dart';

void main() {
  group('assistant transcript row typed payload', () {
    test('typed payload 经 codec 往返后读数不变（替代 encode->resolve 桥）', () {
      final runArtifacts = const RunArtifacts(
        displayMarkdown: 'hello',
        displayPlainText: 'hello',
        journey: AssistantJourney(
          summary: 'done',
          stages: <AssistantJourneyStage>[],
          entries: <AssistantJourneyEntry>[],
        ),
        retrievalProcessing: RetrievalProcessingSnapshot(
          processingSummary: 'done',
          processedDocumentCount: 1,
          acceptedDocumentCount: 1,
        ),
      ).toJson();
      final row = AssistantAnswerTranscriptRow(
        id: 'm1',
        sessionId: 'c1',
        content: 'hello',
        senderId: 'assistant',
        senderName: 'Assistant',
        persisted: PersistedAssistantTimelinePayload.fromMap(runArtifacts),
      );

      final roundTripped = PersistedTimelineTurnCodec.decode(
        PersistedTimelineTurnCodec.encode(row),
      );

      expect(roundTripped, isA<AssistantAnswerTranscriptRow>());
      final decoded = (roundTripped as AssistantAnswerTranscriptRow).persisted;
      expect(
        decoded.journey?.toJson(),
        row.persisted.journey?.toJson(),
      );
      expect(
        decoded.visibleProcessTimeline
            .map((frame) => frame.toJson())
            .toList(),
        row.persisted.visibleProcessTimeline
            .map((frame) => frame.toJson())
            .toList(),
      );
      expect(
        decoded.retrievalProcessing?.processingSummary,
        row.persisted.retrievalProcessing?.processingSummary,
      );
    });

    test('空 payload 的派生读数为空（原非助手行语义）', () {
      final empty = PersistedAssistantTimelinePayload.empty();

      expect(empty.journey, isNull);
      expect(empty.visibleProcessTimeline, isEmpty);
      expect(empty.retrievalProcessing, isNull);
      expect(empty.resolvedDisplayMarkdown, isEmpty);
      expect(empty.sanitizedFollowupPrompt, isEmpty);
      expect(empty.sanitizedActionHints, isEmpty);
    });

    test('持久化 payload 只读取 canonical 顶层字段', () {
      final payload = PersistedAssistantTimelinePayload.fromMap(
        const <String, dynamic>{
          'runArtifacts': <String, dynamic>{
            'journey': <String, dynamic>{'summary': 'retired nested value'},
            'retrievalProcessing': <String, dynamic>{
              'processingSummary': 'retired nested value',
            },
          },
        },
      );

      expect(payload.journey, isNull);
      expect(payload.retrievalProcessing, isNull);
    });

    test('持久化 payload 只保留单轨字段并完整往返结构化状态', () {
      final payload = PersistedAssistantTimelinePayload.fromMap(
        <String, dynamic>{
          assistantJourneyField: <String, dynamic>{'summary': 'canonical'},
          assistantRetrievalProcessingField: <String, dynamic>{
            'processingSummary': 'summary-1',
          },
          'uiProcessTimeline': <String, dynamic>{'summary': 'retired'},
        },
      ).toMap();

      expect(payload[assistantJourneyField], isNotNull);
      expect(payload[assistantRetrievalProcessingField], isNotNull);
      expect(payload.containsKey('uiProcessTimeline'), isFalse);
    });

    test('typed uiUsageStats 与 uiReferences 经 codec 往返读数不变', () {
      final row = AssistantAnswerTranscriptRow(
        id: 'm2',
        sessionId: 'c1',
        content: 'hello',
        senderId: 'assistant',
        senderName: 'Assistant',
        uiUsageStats: const AssistantUiUsageStatsViewData(
          runModelCallCount: 2,
          runTotalTokens: 120,
          runMaxTokensPerCall: 80,
          sessionModelCallCount: 5,
          sessionTotalTokens: 300,
          sessionMaxTokensPerCall: 90,
          runLedger: <AssistantUsageLedgerEntryViewData>[
            AssistantUsageLedgerEntryViewData(
              totalTokens: 120,
              inputTokens: 40,
              outputTokens: 80,
              source: 'understanding',
              modelRef: 'model-a',
            ),
          ],
        ),
        uiReferences: <AssistantCitation>[
          AssistantCitation.external(
            url: 'https://example.com/doc',
            title: 'Example Doc',
            source: 'example.com',
            snippet: 'snippet text',
          ),
        ],
      );

      final decoded =
          PersistedTimelineTurnCodec.decode(
                PersistedTimelineTurnCodec.encode(row),
              )
              as AssistantAnswerTranscriptRow;

      expect(decoded.uiUsageStats.runModelCallCount, 2);
      expect(decoded.uiUsageStats.runTotalTokens, 120);
      expect(decoded.uiUsageStats.sessionModelCallCount, 5);
      expect(decoded.uiUsageStats.sessionMaxTokensPerCall, 90);
      expect(decoded.uiUsageStats.runLedger, hasLength(1));
      expect(decoded.uiUsageStats.runLedger.first.modelRef, 'model-a');
      expect(decoded.uiReferences, hasLength(1));
      expect(decoded.uiReferences.first.title, 'Example Doc');
      expect(
        decoded.uiReferences.first.externalUrl,
        'https://example.com/doc',
      );
    });

    test('typed runArtifacts 经 codec 往返读数不变', () {
      final row = AssistantAnswerTranscriptRow(
        id: 'm4',
        sessionId: 'c1',
        content: 'hello',
        senderId: 'assistant',
        senderName: 'Assistant',
        runArtifacts: const RunArtifacts(
          diagnostics: RunArtifactsDiagnosticsPartitioned(
            extensions: <String, dynamic>{
              'lastEventType': 'completed',
              'processedCount': 3,
            },
          ),
        ),
      );

      final decoded =
          PersistedTimelineTurnCodec.decode(
                PersistedTimelineTurnCodec.encode(row),
              )
              as AssistantAnswerTranscriptRow;

      expect(decoded.runArtifacts, isNotNull);
      expect(
        decoded.runArtifacts!.diagnostics.extensions['lastEventType'],
        'completed',
      );
      expect(
        decoded.runArtifacts!.diagnostics.extensions['processedCount'],
        3,
      );
    });

    test('非法 runArtifacts 袋 fail-soft 置 null 而不炸整行', () {
      final decoded =
          PersistedTimelineTurnCodec.decode(<String, dynamic>{
                'id': 'm5',
                'sessionId': 'c1',
                'content': 'hello',
                'senderId': 'assistant',
                'senderName': 'Assistant',
                'runArtifacts': <String, dynamic>{
                  'displayMarkdown': 42,
                },
              })
              as AssistantAnswerTranscriptRow;

      expect(decoded.runArtifacts, isNull);
      expect(decoded.content, 'hello');
    });

    test('退役键 dialogueState/uiActions/assistantBoundaryOutcome 被丢弃且不进 extra',
        () {
      final decoded =
          PersistedTimelineTurnCodec.decode(<String, dynamic>{
                'id': 'm3',
                'sessionId': 'c1',
                'content': 'hello',
                'senderId': 'assistant',
                'senderName': 'Assistant',
                'dialogueState': <String, dynamic>{'retired': true},
                'uiActions': <Map<String, dynamic>>[
                  <String, dynamic>{'retired': true},
                ],
                'assistantBoundaryOutcome': <String, dynamic>{'retired': true},
                'customKey': 'kept',
              })
              as AssistantAnswerTranscriptRow;

      expect(decoded.extra.containsKey('dialogueState'), isFalse);
      expect(decoded.extra.containsKey('uiActions'), isFalse);
      expect(decoded.extra.containsKey('assistantBoundaryOutcome'), isFalse);
      expect(decoded.extra['customKey'], 'kept');

      final reEncoded = PersistedTimelineTurnCodec.encode(decoded);
      expect(reEncoded.containsKey('dialogueState'), isFalse);
      expect(reEncoded.containsKey('uiActions'), isFalse);
      expect(reEncoded.containsKey('assistantBoundaryOutcome'), isFalse);
    });

    test('displayState answer blocks 优先于持久化 markdown 字符串', () {
      final payload = PersistedAssistantTimelinePayload.fromMap(
        <String, dynamic>{
          assistantDisplayMarkdownField: 'fallback text',
          assistantDisplayStateField: const AssistantDisplayState(
            answer: AssistantAnswerDisplayState(
              blocks: <AssistantAnswerDisplayBlock>[
                AssistantAnswerDisplayBlock(
                  blockId: 'b1',
                  kind: DisplayBlockKind.paragraph,
                  body: 'typed',
                ),
              ],
            ),
          ).toJson(),
        },
      );

      expect(payload.resolvedDisplayMarkdown, contains('typed'));

      final withoutState = PersistedAssistantTimelinePayload.fromMap(
        <String, dynamic>{assistantDisplayMarkdownField: 'fallback text'},
      );
      expect(withoutState.resolvedDisplayMarkdown, 'fallback text');
    });
  });
}
