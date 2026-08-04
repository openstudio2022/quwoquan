// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/interest-onboarding-prior/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#sit-005

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/content/generated/content_errors.g.dart';
import 'package:quwoquan_app/content/content/post/adapters/author_impact_remote.dart';
import 'package:quwoquan_app/content/content/post/adapters/content_behavior_remote.dart';
import 'package:quwoquan_app/tag/tag/tag_node_view/adapters/tag_catalog_remote.dart';
import 'package:quwoquan_app/cloud/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/cloud/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/cloud/runtime/context/actor_queue_partition.dart';
import 'package:quwoquan_app/cloud/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/observability/cloud_operation_telemetry.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

const _gatewayURL = String.fromEnvironment('GAMMA_GATEWAY_URL');
const _accessToken = String.fromEnvironment('TEST_AUTH_TOKEN');
const _personaID = String.fromEnvironment('GAMMA_ACCEPTANCE_PERSONA_ID');

void main() {
  setUpAll(_requireGammaRuntimeInputs);

  test(
    'onboarding interest is confirmed by Gamma and rejects non-leaf taxonomy paths',
    () async {
      final httpClient = _newCloudHttpClient();
      final client = buildGeneratedCloudOperationClient(
        httpClient: httpClient,
        clientContextProvider: const _GammaClientContext(),
        telemetrySink: _RecordingTelemetry(),
        environment: CloudRuntimeEnvironment(
          environment: CloudEnvironment.gamma,
          gatewayBaseUri: Uri.parse(_gatewayURL),
        ),
      );
      final repository = RemoteBehaviorRepository(
        writer: RemoteContentBehaviorCommandAdapter(
          client: client,
          invocationContext: (pageID) => CloudOperationInvocationContext(
            surfaceId: AppUiSurfaces.interestOnboarding.id,
            routeId: AppUiSurfaces.interestOnboarding.routeId,
            clientPageId: pageID,
            actor: CloudOperationActorContext(
              accountId: _personaID,
              personaId: _personaID,
              deviceActorId: 'gamma-uat-device',
            ),
          ),
        ),
        queuePartition: ActorQueuePartition(
          environment: 'gamma',
          accountId: _personaID,
          personaId: _personaID,
          deviceId: 'gamma-uat-device',
        ),
      );
      addTearDown(() {
        repository.dispose();
        httpClient.close();
      });

      final eventID =
          'gamma-onboarding-${DateTime.now().microsecondsSinceEpoch}';
      const tagRefs = <String>['Topic/旅行/创作者类型/旅行博主'];

      // 发布身份取自云侧目录本身，和页面同源。写死 release 号会让这条用例
      // 在下一次 tag 发布后失败，也会掩盖端侧固化常量的回归。
      final taxonomyReleaseID = await _activeTaxonomyReleaseId(
        httpClient,
        parentTagRef: 'Topic/旅行/创作者类型',
      );

      // Same clientEventId must be safe to replay. Server-side local Gamma
      // owns the durable de-duplication; this adapter must not queue or claim
      // success before it receives the confirmed response.
      await repository.submitOnboardingInterest(
        clientEventId: eventID,
        taxonomyReleaseId: taxonomyReleaseID,
        tagRefs: tagRefs,
      );
      await repository.submitOnboardingInterest(
        clientEventId: eventID,
        taxonomyReleaseId: taxonomyReleaseID,
        tagRefs: tagRefs,
      );

      await expectLater(
        repository.submitOnboardingInterest(
          clientEventId: '$eventID-invalid',
          taxonomyReleaseId: taxonomyReleaseID,
          tagRefs: const <String>['Topic/旅行'],
        ),
        throwsA(
          isA<CloudException>()
              .having((error) => error.statusCode, 'statusCode', 400)
              .having(
                (error) => error.code,
                'code',
                ContentErrorCode.invalidArgument.code,
              ),
        ),
      );
    },
    tags: const <String>['gamma', 'content', 'onboarding'],
  );

  test(
    'author impact summary and drill-down decode from Gamma evidence truth',
    () async {
      final httpClient = _newCloudHttpClient();
      addTearDown(httpClient.close);
      final telemetry = _RecordingTelemetry();
      final client = buildGeneratedCloudOperationClient(
        httpClient: httpClient,
        clientContextProvider: const _GammaClientContext(),
        telemetrySink: telemetry,
        environment: CloudRuntimeEnvironment(
          environment: CloudEnvironment.gamma,
          gatewayBaseUri: Uri.parse(_gatewayURL),
        ),
      );
      final query = RemoteAuthorImpactQuery(
        client: client,
        invocationContext: (pageID) => CloudOperationInvocationContext(
          surfaceId: AppUiSurfaces.userProfile.id,
          routeId: AppUiSurfaces.userProfile.routeId,
          clientPageId: pageID,
          actor: CloudOperationActorContext(
            personaId: _personaID,
            deviceActorId: 'gamma-uat-device',
          ),
        ),
      );

      final AuthorImpactSummary summary = await query.getAuthorImpact(
        _personaID,
      );
      expect(summary.authorId, _personaID);
      expect(summary.total, greaterThanOrEqualTo(1));
      expect(summary.items, isNotEmpty);
      final item = summary.items.first;
      expect(item.primaryText, isNotEmpty);
      expect(item.impactId, isNotEmpty);
      expect(item.evidenceSnapshotId, item.impactId);

      final evidence = await query.listAuthorImpactEvidence(
        personaId: _personaID,
        impactId: item.impactId,
        evidenceSnapshotId: item.evidenceSnapshotId,
      );
      expect(evidence.impactId, item.impactId);
      expect(evidence.totalCount, greaterThanOrEqualTo(1));
      expect(evidence.items, isNotEmpty);
      expect(telemetry.events, hasLength(2));
      expect(telemetry.events.every((event) => event.succeeded), isTrue);
    },
    tags: const <String>['gamma', 'content', 'author-impact'],
  );
}

