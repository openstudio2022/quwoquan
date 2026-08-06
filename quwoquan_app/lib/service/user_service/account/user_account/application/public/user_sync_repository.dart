import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

const int userSyncPullDefaultLimit = 200;

abstract class UserSyncRepository {
  Future<PullUserSyncSlice> pull({
    required int afterSeq,
    int limit = userSyncPullDefaultLimit,
  });
}
