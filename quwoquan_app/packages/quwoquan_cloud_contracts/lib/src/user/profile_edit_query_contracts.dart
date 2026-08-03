import 'user_operation_contracts.g.dart';

abstract interface class ProfileEditSnapshotQueryFacet {
  Future<ProfileEditSnapshotWire> getProfileEditSnapshot(
    GetProfileEditSnapshotQuery query,
  );
}
