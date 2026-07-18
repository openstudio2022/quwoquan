import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('可见读取取消会触发 AbortableRequest transport abort', () async {
    final transport = _HangingAbortAwareClient();
    final client = CloudHttpClient(client: transport);
    final cancellation = CloudOperationCancellationSignal();
    final uri = Uri.parse('https://api.example.test/search');

    final request = client.getJsonAbortable(
      uri,
      gatewayOrigin: Uri.parse('https://api.example.test'),
      headers: const <String, String>{},
      cancellation: cancellation,
    );
    await transport.requestStarted.future;

    cancellation.cancel();

    await expectLater(request, throwsA(isA<CloudException>()));
    expect(transport.abortObserved, isTrue);
  });
}

final class _HangingAbortAwareClient extends http.BaseClient {
  final Completer<void> requestStarted = Completer<void>();
  bool abortObserved = false;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) {
    final completer = Completer<http.StreamedResponse>();
    requestStarted.complete();
    final abortable = request as http.AbortableRequest;
    abortable.abortTrigger!.then((_) {
      abortObserved = true;
      completer.completeError(http.RequestAbortedException(request.url));
    });
    return completer.future;
  }
}
