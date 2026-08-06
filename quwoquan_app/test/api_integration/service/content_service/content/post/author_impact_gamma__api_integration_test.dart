// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#sit-005

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/author_impact_remote.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/content_environment_api_support.dart';

void main() {
  setUpAll(requireContentApiRuntimeInputs);

  test(
    'author impact summary and drill-down decode from Gamma evidence truth',
    () async {
      final httpClient = newContentApiHttpClient();
      addTearDown(httpClient.close);
      final telemetry = await startContentApiTelemetryEvidence();
      addTearDown(telemetry.dispose);
      final client = buildContentApiClient(
        httpClient: httpClient,
        telemetrySink: telemetry.sink,
      );
      final query = RemoteAuthorImpactQuery(
        client: client,
        invocationContext: (pageID) => CloudOperationInvocationContext(
          surfaceId: AppUiSurfaces.userProfile.id,
          routeId: AppUiSurfaces.userProfile.routeId,
          clientPageId: pageID,
          actor: CloudOperationActorContext(
            personaId: contentApiPersonaId,
            deviceActorId: 'content-api-integration-device',
          ),
        ),
      );

      final AuthorImpactSummary summary = await query.getAuthorImpact(
        contentApiPersonaId,
      );
      expect(summary.authorId, contentApiPersonaId);
      expect(summary.total, greaterThanOrEqualTo(1));
      expect(summary.items, isNotEmpty);
      final item = summary.items.first;
      expect(item.primaryText, isNotEmpty);
      expect(item.impactId, isNotEmpty);
      expect(item.evidenceSnapshotId, item.impactId);

      final evidence = await query.listAuthorImpactEvidence(
        personaId: contentApiPersonaId,
        impactId: item.impactId,
        evidenceSnapshotId: item.evidenceSnapshotId,
      );
      expect(evidence.impactId, item.impactId);
      expect(evidence.totalCount, greaterThanOrEqualTo(1));
      expect(evidence.items, isNotEmpty);
      final telemetryEvents = await telemetry.waitForEvents(minimumCount: 2);
      expect(telemetryEvents, hasLength(2));
      expect(telemetryEvents.every((event) => event.succeeded), isTrue);
    },
    tags: const <String>['gamma', 'content', 'author-impact'],
  );
}
