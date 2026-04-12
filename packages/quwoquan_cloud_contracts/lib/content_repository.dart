import 'package:quwoquan_app/cloud/content/models/content_behavior_batch_event_dto.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_app_config_wire.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_detail_payload.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_reaction_state.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/cloud/runtime/models/post_engagement_counters.dart';

/// 与 [`quwoquan_app/lib/cloud/services/content/content_repository.dart`] 中常量一致。
const String kFeedSortRecommend = 'recommend';

/// Content 域 Repository 抽象（实现见 Mock / Remote）。
abstract class ContentRepository {
  Future<CursorPage<PostBaseDto>> listDiscoveryFeedPage({
    required String category,
    String? identity,
    String? type,
    String? subCategory,
    int limit = GeneratedPostRuntimeMetadata.feedDefaultLimit,
    String? cursor,
    String sort = kFeedSortRecommend,
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

  Future<PostBaseDto> createPost({
    required CreatePostRequestWire body,
  });

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

  Future<void> likePost({required String postId});
  Future<void> unlikePost({required String postId});
  Future<void> favoritePost({required String postId});
  Future<void> unfavoritePost({required String postId});
  Future<ContentReactionState> getReactionState({required String postId});
  Future<CommentPage> listComments({
    required String postId,
    String? cursor,
    String sort = 'latest',
    int limit = CloudApiDefaults.pageLimit,
  });
  Future<CommentDto> createComment({
    required String postId,
    required String content,
    String? replyToCommentId,
    String? personaId,
    String? profileSubjectId,
    String? personaContextVersion,
  });
  Future<void> deleteComment({
    required String postId,
    required String commentId,
  });
  Future<void> likeComment({required String commentId});
  Future<void> unlikeComment({required String commentId});
  Future<CommentPage> listCommentsByAuthor({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });
  Future<CommentPage> listCommentsForPostAuthor({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });
  Future<ContentAppConfigWire> getAppConfig();
  Future<void> reportBehaviors({
    required List<ContentBehaviorBatchEventDto> events,
  });
  Future<PostEngagementCounters> getCounters({required String postId});

  bool get requiresResolvedPersonaForMutations;

  bool get usesEmbeddedContentCatalog;

  bool get usesCloudAssistantEdgeSync;

  Map<String, dynamic>? discoveryPresentationWireForPost(String postId);

  List<PostBaseDto> embeddedDiscoveryArticlePostsForFollowingMix();
}

/// 评论分页（与实现侧一致）。
class CommentPage {
  final List<CommentDto> items;
  final String? nextCursor;

  const CommentPage({required this.items, this.nextCursor});
}
