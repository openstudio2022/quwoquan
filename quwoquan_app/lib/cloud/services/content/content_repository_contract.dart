import 'package:quwoquan_app/cloud/content/models/content_behavior_batch_event_dto.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_app_config_wire.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_detail_payload.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/cloud/runtime/models/discovery_feed_page.dart';
import 'package:quwoquan_app/cloud/runtime/models/discovery_presentation_wire.dart';
import 'package:quwoquan_app/cloud/runtime/models/post_engagement_counters.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

const String kFeedSortRecommend = 'recommend';

abstract interface class ContentReadRepository {
  Future<DiscoveryFeedPage> listDiscoveryFeedPage({
    required String category,
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

  Future<List<PostBaseDto>> listDiscoveryFeed({
    required String category,
    String? identity,
    String? type,
    String? subCategory,
    int limit = GeneratedPostRuntimeMetadata.feedDefaultLimit,
    String? cursor,
    String sort = kFeedSortRecommend,
  });

  Future<ContentPostDetailPayload> getPost({required String postId});

  Future<CursorPage<PostBaseDto>> listUserPosts({
    required String userId,
    String? identity,
    String? type,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });

  DiscoveryPresentationWire? discoveryPresentationWireForPost(String postId);

  List<PostBaseDto> embeddedDiscoveryArticlePostsForFollowingMix();
}

/// 单帖详情读取独立于发现流，避免详情页依赖通用读侧 Facet。
abstract interface class ContentPostDetailReader {
  Future<ContentPostDetailPayload> getPost({required String postId});
}

/// 作者作品分页读取独立于发现流，供用户主页创作 Tab 使用。
abstract interface class ContentAuthorPostsReader {
  Future<CursorPage<PostBaseDto>> listUserPosts({
    required String userId,
    String? identity,
    String? type,
    String? visibility,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });
}

/// Content Post 搜索独立于通用内容读取，避免搜索调用方依赖完整读侧 Facet。
abstract interface class ContentPostSearchRepository {
  Future<List<PostSearchItemView>> searchPosts({
    required String query,
    String? identity,
    String? type,
    String? categoryId,
    String? subCategory,
    int limit = CloudApiDefaults.pageLimit,
  });
}

abstract interface class ContentWriteRepository {
  Future<void> deletePost({required String postId});

  Future<PostBaseDto> updatePostSettings({
    required String postId,
    required UpdatePostSettingsRequestWire body,
  });

  Future<PostBaseDto> promotePostToWork({
    required String postId,
    required PromotePostToWorkRequestWire body,
  });
}

abstract interface class ContentEngagementRepository {
  Future<PostEngagementCounters> getCounters({required String postId});

  Future<void> reportBehaviors({
    required List<ContentBehaviorBatchEventDto> events,
  });
}

abstract interface class ContentConfigRepository {
  Future<ContentAppConfigWire> getAppConfig();

  bool get requiresResolvedPersonaForMutations;

  bool get usesEmbeddedContentCatalog;

  bool get usesCloudAssistantEdgeSync;
}
