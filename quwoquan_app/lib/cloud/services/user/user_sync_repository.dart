import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    as user_contracts;

const int userSyncPullDefaultLimit = 200;

/// User Sync App port 直接使用 canonical generated wire；不维护第二份 DTO、
/// decoder 或动态 payload。
typedef UserSyncPatch = user_contracts.UserSyncPatch;
typedef UserSyncPullResult = user_contracts.PullUserSyncSlice;

abstract class UserSyncRepository {
  Future<UserSyncPullResult> pull({
    required int afterSeq,
    int limit = userSyncPullDefaultLimit,
  });
}
