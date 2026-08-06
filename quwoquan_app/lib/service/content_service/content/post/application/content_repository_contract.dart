import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_detail_payload.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/runtime/transport/models/cursor_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    hide ContentDiscoveryFeedQuery;

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
    int limit = ContentAuthorPostsQuery.defaultLimit,
  });
}

abstract interface class ContentConfigRepository {
  Future<AppConfigSlice> getAppConfig();

  bool get requiresResolvedPersonaForMutations;
}
