import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/transcript/persisted_timeline/persisted_timeline_turn_codec.dart';
import 'package:quwoquan_app/assistant/transcript/row/assistant_transcript_timeline_row.dart';

Future<Map<String, dynamic>> _loadFixture(String name) async {
  final path = 'test/assistant/transcript/fixtures/$name';
  final text = await File(path).readAsString();
  final decoded = jsonDecode(text);
  return Map<String, dynamic>.from(decoded as Map);
}

void main() {
  test('codec round-trip user_text_row fixture', () async {
    final raw = await _loadFixture('user_text_row.json');
    final row = PersistedTimelineTurnCodec.decode(raw);
    final out = PersistedTimelineTurnCodec.encode(row);
    expect(out['id'], raw['id']);
    expect(out['content'], raw['content']);
    expect(out['isSelf'], true);
  });

  test('codec round-trip assistant_streaming_placeholder fixture', () async {
    final raw = await _loadFixture('assistant_streaming_placeholder.json');
    final row = PersistedTimelineTurnCodec.decode(raw);
    final out = PersistedTimelineTurnCodec.encode(row);
    expect(out['id'], raw['id']);
    expect(out['streaming'], true);
    expect(out['assistantTurnSchemaVersion'], raw['assistantTurnSchemaVersion']);
    expect(out['displayMarkdown'], raw['displayMarkdown']);
  });

  test('codec round-trip assistant_error_row fixture', () async {
    final raw = await _loadFixture('assistant_error_row.json');
    final row = PersistedTimelineTurnCodec.decode(raw);
    final out = PersistedTimelineTurnCodec.encode(row);
    expect(out['isError'], true);
    expect(out['content'], raw['content']);
  });

  test('codec round-trip preserves assistant runArtifacts for parseRunArtifacts', () {
    const md = '# codec-round-trip';
    final row = AssistantAnswerTranscriptRow(
      id: 'codec_ra',
      conversationId: 'c1',
      content: 'body',
      senderId: 'assistant',
      senderName: 'Assistant',
      runArtifacts: <String, dynamic>{'displayMarkdown': md},
    );
    final decoded = PersistedTimelineTurnCodec.decode(
      PersistedTimelineTurnCodec.encode(row),
    );
    expect(decoded, isA<AssistantAnswerTranscriptRow>());
    final answer = decoded as AssistantAnswerTranscriptRow;
    expect(parseRunArtifacts(answer.runArtifacts).displayMarkdown, md);
  });
}
