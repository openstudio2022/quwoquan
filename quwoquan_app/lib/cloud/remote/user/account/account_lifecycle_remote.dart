import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef AccountLifecycleInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

/// UserAccount 生命周期终态（CloseAccount，Apple 5.1.1(v) 注销）的
/// production generated-client adapter。
final class RemoteAccountLifecycleCommandWriter
    implements AccountLifecycleCommandWriter {
  const RemoteAccountLifecycleCommandWriter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final AccountLifecycleInvocationContextFactory invocationContext;

  @override
  Future<CloseAccountResult> closeAccount(CloseAccountCommand command) =>
      client.userUserProfileCloseAccount(
        command,
        context: invocationContext(UserRequestPageIds.closeAccount),
      );
}
