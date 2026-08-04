import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_detail_payload.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_view_data.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/content/content/feed_delivery_page/domain/discovery_feed_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

const String kFeedSortRecommend = 'recommend';

String contentPostDeleteIdempotencyKey(String postId) {
  final normalized = postId.trim();
  if (normalized.isEmpty) {
    throw ArgumentError.value(postId, 'postId', 'must not be empty');
  }
  return 'content.post.delete:$normalized';
}

/// DiscoveryFeed named query：只暴露发现/首页分页 Slice。
abstract interface class ContentDiscoveryFeedQuery {
  /// [channelId] 首页频道路由标识（home_channels.feed_query.channel 真相源）。
  /// 非空时走频道推荐主链路（服务端进推荐引擎并按 channelId 归因），
  /// identity/type 不参与请求——它们是发现页浏览流（时间线具名查询）的专属参数。
  Future<DiscoveryFeedPage> listDiscoveryFeedPage({
    required String category,
    String? channelId,
    String? identity,
    String? type,
    String? subCategory,
    int limit = GeneratedPostRuntimeMetadata.feedDefaultLimit,
    String? cursor,
    String sort = kFeedSortRecommend,
    String? sessionId,
    String? feedRequestId,
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  });
}

abstract interface class ContentReadRepository
    implements ContentDiscoveryFeedQuery {
  Future<List<ContentPostViewData>> listDiscoveryFeed({
    required String category,
    String? identity,
    String? type,
    String? subCategory,
    int limit = GeneratedPostRuntimeMetadata.feedDefaultLimit,
    String? cursor,
    String sort = kFeedSortRecommend,
  });

  Future<ContentPostDetailPayload> getPost({
    required String postId,
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  });

  Future<CursorPage<ContentPostViewData>> listUserPosts({
    required String userId,
    String? identity,
    String? type,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });
}

/// 单帖详情读取独立于发现流，避免详情页依赖通用读侧 Facet。
abstract interface class ContentPostDetailReader {
  Future<ContentPostDetailPayload> getPost({
    required String postId,
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  });
}

/// 当前用户对实体对象的「想去」状态读取，供实体主页独立注入。
abstract interface class ContentEntityWishlistStateReader {
  Future<EntityWishlistState> getEntityWishlistState({
    required String objectId,
    required String objectKind,
  });
}

/// 作者作品分页读取独立于发现流，供用户主页创作 Tab 使用。
abstract interface class ContentAuthorPostsReader {
  Future<CursorPage<ContentPostViewData>> listUserPosts({
    required String userId,
    String? identity,
    String? type,
    String? visibility,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });
}

/// Post 聚合的删除命令写面；wire request/receipt 由 ContractGraph 生成。
abstract interface class ContentPostDeleteCommandWriter {
  Future<PostDeletionReceipt> deletePost({
    required String postId,
    required String idempotencyKey,
  });
}

abstract interface class ContentConfigRepository {
  Future<AppConfigSlice> getAppConfig();

  bool get requiresResolvedPersonaForMutations;
}
