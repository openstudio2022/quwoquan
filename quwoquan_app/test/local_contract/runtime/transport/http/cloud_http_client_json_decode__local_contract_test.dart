// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-002

import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/runtime/codec/cloud_json_body_decoder.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/context/cloud_operation_header_factory.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/transport/executor/generated_cloud_operation_executor.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/runtime/observability/cloud_operation_telemetry.dart';
import 'package:quwoquan_app/runtime/transport/cloud_json_transport.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  group('CloudJsonBodyDecoder threshold and capacity', () {
    test(
      'small object stays inline and exact-threshold array uses background',
      () async {
        const objectBody = '{"v":1}';
        const arrayBody = '[{"v":1}]';
        final executions = <CloudJsonDecodeExecution>[];
        var inlineCalls = 0;
        var backgroundCalls = 0;
        final decoder = CloudJsonBodyDecoder(
          backgroundThresholdBytes: utf8.encode(arrayBody).length,
          inlineDecoder: (bytes) {
            inlineCalls += 1;
            return jsonDecode(utf8.decode(bytes));
          },
          backgroundDecoder: (bytes) async {
            backgroundCalls += 1;
            return jsonDecode(utf8.decode(bytes));
          },
          observer: (execution, _) => executions.add(execution),
        );

        final object = await decoder.decode(
          bytes: Uint8List.fromList(utf8.encode(objectBody)),
        );
        final array = await decoder.decode(
          bytes: Uint8List.fromList(utf8.encode(arrayBody)),
        );

        expect(object, <String, dynamic>{'v': 1});
        expect(array, <dynamic>[
          <String, dynamic>{'v': 1},
        ]);
        expect(inlineCalls, 1);
        expect(backgroundCalls, 1);
        expect(executions, <CloudJsonDecodeExecution>[
          CloudJsonDecodeExecution.inline,
          CloudJsonDecodeExecution.background,
        ]);
      },
    );

    test(
      'large response burst never exceeds configured decode concurrency',
      () async {
        final gates = <String, Completer<Object?>>{
          'first': Completer<Object?>(),
          'second': Completer<Object?>(),
          'third': Completer<Object?>(),
        };
        final started = <String>[];
        var active = 0;
        var peakActive = 0;
        final decoder = CloudJsonBodyDecoder(
          backgroundThresholdBytes: 1,
          maxConcurrentBackgroundDecodes: 2,
          maxPendingBackgroundDecodes: 1,
          maxQueuedBackgroundDecodeBytes: 64,
          backgroundDecoder: (bytes) {
            final source = utf8.decode(bytes);
            started.add(source);
            active += 1;
            if (active > peakActive) peakActive = active;
            return gates[source]!.future.whenComplete(() => active -= 1);
          },
        );

        final first = decoder.decode(
          bytes: Uint8List.fromList(utf8.encode('first')),
        );
        final second = decoder.decode(
          bytes: Uint8List.fromList(utf8.encode('second')),
        );
        final third = decoder.decode(
          bytes: Uint8List.fromList(utf8.encode('third')),
        );
        await Future<void>.delayed(Duration.zero);

        expect(started, <String>['first', 'second']);
        expect(peakActive, 2);

        gates['first']!.complete('first-result');
        expect(await first, 'first-result');
        await Future<void>.delayed(Duration.zero);
        expect(started, <String>['first', 'second', 'third']);

        gates['second']!.complete('second-result');
        gates['third']!.complete('third-result');
        expect(await second, 'second-result');
        expect(await third, 'third-result');
        expect(peakActive, 2);
      },
    );

    test(
      'cancelled stuck generation releases its logical slot while physical work stays bounded',
      () async {
        final firstAbort = Completer<void>();
        final secondAbort = Completer<void>();
        final gates = <String, Completer<Object?>>{
          'first': Completer<Object?>(),
          'second': Completer<Object?>(),
          'third': Completer<Object?>(),
        };
        final started = <String>[];
        final decoder = CloudJsonBodyDecoder(
          backgroundThresholdBytes: 1,
          maxConcurrentBackgroundDecodes: 1,
          maxPendingBackgroundDecodes: 1,
          maxQueuedBackgroundDecodeBytes: 64,
          maxPhysicalBackgroundDecodes: 2,
          backgroundDecoder: (bytes) {
            final source = utf8.decode(bytes);
            started.add(source);
            return gates[source]!.future;
          },
        );

        final first = decoder.decode(
          bytes: Uint8List.fromList(utf8.encode('first')),
          abortTrigger: firstAbort.future,
        );
        await Future<void>.delayed(Duration.zero);
        expect(started, <String>['first']);

        final firstFailure = expectLater(
          first,
          throwsA(isA<CloudJsonDecodeAbortedException>()),
        );
        firstAbort.complete();
        await firstFailure;

        final second = decoder.decode(
          bytes: Uint8List.fromList(utf8.encode('second')),
          abortTrigger: secondAbort.future,
        );
        await Future<void>.delayed(Duration.zero);
        expect(
          started,
          <String>['first', 'second'],
          reason:
              'the cancelled, never-completing first Future cannot hold the logical slot',
        );

        final secondFailure = expectLater(
          second,
          throwsA(isA<CloudJsonDecodeAbortedException>()),
        );
        secondAbort.complete();
        await secondFailure;

        final third = decoder.decode(
          bytes: Uint8List.fromList(utf8.encode('third')),
        );
        final rejected = decoder.decode(
          bytes: Uint8List.fromList(utf8.encode('fourth')),
        );
        await expectLater(
          rejected,
          throwsA(
            isA<CloudJsonDecodeAdmissionException>().having(
              (error) => error.reason,
              'reason',
              'pending_task_limit',
            ),
          ),
        );
        await Future<void>.delayed(Duration.zero);
        expect(
          started,
          <String>['first', 'second'],
          reason: 'retired physical Futures cap replacement generations at two',
        );

        gates['first']!.complete('late-first');
        await Future<void>.delayed(Duration.zero);
        expect(started, <String>['first', 'second', 'third']);
        gates['third']!.complete('third-result');
        expect(await third, 'third-result');

        gates['second']!.complete('late-second');
        await Future<void>.delayed(Duration.zero);
      },
    );

    test('queued response bytes have an independent hard boundary', () async {
      final activeGate = Completer<Object?>();
      final decoder = CloudJsonBodyDecoder(
        backgroundThresholdBytes: 1,
        maxResponseBytes: 64,
        maxConcurrentBackgroundDecodes: 1,
        maxPhysicalBackgroundDecodes: 1,
        maxPendingBackgroundDecodes: 2,
        maxQueuedBackgroundDecodeBytes: 6,
        backgroundDecoder: (_) => activeGate.future,
      );

      final active = decoder.decode(
        bytes: Uint8List.fromList(utf8.encode('a')),
      );
      final queued = decoder.decode(
        bytes: Uint8List.fromList(utf8.encode('123456')),
      );
      final rejected = decoder.decode(
        bytes: Uint8List.fromList(utf8.encode('b')),
      );

      await expectLater(
        rejected,
        throwsA(
          isA<CloudJsonDecodeAdmissionException>().having(
            (error) => error.reason,
            'reason',
            'queued_byte_limit',
          ),
        ),
      );
      activeGate.complete('active-result');
      expect(await active, 'active-result');
      expect(await queued, 'active-result');
    });
  });

  group('CloudHttpClient JSON caller semantics', () {
    test(
      'object and list roots keep their wire shapes across both paths',
      () async {
        const smallBody = '{"v":1}';
        final largeBody = jsonEncode(
          List<Map<String, Object?>>.generate(
            12,
            (index) => <String, Object?>{'index': index, 'label': 'feed-item'},
          ),
        );
        final executions = <CloudJsonDecodeExecution>[];
        final client = CloudHttpClient(
          client: MockClient((request) async {
            return http.Response(
              request.url.path == '/small' ? smallBody : largeBody,
              200,
              headers: const <String, String>{
                'content-type': 'application/json; charset=utf-8',
              },
            );
          }),
          jsonBodyDecoder: CloudJsonBodyDecoder(
            backgroundThresholdBytes: 32,
            observer: (execution, _) => executions.add(execution),
          ),
        );

        final object = await client.getJson(
          Uri.parse('https://api.example.test/small'),
          headers: const <String, String>{},
        );
        final list = await client.getJson(
          Uri.parse('https://api.example.test/content/feed'),
          headers: const <String, String>{},
        );

        expect(object, <String, dynamic>{'v': 1});
        expect(list, isA<List<dynamic>>());
        expect((list as List<dynamic>), hasLength(12));
        expect(executions, <CloudJsonDecodeExecution>[
          CloudJsonDecodeExecution.inline,
          CloudJsonDecodeExecution.background,
        ]);
        client.close();
      },
    );

    test(
      'malformed large JSON remains canonical typed invalid-json failure',
      () async {
        final client = CloudHttpClient(
          client: MockClient(
            (_) async => http.Response(
              '{"items": [',
              200,
              headers: const <String, String>{
                'content-type': 'application/json; charset=utf-8',
              },
            ),
          ),
          jsonBodyDecoder: CloudJsonBodyDecoder(backgroundThresholdBytes: 1),
        );

        await expectLater(
          client.getJson(
            Uri.parse('https://api.example.test/content/feed'),
            headers: const <String, String>{},
          ),
          throwsA(
            isA<CloudException>()
                .having(
                  (error) => error.runtimeFailure.code,
                  'code',
                  'APP.CONTRACT.invalid_json',
                )
                .having(
                  (error) => error.runtimeFailure.context.attributes.any(
                    (attribute) =>
                        attribute.key == 'requestPath' &&
                        attribute.value == '/content/feed',
                  ),
                  'request path',
                  isTrue,
                ),
          ),
        );
        client.close();
      },
    );

    test(
      'large generated-operation error body is background-decoded exactly once',
      () async {
        var backgroundCalls = 0;
        final executions = <CloudJsonDecodeExecution>[];
        final rawBody = jsonEncode(<String, Object?>{
          'code': 'CONTENT.SYSTEM.raw_body_must_not_be_reparsed',
          'message': 'raw-message',
          'padding': List<String>.filled(512, 'x').join(),
        });
        final client = CloudHttpClient(
          client: MockClient(
            (_) async => http.Response(
              rawBody,
              429,
              headers: const <String, String>{
                'content-type': 'application/json; charset=utf-8',
              },
            ),
          ),
          jsonBodyDecoder: CloudJsonBodyDecoder(
            backgroundThresholdBytes: 32,
            maxResponseBytes: 4096,
            backgroundDecoder: (_) async {
              backgroundCalls += 1;
              // Gateway 错误信封的用户可见文案键是 canonical `userMessage`，
              // `message` 不在信封契约内。
              return const <String, Object?>{
                'code': 'CONTENT.RATE_LIMIT.background_decoded',
                'userMessage': '请稍后重试',
              };
            },
            observer: (execution, _) => executions.add(execution),
          ),
        );

        await expectLater(
          client.getJsonAbortable(
            Uri.parse('https://api.example.test/content/feed'),
            gatewayOrigin: Uri.parse('https://api.example.test'),
            headers: const <String, String>{},
            cancellation: CloudOperationCancellationSignal(),
          ),
          throwsA(
            isA<CloudException>()
                .having((error) => error.statusCode, 'statusCode', 429)
                .having(
                  (error) => error.code,
                  'code',
                  'CONTENT.RATE_LIMIT.background_decoded',
                )
                .having((error) => error.userMessage, 'userMessage', '请稍后重试'),
          ),
        );
        expect(backgroundCalls, 1);
        expect(executions, <CloudJsonDecodeExecution>[
          CloudJsonDecodeExecution.background,
        ]);
        client.close();
      },
    );

    test(
      'minimum-build 426 signals blocking recovery before preserving the canonical failure',
      () async {
        final signals = <CloudException>[];
        http.Response responseFor(String code) => http.Response(
          jsonEncode(<String, Object?>{
            'code': code,
            'userMessage': '当前版本已不受支持，请先完成更新',
          }),
          426,
          headers: const <String, String>{
            'content-type': 'application/json; charset=utf-8',
          },
        );
        final client = CloudHttpClient(
          client: MockClient(
            (request) async => responseFor(
              request.url.path == '/unrelated'
                  ? 'GATEWAY.USER.unrelated_upgrade'
                  : cloudClientUpgradeRequiredCode,
            ),
          ),
          onClientUpgradeRequired: signals.add,
          jsonBodyDecoder: CloudJsonBodyDecoder(maxResponseBytes: 4096),
        );

        await expectLater(
          client.getJsonAbortable(
            Uri.parse('https://api.example.test/content/feed'),
            gatewayOrigin: Uri.parse('https://api.example.test'),
            headers: const <String, String>{},
            cancellation: CloudOperationCancellationSignal(),
          ),
          throwsA(
            isA<CloudException>()
                .having((error) => error.statusCode, 'statusCode', 426)
                .having(
                  (error) => error.code,
                  'code',
                  cloudClientUpgradeRequiredCode,
                ),
          ),
        );
        expect(signals, hasLength(1));

        final raw = await client.get(
          Uri.parse('https://api.example.test/legacy-business-read'),
        );
        expect(raw.statusCode, 426);
        expect(signals, hasLength(2));

        await client.get(Uri.parse('https://api.example.test/unrelated'));
        expect(signals, hasLength(2));
        client.close();
      },
    );

    test(
      'streamed response crosses byte cap before full buffering or JSON decode',
      () async {
        var decodeCalls = 0;
        final transport = _ChunkedResponseClient(<List<int>>[
          utf8.encode('{"v":'),
          utf8.encode('12345'),
          utf8.encode('}'),
        ]);
        final client = CloudHttpClient(
          client: transport,
          jsonBodyDecoder: CloudJsonBodyDecoder(
            backgroundThresholdBytes: 32,
            maxResponseBytes: 8,
            inlineDecoder: (bytes) {
              decodeCalls += 1;
              return jsonDecode(utf8.decode(bytes));
            },
          ),
        );

        await expectLater(
          client.getJsonAbortable(
            Uri.parse('https://api.example.test/content/feed'),
            gatewayOrigin: Uri.parse('https://api.example.test'),
            headers: const <String, String>{},
            cancellation: CloudOperationCancellationSignal(),
          ),
          throwsA(
            isA<CloudException>().having(
              (error) => error.runtimeFailure.code,
              'code',
              'APP.CONTRACT.invalid_response',
            ),
          ),
        );
        expect(transport.emittedChunks, 2);
        expect(decodeCalls, 0);
        client.close();
      },
    );

    test(
      'generated operation byte cap applies when the shared decoder is unbounded',
      () async {
        var decodeCalls = 0;
        final transport = _ChunkedResponseClient(<List<int>>[
          utf8.encode('{"v":'),
          utf8.encode('12345'),
          utf8.encode('}'),
        ]);
        final client = CloudHttpClient(
          client: transport,
          jsonBodyDecoder: CloudJsonBodyDecoder(
            backgroundThresholdBytes: 32,
            inlineDecoder: (bytes) {
              decodeCalls += 1;
              return jsonDecode(utf8.decode(bytes));
            },
          ),
        );

        await expectLater(
          client.sendOperationJson(
            method: 'GET',
            uri: Uri.parse('https://api.example.test/content/feed'),
            gatewayOrigin: Uri.parse('https://api.example.test'),
            headers: const <String, String>{},
            requireAuth: false,
            abortTrigger: Completer<void>().future,
            maximumResponseBodyBytes: 8,
          ),
          throwsA(
            isA<CloudException>().having(
              (error) => error.runtimeFailure.code,
              'code',
              'APP.CONTRACT.invalid_response',
            ),
          ),
        );
        expect(transport.emittedChunks, 2);
        expect(decodeCalls, 0);
        client.close();
      },
    );

    test(
      'cancellation interrupts an in-flight background decode as typed cancelled',
      () async {
        final decodeStarted = Completer<void>();
        final decodeGate = Completer<Object?>();
        final client = CloudHttpClient(
          client: MockClient(
            (_) async => http.Response(
              '{"items":[]}',
              200,
              headers: const <String, String>{
                'content-type': 'application/json; charset=utf-8',
              },
            ),
          ),
          jsonBodyDecoder: CloudJsonBodyDecoder(
            backgroundThresholdBytes: 1,
            backgroundDecoder: (_) {
              decodeStarted.complete();
              return decodeGate.future;
            },
          ),
        );
        final cancellation = CloudOperationCancellationSignal();
        final request = client.getJsonAbortable(
          Uri.parse('https://api.example.test/content/feed'),
          gatewayOrigin: Uri.parse('https://api.example.test'),
          headers: const <String, String>{},
          cancellation: cancellation,
        );

        await decodeStarted.future;
        cancellation.cancel();
        await expectLater(
          request,
          throwsA(
            isA<CloudException>().having(
              (error) => error.runtimeFailure.code,
              'code',
              'APP.CANCELLED.operation_cancelled',
            ),
          ),
        );

        decodeGate.complete(const <String, dynamic>{'items': <dynamic>[]});
        await Future<void>.delayed(Duration.zero);
        client.close();
      },
    );

    test(
      'generated deadline interrupts decode as canonical typed timeout',
      () async {
        final decodeStarted = Completer<void>();
        final decodeGate = Completer<Object?>();
        final client = CloudHttpClient(
          client: MockClient(
            (_) async => http.Response(
              '{"items":[]}',
              200,
              headers: const <String, String>{
                'content-type': 'application/json; charset=utf-8',
              },
            ),
          ),
          jsonBodyDecoder: CloudJsonBodyDecoder(
            backgroundThresholdBytes: 1,
            backgroundDecoder: (_) {
              decodeStarted.complete();
              return decodeGate.future;
            },
          ),
        );
        final executor = AppGeneratedCloudOperationExecutor(
          environment: CloudRuntimeEnvironment(
            environment: CloudEnvironment.gamma,
            gatewayBaseUri: Uri.parse('https://api.example.test'),
          ),
          transport: HttpCloudJsonTransport(client),
          headerFactory: CloudOperationHeaderFactory(
            clientContextProvider: const FallbackCloudClientContextProvider(),
          ),
          telemetrySink: const _NoopCloudOperationTelemetry(),
        );
        final request = executor.send<Object?>(
          appCloudOperationContracts[AppCloudOperationIds.contentPostGetFeed]!,
          context: CloudOperationInvocationContext(
            surfaceId: 'homeFeed',
            clientPageId: 'homeFeed',
            actor: const CloudOperationActorContext(),
            deadlineAt: DateTime.now().add(const Duration(seconds: 1)),
          ),
          responseDecoder: (value) => value,
          requestEncoder: () => CloudOperationRequestPayload(),
        );

        await decodeStarted.future;
        await expectLater(
          request,
          throwsA(
            isA<CloudException>().having(
              (error) => error.runtimeFailure.code,
              'code',
              'APP.TIMEOUT.request_timeout',
            ),
          ),
        );

        decodeGate.complete(const <String, dynamic>{'items': <dynamic>[]});
        await Future<void>.delayed(Duration.zero);
        client.close();
      },
    );
  });

  group('Content discovery feed envelope admission', () {
    test(
      'App query refuses a requested page larger than its 20-item budget',
      () {
        expect(
          () => encodeContentPostGetFeedGeneratedRequest(
            ContentDiscoveryFeedQuery(
              limit: contentDiscoveryFeedMaxPageItems + 1,
            ),
          ),
          throwsArgumentError,
        );
      },
    );

    test('items 中的非对象条目在 Post projection 物化前失败', () {
      expect(
        () => _decodeFeedEnvelope(items: <Object?>[null]),
        throwsA(
          isA<FormatException>().having(
            (error) => error.message,
            'message',
            contains('items[0] must be an object'),
          ),
        ),
      );
    });

    test('object cards reject recursive or unknown fields before mapping', () {
      expect(
        () => _decodeFeedEnvelope(
          items: <Object?>[_feedItemWire()],
          objectCards: <Object?>[
            <String, Object?>{
              ..._feedObjectCardWire(),
              'nested': <String, Object?>{'unbounded': true},
            },
          ],
        ),
        throwsA(
          isA<FormatException>().having(
            (error) => error.message,
            'message',
            contains('unknown field'),
          ),
        ),
      );
    });

    test('bidirectional cursor envelope decodes an explicit expiry', () {
      final page = _decodeFeedEnvelope(
        items: <Object?>[_feedItemWire()],
        extra: <String, Object?>{
          'nextCursor': 'fc.next',
          'previousCursor': 'fc.previous',
          'paginationExpiresAt': '2026-07-29T12:00:00Z',
        },
      );

      expect(page.nextCursor, 'fc.next');
      expect(page.previousCursor, 'fc.previous');
      expect(page.paginationExpiresAt, DateTime.utc(2026, 7, 29, 12));
    });

    test('malformed pagination expiry fails closed', () {
      expect(
        () => _decodeFeedEnvelope(
          extra: <String, Object?>{
            'previousCursor': 'fc.previous',
            'paginationExpiresAt': 'not-a-timestamp',
          },
        ),
        throwsFormatException,
      );
    });

    test('empty feed requires canonical outcome and bounded emptyReason', () {
      for (final extra in <Map<String, Object?>>[
        <String, Object?>{'outcome': null},
        <String, Object?>{'outcome': 'future_outcome'},
        <String, Object?>{'outcome': 'empty', 'emptyReason': 'future_reason'},
      ]) {
        expect(
          () => _decodeFeedEnvelope(extra: extra),
          throwsFormatException,
          reason: 'must reject malformed empty envelope $extra',
        );
      }

      final page = _decodeFeedEnvelope(
        extra: <String, Object?>{
          'outcome': 'empty',
          'emptyReason': 'no_active_release',
        },
      );
      expect(page.outcome, ContentFeedOutcome.empty);
      expect(page.emptyReason, ContentFeedEmptyReason.noActiveRelease);
    });

    test('feed envelope 只接受精确 canonical policyDigest 或未提供', () {
      const canonical =
          'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
      expect(
        _decodeFeedEnvelope(
          extra: <String, Object?>{
            'outcome': 'empty',
            'emptyReason': 'no_eligible_content',
            'policyDigest': canonical,
          },
        ).policyDigest,
        canonical,
      );
      expect(
        _decodeFeedEnvelope(
          extra: <String, Object?>{
            'outcome': 'empty',
            'emptyReason': 'no_eligible_content',
          },
        ).policyDigest,
        isNull,
      );
      expect(
        _decodeFeedEnvelope(
          extra: <String, Object?>{
            'outcome': 'empty',
            'emptyReason': 'no_eligible_content',
            'policyDigest': null,
          },
        ).policyDigest,
        isNull,
      );

      // 非字符串 digest 仍然 fail-closed；digest 字形（sha256:<64 hex>）的
      // 精确校验属于 metadata-driven-client-data-contract OPEN-004 记录的
      // codegen 缺口，不在此处伪造第二真相源。
      for (final invalid in <Object?>[42, <String, Object?>{}]) {
        expect(
          () => _decodeFeedEnvelope(
            extra: <String, Object?>{
              'outcome': 'empty',
              'emptyReason': 'no_eligible_content',
              'policyDigest': invalid,
            },
          ),
          throwsFormatException,
          reason: 'must reject <$invalid> without coercion or normalization',
        );
      }
    });
  });
}

