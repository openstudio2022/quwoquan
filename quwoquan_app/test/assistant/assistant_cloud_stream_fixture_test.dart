import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:quwoquan_app/assistant/generated/contracts/runtime_failure.g.dart';
import 'package:quwoquan_app/assistant/generated/contracts/tool_use.g.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';
import 'package:test/test.dart';

import 'assistant_test_fixture_paths.dart';

void main() {
  group('assistant-service M5 stream fixtures', () {
    test('ToolUseWire and RuntimeFailureWire roundtrip golden payloads', () {
      const failure = RuntimeFailureWire(
        code: 'ASSISTANT.MIDDLEWARE.tool_failed',
        origin: 'remoteDependency',
        kind: 'unavailable',
        nature: 'transient',
        messageKey: 'assistant.error.tool_failed',
        recoveryAction: 'retry',
        disruptionLevel: 'inlineCard',
        traceId: 'trace_tool',
        context: <String, dynamic>{'toolName': 'web_search'},
      );
      const toolUse = ToolUseWire(
        toolUseId: 'tu_test',
        turnId: 'atn_test',
        toolName: 'web_search',
        placement: 'cloud',
        input: <String, dynamic>{'query': 'AI chip news'},
        status: 'failed',
        requiresConfirmation: false,
        result: <String, dynamic>{},
        failure: failure,
        createdAt: '2026-04-29T00:00:00Z',
        completedAt: '2026-04-29T00:00:01Z',
      );

      final decoded = ToolUseWire.fromJson(toolUse.toJson());

      expect(decoded.toolUseId, toolUse.toolUseId);
      expect(decoded.toolName, 'web_search');
      expect(decoded.input['query'], 'AI chip news');
      expect(decoded.failure?.code, failure.code);
      expect(decoded.failure?.context['toolName'], 'web_search');
    });

    test('MockAssistantRepository emits canonical tool events', () async {
      final events = await MockAssistantRepository()
          .streamAssistantTurn(turnId: 'atn_mock_personal_assistant')
          .toList();

      expect(
        events.map((event) => event.eventType),
        containsAllInOrder(<String>[
          'turn_started',
          'tool_use_requested',
          'tool_result_received',
          'final_answer',
        ]),
      );
      final requested = events.firstWhere(
        (event) => event.eventType == 'tool_use_requested',
      );
      final rawToolUse = requested.payload['toolUse'] as Map;
      final toolUse = ToolUseWire.fromJson(rawToolUse.cast<String, dynamic>());
      expect(toolUse.toolName, 'web_search');
      expect(toolUse.status, 'requested');
    });

    test(
      'RemoteAssistantRepository decodes canonical success SSE events',
      () async {
        final body = File(
          assistantMetadataFixturePath('sse/sse_turn_stream_success.golden'),
        ).readAsStringSync();
        final repository = RemoteAssistantRepository(
          client: _StreamingFixtureClient(body),
        );

        final events = await repository
            .streamAssistantTurn(turnId: 'atn_replay_tool')
            .toList();

        expect(
          events.map((event) => event.eventType),
          contains('final_answer'),
        );
        expect(
          events.last.payload['text'],
          'Recent AI chip news focuses on accelerator supply, export rules, and inference cost.',
        );
      },
    );

    test(
      'RemoteAssistantRepository preserves runtimeFailure from failed SSE',
      () async {
        final body = File(
          assistantMetadataFixturePath('sse/sse_turn_stream_failure.golden'),
        ).readAsStringSync();
        final repository = RemoteAssistantRepository(
          client: _StreamingFixtureClient(body),
        );

        final events = await repository
            .streamAssistantTurn(turnId: 'atn_replay_failure')
            .toList();

        final failed = events.last;
        expect(failed.eventType, 'turn_failed');
        expect(failed.runtimeFailure?.code, 'ASSISTANT.MIDDLEWARE.tool_failed');
      },
    );
  });
}

class _StreamingFixtureClient extends http.BaseClient {
  _StreamingFixtureClient(this.body);

  final String body;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    return http.StreamedResponse(Stream<List<int>>.value(body.codeUnits), 200);
  }
}
