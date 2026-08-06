import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/runtime/observability/cloud_operation_telemetry.dart';
import 'package:quwoquan_app/service/content_service/content/intersection_visit_state/adapters/intersection_repository.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/domain/intersection_statement_synthesizer.dart';
import 'package:quwoquan_app/service/content_service/content/intersection_visit_state/adapters/intersection_visit_writer.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../../support/runtime/api_contract/production_cloud_operation_telemetry_evidence.dart';

const _baseUrl = String.fromEnvironment('LOCAL_GAMMA_CONTENT_BASE_URL');
const _viewerId = String.fromEnvironment('APP_CURRENT_USER_ID');
const _personObjectId = String.fromEnvironment('TEST_INTERSECTION_OBJECT_ID');

/// canonical acceptance JWT（`quwoquan_ops/cli/lib/local_environment_auth.py`
/// 本地签发通道），由包装脚本 `quwoquan_app/scripts/gamma/run_intersection_remote_smoke.py`
/// 仅通过测试子进程环境注入，禁止写入 flutter argv / dart-define / 报告。
/// content-service 强制 verified principal，无 token 的 smoke 恒 401（R-IX08）。
final _acceptanceToken =
    Platform.environment['LOCAL_GAMMA_ACCEPTANCE_TOKEN'] ?? '';

class _StaticTokenProvider implements CloudAuthTokenProvider {
  const _StaticTokenProvider(this._token);

  final String _token;

  @override
  Future<String?> getAccessToken() async =>
      _token.trim().isEmpty ? null : _token;
}

CloudHttpClient _authedClient() =>
    CloudHttpClient(authTokenProvider: _StaticTokenProvider(_acceptanceToken));

GeneratedCloudOperationClient _operationClient(
  CloudHttpClient httpClient,
  CloudOperationTelemetrySink telemetrySink,
) => buildGeneratedCloudOperationClient(
  httpClient: httpClient,
  clientContextProvider: const FallbackCloudClientContextProvider(),
  telemetrySink: telemetrySink,
  environment: CloudRuntimeEnvironment(
    environment: CloudEnvironment.gamma,
    gatewayBaseUri: Uri.parse(_baseUrl),
  ),
);

CloudOperationInvocationContext _intersectionContext(String clientPageId) =>
    CloudOperationInvocationContext(
      surfaceId: 'myIntersections',
      clientPageId: clientPageId,
      actor: const CloudOperationActorContext(),
    );

IntersectionReason _expectDisplayReady(
  IntersectionReason reason,
  String label, {
  IntersectionTarget? contextObjectTarget,
}) {
  final displayReason = displayReadyIntersectionReason(
    reason,
    contextObjectTarget: contextObjectTarget,
  );
  expect(displayReason, isNotNull, reason: label);
  expect(displayReason!.primaryText, reason.primaryText, reason: label);
  expect(
    displayReason.primarySpans.map((span) => span.text).join(),
    displayReason.primaryText,
    reason: '$label primarySpans must join primaryText',
  );
  return displayReason;
}

