import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_claim_request/application/public/homepage_claim_request_command_writer.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/entity/entity_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef HomepageClaimRequestInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId,
      AppUiSurface surface,
    );

/// HomepageClaimRequest 的 production generated-client adapter。
final class RemoteHomepageClaimRequestWriter
    implements HomepageClaimRequestCommandWriter {
  const RemoteHomepageClaimRequestWriter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final HomepageClaimRequestInvocationContextFactory invocationContext;

  @override
  Future<HomepageClaimRequestView> createClaimRequest({
    required String homepageId,
    required HomepageClaimRequestDraft draft,
  }) => client.entityHomepageClaimRequestCreateHomepageClaimRequest(
    CreateHomepageClaimRequestCommand(
      homepageId: homepageId,
      claimTier: draft.claimTier,
      businessLicenseUrl: draft.businessLicenseUrl,
      contactPhone: draft.contactPhone,
      identityCardFrontUrl: draft.identityCardFrontUrl,
      identityCardBackUrl: draft.identityCardBackUrl,
      note: draft.note,
    ),
    context: invocationContext(
      EntityRequestPageIds.createHomepageClaimRequest,
      AppUiSurfaces.homepageClaim,
    ),
  );
}
