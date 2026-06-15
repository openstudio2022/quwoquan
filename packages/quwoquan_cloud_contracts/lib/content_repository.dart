import 'package:quwoquan_app/cloud/content/models/content_behavior_batch_event_dto.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_app_config_wire.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_detail_payload.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_reaction_state.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/cloud/runtime/models/discovery_presentation_wire.dart';
import 'package:quwoquan_app/cloud/runtime/models/post_engagement_counters.dart';

/// 与 [`quwoquan_app/lib/cloud/services/content/content_repository.dart`] 中常量一致。
const String kFeedSortRecommend = 'recommend';

/// 内容读取（feed / 搜索 / 详情 / 用户作品 / 推荐 / 展示 wire）。
///
/// R02：单接口 ≤10 方法。
abstract class ContentReadRepository {
  Future<CursorPage<PostBaseDto>> listDiscoveryFeedPage({
    required String category,
    String? identity,
    String? type,
    String? subCategory,
    int limit = GeneratedPostRuntimeMetadata.feedDefaultLimit,
    String? cursor,
    String sort = kFeedSortRecommend,
    String? sessionId,
    String? feedRequestId,
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

  Future<List<PostSearchItemView>> searchPosts({
    required String query,
    String? identity,
    String? type,
    String? categoryId,
    String? subCategory,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<ContentPostDetailPayload> getPost({required String postId});

  Future<ContentRecommendationResponseDto> getRecommendation({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<CursorPage<PostBaseDto>> listUserPosts({
    required String userId,
    String? identity,
    String? type,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });

  /// 发现流展示 wire（强类型封装，替代既有裸 Map 返回）。
  DiscoveryPresentationWire? discoveryPresentationWireForPost(String postId);

  List<PostBaseDto> embeddedDiscoveryArticlePostsForFollowingMix();
}

/// 内容写入（创建 / 更新 / 发布 / 删除 / 设置 / 升级 / 圈子分发）。
///
/// R02：单接口 ≤10 方法。
abstract class ContentWriteRepository {
  Future<PostBaseDto> createPost({required CreatePostRequestWire body});

  Future<PostBaseDto> updatePost({
    required String postId,
    required UpdatePostRequestWire body,
  });

  Future<void> deletePost({required String postId});

  Future<PostBaseDto> publishPost({
    required String postId,
    PublishPostRequestWire? body,
  });

  Future<PostBaseDto> updatePostSettings({
    required String postId,
    required UpdatePostSettingsRequestWire body,
  });

  Future<PostBaseDto> promotePostToWork({
    required String postId,
    required PromotePostToWorkRequestWire body,
  });

  Future<PostBaseDto> updatePostCircles({
    required String postId,
    List<String> add = const [],
    List<String> remove = const [],
  });

  Future<PostBaseDto> repostToCircle({
    required String postId,
    required String circleId,
  });

  Future<PostBaseDto> quoteToCircle({
    required String postId,
    required String circleId,
    String quoteText = '',
  });
}

/// 内容互动反应（点赞 / 分享 / 反应态 / 计数 / 行为上报）。
///
/// 唯一的内容互动接口（内容只有 赞/评/转 三动作）。
/// R02：单接口 ≤10 方法。
abstract class ContentReactionRepository {
  Future<void> likePost({required String postId});
  Future<void> unlikePost({required String postId});
  Future<bool> sharePost({required String postId});
  Future<bool> unsharePost({required String postId});
  Future<ContentReactionState> getReactionState({required String postId});
  Future<PostEngagementCounters> getCounters({required String postId});
  Future<void> reportBehaviors({
    required List<ContentBehaviorBatchEventDto> events,
  });
}

/// 内容评论（列表 / 创建 / 删除 / 点赞 / 作者维度查询）。
///
/// R02：单接口 ≤10 方法。
abstract class ContentCommentRepository {
  Future<CommentPage> listComments({
    required String postId,
    String? cursor,
    String sort = 'recommended',
    int limit = CloudApiDefaults.pageLimit,
  });
  Future<CommentPage> listCommentReplies({
    required String postId,
    required String commentId,
    String? cursor,
    int limit = 10,
  });
  Future<CommentDto> createComment({
    required String postId,
    required String content,
    String? replyToCommentId,
    List<String> attachmentMediaIds = const <String>[],
    List<Map<String, dynamic>> mentions = const <Map<String, dynamic>>[],
    String? subAccountId,
    String? personaContextVersion,
  });
  Future<void> deleteComment({
    required String postId,
    required String commentId,
  });
  Future<CommentDto> reactToComment({
    required String commentId,
    required String reaction,
  });
  Future<CommentPage> listCommentsByAuthor({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });
  Future<CommentPage> listCommentsForPostAuthor({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });
}

/// 内容媒体（上传会话 / 资产 / 视频封面 / 长文摘要生成）。
///
/// R02：单接口 ≤10 方法。
abstract class ContentMediaRepository {
  Future<ContentMediaInitUploadResponseDto> initMediaUpload({
    String mediaType = 'image',
  });
  Future<ContentMediaCompleteUploadResponseDto> completeMediaUpload({
    required String sessionId,
  });
  Future<void> abortMediaUpload({required String sessionId});
  Future<ContentMediaAssetWireDto> getMediaAsset({required String mediaId});
  Future<ContentVideoCoverSelectionWireDto> selectAutoVideoCover({
    required String mediaId,
  });
  Future<ContentVideoCoverSelectionWireDto> selectManualVideoCover({
    required String mediaId,
    required String coverAssetId,
  });
  Future<ContentArticleSummaryGenerateResponseDto> generateArticleSummary({
    required String title,
    required String body,
  });
}

/// 内容运行时配置与能力开关。
///
/// R02：单接口 ≤10 方法。
abstract class ContentConfigRepository {
  Future<ContentAppConfigWire> getAppConfig();

  bool get requiresResolvedPersonaForMutations;

  bool get usesEmbeddedContentCatalog;

  bool get usesCloudAssistantEdgeSync;
}

/// Content 域 Repository 抽象（实现见 Mock / Remote）。
///
/// 由 6 个 ≤10 方法子接口组合（R02）。既有消费方继续依赖 `ContentRepository`
/// 不变；新消费方可只依赖所需子接口。
abstract class ContentRepository
    implements
        ContentReadRepository,
        ContentWriteRepository,
        ContentReactionRepository,
        ContentCommentRepository,
        ContentMediaRepository,
        ContentConfigRepository {}

/// 评论分页（与实现侧一致）。
class CommentPage {
  final List<CommentDto> items;
  final String? nextCursor;

  const CommentPage({required this.items, this.nextCursor});
}
