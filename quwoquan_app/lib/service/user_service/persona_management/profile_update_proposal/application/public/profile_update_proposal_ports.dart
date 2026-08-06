import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        ApplyProfileUpdateProposalCommand,
        ConfirmProfileUpdateProposalCommand,
        CreateProfileUpdateProposalCommand,
        ProfileUpdateProposalCommandResult,
        ProfileUpdateProposalListQuery,
        ProfileUpdateProposalQuery,
        ProfileUpdateProposalSlice,
        ProfileUpdateProposalView,
        RejectProfileUpdateProposalCommand,
        RollbackProfileUpdateProposalCommand;

abstract interface class ProfileUpdateProposalWriter {
  Future<ProfileUpdateProposalCommandResult> create(
    CreateProfileUpdateProposalCommand command,
  );

  Future<ProfileUpdateProposalCommandResult> confirm(
    ConfirmProfileUpdateProposalCommand command,
  );

  Future<ProfileUpdateProposalCommandResult> apply(
    ApplyProfileUpdateProposalCommand command,
  );

  Future<ProfileUpdateProposalCommandResult> rollback(
    RollbackProfileUpdateProposalCommand command,
  );

  Future<ProfileUpdateProposalCommandResult> reject(
    RejectProfileUpdateProposalCommand command,
  );
}

abstract interface class ProfileUpdateProposalReader {
  Future<ProfileUpdateProposalView> get(ProfileUpdateProposalQuery query);

  Future<ProfileUpdateProposalSlice> list(ProfileUpdateProposalListQuery query);
}
