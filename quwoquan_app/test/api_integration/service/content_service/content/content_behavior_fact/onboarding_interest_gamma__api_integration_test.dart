// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/interest-onboarding-prior/spec.md#gwt-001

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/adapters/content_behavior_command_remote.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/adapters/content_behavior_outbox_adapter.dart';
import 'package:quwoquan_app/runtime/context/actor_queue_partition.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/errors/generated/content/content_errors.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/actor_queue/actor_queue_storage.dart';
import 'package:quwoquan_app/service/tag_service/tag/tag_node_view/adapters/tag_catalog_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/content_environment_api_support.dart';

void main() {
  setUpAll(requireContentApiRuntimeInputs);

  test(
    'onboarding interest is confirmed by Gamma and rejects non-leaf taxonomy paths',
    () async {
      final httpClient = newContentApiHttpClient();
      final telemetry = await startContentApiTelemetryEvidence();
      final client = buildContentApiClient(
        httpClient: httpClient,
        telemetrySink: telemetry.sink,
      );
      final repository = DurableContentBehaviorRepository(
        writer: RemoteContentBehaviorCommandAdapter(
          client: client,
          invocationContext: (pageID) => CloudOperationInvocationContext(
            surfaceId: AppUiSurfaces.interestOnboarding.id,
            routeId: AppUiSurfaces.interestOnboarding.routeId,
            clientPageId: pageID,
            actor: CloudOperationActorContext(
              accountId: contentApiPersonaId,
              personaId: contentApiPersonaId,
              deviceActorId: 'content-api-integration-device',
            ),
          ),
        ),
        queuePartition: ActorQueuePartition(
          environment: contentApiEnvironment,
          accountId: contentApiPersonaId,
          personaId: contentApiPersonaId,
          deviceId: 'content-api-integration-device',
        ),
        queueStorage: ActorQueueStorage(),
      );
      addTearDown(() async {
        repository.dispose();
        httpClient.close();
        await telemetry.dispose();
      });

      final eventID =
          'gamma-onboarding-${DateTime.now().microsecondsSinceEpoch}';
      const tagRefs = <String>['Topic/旅行/创作者类型/旅行博主'];
      final taxonomyReleaseID = await _activeTaxonomyReleaseId(
        client,
        parentTagRef: 'Topic/旅行/创作者类型',
      );

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
      final telemetryEvents = await telemetry.waitForEvents(minimumCount: 1);
      expect(telemetryEvents, isNotEmpty);
      expect(telemetryEvents.any((event) => !event.succeeded), isTrue);
    },
    tags: const <String>['gamma', 'content', 'onboarding'],
  );
}

Future<String> _activeTaxonomyReleaseId(
  GeneratedCloudOperationClient client, {
  required String parentTagRef,
}) async {
  final catalog = RemoteGeneratedTagCatalogQuery(
    client: client,
    invocationContext: (pageID) => CloudOperationInvocationContext(
      surfaceId: AppUiSurfaces.interestOnboarding.id,
      routeId: AppUiSurfaces.interestOnboarding.routeId,
      clientPageId: pageID,
      actor: CloudOperationActorContext(
        personaId: contentApiPersonaId,
        deviceActorId: 'content-api-integration-device',
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
