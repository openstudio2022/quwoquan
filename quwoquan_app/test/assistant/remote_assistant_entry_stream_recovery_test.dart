import 'dart:convert';
import 'dart:io';

import 'package:quwoquan_app/assistant/application/assistant_request_policy.dart';
import 'package:quwoquan_app/assistant/application/assistant_run_stream.dart';
import 'package:quwoquan_app/assistant/application/remote_assistant_entry.dart';
import 'package:quwoquan_app/assistant/infrastructure/openclaw_bridge.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:test/test.dart';

void main() {
  test('远端 stream 缺少 final payload 时会从增量答案合成 completed 响应', () async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    addTearDown(() async {
      await server.close(force: true);
    });
    server.listen((request) async {
      if (request.method.toUpperCase() == 'POST' &&
          request.uri.path == '/v1/run/stream') {
        request.response.headers.set(
          HttpHeaders.contentTypeHeader,
          'text/event-stream; charset=utf-8',
        );
        request.response.write(
          'event: trace\n'
          'data: ${jsonEncode(<String, dynamic>{
            'type': 'thinkingProgress',
            'message': '正在理解你的问题',
            'timestamp': DateTime.now().toIso8601String(),
            'data': <String, dynamic>{'phase': 'analyze'},
          })}\n\n',
        );
        request.response.write(
          'event: answer_delta\n'
          'data: ${jsonEncode(<String, dynamic>{'type': 'answer_delta', 'scope': 'aggregation', 'message': '这是远端流式回答。'})}\n\n',
        );
        request.response.write('data: [DONE]\n\n');
        await request.response.close();
        return;
      }
      request.response.statusCode = HttpStatus.notFound;
      await request.response.close();
    });

    final entry = RemoteAssistantEntry(
      openClawBridge: OpenClawBridge(
        baseUrl: 'http://127.0.0.1:${server.port}',
      ),
      requestPolicy: const AssistantRequestPolicy(),
    );

    final events = await entry
        .runStream(
          request: const AssistantRunRequest(
            sessionId: 'remote_stream_recovery',
            traceId: 'trace_remote_stream_recovery',
            messages: <AssistantRunMessage>[
              AssistantRunMessage(role: 'user', content: '帮我总结一下'),
            ],
          ),
        )
        .toList();

    expect(
      events.where(
        (event) => event.type == AssistantRunStreamEventType.answerDelta,
      ),
      isNotEmpty,
    );
    final completed = events
        .where((event) => event.type == AssistantRunStreamEventType.completed)
        .single
        .response;
    expect(completed, isNotNull);
    expect(completed!.finalText, '这是远端流式回答。');
    expect(completed.degraded, isTrue);
    expect(completed.errorCode, 'remote_stream_terminal_payload_missing');
    expect(
      events.where(
        (event) => event.type == AssistantRunStreamEventType.journeyUpdate,
      ),
      isNotEmpty,
    );
    final runArtifacts = (completed.structuredResponse['runArtifacts'] as Map?)
        ?.cast<String, dynamic>();
    expect(runArtifacts, isNotNull);
    expect(
      (runArtifacts!['displayMarkdown'] as String?) ?? '',
      equals('这是远端流式回答。'),
    );
    final journey = (runArtifacts['journey'] as Map?)?.cast<String, dynamic>();
    expect(journey, isNotNull);
    expect((journey!['stages'] as List?) ?? const <dynamic>[], isNotEmpty);
  });

  test('远端 stream 没有可用增量时会回退到非流式 run', () async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    addTearDown(() async {
      await server.close(force: true);
    });
    server.listen((request) async {
      if (request.method.toUpperCase() == 'POST' &&
          request.uri.path == '/v1/run/stream') {
        request.response.headers.set(
          HttpHeaders.contentTypeHeader,
          'text/event-stream; charset=utf-8',
        );
        request.response.write('data: [DONE]\n\n');
        await request.response.close();
        return;
      }
      if (request.method.toUpperCase() == 'POST' &&
          request.uri.path == '/v1/run') {
        request.response.headers.contentType = ContentType.json;
        request.response.write(
          jsonEncode(<String, dynamic>{
            'finalText': '来自非流式回退的完整回答',
            'traces': const <Map<String, dynamic>>[],
            'structuredResponse': const <String, dynamic>{},
          }),
        );
        await request.response.close();
        return;
      }
      request.response.statusCode = HttpStatus.notFound;
      await request.response.close();
    });

    final entry = RemoteAssistantEntry(
      openClawBridge: OpenClawBridge(
        baseUrl: 'http://127.0.0.1:${server.port}',
      ),
      requestPolicy: const AssistantRequestPolicy(),
    );

    final events = await entry
        .runStream(
          request: const AssistantRunRequest(
            sessionId: 'remote_stream_run_fallback',
            traceId: 'trace_remote_stream_run_fallback',
            messages: <AssistantRunMessage>[
              AssistantRunMessage(role: 'user', content: '继续回答'),
            ],
          ),
        )
        .toList();

    final completed = events
        .where((event) => event.type == AssistantRunStreamEventType.completed)
        .single
        .response;
    expect(completed, isNotNull);
    expect(completed!.finalText, '来自非流式回退的完整回答');
    expect(completed.errorCode, isNull);
    final runArtifacts = (completed.structuredResponse['runArtifacts'] as Map?)
        ?.cast<String, dynamic>();
    expect(runArtifacts, isNotNull);
    expect(
      (runArtifacts!['displayMarkdown'] as String?) ?? '',
      equals('来自非流式回退的完整回答'),
    );
  });

  test('远端 stream 只有 thinking 或不完整答案时不会误合成 completed', () async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    addTearDown(() async {
      await server.close(force: true);
    });
    server.listen((request) async {
      if (request.method.toUpperCase() == 'POST' &&
          request.uri.path == '/v1/run/stream') {
        request.response.headers.set(
          HttpHeaders.contentTypeHeader,
          'text/event-stream; charset=utf-8',
        );
        request.response.write(
          'event: trace\n'
          'data: ${jsonEncode(<String, dynamic>{
            'type': 'thinkingProgress',
            'message': 'shen zhen tian qi',
            'timestamp': DateTime.now().toIso8601String(),
            'data': <String, dynamic>{'phase': 'answering', 'streaming': true, 'extracted': true},
          })}\n\n',
        );
        request.response.write(
          'event: answer_delta\n'
          'data: ${jsonEncode(<String, dynamic>{'type': 'answer_delta', 'scope': 'aggregation', 'message': '```md'})}\n\n',
        );
        request.response.write('data: [DONE]\n\n');
        await request.response.close();
        return;
      }
      if (request.method.toUpperCase() == 'POST' &&
          request.uri.path == '/v1/run') {
        request.response.headers.contentType = ContentType.json;
        request.response.write(
          jsonEncode(<String, dynamic>{
            'finalText': '来自非流式兜底的完整回答',
            'traces': const <Map<String, dynamic>>[],
            'structuredResponse': const <String, dynamic>{
              'runArtifacts': <String, dynamic>{
                'displayMarkdown': '来自非流式兜底的完整回答',
                'displayPlainText': '来自非流式兜底的完整回答',
              },
            },
          }),
        );
        await request.response.close();
        return;
      }
      request.response.statusCode = HttpStatus.notFound;
      await request.response.close();
    });

    final entry = RemoteAssistantEntry(
      openClawBridge: OpenClawBridge(
        baseUrl: 'http://127.0.0.1:${server.port}',
      ),
      requestPolicy: const AssistantRequestPolicy(),
    );

    final events = await entry
        .runStream(
          request: const AssistantRunRequest(
            sessionId: 'remote_stream_incomplete_answer',
            traceId: 'trace_remote_stream_incomplete_answer',
            messages: <AssistantRunMessage>[
              AssistantRunMessage(role: 'user', content: '继续回答'),
            ],
          ),
        )
        .toList();

    final completed = events
        .where((event) => event.type == AssistantRunStreamEventType.completed)
        .single
        .response;
    expect(completed, isNotNull);
    expect(completed!.finalText, '来自非流式兜底的完整回答');
    expect(completed.errorCode, isNull);
    final runArtifacts = (completed.structuredResponse['runArtifacts'] as Map?)
        ?.cast<String, dynamic>();
    expect(runArtifacts, isNotNull);
    expect(
      (runArtifacts!['displayMarkdown'] as String?) ?? '',
      equals('来自非流式兜底的完整回答'),
    );
    expect(
      completed.traces.any(
        (trace) =>
            trace.message.contains('synthesized response from streamed answer'),
      ),
      isFalse,
    );
  });
}
