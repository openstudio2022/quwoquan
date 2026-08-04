import 'package:quwoquan_app/assistant/assistant/assistant_run/domain/assistant_journey.dart';
import 'package:quwoquan_app/assistant/assistant/assistant_run/domain/run_artifacts.dart';
import 'package:quwoquan_app/assistant/assistant/assistant_turn_view/domain/persisted_assistant_turn.dart';
import 'package:quwoquan_app/assistant/assistant/assistant_turn_view/domain/persisted_assistant_timeline_payload.dart';
import 'package:quwoquan_app/assistant/assistant/assistant_turn_view/domain/persisted_timeline_turn_codec.dart';
import 'package:quwoquan_app/assistant/assistant/assistant_turn_view/domain/assistant_transcript_timeline_row.dart';
import 'package:quwoquan_app/assistant/assistant/assistant_run/presentation/assistant_turn_message_resolver.dart';
import 'package:test/test.dart';

void main() {
  group('assistant transcript row protocol parity', () {
    test('FromTranscriptRow 与 FromMessage(encode(row)) 对助手行一致', () {
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
      final m = PersistedTimelineTurnCodec.encode(row);
      expect(
        resolveAssistantJourneyFromTranscriptRow(row).toJson(),
        resolveAssistantJourneyFromMessage(m).toJson(),
      );
      expect(
        resolveAssistantProcessTimelineFromTranscriptRow(
          row,
        ).map((frame) => frame.toJson()).toList(),
        resolveAssistantProcessTimelineFromMessage(
          m,
        ).map((frame) => frame.toJson()).toList(),
      );
      expect(
        resolveAssistantRetrievalProcessingFromTranscriptRow(
          row,
        ).processingSummary,
        resolveAssistantRetrievalProcessingFromMessage(m).processingSummary,
      );
    });

    test('非助手行 FromTranscriptRow 给出空 journey / timeline', () {
      final row = UserTranscriptTimelineRow(
        id: 'u1',
        sessionId: 'c1',
        content: 'hi',
        senderId: 'user1',
        senderName: 'Me',
      );
      expect(resolveAssistantJourneyFromTranscriptRow(row).isEmpty, isTrue);
      expect(resolveAssistantProcessTimelineFromTranscriptRow(row), isEmpty);
    });

    test('持久化 turn 只读取 canonical 顶层字段', () {
      const nestedOnly = <String, dynamic>{
        'runArtifacts': <String, dynamic>{
          'journey': <String, dynamic>{'summary': 'retired nested value'},
          'retrievalProcessing': <String, dynamic>{
            'processingSummary': 'retired nested value',
          },
        },
      };

      expect(resolveAssistantJourneyFromMessage(nestedOnly).isEmpty, isTrue);
      expect(
        resolveAssistantRetrievalProcessingFromMessage(
          nestedOnly,
        ).processingSummary,
        isEmpty,
      );
    });

    test('持久化 payload 只保留单轨字段并完整往返结构化状态', () {
      final payload = PersistedAssistantTimelinePayload.fromMap(
        <String, dynamic>{
          assistantJourneyField: <String, dynamic>{'summary': 'canonical'},
          assistantSystemContextEnvelopeField: <String, dynamic>{
            'contextKey': 'ctx-1',
          },
          assistantTaskGraphField: <String, dynamic>{'graphId': 'graph-1'},
          'uiProcessTimeline': <String, dynamic>{'summary': 'retired'},
        },
      ).toMap();

      expect(payload[assistantJourneyField], isNotNull);
      expect(payload[assistantSystemContextEnvelopeField], isNotNull);
      expect(payload[assistantTaskGraphField], isNotNull);
      expect(payload.containsKey('uiProcessTimeline'), isFalse);
    });
  });
}
