import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/http/retry_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/transport/cloud_retry_policy.dart';

void main() {
  test('GET 在 503 后 drain 响应并尊重 Retry-After', () async {
    var firstResponseListened = false;
    final firstBody = StreamController<List<int>>();
    firstBody.onListen = () {
      firstResponseListened = true;
    };
    firstBody
      ..add(utf8.encode('temporarily unavailable'))
      ..close();
    final inner = _SequenceClient(<Object>[
      http.StreamedResponse(
        firstBody.stream,
        503,
        headers: const <String, String>{'retry-after': '3'},
      ),
      http.StreamedResponse(Stream<List<int>>.value(utf8.encode('ok')), 200),
    ]);
    final waits = <Duration>[];
    final client = RetryHttpClient(
      inner: inner,
      policy: const CloudRetryPolicy(
        maxRetries: 2,
        maxBackoff: Duration(seconds: 8),
      ),
      sleeper: (delay) async {
        waits.add(delay);
      },
    );

    final response = await client.send(
      http.Request('GET', Uri.parse('https://api.example.test/items')),
    );

    expect(response.statusCode, 200);
    expect(inner.attempts, 2);
    expect(firstResponseListened, isTrue);
    expect(waits, <Duration>[const Duration(seconds: 3)]);
  });

  test('POST 即使收到 503 也不会由 transport 自动重放', () async {
    final inner = _SequenceClient(<Object>[
      http.StreamedResponse(const Stream<List<int>>.empty(), 503),
      http.StreamedResponse(const Stream<List<int>>.empty(), 200),
    ]);
    final client = RetryHttpClient(inner: inner, sleeper: (_) async {});

    final response = await client.send(
      http.Request('POST', Uri.parse('https://api.example.test/commands'))
        ..body = '{"command":"create"}',
    );

    expect(response.statusCode, 503);
    expect(inner.attempts, 1);
  });

  test('GET 的 ClientException 按策略重试且 close 下沉', () async {
    final inner = _SequenceClient(<Object>[
      http.ClientException('offline'),
      http.StreamedResponse(const Stream<List<int>>.empty(), 200),
    ]);
    final client = RetryHttpClient(
      inner: inner,
      policy: const CloudRetryPolicy(
        maxRetries: 1,
        initialBackoff: Duration(milliseconds: 10),
      ),
      sleeper: (_) async {},
    );

    final response = await client.send(
      http.Request('GET', Uri.parse('https://api.example.test/items')),
    );
    client.close();

    expect(response.statusCode, 200);
    expect(inner.attempts, 2);
    expect(inner.closed, isTrue);
  });

  test('500 非显式可重试状态，不会掩盖服务端业务失败', () async {
    final inner = _SequenceClient(<Object>[
      http.StreamedResponse(const Stream<List<int>>.empty(), 500),
      http.StreamedResponse(const Stream<List<int>>.empty(), 200),
    ]);
    final client = RetryHttpClient(inner: inner, sleeper: (_) async {});

    final response = await client.send(
      http.Request('GET', Uri.parse('https://api.example.test/items')),
    );

    expect(response.statusCode, 500);
    expect(inner.attempts, 1);
  });
}

final class _SequenceClient extends http.BaseClient {
  _SequenceClient(this.results);

  final List<Object> results;
  var attempts = 0;
  var closed = false;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final result = results[attempts++];
    if (result is http.StreamedResponse) return result;
    throw result;
  }

  @override
  void close() {
    closed = true;
  }
}
