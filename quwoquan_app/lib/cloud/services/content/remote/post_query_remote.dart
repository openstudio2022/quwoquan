import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/post_search_item_view_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository_contract.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ContentPostSearchInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

/// Content Post 搜索的正式远端适配器。
///
/// 仅负责把纯 Dart operation 响应投影为既有 App 搜索 view，不持有旧 HTTP、
/// header 或 decoder 路径。
final class RemoteContentPostSearchAdapter
    implements ContentPostSearchRepository {
  const RemoteContentPostSearchAdapter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final ContentPostSearchInvocationContextFactory invocationContext;

  @override
  Future<List<PostSearchItemView>> searchPosts({
    required String query,
    String? identity,
    String? type,
    String? categoryId,
    String? subCategory,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final response = await client.contentPostSearchPosts(
      ContentPostSearchQuery(
        query: query,
        identity: identity,
        type: type,
        categoryId: categoryId,
        subCategory: subCategory,
        limit: limit,
      ),
      context: invocationContext(ContentRequestPageIds.searchPosts),
    );
    return response.items.map(_toAppSearchItem).toList(growable: false);
  }

  PostSearchItemView _toAppSearchItem(ContentPostSearchItem item) {
    final reason = item.intersectionReason;
    return PostSearchItemView(
      postId: item.postId,
      contentType: item.contentType,
      contentIdentity: item.contentIdentity,
      title: item.title,
      summary: item.summary,
      coverUrl: item.coverUrl,
      authorId: item.authorId,
      authorDisplayName: item.authorDisplayName,
      authorAvatarUrl: item.authorAvatarUrl,
      categoryId: item.categoryId,
      subCategory: item.subCategory,
      likeCount: item.likeCount,
      highlightText: item.highlightText,
      matchedField: item.matchedField,
      publishedAt: item.publishedAt,
      connectionState: item.connectionState,
      intersectionReason: reason == null
          ? null
          : IntersectionReason(
              kind: reason.kind,
              primaryText: reason.primaryText,
              secondaryText: reason.secondaryText,
              strength: reason.strength,
            ),
    );
  }
}
