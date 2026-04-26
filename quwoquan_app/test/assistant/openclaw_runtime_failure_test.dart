import 'dart:convert';
import 'dart:io';

import 'package:quwoquan_app/assistant/infrastructure/openclaw_bridge.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';
import 'package:test/test.dart';

void main() {
  test('runRemote HTTP failure carries structured boundary failure', () async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    server.listen((request) async {
      request.response
        ..statusCode = HttpStatus.serviceUnavailable
        ..headers.contentType = ContentType.json
        ..write(jsonEncode(<String, Object?>{'message': 'down'}));
      await request.response.close();
    });
    addTearDown(() => server.close(force: true));

    final bridge = OpenClawBridge(baseUrl: 'http://127.0.0.1:${server.port}');
    final response = await bridge.runRemote(_request());

    expect(response, isNotNull);
    final failure = response!.assistantBoundaryOutcome?.failure;
    expect(failure, isNotNull);
    expect(failure!.code, equals('ASSISTANT.NETWORK.remote_model_http'));
    expect(failure.kind, equals(RuntimeFailureKind.unavailable));
  });

  test('runRemote invalid payload carries contract failure', () async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    server.listen((request) async {
      request.response
        ..headers.contentType = ContentType.json
        ..write(jsonEncode(<Object?>[]));
      await request.response.close();
    });
    addTearDown(() => server.close(force: true));

    final bridge = OpenClawBridge(baseUrl: 'http://127.0.0.1:${server.port}');
    final response = await bridge.runRemote(_request());

    final failure = response!.assistantBoundaryOutcome?.failure;
    expect(failure, isNotNull);
    expect(
      failure!.code,
      equals('ASSISTANT.CONTRACT.remote_model_invalid_payload'),
    );
    expect(failure.kind, equals(RuntimeFailureKind.contract));
  });

  test(
    'invokeSkillRemote invalid runtime failure payload is structured',
    () async {
      final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      server.listen((request) async {
        request.response
          ..headers.contentType = ContentType.json
          ..write(
            jsonEncode(<String, Object?>{
              'success': false,
              'message': 'bad',
              'runtimeFailure': <String, Object?>{'origin': 'bad'},
            }),
          );
        await request.response.close();
      });
      addTearDown(() => server.close(force: true));

      final bridge = OpenClawBridge(baseUrl: 'http://127.0.0.1:${server.port}');
      final result = await bridge.invokeSkillRemote(
        skillId: 'remote.skill',
        arguments: const <String, dynamic>{},
      );

      expect(result, isNotNull);
      expect(result!.success, isFalse);
      expect(result.runtimeFailure, isNotNull);
      expect(
        result.runtimeFailure!.code,
        equals('ASSISTANT.SYSTEM.execution_failed'),
      );
    },
  );
}

AssistantRunRequest _request() {
  return const AssistantRunRequest(
    sessionId: 's1',
    userId: 'u1',
    deviceProfile: 'test',
    messages: <AssistantRunMessage>[
      AssistantRunMessage(role: 'user', content: 'hello'),
    ],
  );
}
