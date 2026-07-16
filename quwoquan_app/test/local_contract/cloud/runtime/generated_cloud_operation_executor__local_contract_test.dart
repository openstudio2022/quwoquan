import 'dart:async';

import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/cloud/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/cloud/runtime/context/cloud_operation_header_factory.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/cloud/runtime/executor/generated_cloud_operation_executor.dart';
import 'package:quwoquan_app/cloud/runtime/generated/integration/integration_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/observability/cloud_operation_telemetry.dart';
import 'package:quwoquan_app/cloud/runtime/transport/cloud_json_transport.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  final searchOperation =
      appCloudOperationContracts[AppCloudOperationIds
          .integrationLocationSearchLocations]!;
  final nearbyOperation =
      appCloudOperationContracts[AppCloudOperationIds
          .integrationLocationGetNearbyLocations]!;
  final reportOperation =
      appCloudOperationContracts[AppCloudOperationIds
          .contentReportCreateReport]!;
  final fixedNow = DateTime.utc(2026, 7, 13, 1, 2, 3);
  const clientContext = _FixedClientContextProvider();

  CloudOperationInvocationContext invocation({
    DateTime? deadlineAt,
    String surfaceId = 'createWorkspace',
  }) {
    return CloudOperationInvocationContext(
      surfaceId: surfaceId,
      clientPageId: IntegrationRequestPageIds.searchLocations,
      routeId: 'create',
      referralSource: 'createEntry',
      idempotencyKey: 'request-1',
      deadlineAt: deadlineAt ?? fixedNow.add(const Duration(seconds: 5)),
      actor: const CloudOperationActorContext(
        accountId: 'account-1',
        personaId: 'persona-1',
      ),
    );
  }

  group('CloudRuntimeEnvironment', () {
    test('prod 仅接受无凭据、无 query 的 HTTPS Gateway', () {
      expect(
        () => CloudRuntimeEnvironment(
          environment: CloudEnvironment.prod,
          gatewayBaseUri: Uri.parse('http://api.example.test'),
        ),
        throwsArgumentError,
      );
      expect(
        () => CloudRuntimeEnvironment(
          environment: CloudEnvironment.prod,
          gatewayBaseUri: Uri.parse(
            'https://token@api.example.test?secret=value',
          ),
        ),
        throwsArgumentError,
      );
      expect(
        CloudRuntimeEnvironment(
          environment: CloudEnvironment.prod,
          gatewayBaseUri: Uri.parse('https://api.example.test/gateway'),
        ).gatewayBaseUri.path,
        '/gateway',
      );
    });
  });

  group('CloudOperationHeaderFactory', () {
    test('仅按 operation 需求披露 actor，并生成追踪、归因、幂等与 deadline headers', () {
      final headers = CloudOperationHeaderFactory(
        clientContextProvider: clientContext,
        now: () => fixedNow,
        entropy: () => 7,
      ).build(operation: searchOperation, invocation: invocation());

      expect(
        headers['X-Client-Operation-Id'],
        searchOperation.canonicalOperationId,
      );
      expect(headers['X-Client-Surface-Id'], 'createWorkspace');
      expect(headers['X-Client-Account-Id'], isNull);
      expect(headers['X-Client-Persona-Id'], isNull);
      expect(headers['X-Client-Device-Actor-Id'], isNull);
      expect(headers['X-Referral-Source'], 'createEntry');
      expect(headers['Idempotency-Key'], 'request-1');
      expect(headers['X-Client-Deadline-At'], '2026-07-13T01:02:08.000Z');
      expect(
        headers['X-Trace-Id'],
        contains(searchOperation.canonicalOperationId),
      );
    });

    test('拒绝越权 surface、缺失 actor、过期 deadline 与 header 注入', () {
      final factory = CloudOperationHeaderFactory(
        clientContextProvider: clientContext,
        now: () => fixedNow,
      );
      final factoryWithoutDevice = CloudOperationHeaderFactory(
        clientContextProvider: const _NoDeviceClientContextProvider(),
        now: () => fixedNow,
      );
      expect(
        () => factory.build(
          operation: searchOperation,
          invocation: invocation(surfaceId: 'unboundSurface'),
        ),
        throwsArgumentError,
      );
      expect(
        () => factoryWithoutDevice.build(
          operation: nearbyOperation,
          invocation: CloudOperationInvocationContext(
            surfaceId: 'createWorkspace',
            clientPageId: IntegrationRequestPageIds.getNearbyLocations,
            actor: const CloudOperationActorContext(),
            deadlineAt: fixedNow.add(const Duration(seconds: 1)),
          ),
        ),
        throwsArgumentError,
      );
      expect(
        () => factory.build(
          operation: searchOperation,
          invocation: invocation(deadlineAt: fixedNow),
        ),
        throwsArgumentError,
      );
      expect(
        () => factory.build(
          operation: searchOperation,
          invocation: CloudOperationInvocationContext(
            surfaceId: 'createWorkspace',
            clientPageId:
                '${IntegrationRequestPageIds.searchLocations}\r\nX-Injected: true',
            actor: const CloudOperationActorContext(personaId: 'persona-1'),
            deadlineAt: fixedNow.add(const Duration(seconds: 1)),
          ),
        ),
        throwsArgumentError,
      );
    });
  });

  group('AppGeneratedCloudOperationExecutor', () {
    test('保留 Gateway prefix、编码 query 并记录成功 telemetry', () async {
      final transport = _RecordingTransport(
        response: <String, dynamic>{'items': <dynamic>[]},
      );
      final telemetry = _RecordingTelemetry();
      final executor = AppGeneratedCloudOperationExecutor(
        environment: CloudRuntimeEnvironment(
          environment: CloudEnvironment.gamma,
          gatewayBaseUri: Uri.parse('https://api.example.test/gateway'),
        ),
        transport: transport,
        headerFactory: CloudOperationHeaderFactory(
          clientContextProvider: clientContext,
          now: () => fixedNow,
          entropy: () => 9,
        ),
        telemetrySink: telemetry,
        now: () => fixedNow,
      );

      final response = await executor.send<Object?>(
        searchOperation,
        context: invocation(),
        responseDecoder: (value) => value,
        requestEncoder: () => const CloudOperationRequestPayload(
          queryParameters: <String, String>{'q': '咖啡/茶', 'limit': '20'},
        ),
      );

      expect(response, <String, dynamic>{'items': <dynamic>[]});
      expect(transport.request, isNotNull);
      expect(
        transport.request!.uri.toString(),
        'https://api.example.test/gateway/v1/integration/location/search?'
        'q=%E5%92%96%E5%95%A1%2F%E8%8C%B6&limit=20',
      );
      expect(telemetry.events, hasLength(1));
      expect(telemetry.events.single.succeeded, isTrue);
    });

    test('请求成功后立即释放 operation deadline timer', () {
      fakeAsync((clock) {
        final executor = AppGeneratedCloudOperationExecutor(
          environment: CloudRuntimeEnvironment(
            environment: CloudEnvironment.gamma,
            gatewayBaseUri: Uri.parse('https://api.example.test'),
          ),
          transport: _RecordingTransport(
            response: const <String, dynamic>{'items': <dynamic>[]},
          ),
          headerFactory: CloudOperationHeaderFactory(
            clientContextProvider: clientContext,
            now: () => fixedNow,
          ),
          telemetrySink: _RecordingTelemetry(),
          now: () => fixedNow,
        );
        var completed = false;

        executor
            .send<Object?>(
              searchOperation,
              context: invocation(),
              responseDecoder: (value) => value,
              requestEncoder: _emptyRequestEncoder,
            )
            .then((_) => completed = true);
        clock.flushMicrotasks();

        expect(completed, isTrue);
        expect(clock.pendingTimers, isEmpty);
      });
    });

    test('拒绝 GET body', () async {
      final executor = AppGeneratedCloudOperationExecutor(
        environment: CloudRuntimeEnvironment(
          environment: CloudEnvironment.gamma,
          gatewayBaseUri: Uri.parse('https://api.example.test'),
        ),
        transport: _RecordingTransport(response: const <String, dynamic>{}),
        headerFactory: CloudOperationHeaderFactory(
          clientContextProvider: clientContext,
          now: () => fixedNow,
        ),
        telemetrySink: _RecordingTelemetry(),
        now: () => fixedNow,
      );

      await expectLater(
        executor.send<Object?>(
          searchOperation,
          context: invocation(),
          responseDecoder: (value) => value,
          requestEncoder: () => const CloudOperationRequestPayload(
            body: <String, dynamic>{'unexpected': true},
          ),
        ),
        throwsA(
          isA<CloudException>().having(
            (error) => error.runtimeFailure.code,
            'code',
            'APP.CONTRACT.invalid_response',
          ),
        ),
      );
    });

    test('取消或 deadline 耗尽时不得执行 encoder 或发网', () async {
      final transport = _RecordingTransport(
        response: const <String, dynamic>{},
      );
      final executor = AppGeneratedCloudOperationExecutor(
        environment: CloudRuntimeEnvironment(
          environment: CloudEnvironment.gamma,
          gatewayBaseUri: Uri.parse('https://api.example.test'),
        ),
        transport: transport,
        headerFactory: CloudOperationHeaderFactory(
          clientContextProvider: clientContext,
          now: () => fixedNow,
        ),
        telemetrySink: _RecordingTelemetry(),
        now: () => fixedNow,
      );
      var encoderCalls = 0;
      final cancellation = CloudOperationCancellationSignal()..cancel();

      await expectLater(
        executor.send<Object?>(
          searchOperation,
          context: CloudOperationInvocationContext(
            surfaceId: 'createWorkspace',
            clientPageId: IntegrationRequestPageIds.searchLocations,
            actor: const CloudOperationActorContext(personaId: 'persona-1'),
            deadlineAt: fixedNow.add(const Duration(seconds: 5)),
            cancellation: cancellation,
          ),
          responseDecoder: (value) => value,
          requestEncoder: () {
            encoderCalls += 1;
            return const CloudOperationRequestPayload();
          },
        ),
        throwsA(
          isA<CloudException>().having(
            (error) => error.runtimeFailure.code,
            'code',
            'APP.CANCELLED.operation_cancelled',
          ),
        ),
      );
      await expectLater(
        executor.send<Object?>(
          searchOperation,
          context: invocation(deadlineAt: fixedNow),
          responseDecoder: (value) => value,
          requestEncoder: () {
            encoderCalls += 1;
            return const CloudOperationRequestPayload();
          },
        ),
        throwsA(
          isA<CloudException>().having(
            (error) => error.runtimeFailure.code,
            'code',
            'APP.TIMEOUT.request_timeout',
          ),
        ),
      );

      expect(encoderCalls, 0);
      expect(transport.requests, isEmpty);
    });

    test('typed request encoder 在 executor 内只执行一次，编码失败统一映射', () async {
      var encodeCalls = 0;
      final transport = _RecordingTransport(
        handler: (request) {
          if (request.headers['X-Client-Attempt'] == '1') {
            throw CloudErrorMapper.fromStatusCode(
              503,
              requestPath: request.uri.path,
            );
          }
          return const <String, dynamic>{'items': <dynamic>[]};
        },
      );
      final executor = AppGeneratedCloudOperationExecutor(
        environment: CloudRuntimeEnvironment(
          environment: CloudEnvironment.gamma,
          gatewayBaseUri: Uri.parse('https://api.example.test'),
        ),
        transport: transport,
        headerFactory: CloudOperationHeaderFactory(
          clientContextProvider: clientContext,
          now: () => fixedNow,
        ),
        telemetrySink: _RecordingTelemetry(),
        now: () => fixedNow,
        sleeper: (_) async {},
      );

      await executor.send<Object?>(
        searchOperation,
        context: invocation(),
        responseDecoder: (value) => value,
        requestEncoder: () {
          encodeCalls += 1;
          return const CloudOperationRequestPayload(
            queryParameters: <String, String>{'q': '咖啡'},
          );
        },
      );

      expect(encodeCalls, 1);
      expect(transport.requests, hasLength(2));
      expect(transport.requests.last.uri.queryParameters['q'], '咖啡');

      final rejectedTransport = _RecordingTransport(response: null);
      final rejectedExecutor = AppGeneratedCloudOperationExecutor(
        environment: CloudRuntimeEnvironment(
          environment: CloudEnvironment.gamma,
          gatewayBaseUri: Uri.parse('https://api.example.test'),
        ),
        transport: rejectedTransport,
        headerFactory: CloudOperationHeaderFactory(
          clientContextProvider: clientContext,
          now: () => fixedNow,
        ),
        telemetrySink: _RecordingTelemetry(),
        now: () => fixedNow,
      );
      await expectLater(
        rejectedExecutor.send<Object?>(
          searchOperation,
          context: invocation(),
          responseDecoder: (value) => value,
          requestEncoder: () => throw const FormatException('bad request'),
        ),
        throwsA(
          isA<CloudException>().having(
            (error) => error.runtimeFailure.code,
            'code',
            'APP.CONTRACT.invalid_json',
          ),
        ),
      );
      expect(rejectedTransport.requests, isEmpty);
    });

    test('仅合并 generated If-Match，拒绝业务请求编码器注入 runtime header', () async {
      final transport = _RecordingTransport(
        response: const <String, dynamic>{},
      );
      final executor = AppGeneratedCloudOperationExecutor(
        environment: CloudRuntimeEnvironment(
          environment: CloudEnvironment.gamma,
          gatewayBaseUri: Uri.parse('https://api.example.test'),
        ),
        transport: transport,
        headerFactory: CloudOperationHeaderFactory(
          clientContextProvider: clientContext,
          now: () => fixedNow,
        ),
        telemetrySink: _RecordingTelemetry(),
        now: () => fixedNow,
      );
      final commandInvocation = CloudOperationInvocationContext(
        surfaceId: 'homeFeed',
        clientPageId: 'content.report.create',
        idempotencyKey: 'report-request-1',
        deadlineAt: fixedNow.add(const Duration(seconds: 1)),
        actor: const CloudOperationActorContext(
          accountId: 'account-1',
          personaId: 'persona-1',
        ),
      );

      await executor.send<Object?>(
        reportOperation,
        context: commandInvocation,
        responseDecoder: (value) => value,
        requestEncoder: () => const CloudOperationRequestPayload(
          headers: <String, String>{'If-Match': '"7"'},
        ),
      );

      expect(transport.request!.headers['If-Match'], '"7"');
      expect(transport.request!.headers['Idempotency-Key'], 'report-request-1');
      expect(transport.request!.headers['X-Client-Persona-Id'], 'persona-1');

      final rejectedTransport = _RecordingTransport(response: null);
      final rejectedExecutor = AppGeneratedCloudOperationExecutor(
        environment: executor.environment,
        transport: rejectedTransport,
        headerFactory: executor.headerFactory,
        telemetrySink: _RecordingTelemetry(),
        now: () => fixedNow,
      );
      await expectLater(
        rejectedExecutor.send<Object?>(
          reportOperation,
          context: commandInvocation,
          responseDecoder: (value) => value,
          requestEncoder: () => const CloudOperationRequestPayload(
            headers: <String, String>{'Authorization': 'Bearer forged'},
          ),
        ),
        throwsA(
          isA<CloudException>().having(
            (error) => error.runtimeFailure.code,
            'code',
            'APP.CONTRACT.invalid_response',
          ),
        ),
      );
      expect(rejectedTransport.requests, isEmpty);
    });

    test('失败记录不可含实例 URL 或请求 body', () async {
      final telemetry = _RecordingTelemetry();
      final executor = AppGeneratedCloudOperationExecutor(
        environment: CloudRuntimeEnvironment(
          environment: CloudEnvironment.gamma,
          gatewayBaseUri: Uri.parse('https://api.example.test'),
        ),
        transport: _RecordingTransport(error: StateError('transport failed')),
        headerFactory: CloudOperationHeaderFactory(
          clientContextProvider: clientContext,
          now: () => fixedNow,
        ),
        telemetrySink: telemetry,
        now: () => fixedNow,
      );

      await expectLater(
        executor.send<Object?>(
          searchOperation,
          context: invocation(),
          responseDecoder: (value) => value,
          requestEncoder: () => const CloudOperationRequestPayload(
            queryParameters: <String, String>{'q': 'private-keyword'},
          ),
        ),
        throwsA(isA<CloudException>()),
      );
      expect(telemetry.events, hasLength(1));
      expect(telemetry.events.single.succeeded, isFalse);
      expect(
        telemetry.events.single.pathTemplate,
        searchOperation.pathTemplate,
      );
      expect(
        telemetry.events.single.pathTemplate,
        isNot(contains('private-keyword')),
      );
    });

    test('503 仅按 Graph maxAttempts 重试并记录真实 attempt', () async {
      final transport = _RecordingTransport(
        handler: (request) {
          if (request.headers['X-Client-Attempt'] == '1') {
            throw CloudErrorMapper.fromStatusCode(
              503,
              requestPath: request.uri.path,
            );
          }
          return <String, dynamic>{'items': <dynamic>[]};
        },
      );
      final telemetry = _RecordingTelemetry();
      final delays = <Duration>[];
      final executor = AppGeneratedCloudOperationExecutor(
        environment: CloudRuntimeEnvironment(
          environment: CloudEnvironment.gamma,
          gatewayBaseUri: Uri.parse('https://api.example.test'),
        ),
        transport: transport,
        headerFactory: CloudOperationHeaderFactory(
          clientContextProvider: clientContext,
          now: () => fixedNow,
        ),
        telemetrySink: telemetry,
        now: () => fixedNow,
        sleeper: (delay) async => delays.add(delay),
        jitterUnit: () => 0.5,
      );

      await executor.send<Object?>(
        searchOperation,
        context: invocation(),
        responseDecoder: (value) => value,
        requestEncoder: _emptyRequestEncoder,
      );

      expect(transport.requests, hasLength(2));
      expect(
        transport.requests.map(
          (request) => request.headers['X-Client-Attempt'],
        ),
        <String?>['1', '2'],
      );
      expect(delays, hasLength(1));
      expect(telemetry.events.map((event) => event.attempt), <int>[1, 2]);
      expect(telemetry.events.first.retryReason, 'retryable_status');
      expect(telemetry.events.last.succeeded, isTrue);
    });

    test('429 尊重 Retry-After，401 刷新也受同一 operation deadline 约束', () async {
      final rateLimitedTransport = _RecordingTransport(
        handler: (request) {
          if (request.headers['X-Client-Attempt'] == '1') {
            throw CloudErrorMapper.fromStatusCode(
              429,
              requestPath: request.uri.path,
              retryAfter: '1',
            );
          }
          return const <String, dynamic>{'items': <dynamic>[]};
        },
      );
      final delays = <Duration>[];
      final rateLimitedExecutor = AppGeneratedCloudOperationExecutor(
        environment: CloudRuntimeEnvironment(
          environment: CloudEnvironment.gamma,
          gatewayBaseUri: Uri.parse('https://api.example.test'),
        ),
        transport: rateLimitedTransport,
        headerFactory: CloudOperationHeaderFactory(
          clientContextProvider: clientContext,
          now: () => fixedNow,
        ),
        telemetrySink: _RecordingTelemetry(),
        now: () => fixedNow,
        sleeper: (delay) async => delays.add(delay),
      );

      await rateLimitedExecutor.send<Object?>(
        searchOperation,
        context: invocation(),
        responseDecoder: (value) => value,
        requestEncoder: _emptyRequestEncoder,
      );
      expect(delays, <Duration>[const Duration(seconds: 1)]);

      final refreshTransport = _RecordingTransport(
        handler: (request) {
          if (request.headers['X-Client-Attempt'] == '1') {
            throw CloudErrorMapper.fromStatusCode(
              401,
              requestPath: request.uri.path,
            );
          }
          return const <String, dynamic>{'items': <dynamic>[]};
        },
        refreshHandler: (_) async => true,
      );
      final refreshExecutor = AppGeneratedCloudOperationExecutor(
        environment: CloudRuntimeEnvironment(
          environment: CloudEnvironment.gamma,
          gatewayBaseUri: Uri.parse('https://api.example.test'),
        ),
        transport: refreshTransport,
        headerFactory: CloudOperationHeaderFactory(
          clientContextProvider: clientContext,
          now: () => fixedNow,
        ),
        telemetrySink: _RecordingTelemetry(),
        now: () => fixedNow,
        sleeper: (_) async {},
      );

      await refreshExecutor.send<Object?>(
        searchOperation,
        context: invocation(),
        responseDecoder: (value) => value,
        requestEncoder: _emptyRequestEncoder,
      );
      expect(refreshTransport.refreshCount, 1);
      expect(refreshTransport.requests, hasLength(2));

      final failedRefreshTelemetry = _RecordingTelemetry();
      final failedRefreshTransport = _RecordingTransport(
        error: CloudErrorMapper.fromStatusCode(
          401,
          requestPath: searchOperation.pathTemplate,
        ),
        refreshHandler: (_) => throw TimeoutException('refresh timed out'),
      );
      final failedRefreshExecutor = AppGeneratedCloudOperationExecutor(
        environment: CloudRuntimeEnvironment(
          environment: CloudEnvironment.gamma,
          gatewayBaseUri: Uri.parse('https://api.example.test'),
        ),
        transport: failedRefreshTransport,
        headerFactory: CloudOperationHeaderFactory(
          clientContextProvider: clientContext,
          now: () => fixedNow,
        ),
        telemetrySink: failedRefreshTelemetry,
        now: () => fixedNow,
        sleeper: (_) async {},
      );

      await expectLater(
        failedRefreshExecutor.send<Object?>(
          searchOperation,
          context: invocation(),
          responseDecoder: (value) => value,
          requestEncoder: _emptyRequestEncoder,
        ),
        throwsA(
          isA<CloudException>().having(
            (error) => error.runtimeFailure.code,
            'code',
            'APP.TIMEOUT.request_timeout',
          ),
        ),
      );
      expect(failedRefreshTransport.refreshCount, 1);
      expect(
        failedRefreshTelemetry.events.single.failureCode,
        'APP.TIMEOUT.request_timeout',
      );
    });

    test('command 缺幂等键发网前失败；有键时安全重放且键不变', () async {
      final rejectedTransport = _RecordingTransport(response: null);
      final rejectedExecutor = AppGeneratedCloudOperationExecutor(
        environment: CloudRuntimeEnvironment(
          environment: CloudEnvironment.gamma,
          gatewayBaseUri: Uri.parse('https://api.example.test'),
        ),
        transport: rejectedTransport,
        headerFactory: CloudOperationHeaderFactory(
          clientContextProvider: clientContext,
          now: () => fixedNow,
        ),
        telemetrySink: _RecordingTelemetry(),
        now: () => fixedNow,
      );
      final noIdempotency = CloudOperationInvocationContext(
        surfaceId: 'homeFeed',
        clientPageId: 'content.report.create',
        actor: const CloudOperationActorContext(personaId: 'persona-1'),
        deadlineAt: fixedNow.add(const Duration(seconds: 5)),
      );

      await expectLater(
        rejectedExecutor.send<void>(
          reportOperation,
          context: noIdempotency,
          responseDecoder: (_) {},
          requestEncoder: () => const CloudOperationRequestPayload(
            body: <String, dynamic>{'targetId': 'post-1'},
          ),
        ),
        throwsA(isA<CloudException>()),
      );
      expect(rejectedTransport.requests, isEmpty);

      final retryingTransport = _RecordingTransport(
        handler: (request) {
          if (request.headers['X-Client-Attempt'] == '1') {
            throw CloudErrorMapper.fromStatusCode(
              503,
              requestPath: request.uri.path,
            );
          }
          return const <String, dynamic>{};
        },
      );
      final executor = AppGeneratedCloudOperationExecutor(
        environment: CloudRuntimeEnvironment(
          environment: CloudEnvironment.gamma,
          gatewayBaseUri: Uri.parse('https://api.example.test'),
        ),
        transport: retryingTransport,
        headerFactory: CloudOperationHeaderFactory(
          clientContextProvider: clientContext,
          now: () => fixedNow,
        ),
        telemetrySink: _RecordingTelemetry(),
        now: () => fixedNow,
        sleeper: (_) async {},
      );
      final commandContext = CloudOperationInvocationContext(
        surfaceId: 'homeFeed',
        clientPageId: 'content.report.create',
        idempotencyKey: 'report-key-1',
        actor: const CloudOperationActorContext(personaId: 'persona-1'),
        deadlineAt: fixedNow.add(const Duration(seconds: 5)),
      );

      await executor.send<void>(
        reportOperation,
        context: commandContext,
        responseDecoder: (_) {},
        requestEncoder: () => const CloudOperationRequestPayload(
          body: <String, dynamic>{'targetId': 'post-1'},
        ),
      );

      expect(retryingTransport.requests, hasLength(2));
      expect(
        retryingTransport.requests
            .map((request) => request.headers['Idempotency-Key'])
            .toSet(),
        <String?>{'report-key-1'},
      );
    });

    test('取消与 deadline 都映射为结构化 RuntimeFailure', () async {
      final cancellation = CloudOperationCancellationSignal();
      final cancelTransport = _RecordingTransport(
        handler: (request) async {
          scheduleMicrotask(cancellation.cancel);
          await request.abortTrigger;
          throw const CloudOperationCancelledException();
        },
      );
      final cancelTelemetry = _RecordingTelemetry();
      final cancelExecutor = AppGeneratedCloudOperationExecutor(
        environment: CloudRuntimeEnvironment(
          environment: CloudEnvironment.gamma,
          gatewayBaseUri: Uri.parse('https://api.example.test'),
        ),
        transport: cancelTransport,
        headerFactory: CloudOperationHeaderFactory(
          clientContextProvider: clientContext,
          now: () => fixedNow,
        ),
        telemetrySink: cancelTelemetry,
        now: () => fixedNow,
      );

      await expectLater(
        cancelExecutor.send<Object?>(
          searchOperation,
          context: CloudOperationInvocationContext(
            surfaceId: 'createWorkspace',
            clientPageId: IntegrationRequestPageIds.searchLocations,
            actor: const CloudOperationActorContext(personaId: 'persona-1'),
            deadlineAt: fixedNow.add(const Duration(seconds: 5)),
            cancellation: cancellation,
          ),
          responseDecoder: (value) => value,
          requestEncoder: _emptyRequestEncoder,
        ),
        throwsA(
          isA<CloudException>().having(
            (error) => error.runtimeFailure.code,
            'code',
            'APP.CANCELLED.operation_cancelled',
          ),
        ),
      );
      expect(cancelTelemetry.events.single.disruptionLevel, 'silent');

      var clock = fixedNow;
      final deadlineTransport = _RecordingTransport(
        handler: (request) {
          clock = fixedNow.add(const Duration(seconds: 4));
          throw TimeoutException('request timed out');
        },
      );
      final deadlineExecutor = AppGeneratedCloudOperationExecutor(
        environment: CloudRuntimeEnvironment(
          environment: CloudEnvironment.gamma,
          gatewayBaseUri: Uri.parse('https://api.example.test'),
        ),
        transport: deadlineTransport,
        headerFactory: CloudOperationHeaderFactory(
          clientContextProvider: clientContext,
          now: () => fixedNow,
        ),
        telemetrySink: _RecordingTelemetry(),
        now: () => clock,
      );

      await expectLater(
        deadlineExecutor.send<Object?>(
          searchOperation,
          context: invocation(
            deadlineAt: fixedNow.add(const Duration(seconds: 3)),
          ),
          responseDecoder: (value) => value,
          requestEncoder: _emptyRequestEncoder,
        ),
        throwsA(
          isA<CloudException>().having(
            (error) => error.runtimeFailure.code,
            'code',
            'APP.TIMEOUT.request_timeout',
          ),
        ),
      );
      expect(deadlineTransport.requests, hasLength(1));
    });

    test('decoder 与 telemetry sink 失败不旁路 RuntimeFailure 或业务结果', () async {
      Object? observedTelemetryError;
      final executor = AppGeneratedCloudOperationExecutor(
        environment: CloudRuntimeEnvironment(
          environment: CloudEnvironment.gamma,
          gatewayBaseUri: Uri.parse('https://api.example.test'),
        ),
        transport: _RecordingTransport(
          response: const <String, dynamic>{'invalid': true},
        ),
        headerFactory: CloudOperationHeaderFactory(
          clientContextProvider: clientContext,
          now: () => fixedNow,
        ),
        telemetrySink: const _ThrowingTelemetry(),
        telemetryFailureObserver: (error, _) {
          observedTelemetryError = error;
        },
        now: () => fixedNow,
      );

      await expectLater(
        executor.send<Object?>(
          searchOperation,
          context: invocation(),
          responseDecoder: (_) => throw const FormatException('bad payload'),
          requestEncoder: _emptyRequestEncoder,
        ),
        throwsA(
          isA<CloudException>().having(
            (error) => error.runtimeFailure.code,
            'code',
            'APP.CONTRACT.invalid_json',
          ),
        ),
      );
      expect(observedTelemetryError, isA<StateError>());

      final success =
          await AppGeneratedCloudOperationExecutor(
            environment: CloudRuntimeEnvironment(
              environment: CloudEnvironment.gamma,
              gatewayBaseUri: Uri.parse('https://api.example.test'),
            ),
            transport: _RecordingTransport(response: 'ok'),
            headerFactory: CloudOperationHeaderFactory(
              clientContextProvider: clientContext,
              now: () => fixedNow,
            ),
            telemetrySink: const _ThrowingTelemetry(),
            telemetryFailureObserver: (error, _) {
              observedTelemetryError = error;
            },
            now: () => fixedNow,
          ).send<String>(
            searchOperation,
            context: invocation(),
            responseDecoder: (value) => value! as String,
            requestEncoder: _emptyRequestEncoder,
          );
      expect(success, 'ok');
    });
  });
}

