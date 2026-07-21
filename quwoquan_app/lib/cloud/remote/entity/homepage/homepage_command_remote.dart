import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/entity_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef HomepageCommandInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId,
      AppUiSurface surface,
    );

/// Production Remote command adapter for the Homepage object.
final class RemoteHomepageCommandWriter
    implements
        HomepageCandidateCommandWriter,
        HomepageClaimRequestCommandWriter,
        HomepageStatusReportCommandWriter {
  const RemoteHomepageCommandWriter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final HomepageCommandInvocationContextFactory invocationContext;

  @override
  Future<HomepageDetailProjection> suggest(
    SuggestHomepageCandidateCommand command,
  ) => client.entityHomepageSuggestHomepageCandidate(
    command,
    context: _context(
      EntityRequestPageIds.suggestHomepageCandidate,
      AppUiSurfaces.suggestHomepage,
    ),
  );

  @override
  Future<HomepageDetailProjection> updateClaimedBasics(
    UpdateClaimedHomepageBasicsCommand command,
  ) => client.entityHomepageUpdateClaimedHomepageBasics(
    command,
    context: _context(
      EntityRequestPageIds.updateClaimedHomepageBasics,
      AppUiSurfaces.homepageMaintenance,
    ),
  );

  @override
  Future<HomepageClaimRequestView> createClaimRequest(
    CreateHomepageClaimRequestCommand command,
  ) => client.entityHomepageClaimRequestCreateHomepageClaimRequest(
    command,
    context: _context(
      EntityRequestPageIds.createHomepageClaimRequest,
      AppUiSurfaces.homepageClaim,
    ),
  );

  @override
  Future<HomepageStatusReportView> createStatusReport(
    CreateHomepageStatusReportCommand command,
  ) => client.entityHomepageStatusReportCreateHomepageStatusReport(
    command,
    context: _context(
      EntityRequestPageIds.createHomepageStatusReport,
      AppUiSurfaces.homepageStatusReport,
    ),
  );

  CloudOperationInvocationContext _context(
    String clientPageId,
    AppUiSurface surface,
  ) => invocationContext(clientPageId, surface);
}
