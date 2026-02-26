import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/feed_item_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/services/content/mock/content_mock_data.dart';

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
///
/// 兼容层：[listDiscoveryFeedItems] 为旧 [FeedItemDto] 调用方过渡提供，
/// 待全部迁移至 [PostBaseDto] 后删除。
abstract class ContentRepository {
  Future<CursorPage<PostBaseDto>> listDiscoveryFeedPage({
    required String category,
    String? subCategory,
    int limit = GeneratedPostRuntimeMetadata.feedDefaultLimit,
    String? cursor,
  });

  Future<List<PostBaseDto>> listDiscoveryFeed({
    required String category,
    String? subCategory,
    int limit = GeneratedPostRuntimeMetadata.feedDefaultLimit,
    String? cursor,
  });

  /// @deprecated 兼容层：给尚未迁移到 PostBaseDto 的调用方使用。
  /// 内部调用 [listDiscoveryFeedPage] 并将结果转换为 [FeedItemDto]。
  Future<CursorPage<FeedItemDto>> listDiscoveryFeedPageLegacy({
    required String category,
    String? subCategory,
    int limit = GeneratedPostRuntimeMetadata.feedDefaultLimit,
    String? cursor,
  });

  Future<Map<String, dynamic>> getPost({
    required String postId,
  });

  Future<Map<String, dynamic>> createPost({
    required Map<String, dynamic> payload,
  });

