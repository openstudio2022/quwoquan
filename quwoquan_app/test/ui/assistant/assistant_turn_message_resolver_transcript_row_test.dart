import 'dart:convert';
import 'dart:io';

import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';
import 'package:quwoquan_app/assistant/transcript/persisted_timeline/persisted_timeline_turn_codec.dart';
import 'package:quwoquan_app/assistant/transcript/row/assistant_transcript_timeline_row.dart';
import 'package:quwoquan_app/ui/assistant/widgets/message/assistant_turn_message_resolver.dart';
import 'package:test/test.dart';

import '../../assistant/assistant_test_fixture_paths.dart';

void main() {
  group('assistant transcript row protocol parity', () {
    test('FromTranscriptRow 与 FromMessage(encode(row)) 对助手行一致', () {
      final runPath = assistantMetadataFixturePath('wire_min_run_artifacts.json');
      final base =
          jsonDecode(File(runPath).readAsStringSync()) as Map<String, dynamic>;
      final runArtifacts = RunArtifacts.fromJson(
        <String, dynamic>{
          ...base,
          'retrievalProcessing': <String, dynamic>{
            'processingSummary': 'done',
            'processedDocumentCount': 1,
            'acceptedDocumentCount': 1,
          },
        },
      ).toJson();
      final row = AssistantAnswerTranscriptRow(
        id: 'm1',
        conversationId: 'c1',
        content: 'hello',
        senderId: 'assistant',
        senderName: 'Assistant',
        runArtifacts: runArtifacts,
      );
      final m = PersistedTimelineTurnCodec.encode(row);
      expect(
        resolveAssistantJourneyFromTranscriptRow(row),
        resolveAssistantJourneyFromMessage(m),
      );
      expect(
        resolveAssistantProcessTimelineFromTranscriptRow(row),
        resolveAssistantProcessTimelineFromMessage(m),
      );
      expect(
        resolveAssistantRetrievalProcessingFromTranscriptRow(row).processingSummary,
        resolveAssistantRetrievalProcessingFromMessage(m).processingSummary,
      );
    });

    test('非助手行 FromTranscriptRow 给出空 journey / timeline', () {
      final row = UserTranscriptTimelineRow(
        id: 'u1',
        conversationId: 'c1',
        content: 'hi',
        senderId: 'user1',
        senderName: 'Me',
      );
      expect(resolveAssistantJourneyFromTranscriptRow(row).isEmpty, isTrue);
      expect(resolveAssistantProcessTimelineFromTranscriptRow(row), isEmpty);
    });
  });
}
