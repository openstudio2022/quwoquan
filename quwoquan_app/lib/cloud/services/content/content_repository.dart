import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/services/content/mock/content_mock_data.dart';

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
    String? subCategory,
    int limit = GeneratedPostRuntimeMetadata.feedDefaultLimit,
    String? cursor,
    String sort = kFeedSortRecommend,
  });

  Future<List<PostBaseDto>> listDiscoveryFeed({
    required String category,
    String? subCategory,
    int limit = GeneratedPostRuntimeMetadata.feedDefaultLimit,
    String? cursor,
    String sort = kFeedSortRecommend,
  });

  Future<Map<String, dynamic>> getPost({required String postId});

  Future<Map<String, dynamic>> createPost({
    required Map<String, dynamic> payload,
  });

  Future<Map<String, dynamic>> updatePost({
    required String postId,
    required Map<String, dynamic> payload,
  });
  Future<void> deletePost({required String postId});
  Future<Map<String, dynamic>> publishPost({required String postId});

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
  Future<Map<String, dynamic>> completeMediaUpload({
    required String sessionId,
  });
  Future<void> abortMediaUpload({required String sessionId});
  Future<Map<String, dynamic>> getMediaAsset({required String mediaId});

  Future<Map<String, dynamic>> selectAutoVideoCover({
    required String mediaId,
  });
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
    int limit = 20,
  });

  Future<CursorPage<PostBaseDto>> listUserPosts({
    required String userId,
    String? cursor,
    int limit = 20,
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
  Future<void> deleteComment({
    required String postId,
    required String commentId,
  });
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
    String sort = kFeedSortRecommend,
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
    String sort = kFeedSortRecommend,
  }) async {
    final page = await listDiscoveryFeedPage(
      category: category,
      subCategory: subCategory,
      limit: limit,
      cursor: cursor,
      sort: sort,
    );
    return page.items;
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
    return <String, dynamic>{
      ...payload,
      'postId': 'local_${DateTime.now().millisecondsSinceEpoch}',
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
  Future<Map<String, dynamic>> publishPost({required String postId}) async {
    return {'postId': postId, 'status': 'published'};
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
    int limit = 20,
  }) async {
    return {'items': [], 'nextCursor': null};
  }

  @override
  Future<CursorPage<PostBaseDto>> listUserPosts({
    required String userId,
    String? cursor,
    int limit = 20,
  }) async {
    final allRaw = [
      ...ContentMockData.discoveryPhotoData,
      ...ContentMockData.discoveryVideoData,
      ...ContentMockData.discoveryMomentData,
      ...ContentMockData.discoveryArticleData,
    ];
    final filtered = allRaw
        .where((m) => m['authorId']?.toString() == userId)
        .toList();
    final items = filtered.map(postBaseDtoFromMap).toList(growable: false);
    return CursorPage<PostBaseDto>(items: items, nextCursor: null);
  }

  List<Map<String, dynamic>> _getRawListForCategory(String category) {
    final feedType =
        GeneratedPostRuntimeMetadata.feedCategoryToRequestType[category] ?? '';
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
    String sort = kFeedSortRecommend,
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
    if (keys.contains('sort') && sort.trim().isNotEmpty) {
      query['sort'] = sort.trim();
    }
    if (keys.contains('limit')) {
      query['limit'] = '$limit';
    }
    if (keys.contains('subCategory') && subCategory?.isNotEmpty == true) {
      query['subCategory'] = subCategory!;
    }
    final uri = Uri.parse(
      '$_baseUrl${GeneratedPostRuntimeMetadata.feedPath}',
    ).replace(queryParameters: query);
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage('content.feed.list'),
    );
    final rawPage = CloudResponseDecoder.asCursorPage(
      decoded,
      context: 'content.feed.list',
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
    String? subCategory,
    int limit = GeneratedPostRuntimeMetadata.feedDefaultLimit,
    String? cursor,
    String sort = kFeedSortRecommend,
  }) async {
    final page = await listDiscoveryFeedPage(
      category: category,
      subCategory: subCategory,
      limit: limit,
      cursor: cursor,
      sort: sort,
    );
    return page.items;
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
    return CloudResponseDecoder.asObject(
      decoded,
      context: 'content.post.create',
    );
  }

  @override
  Future<void> likePost({required String postId}) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/content/posts/${Uri.encodeComponent(postId)}/like',
    );
    await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage('content.post.like'),
      body: {},
    );
  }

  @override
  Future<void> unlikePost({required String postId}) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/content/posts/${Uri.encodeComponent(postId)}/like',
    );
    await _httpClient.deleteJson(
      uri,
      headers: CloudRequestHeaders.forPage('content.post.unlike'),
    );
  }

  @override
  Future<void> favoritePost({required String postId}) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/content/posts/${Uri.encodeComponent(postId)}/favorite',
    );
    await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage('content.post.favorite'),
      body: {},
    );
  }

  @override
  Future<void> unfavoritePost({required String postId}) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/content/posts/${Uri.encodeComponent(postId)}/favorite',
    );
    await _httpClient.deleteJson(
      uri,
      headers: CloudRequestHeaders.forPage('content.post.unfavorite'),
    );
  }

  @override
  Future<Map<String, dynamic>> getReactionState({
    required String postId,
  }) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/content/posts/${Uri.encodeComponent(postId)}/reactions',
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage('content.post.reactions'),
    );
    return CloudResponseDecoder.asObject(
      decoded,
      context: 'content.post.reactions',
    );
  }

  @override
  Future<List<Map<String, dynamic>>> listComments({
    required String postId,
    String? cursor,
    int limit = 20,
  }) async {
    final query = <String, String>{'limit': '$limit'};
    if (cursor != null) query['cursor'] = cursor;
    final uri = Uri.parse(
      '$_baseUrl/v1/content/posts/${Uri.encodeComponent(postId)}/comments',
    ).replace(queryParameters: query);
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage('content.comment.list'),
    );
    final page = CloudResponseDecoder.asCursorPage(
      decoded,
      context: 'content.comment.list',
    );
    return page.items.cast<Map<String, dynamic>>();
  }

  @override
  Future<Map<String, dynamic>> createComment({
    required String postId,
    required String content,
    String? replyToCommentId,
  }) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/content/posts/${Uri.encodeComponent(postId)}/comments',
    );
    final body = <String, dynamic>{'content': content};
    if (replyToCommentId != null) body['replyToCommentId'] = replyToCommentId;
    final decoded = await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage('content.comment.create'),
      body: body,
    );
    return CloudResponseDecoder.asObject(
      decoded,
      context: 'content.comment.create',
    );
  }

  @override
  Future<void> deleteComment({
    required String postId,
    required String commentId,
  }) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/content/posts/${Uri.encodeComponent(postId)}/comments/${Uri.encodeComponent(commentId)}',
    );
    await _httpClient.deleteJson(
      uri,
      headers: CloudRequestHeaders.forPage('content.comment.delete'),
    );
  }

  @override
  Future<void> reportBehaviors({
    required List<Map<String, dynamic>> events,
  }) async {
    final uri = Uri.parse('$_baseUrl/v1/content/behaviors');
    await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage('content.behaviors.report'),
      body: {'events': events},
    );
  }

  @override
  Future<Map<String, dynamic>> getCounters({required String postId}) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/content/posts/${Uri.encodeComponent(postId)}/counters',
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage('content.post.counters'),
    );
    return CloudResponseDecoder.asObject(
      decoded,
      context: 'content.post.counters',
    );
  }

  @override
  Future<Map<String, dynamic>> updatePost({
    required String postId,
    required Map<String, dynamic> payload,
  }) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/content/posts/${Uri.encodeComponent(postId)}',
    );
    final decoded = await _httpClient.patchJson(
      uri,
      headers: CloudRequestHeaders.forPage('content.post.update'),
      body: payload,
    );
    return CloudResponseDecoder.asObject(decoded, context: 'content.post.update');
  }

  @override
  Future<void> deletePost({required String postId}) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/content/posts/${Uri.encodeComponent(postId)}',
    );
    await _httpClient.deleteJson(
      uri,
      headers: CloudRequestHeaders.forPage('content.post.delete'),
    );
  }

  @override
  Future<Map<String, dynamic>> publishPost({required String postId}) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/content/posts/${Uri.encodeComponent(postId)}/publish',
    );
    final decoded = await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage('content.post.publish'),
      body: {},
    );
    return CloudResponseDecoder.asObject(decoded, context: 'content.post.publish');
  }

  @override
  Future<Map<String, dynamic>> updatePostCircles({
    required String postId,
    List<String> add = const [],
    List<String> remove = const [],
  }) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/content/posts/${Uri.encodeComponent(postId)}/circles',
    );
    final decoded = await _httpClient.patchJson(
      uri,
      headers: CloudRequestHeaders.forPage('content.post.circles'),
      body: {'add': add, 'remove': remove},
    );
    return CloudResponseDecoder.asObject(decoded, context: 'content.post.circles');
  }

  @override
  Future<Map<String, dynamic>> repostToCircle({
    required String postId,
    required String circleId,
  }) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/content/posts/${Uri.encodeComponent(postId)}/repost',
    );
    final decoded = await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage('content.post.repost'),
      body: {'circleId': circleId},
    );
    return CloudResponseDecoder.asObject(decoded, context: 'content.post.repost');
  }

  @override
  Future<Map<String, dynamic>> quoteToCircle({
    required String postId,
    required String circleId,
    String quoteText = '',
  }) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/content/posts/${Uri.encodeComponent(postId)}/quote',
    );
    final decoded = await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage('content.post.quote'),
      body: {'circleId': circleId, 'quoteText': quoteText},
    );
    return CloudResponseDecoder.asObject(decoded, context: 'content.post.quote');
  }

  @override
  Future<Map<String, dynamic>> initMediaUpload({
    String mediaType = 'image',
  }) async {
    final uri = Uri.parse('$_baseUrl/v1/content/media/uploads:init');
    final decoded = await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage('content.media.init'),
      body: {'mediaType': mediaType},
    );
    return CloudResponseDecoder.asObject(decoded, context: 'content.media.init');
  }

  @override
  Future<Map<String, dynamic>> completeMediaUpload({
    required String sessionId,
  }) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/content/media/uploads/${Uri.encodeComponent(sessionId)}:complete',
    );
    final decoded = await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage('content.media.complete'),
      body: {},
    );
    return CloudResponseDecoder.asObject(decoded, context: 'content.media.complete');
  }

  @override
  Future<void> abortMediaUpload({required String sessionId}) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/content/media/uploads/${Uri.encodeComponent(sessionId)}:abort',
    );
    await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage('content.media.abort'),
      body: {},
    );
  }

  @override
  Future<Map<String, dynamic>> getMediaAsset({required String mediaId}) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/content/media/${Uri.encodeComponent(mediaId)}',
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage('content.media.get'),
    );
    return CloudResponseDecoder.asObject(decoded, context: 'content.media.get');
  }

  @override
  Future<Map<String, dynamic>> selectAutoVideoCover({
    required String mediaId,
  }) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/content/media/${Uri.encodeComponent(mediaId)}/cover:auto',
    );
    final decoded = await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage('content.media.cover.auto'),
      body: {},
    );
    return CloudResponseDecoder.asObject(decoded, context: 'content.media.cover.auto');
  }

  @override
  Future<Map<String, dynamic>> selectManualVideoCover({
    required String mediaId,
    required String coverAssetId,
  }) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/content/media/${Uri.encodeComponent(mediaId)}/cover:manual',
    );
    final decoded = await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage('content.media.cover.manual'),
      body: {'coverAssetId': coverAssetId},
    );
    return CloudResponseDecoder.asObject(decoded, context: 'content.media.cover.manual');
  }

  @override
  Future<Map<String, dynamic>> generateArticleSummary({
    required String title,
    required String body,
  }) async {
    final uri = Uri.parse('$_baseUrl/v1/content/articles/summary:generate');
    final decoded = await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage('content.article.summary'),
      body: {'title': title, 'body': body},
    );
    return CloudResponseDecoder.asObject(decoded, context: 'content.article.summary');
  }

  @override
  Future<Map<String, dynamic>> getRecommendation({
    String? cursor,
    int limit = 20,
  }) async {
    final uri = Uri.parse('$_baseUrl/v1/content/recommend');
    final decoded = await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage('content.recommend'),
      body: {
        'limit': limit,
        if (cursor != null) 'cursor': cursor,
      },
    );
    return CloudResponseDecoder.asObject(decoded, context: 'content.recommend');
  }

  @override
  Future<CursorPage<PostBaseDto>> listUserPosts({
    required String userId,
    String? cursor,
    int limit = 20,
  }) async {
    final query = <String, String>{
      'userId': userId,
      'limit': '$limit',
    };
    if (cursor != null) query['cursor'] = cursor;
    final uri = Uri.parse('$_baseUrl/v1/content/users/posts')
        .replace(queryParameters: query);
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage('content.user.posts'),
    );
    final rawPage = CloudResponseDecoder.asCursorPage(
      decoded,
      context: 'content.user.posts',
    );
    final dtoItems = rawPage.items
        .map(postBaseDtoFromMap)
        .toList(growable: false);
    return CursorPage<PostBaseDto>(
      items: dtoItems,
      nextCursor: rawPage.nextCursor,
    );
  }

  String? _mapCategoryToFeedType(String category) {
    return GeneratedPostRuntimeMetadata.feedCategoryToRequestType[category];
  }
}
