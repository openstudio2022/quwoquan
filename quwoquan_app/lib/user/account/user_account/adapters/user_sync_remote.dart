import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/services/user/user_sync_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef UserSyncInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

/// UserAccount sync stream 的唯一 production Remote adapter。
///
/// path/auth/retry/deadline/request encoder/response decoder 全部由 accepted
/// ContractGraph generated client 拥有；本层只把对象级 App port 映射到它。
final class RemoteUserSyncRepository implements UserSyncRepository {
  const RemoteUserSyncRepository({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final UserSyncInvocationContextFactory invocationContext;

  @override
  Future<UserSyncPullResult> pull({
    required int afterSeq,
    int limit = userSyncPullDefaultLimit,
  }) {
    return client.userUserAccountPullUserSync(
      UserSyncPullRequestWire(afterSeq: afterSeq, limit: limit),
      context: invocationContext(UserRequestPageIds.pullUserSync),
    );
  }
}
