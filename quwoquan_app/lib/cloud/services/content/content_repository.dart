import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_detail_payload.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/services/circle/mock/circle_mock_data.dart';
import 'package:quwoquan_app/cloud/services/content/mock/content_mock_data.dart';
import 'package:quwoquan_app/core/models/search_models.dart';

const String kFeedSortRecommend = 'recommend';

/// Content 域 Repository（端侧按业务对象组织的统一入口）。
///
/// 输出统一为 [PostBaseDto] 子类（codegen 产物，DO NOT EDIT）：
/// - photo → [PhotoPostDto]（含 width/height）
/// - video → [VideoPostDto]（含 width/height 分辨率）
/// - article → [ArticlePostDto]
/// - moment → [MomentPostDto]
///
/// Mock：使用 [ContentMockData]（canonical 字段，与各 DTO schema 严格对齐）。
/// Remote：对接云侧 REST 契约，响应经 [postBaseDtoFromMap] 规范化。
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

  Future<Map<String, dynamic>> createPost({
    required Map<String, dynamic> payload,
  });

  Future<Map<String, dynamic>> updatePost({
    required String postId,
    required Map<String, dynamic> payload,
  });
  Future<void> deletePost({required String postId});
  Future<Map<String, dynamic>> publishPost({
    required String postId,
    Map<String, dynamic> payload = const <String, dynamic>{},
  });
  Future<Map<String, dynamic>> updatePostSettings({
    required String postId,
    required Map<String, dynamic> payload,
  });
  Future<Map<String, dynamic>> promotePostToWork({
    required String postId,
    required Map<String, dynamic> payload,
  });

  Future<Map<String, dynamic>> updatePostCircles({
    required String postId,
    List<String> add = const [],
    List<String> remove = const [],
  });
  Future<Map<String, dynamic>> repostToCircle({
    required String postId,
    required String circleId,
  });
  Future<Map<String, dynamic>> quoteToCircle({
    required String postId,
    required String circleId,
    String quoteText = '',
  });

  Future<Map<String, dynamic>> initMediaUpload({String mediaType = 'image'});
  Future<Map<String, dynamic>> completeMediaUpload({required String sessionId});
  Future<void> abortMediaUpload({required String sessionId});
  Future<Map<String, dynamic>> getMediaAsset({required String mediaId});

  Future<Map<String, dynamic>> selectAutoVideoCover({required String mediaId});
  Future<Map<String, dynamic>> selectManualVideoCover({
    required String mediaId,
    required String coverAssetId,
  });

  Future<Map<String, dynamic>> generateArticleSummary({
    required String title,
    required String body,
  });

  Future<Map<String, dynamic>> getRecommendation({
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
  Future<Map<String, dynamic>> getReactionState({required String postId});
  Future<CommentPage> listComments({
    required String postId,
    String? cursor,
    String sort = 'latest',
    int limit = CloudApiDefaults.pageLimit,
  });
  Future<Map<String, dynamic>> createComment({
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
  Future<Map<String, dynamic>> getAppConfig();
  Future<void> reportBehaviors({required List<Map<String, dynamic>> events});
  Future<Map<String, dynamic>> getCounters({required String postId});
}

class CommentDto {
  final String id;
  final String postId;
  final String authorId;
  final String? personaId;
  final String? displayName;
  final String? avatarUrl;
  final String content;
  final String? replyToCommentId;
  final String? replyToUserId;
  final String? replyToDisplayName;
  final int replyCount;
  final int likeCount;
  final String status;
  final bool isAuthor;
  final DateTime createdAt;

  const CommentDto({
    required this.id,
    required this.postId,
    required this.authorId,
    this.personaId,
    this.displayName,
    this.avatarUrl,
    required this.content,
    this.replyToCommentId,
    this.replyToUserId,
    this.replyToDisplayName,
    this.replyCount = 0,
    this.likeCount = 0,
    this.status = 'visible',
    this.isAuthor = false,
    required this.createdAt,
  });

  factory CommentDto.fromMap(Map<String, dynamic> m) {
    return CommentDto(
      id: (m['_id'] ?? m['id'] ?? '').toString(),
      postId: (m['postId'] ?? '').toString(),
      authorId: (m['profileSubjectId'] ?? m['authorId'] ?? '').toString(),
      personaId: (m['personaId'] ?? m['subAccountId'])?.toString(),
      displayName: (m['authorDisplayNameSnapshot'] ?? m['displayName'])
          ?.toString(),
      avatarUrl: (m['authorAvatarUrlSnapshot'] ?? m['avatarUrl'])?.toString(),
      content: (m['content'] ?? '').toString(),
      replyToCommentId: m['replyToCommentId']?.toString(),
      replyToUserId: m['replyToUserId']?.toString(),
      replyToDisplayName: m['replyToDisplayName']?.toString(),
      replyCount: (m['replyCount'] as num?)?.toInt() ?? 0,
      likeCount: (m['likeCount'] as num?)?.toInt() ?? 0,
      status: (m['status'] ?? 'visible').toString(),
      isAuthor: m['isAuthor'] == true,
      createdAt:
          DateTime.tryParse(m['createdAt']?.toString() ?? '') ?? DateTime.now(),
    );
  }

  Map<String, dynamic> toMap() => {
    'id': id,
    'postId': postId,
    'authorId': authorId,
    'profileSubjectId': authorId,
    'personaId': personaId,
    'displayName': displayName,
    'authorDisplayNameSnapshot': displayName,
    'avatarUrl': avatarUrl,
    'authorAvatarUrlSnapshot': avatarUrl,
    'content': content,
    'replyToCommentId': replyToCommentId,
    'replyToUserId': replyToUserId,
    'replyToDisplayName': replyToDisplayName,
    'replyCount': replyCount,
    'likeCount': likeCount,
    'status': status,
    'isAuthor': isAuthor,
    'createdAt': createdAt.toIso8601String(),
  };

  CommentDto copyWith({int? replyCount, int? likeCount, String? status}) {
    return CommentDto(
      id: id,
      postId: postId,
      authorId: authorId,
      personaId: personaId,
      displayName: displayName,
      avatarUrl: avatarUrl,
      content: content,
      replyToCommentId: replyToCommentId,
      replyToUserId: replyToUserId,
      replyToDisplayName: replyToDisplayName,
      replyCount: replyCount ?? this.replyCount,
      likeCount: likeCount ?? this.likeCount,
      status: status ?? this.status,
      isAuthor: isAuthor,
      createdAt: createdAt,
    );
  }
}

class CommentPage {
  final List<CommentDto> items;
  final String? nextCursor;

  const CommentPage({required this.items, this.nextCursor});
}

class MockContentRepository implements ContentRepository {
  Exception? throwOnLike;
  Exception? throwOnCreateComment;
  Exception? throwOnFavorite;

  int likePostCallCount = 0;
  int createCommentCallCount = 0;
  String? lastCommentText;
  String? lastCommentPostId;

  Map<String, dynamic> reactionStateStub = {'liked': false, 'favorited': false};
  List<Map<String, dynamic>> commentsStub = [];
  int countersStubLikeCount = 0;
  int countersStubCommentCount = 0;

  @override
  Future<CursorPage<PostBaseDto>> listDiscoveryFeedPage({
    required String category,
    String? identity,
    String? type,
    String? subCategory,
    int limit = GeneratedPostRuntimeMetadata.feedDefaultLimit,
    String? cursor,
    String sort = kFeedSortRecommend,
  }) async {
    final rawList = _resolveDiscoveryRaw(
      category: category,
      identity: identity,
      type: type,
    );
    final items = rawList.map(postBaseDtoFromMap).toList(growable: false);
    return CursorPage<PostBaseDto>(items: items, nextCursor: null);
  }

  @override
  Future<List<PostBaseDto>> listDiscoveryFeed({
    required String category,
    String? identity,
    String? type,
    String? subCategory,
    int limit = GeneratedPostRuntimeMetadata.feedDefaultLimit,
    String? cursor,
    String sort = kFeedSortRecommend,
  }) async {
    final page = await listDiscoveryFeedPage(
      category: category,
      identity: identity,
      type: type,
      subCategory: subCategory,
      limit: limit,
      cursor: cursor,
      sort: sort,
    );
    return page.items;
  }

  @override
  Future<List<PostSearchItemView>> searchPosts({
    required String query,
    String? identity,
    String? type,
    String? categoryId,
    String? subCategory,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final normalizedQuery = query.trim().toLowerCase();
    if (normalizedQuery.isEmpty) {
      return const <PostSearchItemView>[];
    }
    final expectedIdentity = (identity ?? '').trim().toLowerCase();
    final expectedType = (type ?? '').trim().toLowerCase();
    final expectedCategoryId = (categoryId ?? '').trim().toLowerCase();
    final expectedSubCategory = (subCategory ?? '').trim().toLowerCase();
    final allRaw = <Map<String, dynamic>>[
      ...ContentMockData.discoveryPhotoData,
      ...ContentMockData.discoveryVideoData,
      ...ContentMockData.discoveryMomentData,
      ...ContentMockData.discoveryArticleData,
    ];
    final results = <PostSearchItemView>[];
    for (final item in allRaw) {
      final circleIds = <String>{
        if ((item['circleId'] ?? '').toString().trim().isNotEmpty)
          (item['circleId'] ?? '').toString().trim(),
        ...((item['circleIds'] as List?)
                ?.map((value) => value.toString().trim())
                .where((value) => value.isNotEmpty) ??
            const <String>[]),
      };
      final associatedCircles = circleIds
          .map<Map<String, dynamic>?>(
            (id) =>
                CircleMockData.circles.cast<Map<String, dynamic>?>().firstWhere(
                  (candidate) =>
                      (candidate?['id'] ?? candidate?['circleId'])
                          ?.toString()
                          .trim() ==
                      id,
                  orElse: () => null,
                ),
          )
          .whereType<Map<String, dynamic>>()
          .toList(growable: false);
      final matchedCircle = associatedCircles
          .where(
            (circle) =>
                (expectedCategoryId.isEmpty ||
                    (circle['categoryId'] ?? '').toString().toLowerCase() ==
                        expectedCategoryId) &&
                (expectedSubCategory.isEmpty ||
                    (circle['subCategory'] ?? '').toString().toLowerCase() ==
                        expectedSubCategory),
          )
          .cast<Map<String, dynamic>?>()
          .firstWhere(
            (_) => true,
            orElse: () =>
                associatedCircles.isEmpty ? null : associatedCircles.first,
          );
      final itemIdentity =
          (item['contentIdentity'] ??
                  (item['contentType'] == 'micro' ? 'moment' : 'work'))
              .toString()
              .toLowerCase();
      final itemType = (item['contentType'] ?? item['type'] ?? '')
          .toString()
          .toLowerCase();
      final itemCategoryId =
          (item['categoryId'] ?? matchedCircle?['categoryId'] ?? '')
              .toString()
              .toLowerCase();
      final itemSubCategory =
          (item['subCategory'] ?? matchedCircle?['subCategory'] ?? '')
              .toString()
              .toLowerCase();
      if (expectedIdentity.isNotEmpty && itemIdentity != expectedIdentity) {
        continue;
      }
      if (expectedType.isNotEmpty && itemType != expectedType) {
        continue;
      }
      if (expectedCategoryId.isNotEmpty &&
          itemCategoryId != expectedCategoryId) {
        continue;
      }
      if (expectedSubCategory.isNotEmpty &&
          itemSubCategory != expectedSubCategory) {
        continue;
      }
      final searchable = <String>[
        item['title']?.toString() ?? '',
        item['body']?.toString() ?? '',
        item['summary']?.toString() ?? '',
        item['locationName']?.toString() ?? '',
        item['displayName']?.toString() ?? '',
      ];
      final matched = searchable.firstWhere(
        (value) => value.toLowerCase().contains(normalizedQuery),
        orElse: () => '',
      );
      if (matched.isEmpty) {
        continue;
      }
      results.add(
        PostSearchItemView.fromMap(<String, dynamic>{
          ...item,
          'categoryId': item['categoryId'] ?? matchedCircle?['categoryId'],
          'subCategory': item['subCategory'] ?? matchedCircle?['subCategory'],
          'highlightText': matched,
          'matchedField': matched == (item['title']?.toString() ?? '')
              ? 'title'
              : matched == (item['displayName']?.toString() ?? '')
              ? 'author'
              : 'body',
          'authorProfileSubjectId':
              item['profileSubjectId'] ?? item['authorId'] ?? '',
          'authorDisplayName':
              item['displayName'] ?? item['authorDisplayNameSnapshot'] ?? '',
          'authorAvatarUrl':
              item['authorAvatarUrl'] ?? item['authorAvatarUrlSnapshot'] ?? '',
        }),
      );
      if (results.length >= limit) {
        break;
      }
    }
    return results;
  }

  @override
  Future<ContentPostDetailPayload> getPost({required String postId}) async {
    final allRaw = [
      ...ContentMockData.discoveryPhotoData,
      ...ContentMockData.discoveryVideoData,
      ...ContentMockData.discoveryMomentData,
      ...ContentMockData.discoveryArticleData,
    ];
    final raw = allRaw.firstWhere(
      (m) => m['postId']?.toString() == postId,
      orElse: () => <String, dynamic>{},
    );
    if (raw.isEmpty) return Future.error(Exception('Post $postId not found'));
    return ContentPostDetailPayload.fromWire(raw);
  }

  @override
  Future<Map<String, dynamic>> createPost({
    required Map<String, dynamic> payload,
  }) async {
    final postId = 'local_${DateTime.now().millisecondsSinceEpoch}';
    final type = (payload['type'] ?? payload['contentType'] ?? '')
        .toString()
        .trim();
    return <String, dynamic>{
      ...payload,
      'id': postId,
      'postId': postId,
      if (type.isNotEmpty) 'type': type,
    };
  }

  @override
  Future<void> likePost({required String postId}) async {
    likePostCallCount++;
    if (throwOnLike != null) throw throwOnLike!;
    countersStubLikeCount++;
  }

  @override
  Future<void> unlikePost({required String postId}) async {
    likePostCallCount++;
    if (throwOnLike != null) throw throwOnLike!;
  }

  @override
  Future<void> favoritePost({required String postId}) async {
    if (throwOnFavorite != null) throw throwOnFavorite!;
  }

  @override
  Future<void> unfavoritePost({required String postId}) async {}

  @override
  Future<Map<String, dynamic>> getReactionState({
    required String postId,
  }) async {
    return reactionStateStub;
  }

  @override
  Future<CommentPage> listComments({
    required String postId,
    String? cursor,
    String sort = 'latest',
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final dtos = commentsStub.map(CommentDto.fromMap).toList();
    return CommentPage(items: dtos, nextCursor: null);
  }

  @override
  Future<Map<String, dynamic>> createComment({
    required String postId,
    required String content,
    String? replyToCommentId,
    String? personaId,
    String? profileSubjectId,
    String? personaContextVersion,
  }) async {
    createCommentCallCount++;
    lastCommentPostId = postId;
    lastCommentText = content;
    if (throwOnCreateComment != null) throw throwOnCreateComment!;
    final comment = <String, dynamic>{
      '_id': 'mock_comment_${DateTime.now().millisecondsSinceEpoch}',
      'postId': postId,
      'content': content,
      'authorId': 'mock_user',
      'profileSubjectId': profileSubjectId ?? 'mock_user',
      'personaId': personaId,
      'personaContextVersion': personaContextVersion,
      'replyCount': 0,
      'likeCount': 0,
      'status': 'visible',
      'isAuthor': false,
      'createdAt': DateTime.now().toIso8601String(),
    };
    if (replyToCommentId != null) {
      comment['replyToCommentId'] = replyToCommentId;
    }
    commentsStub = [...commentsStub, comment];
    countersStubCommentCount++;
    return comment;
  }

  @override
  Future<void> deleteComment({
    required String postId,
    required String commentId,
  }) async {
    commentsStub = commentsStub.where((c) => c['_id'] != commentId).toList();
  }

  @override
  Future<void> likeComment({required String commentId}) async {}

  @override
  Future<void> unlikeComment({required String commentId}) async {}

  @override
  Future<CommentPage> listCommentsByAuthor({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return const CommentPage(items: [], nextCursor: null);
  }

  @override
  Future<CommentPage> listCommentsForPostAuthor({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return const CommentPage(items: [], nextCursor: null);
  }

  @override
  Future<Map<String, dynamic>> getAppConfig() async {
    return {
      'content': {
        'comment': {
          'max_length': 500,
          'reply_preview_count': 3,
          'fold_line_count': 3,
        },
        'feature_flags': {
          'enable_create_action_entry': true,
          'enable_unified_create_editor': true,
          'simple_create_action_sheet': true,
          'progressive_title_prompt': true,
          'enable_identity_based_surfaces': true,
          'enable_identity_share_template': true,
          'enable_article_distribution_profiles': true,
          'enable_article_book_reader': true,
          'enable_article_page_curl': true,
          'enable_assistant_content_identity_index': true,
        },
        'gray_release': {
          'experiment_bucket': 'local_story_enabled',
          'current_stage': '100%',
          'canary_matrix': [
            {'stage': '5%', 'rolloutPercent': 5},
            {'stage': '20%', 'rolloutPercent': 20},
            {'stage': '50%', 'rolloutPercent': 50},
            {'stage': '100%', 'rolloutPercent': 100},
          ],
        },
      },
    };
  }

  @override
  Future<void> reportBehaviors({
    required List<Map<String, dynamic>> events,
  }) async {}

  @override
  Future<Map<String, dynamic>> getCounters({required String postId}) async {
    return {
      'likeCount': countersStubLikeCount,
      'commentCount': countersStubCommentCount,
    };
  }

  @override
  Future<Map<String, dynamic>> updatePost({
    required String postId,
    required Map<String, dynamic> payload,
  }) async {
    return <String, dynamic>{'postId': postId, ...payload};
  }

  @override
  Future<void> deletePost({required String postId}) async {}

  @override
  Future<Map<String, dynamic>> publishPost({
    required String postId,
    Map<String, dynamic> payload = const <String, dynamic>{},
  }) async {
    return {'postId': postId, 'status': 'published', ...payload};
  }

  @override
  Future<Map<String, dynamic>> updatePostSettings({
    required String postId,
    required Map<String, dynamic> payload,
  }) async {
    return {'postId': postId, ...payload};
  }

  @override
  Future<Map<String, dynamic>> promotePostToWork({
    required String postId,
    required Map<String, dynamic> payload,
  }) async {
    return {
      'postId': postId,
      'contentIdentity': 'work',
      'status': 'published',
      ...payload,
    };
  }

  @override
  Future<Map<String, dynamic>> updatePostCircles({
    required String postId,
    List<String> add = const [],
    List<String> remove = const [],
  }) async {
    return {'postId': postId, 'circleIds': add};
  }

  @override
  Future<Map<String, dynamic>> repostToCircle({
    required String postId,
    required String circleId,
  }) async {
    return {'postId': postId, 'circleId': circleId, 'type': 'moment'};
  }

  @override
  Future<Map<String, dynamic>> quoteToCircle({
    required String postId,
    required String circleId,
    String quoteText = '',
  }) async {
    return {
      'postId': postId,
      'circleId': circleId,
      'sourceType': 'quote',
      'quoteText': quoteText,
    };
  }

  @override
  Future<Map<String, dynamic>> initMediaUpload({
    String mediaType = 'image',
  }) async {
    final ts = DateTime.now().millisecondsSinceEpoch;
    return {
      'sessionId': 'mock_upload_$ts',
      'mediaId': 'mock_media_$ts',
      'uploadUrl': 'https://origin.example/upload/mock_media_$ts',
    };
  }

  @override
  Future<Map<String, dynamic>> completeMediaUpload({
    required String sessionId,
  }) async {
    return {
      'sessionId': sessionId,
      'status': 'ready',
      'cdnUrl': 'https://cdn.example/media/mock',
    };
  }

  @override
  Future<void> abortMediaUpload({required String sessionId}) async {}

  @override
  Future<Map<String, dynamic>> getMediaAsset({required String mediaId}) async {
    return {
      'mediaId': mediaId,
      'status': 'ready',
      'type': 'image',
      'cdnUrl': 'https://cdn.example/media/$mediaId',
    };
  }

  @override
  Future<Map<String, dynamic>> selectAutoVideoCover({
    required String mediaId,
  }) async {
    return {'mediaId': mediaId, 'coverStrategy': 'first_frame'};
  }

  @override
  Future<Map<String, dynamic>> selectManualVideoCover({
    required String mediaId,
    required String coverAssetId,
  }) async {
    return {
      'mediaId': mediaId,
      'coverStrategy': 'manual',
      'manualCoverAssetId': coverAssetId,
    };
  }

  @override
  Future<Map<String, dynamic>> generateArticleSummary({
    required String title,
    required String body,
  }) async {
    final preview = body.length > 100 ? body.substring(0, 100) : body;
    return {'summary': '$title：$preview'};
  }

  @override
  Future<Map<String, dynamic>> getRecommendation({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return {'items': [], 'nextCursor': null};
  }

  @override
  Future<CursorPage<PostBaseDto>> listUserPosts({
    required String userId,
    String? identity,
    String? type,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final allRaw = _allRawPosts();
    final filtered = allRaw
        .where((m) => m['authorId']?.toString() == userId)
        .where(
          (m) => _matchesIdentityAndType(m, identity: identity, type: type),
        )
        .toList();
    final items = filtered.map(postBaseDtoFromMap).toList(growable: false);
    return CursorPage<PostBaseDto>(items: items, nextCursor: null);
  }

  List<Map<String, dynamic>> _allRawPosts() {
    return <Map<String, dynamic>>[
      ...ContentMockData.discoveryPhotoData,
      ...ContentMockData.discoveryVideoData,
      ...ContentMockData.discoveryMomentData,
      ...ContentMockData.discoveryArticleData,
    ];
  }

  List<Map<String, dynamic>> _resolveDiscoveryRaw({
    required String category,
    String? identity,
    String? type,
  }) {
    final resolvedIdentity = identity ?? _mapCategoryToIdentity(category);
    final resolvedType = _normalizeFeedType(
      type ?? _mapCategoryToFeedType(category),
    );
    return _allRawPosts()
        .where(
          (item) => _matchesIdentityAndType(
            item,
            identity: resolvedIdentity,
            type: resolvedType,
          ),
        )
        .toList(growable: false);
  }

  String? _mapCategoryToIdentity(String category) {
    switch (category.trim()) {
      case 'moment':
      case 'recommended':
      case 'following':
        return 'moment';
      case 'work':
      case 'works':
      case 'photo':
      case 'images':
      case 'video':
      case 'article':
        return 'work';
      default:
        return null;
    }
  }

  String? _mapCategoryToFeedType(String category) {
    final mapped =
        GeneratedPostRuntimeMetadata.feedCategoryToRequestType[category];
    return _normalizeFeedType(mapped);
  }

  String? _normalizeFeedType(String? type) {
    final normalized = (type ?? '').trim().toLowerCase();
    switch (normalized) {
      case '':
        return null;
      case 'photo':
        return 'image';
      case 'note':
        return 'article';
      default:
        return normalized;
    }
  }

  bool _matchesIdentityAndType(
    Map<String, dynamic> item, {
    String? identity,
    String? type,
  }) {
    final itemType = _normalizeFeedType(
      item['contentType']?.toString() ?? item['type']?.toString(),
    );
    final itemIdentity =
        (item['contentIdentity'] ??
                item['identity'] ??
                ((itemType == 'micro' || item['type']?.toString() == 'moment')
                    ? 'moment'
                    : 'work'))
            .toString();
    final expectedIdentity = (identity ?? '').trim();
    final expectedType = _normalizeFeedType(type);
    if (expectedIdentity.isNotEmpty && itemIdentity != expectedIdentity) {
      return false;
    }
    if (expectedType != null && expectedType.isNotEmpty) {
      if (expectedType == 'moment') {
        return itemIdentity == 'moment';
      }
      return itemType == expectedType;
    }
    return true;
  }
}

class RemoteContentRepository implements ContentRepository {
  RemoteContentRepository({
    CloudHttpClient? httpClient,
    http.Client? client,
    String? baseUrl,
  }) : _httpClient =
           httpClient ?? CloudHttpClient(client: client ?? http.Client()),
       _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();

  final CloudHttpClient _httpClient;
  final String _baseUrl;

  Uri _uri(String path, {Map<String, String>? queryParameters}) {
    return Uri.parse(
      '$_baseUrl$path',
    ).replace(queryParameters: queryParameters);
  }

  @override
  Future<CursorPage<PostBaseDto>> listDiscoveryFeedPage({
    required String category,
    String? identity,
    String? type,
    String? subCategory,
    int limit = GeneratedPostRuntimeMetadata.feedDefaultLimit,
    String? cursor,
    String sort = kFeedSortRecommend,
  }) async {
    final resolvedIdentity = identity ?? _mapCategoryToIdentity(category);
    final resolvedType = _normalizeFeedType(
      type ?? _mapCategoryToFeedType(category),
    );
    final query = <String, String>{};
    final keys = GeneratedPostRuntimeMetadata.feedQueryParams;
    if (keys.contains('identity') &&
        resolvedIdentity != null &&
        resolvedIdentity.isNotEmpty) {
      query['identity'] = resolvedIdentity;
    }
    if (keys.contains('type') &&
        resolvedType != null &&
        resolvedType.isNotEmpty &&
        !(resolvedIdentity == 'moment' && (type == null || type.isEmpty))) {
      query['type'] = resolvedType;
    }
    if (keys.contains('cursor') && cursor?.isNotEmpty == true) {
      query['cursor'] = cursor!;
    }
    if (keys.contains('sort') && sort.trim().isNotEmpty) {
      query['sort'] = sort.trim();
    }
    if (keys.contains('limit')) {
      query['limit'] = '$limit';
    }
    if (keys.contains('subCategory') && subCategory?.isNotEmpty == true) {
      query['subCategory'] = subCategory!;
    }
    final uri = _uri(ContentApiMetadata.getFeedPath, queryParameters: query);
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.getFeed),
    );
    final rawPage = CloudResponseDecoder.asCursorPage(
      decoded,
      context: ContentRequestPageIds.getFeed,
    );
    final dtoItems = rawPage.items
        .map(postBaseDtoFromMap)
        .toList(growable: false);
    return CursorPage<PostBaseDto>(
      items: dtoItems,
      nextCursor: rawPage.nextCursor,
    );
  }

  @override
  Future<List<PostBaseDto>> listDiscoveryFeed({
    required String category,
    String? identity,
    String? type,
    String? subCategory,
    int limit = GeneratedPostRuntimeMetadata.feedDefaultLimit,
    String? cursor,
    String sort = kFeedSortRecommend,
  }) async {
    final page = await listDiscoveryFeedPage(
      category: category,
      identity: identity,
      type: type,
      subCategory: subCategory,
      limit: limit,
      cursor: cursor,
      sort: sort,
    );
    return page.items;
  }

  @override
  Future<ContentPostDetailPayload> getPost({required String postId}) async {
    final uri = _uri(ContentApiMetadata.getPostPath(postId: postId));
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.getPost),
    );
    final obj = CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.getPost,
    );
    return ContentPostDetailPayload.fromWire(obj);
  }

  @override
  Future<Map<String, dynamic>> createPost({
    required Map<String, dynamic> payload,
  }) async {
    final uri = _uri(ContentApiMetadata.createPostPath);
    final decoded = await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.createPost),
      body: payload,
    );
    return CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.createPost,
    );
  }

  @override
  Future<void> likePost({required String postId}) async {
    final uri = _uri(ContentApiMetadata.likePostPath(postId: postId));
    await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.likePost),
      body: {},
    );
  }

  @override
  Future<void> unlikePost({required String postId}) async {
    final uri = _uri(ContentApiMetadata.unlikePostPath(postId: postId));
    await _httpClient.deleteJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.unlikePost),
    );
  }

  @override
  Future<void> favoritePost({required String postId}) async {
    final uri = _uri(ContentApiMetadata.favoritePostPath(postId: postId));
    await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.favoritePost),
      body: {},
    );
  }

  @override
  Future<void> unfavoritePost({required String postId}) async {
    final uri = _uri(ContentApiMetadata.unfavoritePostPath(postId: postId));
    await _httpClient.deleteJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.unfavoritePost,
      ),
    );
  }

  @override
  Future<Map<String, dynamic>> getReactionState({
    required String postId,
  }) async {
    final uri = _uri(ContentApiMetadata.getReactionStatePath(postId: postId));
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.getReactionState,
      ),
    );
    return CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.getReactionState,
    );
  }

  @override
  Future<CommentPage> listComments({
    required String postId,
    String? cursor,
    String sort = 'latest',
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final query = <String, String>{'limit': '$limit', 'sort': sort};
    if (cursor != null) query['cursor'] = cursor;
    final uri = _uri(
      ContentApiMetadata.listCommentsPath(postId: postId),
      queryParameters: query,
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.listComments),
    );
    final rawPage = CloudResponseDecoder.asCursorPage(
      decoded,
      context: ContentRequestPageIds.listComments,
    );
    final dtos = rawPage.items
        .cast<Map<String, dynamic>>()
        .map(CommentDto.fromMap)
        .toList(growable: false);
    return CommentPage(items: dtos, nextCursor: rawPage.nextCursor);
  }

  @override
  Future<Map<String, dynamic>> createComment({
    required String postId,
    required String content,
    String? replyToCommentId,
    String? personaId,
    String? profileSubjectId,
    String? personaContextVersion,
  }) async {
    final uri = _uri(ContentApiMetadata.createCommentPath(postId: postId));
    final body = <String, dynamic>{'content': content};
    if (replyToCommentId != null) body['replyToCommentId'] = replyToCommentId;
    if (personaId != null) body['personaId'] = personaId;
    if (profileSubjectId != null) body['profileSubjectId'] = profileSubjectId;
    if (personaContextVersion != null) {
      body['personaContextVersion'] = personaContextVersion;
    }
    final decoded = await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.createComment),
      body: body,
    );
    return CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.createComment,
    );
  }

  @override
  Future<void> deleteComment({
    required String postId,
    required String commentId,
  }) async {
    final uri = _uri(
      ContentApiMetadata.deleteCommentPath(
        postId: postId,
        commentId: commentId,
      ),
    );
    await _httpClient.deleteJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.deleteComment),
    );
  }

  @override
  Future<void> likeComment({required String commentId}) async {
    final uri = _uri(ContentApiMetadata.likeCommentPath(commentId: commentId));
    await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.likeComment),
      body: {},
    );
  }

  @override
  Future<void> unlikeComment({required String commentId}) async {
    final uri = _uri(
      ContentApiMetadata.unlikeCommentPath(commentId: commentId),
    );
    await _httpClient.deleteJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.unlikeComment),
    );
  }

  @override
  Future<CommentPage> listCommentsByAuthor({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final query = <String, String>{'limit': '$limit'};
    if (cursor != null) query['cursor'] = cursor;
    final uri = _uri(
      ContentApiMetadata.listCommentsByAuthorPath,
      queryParameters: query,
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.listCommentsByAuthor,
      ),
    );
    final rawPage = CloudResponseDecoder.asCursorPage(
      decoded,
      context: ContentRequestPageIds.listCommentsByAuthor,
    );
    final dtos = rawPage.items
        .cast<Map<String, dynamic>>()
        .map(CommentDto.fromMap)
        .toList(growable: false);
    return CommentPage(items: dtos, nextCursor: rawPage.nextCursor);
  }

  @override
  Future<CommentPage> listCommentsForPostAuthor({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final query = <String, String>{'limit': '$limit'};
    if (cursor != null) query['cursor'] = cursor;
    final uri = _uri(
      ContentApiMetadata.listCommentsForPostAuthorPath,
      queryParameters: query,
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.listCommentsForPostAuthor,
      ),
    );
    final rawPage = CloudResponseDecoder.asCursorPage(
      decoded,
      context: ContentRequestPageIds.listCommentsForPostAuthor,
    );
    final dtos = rawPage.items
        .cast<Map<String, dynamic>>()
        .map(CommentDto.fromMap)
        .toList(growable: false);
    return CommentPage(items: dtos, nextCursor: rawPage.nextCursor);
  }

  @override
  Future<Map<String, dynamic>> getAppConfig() async {
    final uri = _uri(ContentApiMetadata.getAppConfigPath);
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.getAppConfig),
    );
    return CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.getAppConfig,
    );
  }

  @override
  Future<void> reportBehaviors({
    required List<Map<String, dynamic>> events,
  }) async {
    final uri = _uri(ContentApiMetadata.reportBehaviorsPath);
    await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.reportBehaviors,
      ),
      body: {'events': events},
    );
  }

  @override
  Future<Map<String, dynamic>> getCounters({required String postId}) async {
    final uri = _uri(ContentApiMetadata.getCountersPath(postId: postId));
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.getCounters),
    );
    return CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.getCounters,
    );
  }

  @override
  Future<Map<String, dynamic>> updatePost({
    required String postId,
    required Map<String, dynamic> payload,
  }) async {
    final uri = _uri(ContentApiMetadata.updatePostPath(postId: postId));
    final decoded = await _httpClient.patchJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.updatePost),
      body: payload,
    );
    return CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.updatePost,
    );
  }

  @override
  Future<void> deletePost({required String postId}) async {
    final uri = _uri(ContentApiMetadata.deletePostPath(postId: postId));
    await _httpClient.deleteJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.deletePost),
    );
  }

  @override
  Future<Map<String, dynamic>> publishPost({
    required String postId,
    Map<String, dynamic> payload = const <String, dynamic>{},
  }) async {
    final uri = _uri(ContentApiMetadata.publishPostPath(postId: postId));
    final decoded = await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.publishPost),
      body: payload,
    );
    return CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.publishPost,
    );
  }

  @override
  Future<Map<String, dynamic>> updatePostSettings({
    required String postId,
    required Map<String, dynamic> payload,
  }) async {
    final uri = _uri(ContentApiMetadata.updatePostSettingsPath(postId: postId));
    final decoded = await _httpClient.patchJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.updatePostSettings,
      ),
      body: payload,
    );
    return CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.updatePostSettings,
    );
  }

  @override
  Future<Map<String, dynamic>> promotePostToWork({
    required String postId,
    required Map<String, dynamic> payload,
  }) async {
    final uri = _uri(ContentApiMetadata.promotePostToWorkPath(postId: postId));
    final decoded = await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.promotePostToWork,
      ),
      body: payload,
    );
    return CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.promotePostToWork,
    );
  }

  @override
  Future<Map<String, dynamic>> updatePostCircles({
    required String postId,
    List<String> add = const [],
    List<String> remove = const [],
  }) async {
    final uri = _uri(ContentApiMetadata.updatePostCirclesPath(postId: postId));
    final decoded = await _httpClient.patchJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.updatePostCircles,
      ),
      body: {'add': add, 'remove': remove},
    );
    return CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.updatePostCircles,
    );
  }

  @override
  Future<Map<String, dynamic>> repostToCircle({
    required String postId,
    required String circleId,
  }) async {
    final uri = _uri(ContentApiMetadata.repostToCirclePath(postId: postId));
    final decoded = await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.repostToCircle,
      ),
      body: {'circleId': circleId},
    );
    return CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.repostToCircle,
    );
  }

  @override
  Future<Map<String, dynamic>> quoteToCircle({
    required String postId,
    required String circleId,
    String quoteText = '',
  }) async {
    final uri = _uri(ContentApiMetadata.quoteToCirclePath(postId: postId));
    final decoded = await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.quoteToCircle),
      body: {'circleId': circleId, 'quoteText': quoteText},
    );
    return CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.quoteToCircle,
    );
  }

  @override
  Future<Map<String, dynamic>> initMediaUpload({
    String mediaType = 'image',
  }) async {
    final uri = _uri(ContentApiMetadata.initMediaUploadPath);
    final decoded = await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.initMediaUpload,
      ),
      body: {'mediaType': mediaType},
    );
    return CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.initMediaUpload,
    );
  }

  @override
  Future<Map<String, dynamic>> completeMediaUpload({
    required String sessionId,
  }) async {
    final uri = _uri(
      ContentApiMetadata.completeMediaUploadPath(sessionId: sessionId),
    );
    final decoded = await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.completeMediaUpload,
      ),
      body: {},
    );
    return CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.completeMediaUpload,
    );
  }

  @override
  Future<void> abortMediaUpload({required String sessionId}) async {
    final uri = _uri(
      ContentApiMetadata.abortMediaUploadPath(sessionId: sessionId),
    );
    await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.abortMediaUpload,
      ),
      body: {},
    );
  }

  @override
  Future<Map<String, dynamic>> getMediaAsset({required String mediaId}) async {
    final uri = _uri(ContentApiMetadata.getMediaAssetPath(mediaId: mediaId));
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.getMediaAsset),
    );
    return CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.getMediaAsset,
    );
  }

  @override
  Future<Map<String, dynamic>> selectAutoVideoCover({
    required String mediaId,
  }) async {
    final uri = _uri(
      ContentApiMetadata.selectAutoVideoCoverPath(mediaId: mediaId),
    );
    final decoded = await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.selectAutoVideoCover,
      ),
      body: {},
    );
    return CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.selectAutoVideoCover,
    );
  }

  @override
  Future<Map<String, dynamic>> selectManualVideoCover({
    required String mediaId,
    required String coverAssetId,
  }) async {
    final uri = _uri(
      ContentApiMetadata.selectManualVideoCoverPath(mediaId: mediaId),
    );
    final decoded = await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.selectManualVideoCover,
      ),
      body: {'coverAssetId': coverAssetId},
    );
    return CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.selectManualVideoCover,
    );
  }

  @override
  Future<Map<String, dynamic>> generateArticleSummary({
    required String title,
    required String body,
  }) async {
    final uri = _uri(ContentApiMetadata.generateArticleSummaryPath);
    final decoded = await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.generateArticleSummary,
      ),
      body: {'title': title, 'body': body},
    );
    return CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.generateArticleSummary,
    );
  }

  @override
  Future<Map<String, dynamic>> getRecommendation({
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final uri = _uri(ContentApiMetadata.getRecommendationPath);
    final decoded = await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.getRecommendation,
      ),
      body: {'limit': limit, 'cursor': ?cursor},
    );
    return CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.getRecommendation,
    );
  }

  @override
  Future<CursorPage<PostBaseDto>> listUserPosts({
    required String userId,
    String? identity,
    String? type,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final query = <String, String>{'limit': '$limit'};
    if (cursor != null) query['cursor'] = cursor;
    if (identity != null && identity.isNotEmpty) query['identity'] = identity;
    final resolvedType = _normalizeFeedType(type);
    if (resolvedType != null && resolvedType.isNotEmpty) {
      query['type'] = resolvedType;
    }
    final uri = _uri(
      ContentApiMetadata.listUserPostsPath(profileSubjectId: userId),
      queryParameters: query,
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.listUserPosts),
    );
    final rawPage = CloudResponseDecoder.asCursorPage(
      decoded,
      context: ContentRequestPageIds.listUserPosts,
    );
    final dtoItems = rawPage.items
        .map(postBaseDtoFromMap)
        .toList(growable: false);
    return CursorPage<PostBaseDto>(
      items: dtoItems,
      nextCursor: rawPage.nextCursor,
    );
  }

  @override
  Future<List<PostSearchItemView>> searchPosts({
    required String query,
    String? identity,
    String? type,
    String? categoryId,
    String? subCategory,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final uri = _uri(
      ContentApiMetadata.searchPostsPath,
      queryParameters: <String, String>{
        'query': query,
        if (identity != null && identity.isNotEmpty) 'identity': identity,
        if (type != null && type.isNotEmpty) 'type': type,
        if (categoryId != null && categoryId.isNotEmpty)
          'categoryId': categoryId,
        if (subCategory != null && subCategory.isNotEmpty)
          'subCategory': subCategory,
        'limit': '$limit',
      },
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.searchPosts),
    );
    final rawPage = CloudResponseDecoder.asCursorPage(
      decoded,
      context: ContentRequestPageIds.searchPosts,
    );
    return rawPage.items
        .map(PostSearchItemView.fromMap)
        .toList(growable: false);
  }

  String? _mapCategoryToFeedType(String category) {
    return GeneratedPostRuntimeMetadata.feedCategoryToRequestType[category];
  }

  String? _mapCategoryToIdentity(String category) {
    switch (category.trim()) {
      case 'moment':
      case 'recommended':
      case 'following':
        return 'moment';
      case 'work':
      case 'works':
      case 'photo':
      case 'images':
      case 'video':
      case 'article':
        return 'work';
      default:
        return null;
    }
  }

  String? _normalizeFeedType(String? type) {
    final normalized = (type ?? '').trim().toLowerCase();
    switch (normalized) {
      case '':
        return null;
      case 'photo':
        return 'image';
      case 'note':
        return 'article';
      default:
        return normalized;
    }
  }
}
