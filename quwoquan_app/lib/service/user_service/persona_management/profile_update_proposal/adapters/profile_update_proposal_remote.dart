import 'package:quwoquan_app/runtime/transport/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/service/user_service/persona_management/profile_update_proposal/application/public/profile_update_proposal_ports.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ProfileUpdateProposalInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      required bool command,
    });

/// Production-only adapter. It contains no paths, operation IDs, JSON maps,
/// actor headers, decoders or fallback behavior.
final class RemoteProfileUpdateProposalFacet
    implements ProfileUpdateProposalWriter, ProfileUpdateProposalReader {
  const RemoteProfileUpdateProposalFacet({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final ProfileUpdateProposalInvocationContextFactory invocationContext;

  @override
  Future<ProfileUpdateProposalCommandResult> create(
    CreateProfileUpdateProposalCommand command,
  ) => client.userProfileUpdateProposalCreateProfileUpdateProposal(
    command,
    context: invocationContext(
      UserRequestPageIds.createProfileUpdateProposal,
      command: true,
    ),
  );

  @override
  Future<ProfileUpdateProposalCommandResult> confirm(
    ConfirmProfileUpdateProposalCommand command,
  ) => client.userProfileUpdateProposalConfirmProposal(
    command,
    context: invocationContext(
      UserRequestPageIds.confirmProposal,
      command: true,
    ),
  );

  @override
  Future<ProfileUpdateProposalCommandResult> apply(
    ApplyProfileUpdateProposalCommand command,
  ) => client.userProfileUpdateProposalApplyProposal(
    command,
    context: invocationContext(UserRequestPageIds.applyProposal, command: true),
  );

  @override
  Future<ProfileUpdateProposalCommandResult> rollback(
    RollbackProfileUpdateProposalCommand command,
  ) => client.userProfileUpdateProposalRollbackProposal(
    command,
    context: invocationContext(
      UserRequestPageIds.rollbackProposal,
      command: true,
    ),
  );

  @override
  Future<ProfileUpdateProposalCommandResult> reject(
    RejectProfileUpdateProposalCommand command,
  ) => client.userProfileUpdateProposalRejectProposal(
    command,
    context: invocationContext(
      UserRequestPageIds.rejectProposal,
      command: true,
    ),
  );

  @override
  Future<ProfileUpdateProposalView> get(ProfileUpdateProposalQuery query) =>
      client.userProfileUpdateProposalGetProfileUpdateProposal(
        query,
        context: invocationContext(
          UserRequestPageIds.getProfileUpdateProposal,
          command: false,
        ),
      );

  @override
  Future<ProfileUpdateProposalSlice> list(
    ProfileUpdateProposalListQuery query,
  ) => client.userProfileUpdateProposalListProfileUpdateProposals(
    query,
    context: invocationContext(
      UserRequestPageIds.listProfileUpdateProposals,
      command: false,
    ),
  );
}
