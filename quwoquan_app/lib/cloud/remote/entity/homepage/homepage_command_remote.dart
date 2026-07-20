import 'package:quwoquan_app/cloud/runtime/generated/entity/entity_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef HomepageCommandInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      required bool command,
    });

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
    context: _context(EntityRequestPageIds.suggestHomepageCandidate),
  );

  @override
  Future<HomepageDetailProjection> updateClaimedBasics(
    UpdateClaimedHomepageBasicsCommand command,
  ) => client.entityHomepageUpdateClaimedHomepageBasics(
    command,
    context: _context(EntityRequestPageIds.updateClaimedHomepageBasics),
  );

  @override
  Future<HomepageClaimRequestView> createClaimRequest(
    CreateHomepageClaimRequestCommand command,
  ) => client.entityHomepageClaimRequestCreateHomepageClaimRequest(
    command,
    context: _context(EntityRequestPageIds.createHomepageClaimRequest),
  );

  @override
  Future<HomepageStatusReportView> createStatusReport(
    CreateHomepageStatusReportCommand command,
  ) => client.entityHomepageStatusReportCreateHomepageStatusReport(
    command,
    context: _context(EntityRequestPageIds.createHomepageStatusReport),
  );

  CloudOperationInvocationContext _context(String clientPageId) =>
      invocationContext(clientPageId, command: true);
}
