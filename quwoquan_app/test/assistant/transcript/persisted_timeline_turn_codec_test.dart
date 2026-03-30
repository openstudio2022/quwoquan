import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/transcript/persisted_timeline/persisted_timeline_turn_codec.dart';

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
}
