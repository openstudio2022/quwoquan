import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';

/// 媒体数据面出站的契约：对象存储 / CDN 的授权只由服务端签发的 URL 承载，
/// 因此这条路径必须共享 Gateway 的超时、错误映射与延迟观测，但**永不附带
/// bearer**。这些断言是 adapter 不再自建 `http.Client()` 之后唯一的防回退证据。
void main() {
  test('data-plane stream never forwards an Authorization header', () async {
    final seenHeaders = <Map<String, String>>[];
    final client = CloudHttpClient(
      client: MockClient.streaming((request, bodyStream) async {
        await bodyStream.drain<void>();
        seenHeaders.add(Map<String, String>.from(request.headers));
        return http.StreamedResponse(const Stream<List<int>>.empty(), 200);
      }),
    );
    addTearDown(client.close);

    final request = http.StreamedRequest('PUT', Uri.https('cdn.test', '/object'))
      ..headers['authorization'] = 'Bearer leaked-app-session-token'
      ..headers['content-type'] = 'image/jpeg';
    final responseFuture = client.sendDataPlaneStream(request);
    request.sink.add(const <int>[1, 2, 3]);
    await request.sink.close();
    final response = await responseFuture;

    expect(response.statusCode, 200);
    expect(seenHeaders.single.keys.map((k) => k.toLowerCase()), isNot(contains('authorization')));
    expect(seenHeaders.single['content-type'], 'image/jpeg');
  });

  test('data-plane stream reports latency for the observability chain', () async {
    final observed = <(String, String, int)>[];
    final client = CloudHttpClient(
      client: MockClient.streaming((request, bodyStream) async {
        await bodyStream.drain<void>();
        return http.StreamedResponse(const Stream<List<int>>.empty(), 204);
      }),
      latencyObserver: (method, path, elapsedMs, statusCode) =>
          observed.add((method, path, statusCode)),
    );
    addTearDown(client.close);

    final request = http.StreamedRequest('PUT', Uri.https('cdn.test', '/media/a'));
    final responseFuture = client.sendDataPlaneStream(request);
    await request.sink.close();
    await responseFuture;

    expect(observed.single, ('PUT', '/media/a', 204));
  });

  test('data-plane stream preserves abort as cancellation, not transport failure', () async {
    final client = CloudHttpClient(
      client: MockClient.streaming((request, bodyStream) async {
        await bodyStream.drain<void>();
        throw http.RequestAbortedException();
      }),
    );
    addTearDown(client.close);

    final request = http.StreamedRequest('PUT', Uri.https('cdn.test', '/object'));
    final expectation = expectLater(
      client.sendDataPlaneStream(request),
      throwsA(isA<http.RequestAbortedException>()),
      reason: '取消是产品语义，不得被映射成可重试的 CloudException',
    );
    await request.sink.close();
    await expectation;
  });

  test('data-plane stream maps transport faults through CloudErrorMapper', () async {
    final client = CloudHttpClient(
      client: MockClient.streaming((request, bodyStream) async {
        await bodyStream.drain<void>();
        throw http.ClientException('connection reset by peer');
      }),
    );
    addTearDown(client.close);

    final request = http.StreamedRequest('PUT', Uri.https('cdn.test', '/object'));
    final expectation = expectLater(
      client.sendDataPlaneStream(request),
      throwsA(isA<CloudException>()),
    );
    await request.sink.close();
    await expectation;
  });
}