  Future<void> likePost({required String postId});
  Future<void> unlikePost({required String postId});
  Future<void> favoritePost({required String postId});
  Future<void> unfavoritePost({required String postId});
  Future<Map<String, dynamic>> getReactionState({required String postId});
  Future<List<Map<String, dynamic>>> listComments({
    required String postId,
    String? cursor,
    int limit = 20,
  });
  Future<Map<String, dynamic>> createComment({
    required String postId,
    required String content,
    String? replyToCommentId,
  });
  Future<void> deleteComment({required String postId, required String commentId});
  Future<void> reportBehaviors({required List<Map<String, dynamic>> events});
  Future<Map<String, dynamic>> getCounters({required String postId});
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
    String? subCategory,
    int limit = GeneratedPostRuntimeMetadata.feedDefaultLimit,
    String? cursor,
  }) async {
    final rawList = _getRawListForCategory(category);
    final items = rawList.map(postBaseDtoFromMap).toList(growable: false);
    return CursorPage<PostBaseDto>(items: items, nextCursor: null);
  }

  @override
  Future<List<PostBaseDto>> listDiscoveryFeed({
    required String category,
    String? subCategory,
    int limit = GeneratedPostRuntimeMetadata.feedDefaultLimit,
    String? cursor,
  }) async {
    final page = await listDiscoveryFeedPage(
      category: category,
      subCategory: subCategory,
      limit: limit,
      cursor: cursor,
    );
    return page.items;
  }

  @override
  Future<CursorPage<FeedItemDto>> listDiscoveryFeedPageLegacy({
    required String category,
    String? subCategory,
    int limit = GeneratedPostRuntimeMetadata.feedDefaultLimit,
    String? cursor,
  }) async {
    final page = await listDiscoveryFeedPage(
      category: category,
      subCategory: subCategory,
      limit: limit,
      cursor: cursor,
    );
    final legacyItems = page.items
        .map((dto) => FeedItemDto.fromMap(dto.toMap()))
        .toList(growable: false);
    return CursorPage<FeedItemDto>(items: legacyItems, nextCursor: page.nextCursor);
  }

  @override
  Future<Map<String, dynamic>> getPost({required String postId}) async {
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
    return raw;
  }

  @override
  Future<Map<String, dynamic>> createPost({
    required Map<String, dynamic> payload,
  }) async {
    return <String, dynamic>{...payload, 'postId': 'local_${DateTime.now().millisecondsSinceEpoch}'};
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
  Future<Map<String, dynamic>> getReactionState({required String postId}) async {
    return reactionStateStub;
  }

  @override
  Future<List<Map<String, dynamic>>> listComments({
    required String postId,
    String? cursor,
    int limit = 20,
  }) async {
    return commentsStub;
  }

  @override
  Future<Map<String, dynamic>> createComment({
    required String postId,
    required String content,
    String? replyToCommentId,
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
      'createdAt': DateTime.now().toIso8601String(),
    };
    if (replyToCommentId != null) comment['replyToCommentId'] = replyToCommentId;
    commentsStub = [...commentsStub, comment];
    countersStubCommentCount++;
    return comment;
  }

  @override
  Future<void> deleteComment({required String postId, required String commentId}) async {
    commentsStub = commentsStub.where((c) => c['_id'] != commentId).toList();
  }

  @override
  Future<void> reportBehaviors({required List<Map<String, dynamic>> events}) async {}

  @override
  Future<Map<String, dynamic>> getCounters({required String postId}) async {
    return {
      'likeCount': countersStubLikeCount,
      'commentCount': countersStubCommentCount,
    };
  }

  List<Map<String, dynamic>> _getRawListForCategory(String category) {
    final feedType = GeneratedPostRuntimeMetadata.feedCategoryToRequestType[category] ?? '';
    switch (feedType) {
      case 'photo':
        return ContentMockData.discoveryPhotoData;
      case 'video':
        return ContentMockData.discoveryVideoData;
      case 'article':
        return ContentMockData.discoveryArticleData;
      default:
        return ContentMockData.discoveryMomentData;
    }
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

  @override
  Future<CursorPage<PostBaseDto>> listDiscoveryFeedPage({
    required String category,
    String? subCategory,
    int limit = GeneratedPostRuntimeMetadata.feedDefaultLimit,
    String? cursor,
  }) async {
    final type = _mapCategoryToFeedType(category);
    final query = <String, String>{};
    final keys = GeneratedPostRuntimeMetadata.feedQueryParams;
    if (keys.contains('type') && type != null && type.isNotEmpty) {
      query['type'] = type;
    }
    if (keys.contains('cursor') && cursor?.isNotEmpty == true) {
      query['cursor'] = cursor!;
    }
    if (keys.contains('limit')) {
      query['limit'] = '$limit';
    }
    if (keys.contains('subCategory') && subCategory?.isNotEmpty == true) {
      query['subCategory'] = subCategory!;
    }
    final uri = Uri.parse('$_baseUrl${GeneratedPostRuntimeMetadata.feedPath}').replace(
      queryParameters: query,
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage('content.feed.list'),
    );
    final rawPage = CloudResponseDecoder.asCursorPage(
      decoded,
      context: 'content.feed.list',
    );
    final dtoItems = rawPage.items.map(postBaseDtoFromMap).toList(growable: false);
    return CursorPage<PostBaseDto>(items: dtoItems, nextCursor: rawPage.nextCursor);
  }

  @override
  Future<List<PostBaseDto>> listDiscoveryFeed({
    required String category,
    String? subCategory,
    int limit = GeneratedPostRuntimeMetadata.feedDefaultLimit,
    String? cursor,
  }) async {
    final page = await listDiscoveryFeedPage(
      category: category,
      subCategory: subCategory,
      limit: limit,
      cursor: cursor,
    );
    return page.items;
  }

  @override
  Future<CursorPage<FeedItemDto>> listDiscoveryFeedPageLegacy({
    required String category,
    String? subCategory,
    int limit = GeneratedPostRuntimeMetadata.feedDefaultLimit,
    String? cursor,
  }) async {
    final page = await listDiscoveryFeedPage(
      category: category,
      subCategory: subCategory,
      limit: limit,
      cursor: cursor,
    );
    final legacyItems = page.items
        .map((dto) => FeedItemDto.fromMap(dto.toMap()))
        .toList(growable: false);
    return CursorPage<FeedItemDto>(items: legacyItems, nextCursor: page.nextCursor);
  }

  @override
  Future<Map<String, dynamic>> getPost({required String postId}) async {
    final path = GeneratedPostRuntimeMetadata.postDetailPathTemplate.replaceAll(
      '{postId}',
      Uri.encodeComponent(postId),
    );
    final uri = Uri.parse('$_baseUrl$path');
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage('content.post.get'),
    );
    return CloudResponseDecoder.asObject(decoded, context: 'content.post.get');
  }

  @override
  Future<Map<String, dynamic>> createPost({
    required Map<String, dynamic> payload,
  }) async {
    final uri = Uri.parse('$_baseUrl/v1/content/posts');
    final decoded = await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage('content.post.create'),
      body: payload,
    );
    return CloudResponseDecoder.asObject(decoded, context: 'content.post.create');
  }

  @override
  Future<void> likePost({required String postId}) async {
    final uri = Uri.parse('$_baseUrl/v1/content/posts/${Uri.encodeComponent(postId)}/like');
    await _httpClient.postJson(uri, headers: CloudRequestHeaders.forPage('content.post.like'), body: {});
  }

  @override
  Future<void> unlikePost({required String postId}) async {
    final uri = Uri.parse('$_baseUrl/v1/content/posts/${Uri.encodeComponent(postId)}/like');
    await _httpClient.deleteJson(uri, headers: CloudRequestHeaders.forPage('content.post.unlike'));
  }

  @override
  Future<void> favoritePost({required String postId}) async {
    final uri = Uri.parse('$_baseUrl/v1/content/posts/${Uri.encodeComponent(postId)}/favorite');
    await _httpClient.postJson(uri, headers: CloudRequestHeaders.forPage('content.post.favorite'), body: {});
  }

  @override
  Future<void> unfavoritePost({required String postId}) async {
    final uri = Uri.parse('$_baseUrl/v1/content/posts/${Uri.encodeComponent(postId)}/favorite');
    await _httpClient.deleteJson(uri, headers: CloudRequestHeaders.forPage('content.post.unfavorite'));
  }

  @override
  Future<Map<String, dynamic>> getReactionState({required String postId}) async {
    final uri = Uri.parse('$_baseUrl/v1/content/posts/${Uri.encodeComponent(postId)}/reactions');
    final decoded = await _httpClient.getJson(uri, headers: CloudRequestHeaders.forPage('content.post.reactions'));
    return CloudResponseDecoder.asObject(decoded, context: 'content.post.reactions');
  }

  @override
  Future<List<Map<String, dynamic>>> listComments({
    required String postId,
    String? cursor,
    int limit = 20,
  }) async {
    final query = <String, String>{'limit': '$limit'};
    if (cursor != null) query['cursor'] = cursor;
    final uri = Uri.parse('$_baseUrl/v1/content/posts/${Uri.encodeComponent(postId)}/comments')
        .replace(queryParameters: query);
    final decoded = await _httpClient.getJson(uri, headers: CloudRequestHeaders.forPage('content.comment.list'));
    final page = CloudResponseDecoder.asCursorPage(decoded, context: 'content.comment.list');
    return page.items.cast<Map<String, dynamic>>();
  }

  @override
  Future<Map<String, dynamic>> createComment({
    required String postId,
    required String content,
    String? replyToCommentId,
  }) async {
    final uri = Uri.parse('$_baseUrl/v1/content/posts/${Uri.encodeComponent(postId)}/comments');
    final body = <String, dynamic>{'content': content};
    if (replyToCommentId != null) body['replyToCommentId'] = replyToCommentId;
    final decoded = await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage('content.comment.create'),
      body: body,
    );
    return CloudResponseDecoder.asObject(decoded, context: 'content.comment.create');
  }

  @override
  Future<void> deleteComment({required String postId, required String commentId}) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/content/posts/${Uri.encodeComponent(postId)}/comments/${Uri.encodeComponent(commentId)}',
    );
    await _httpClient.deleteJson(uri, headers: CloudRequestHeaders.forPage('content.comment.delete'));
  }

  @override
  Future<void> reportBehaviors({required List<Map<String, dynamic>> events}) async {
    final uri = Uri.parse('$_baseUrl/v1/content/behaviors');
    await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage('content.behaviors.report'),
      body: {'events': events},
    );
  }

  @override
  Future<Map<String, dynamic>> getCounters({required String postId}) async {
    final uri = Uri.parse('$_baseUrl/v1/content/posts/${Uri.encodeComponent(postId)}/counters');
    final decoded = await _httpClient.getJson(uri, headers: CloudRequestHeaders.forPage('content.post.counters'));
    return CloudResponseDecoder.asObject(decoded, context: 'content.post.counters');
  }

  String? _mapCategoryToFeedType(String category) {
    return GeneratedPostRuntimeMetadata.feedCategoryToRequestType[category];
  }
}