void main() {
  setUpAll(() {
    final gateway = Uri.tryParse(_baseUrl);
    if (gateway == null ||
        !gateway.isAbsolute ||
        gateway.host.isEmpty ||
        _acceptanceToken.trim().isEmpty ||
        _viewerId.trim().isEmpty ||
        _personObjectId.trim().isEmpty) {
      fail(
        'Intersection API integration requires LOCAL_GAMMA_CONTENT_BASE_URL, '
        'LOCAL_GAMMA_ACCEPTANCE_TOKEN, APP_CURRENT_USER_ID and '
        'TEST_INTERSECTION_OBJECT_ID from the candidate-bound environment.',
      );
    }
  });

  test('RemoteIntersectionRepository without bearer fails closed', () async {
    final telemetry = await ProductionCloudOperationTelemetryEvidence.start(
      clientContextProvider: const FallbackCloudClientContextProvider(),
    );
    addTearDown(telemetry.dispose);
    final httpClient = CloudHttpClient();
    addTearDown(httpClient.close);

    final repo = RemoteIntersectionRepository(
      client: _operationClient(httpClient, telemetry.sink),
      myIntersectionsInvocationContext: _intersectionContext,
      objectIntersectionsInvocationContext: _intersectionContext,
    );

    await expectLater(
      repo.getMyIntersectionSummary(),
      throwsA(
        isA<CloudException>()
            .having((error) => error.statusCode, 'statusCode', 401)
            .having(
              (error) => error.runtimeFailure.kind,
              'runtimeFailure.kind',
              RuntimeFailureKind.auth,
            ),
      ),
    );
    final telemetryEvents = await telemetry.waitForEvents(minimumCount: 1);
    expect(telemetryEvents.any((event) => !event.succeeded), isTrue);
  });

  test(
    'RemoteIntersectionRepository reads seeded gamma intersections',
    () async {
      final telemetry = await ProductionCloudOperationTelemetryEvidence.start(
        clientContextProvider: const FallbackCloudClientContextProvider(),
      );
      addTearDown(telemetry.dispose);
      final httpClient = _authedClient();
      addTearDown(httpClient.close);
      final client = _operationClient(httpClient, telemetry.sink);
      final repo = RemoteIntersectionRepository(
        client: client,
        myIntersectionsInvocationContext: _intersectionContext,
        objectIntersectionsInvocationContext: _intersectionContext,
      );
      final visitWriter = RemoteIntersectionVisitWriter(
        client: client,
        invocationContext: _intersectionContext,
      );

      final summary = await repo.getMyIntersectionSummary();
      expect(summary.totalCount, greaterThan(0));
      expect(summary.dimensions, isNotEmpty);
      expect(
        summary.dimensions.every((item) => item.dimension.trim().isNotEmpty),
        isTrue,
      );
      expect(
        summary.dimensions.any((item) => item.dimension == 'relationship'),
        isTrue,
      );

      await visitWriter.markIntersectionsVisited();
      final visitedSummary = await repo.getMyIntersectionSummary();
      expect(visitedSummary.totalCount, summary.totalCount);
      expect(visitedSummary.totalNewCount, 0);
      expect(
        visitedSummary.dimensions.every((item) => item.newCount == 0),
        isTrue,
      );

      final inbox = await repo.listMyIntersections(filter: 'fact');
      expect(inbox, isNotEmpty);
      final renderableInbox = inbox
          .map(displayReadyIntersectionReason)
          .whereType<IntersectionReason>()
          .toList(growable: false);
      expect(renderableInbox, isNotEmpty);
      expect(
        renderableInbox.any((reason) => reason.intersectionPoints.isNotEmpty),
        isTrue,
      );
      expect(
        renderableInbox.any(
          (reason) => reason.intersectionPoints.any(
            (point) => point.sourceRef.trim().isNotEmpty,
          ),
        ),
        isTrue,
      );

      final objectReasons = await repo.getObjectIntersections(
        objectId: _personObjectId,
        objectType: 'user',
      );
      final objectContext = IntersectionTarget(
        objectType: 'user',
        objectId: _personObjectId,
        objectKind: 'person',
        routeId: 'userProfile',
      );
      expect(objectReasons, isNotEmpty);
      expect(objectReasons.first.actionTargetId, _personObjectId);
      _expectDisplayReady(
        objectReasons.first,
        'objectReasons.first',
        contextObjectTarget: objectContext,
      );
      final wishlistReason = objectReasons.firstWhere(
        (reason) => reason.kind == 'coWishlistedEntity',
      );
      _expectDisplayReady(
        wishlistReason,
        'coWishlistedEntity',
        contextObjectTarget: objectContext,
      );
      expect(
        wishlistReason.intersectionPoints.map((point) => point.sourceRef),
        contains('coWishlistedEntity'),
      );
      expect(wishlistReason.actionHints.first.actionKey, 'start_gathering');
      expect(wishlistReason.actionHints.first.dispatch, 'gathering');
      expect(
        wishlistReason.actionHints.first.target?.objectId,
        wishlistReason.actionTargetId,
      );
      final telemetryEvents = await telemetry.waitForEvents(minimumCount: 1);
      expect(telemetryEvents.every((event) => event.succeeded), isTrue);
    },
  );
}
