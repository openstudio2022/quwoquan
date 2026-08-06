import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/homepage_operation_ports.dart';
import 'package:quwoquan_app/runtime/transport/generated/entity/entity_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef HomepageCommandInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId,
      AppUiSurface surface,
    );

/// Production Remote command adapter for the Homepage object.
final class RemoteHomepageCommandWriter
    implements HomepageCandidateCommandWriter {
  const RemoteHomepageCommandWriter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final HomepageCommandInvocationContextFactory invocationContext;

  @override
  Future<HomepageDetailView> suggest(SuggestHomepageCandidateCommand command) =>
      client.entityHomepageSuggestHomepageCandidate(
        command,
        context: _context(
          EntityRequestPageIds.suggestHomepageCandidate,
          AppUiSurfaces.suggestHomepage,
        ),
      );

  @override
  Future<HomepageDetailView> updateClaimedBasics(
    UpdateClaimedHomepageBasicsCommand command,
  ) => client.entityHomepageUpdateClaimedHomepageBasics(
    command,
    context: _context(
      EntityRequestPageIds.updateClaimedHomepageBasics,
      AppUiSurfaces.homepageMaintenance,
    ),
  );

  CloudOperationInvocationContext _context(
    String clientPageId,
    AppUiSurface surface,
  ) => invocationContext(clientPageId, surface);
}