void _requireGammaRuntimeInputs() {
  if (_gatewayURL.trim().isEmpty ||
      _accessToken.trim().isEmpty ||
      _personaID.trim().isEmpty) {
    fail(
      'Gamma UAT requires GAMMA_GATEWAY_URL, TEST_AUTH_TOKEN and '
      'GAMMA_ACCEPTANCE_PERSONA_ID. Use the local Gamma runner so the token '
      'is issued from the local environment signer.',
    );
  }
}

Future<String> _activeTaxonomyReleaseId(
  CloudHttpClient httpClient, {
  required String parentTagRef,
}) async {
  final catalog = RemoteGeneratedTagCatalogQuery(
    client: buildGeneratedCloudOperationClient(
      httpClient: httpClient,
      clientContextProvider: const _GammaClientContext(),
      telemetrySink: _RecordingTelemetry(),
      environment: CloudRuntimeEnvironment(
        environment: CloudEnvironment.gamma,
        gatewayBaseUri: Uri.parse(_gatewayURL),
      ),
    ),
    invocationContext: (pageID) => CloudOperationInvocationContext(
      surfaceId: AppUiSurfaces.interestOnboarding.id,
      routeId: AppUiSurfaces.interestOnboarding.routeId,
      clientPageId: pageID,
      actor: CloudOperationActorContext(
        personaId: _personaID,
        deviceActorId: 'gamma-uat-device',
      ),
    ),
  );
  final children = await catalog.listChildren(parentTagRef);
  final releaseIds = children
      .map((child) => child.releaseId.trim())
      .where((releaseId) => releaseId.isNotEmpty)
      .toSet();
  expect(
    releaseIds,
    hasLength(1),
    reason: 'catalog children must expose exactly one active taxonomy release',
  );
  return releaseIds.single;
}

CloudHttpClient _newCloudHttpClient() {
  return CloudHttpClient(
    authTokenProvider: const _StaticTokenProvider(_accessToken),
  );
}

final class _StaticTokenProvider implements CloudAuthTokenProvider {
  const _StaticTokenProvider(this._token);

  final String _token;

  @override
  Future<String?> getAccessToken() async => _token;
}

final class _GammaClientContext implements CloudClientContextProvider {
  const _GammaClientContext();

  @override
  CloudClientContextSnapshot snapshot() => CloudClientContextSnapshot(
    sessionId: 'gamma-onboarding-author-impact-uat',
    deviceActorId: 'gamma-uat-device',
    platform: 'test',
    appVersion: 'gamma-uat',
    locale: 'zh-CN',
  );
}

final class _RecordingTelemetry implements CloudOperationTelemetrySink {
  final List<CloudOperationTelemetryEvent> events =
      <CloudOperationTelemetryEvent>[];

  @override
  void record(CloudOperationTelemetryEvent event) {
    events.add(event);
  }
}
