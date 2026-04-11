import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';

import 'assistant_test_fixture_paths.dart';

void main() {
  test('AssistantRunRequest 共享 metadata fixture fromJson/toJson 往返', () {
    final path = assistantMetadataFixturePath('wire_min_run_request.json');
    final json =
        jsonDecode(File(path).readAsStringSync()) as Map<String, dynamic>;
    final req = AssistantRunRequest.fromJson(json);
    expect(req.sessionId, 'fixture_session');
    expect(req.messages.single.content, 'fixture hello');
    expect(req.jsonExtension['_fixtureExtension'], isTrue);
    final enc = jsonEncode(req.toJson());
    final round = AssistantRunRequest.fromJson(
      jsonDecode(enc) as Map<String, dynamic>,
    );
    expect(round.jsonExtension['_fixtureExtension'], isTrue);
  });
}
