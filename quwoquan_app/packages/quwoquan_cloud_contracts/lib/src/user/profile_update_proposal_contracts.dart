import 'user_operation_contracts.g.dart';

abstract interface class ProfileUpdateProposalCommandWriter {
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

abstract interface class ProfileUpdateProposalQueryReader {
  Future<ProfileUpdateProposalView> get(ProfileUpdateProposalQuery query);
  Future<ProfileUpdateProposalSlice> list(ProfileUpdateProposalListQuery query);
}