CloudOperationRequestPayload _emptyRequestEncoder() =>
    const CloudOperationRequestPayload();

final class _FixedClientContextProvider implements CloudClientContextProvider {
  const _FixedClientContextProvider();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'session-1',
      platform: 'ios',
      appVersion: '1.0.0',
      locale: 'zh-CN',
      deviceActorId: 'device-1',
    );
  }
}

final class _NoDeviceClientContextProvider
    implements CloudClientContextProvider {
  const _NoDeviceClientContextProvider();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'session-1',
      platform: 'ios',
      appVersion: '1.0.0',
      locale: 'zh-CN',
    );
  }
}

final class _RecordingTransport implements CloudJsonTransport {
  _RecordingTransport({
    this.response,
    this.error,
    this.handler,
    this.refreshHandler,
  });

  final Object? response;
  final Object? error;
  final FutureOr<Object?> Function(CloudJsonTransportRequest request)? handler;
  final FutureOr<bool> Function(Future<void> abortTrigger)? refreshHandler;
  CloudJsonTransportRequest? request;
  int refreshCount = 0;
  final List<CloudJsonTransportRequest> requests =
      <CloudJsonTransportRequest>[];

  @override
  Future<Object?> send(CloudJsonTransportRequest request) async {
    this.request = request;
    requests.add(request);
    final requestHandler = handler;
    if (requestHandler != null) return requestHandler(request);
    final failure = error;
    if (failure != null) throw failure;
    return response;
  }

  @override
  Future<bool> refreshAuthorization({
    required Future<void> abortTrigger,
  }) async {
    refreshCount += 1;
    final handler = refreshHandler;
    return handler == null ? false : await handler(abortTrigger);
  }
}

final class _RecordingTelemetry implements CloudOperationTelemetrySink {
  final List<CloudOperationTelemetryEvent> events =
      <CloudOperationTelemetryEvent>[];

  @override
  void record(CloudOperationTelemetryEvent event) {
    events.add(event);
  }
}

final class _ThrowingTelemetry implements CloudOperationTelemetrySink {
  const _ThrowingTelemetry();

  @override
  void record(CloudOperationTelemetryEvent event) {
    throw StateError('telemetry unavailable');
  }
}
