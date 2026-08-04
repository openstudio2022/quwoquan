import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository_contract.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ContentAppConfigInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

/// `content.post.GetAppConfig` 的唯一 production Remote owner。
///
/// path、鉴权、重试、请求编码与响应解码全部由 generated operation client
/// 承担；本适配器只绑定当前页面调用上下文。
final class RemoteContentAppConfigQuery implements ContentConfigRepository {
  const RemoteContentAppConfigQuery({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final ContentAppConfigInvocationContextFactory invocationContext;

  @override
  Future<AppConfigSlice> getAppConfig() {
    return client.contentPostGetAppConfig(
      const GetAppConfigQuery(),
      context: invocationContext(ContentRequestPageIds.getAppConfig),
    );
  }

  @override
  bool get requiresResolvedPersonaForMutations => true;
}