/// canonical feed 信封的最小合法 wire：generated decoder 现在要求 `outcome`、
/// `feedRequestId` 与 `objectCards` 全部到位，缺一即 fail-closed。
ContentDiscoveryFeedPageSlice _decodeFeedEnvelope({
  List<Object?> items = const <Object?>[],
  List<Object?> objectCards = const <Object?>[],
  Map<String, Object?> extra = const <String, Object?>{},
}) {
  return decodeContentDiscoveryFeedPageSlice(<String, Object?>{
    'items': items,
    'objectCards': objectCards,
    'outcome': items.isEmpty ? 'empty' : 'content',
    if (items.isEmpty) 'emptyReason': 'no_eligible_content',
    'feedRequestId': 'fr_local_contract',
    ...extra,
  });
}

Map<String, Object?> _feedItemWire({String postId = 'post-1'}) =>
    <String, Object?>{
      'postId': postId,
      'contentType': 'image_text',
      'likeCount': 0,
      'commentCount': 0,
      'shareCount': 0,
    };

Map<String, Object?> _feedObjectCardWire({String objectId = 'homepage-1'}) =>
    <String, Object?>{
      'objectKind': 'homepage',
      'objectId': objectId,
      'title': '首页卡片',
      'tagRefs': const <Object?>[],
      'anchorIndex': 0,
    };

final class _ChunkedResponseClient extends http.BaseClient {
  _ChunkedResponseClient(this.chunks);

  final List<List<int>> chunks;
  int emittedChunks = 0;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final stream = Stream<List<int>>.fromIterable(chunks).map((chunk) {
      emittedChunks += 1;
      return chunk;
    });
    return http.StreamedResponse(
      stream,
      200,
      request: request,
      headers: const <String, String>{
        'content-type': 'application/json; charset=utf-8',
      },
    );
  }
}

final class _NoopCloudOperationTelemetry
    implements CloudOperationTelemetrySink {
  const _NoopCloudOperationTelemetry();

  @override
  void record(CloudOperationTelemetryEvent event) {}
}
