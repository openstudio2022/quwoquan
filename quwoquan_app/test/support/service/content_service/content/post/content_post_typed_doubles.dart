import 'package:quwoquan_app/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/runtime/errors/generated/content/content_errors.g.dart';
import 'package:quwoquan_app/runtime/transport/models/cursor_page.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/application/public/discovery_feed_page.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/application/public/discovery_feed_query.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/content_repository_contract.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_delete.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_detail_payload.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    hide ContentDiscoveryFeedQuery;

import '../../../../runtime/remote_api_path_test_harness.dart';
import 'content_post_test_builder.dart';
import 'test_content_app_config.dart';

/// Post 测试状态只保存调用方显式交入的 typed 对象。
final class InMemoryContentPostStore {
  InMemoryContentPostStore({
    Iterable<ContentPostViewData> posts = const <ContentPostViewData>[],
    Map<String, ContentPostDetailPayload> details =
        const <String, ContentPostDetailPayload>{},
  }) : _postsById = <String, ContentPostViewData>{
         for (final post in posts) post.id: post,
       },
       _detailsById = Map<String, ContentPostDetailPayload>.from(details);

  final Map<String, ContentPostViewData> _postsById;
  final Map<String, ContentPostDetailPayload> _detailsById;
  final Set<String> deletedPostIds = <String>{};
  final Set<String> deletionKeys = <String>{};

  List<ContentPostViewData> get posts =>
      List<ContentPostViewData>.unmodifiable(_postsById.values);

  ContentPostViewData? postById(String postId) => _postsById[postId.trim()];

  ContentPostDetailPayload? detailById(String postId) {
    final normalized = postId.trim();
    final explicit = _detailsById[normalized];
    if (explicit != null) return explicit;
    final post = _postsById[normalized];
    return post == null ? null : contentPostDetailPayloadBuilder(post: post);
  }
}

/// 仅实现 Feed Delivery Page query 的对象级内存替身。
class InMemoryContentDiscoveryFeedQuery implements ContentDiscoveryFeedQuery {
  InMemoryContentDiscoveryFeedQuery(
    this._store, {
    Set<String> premiumPostIds = const <String>{},
  }) : _premiumPostIds = Set<String>.unmodifiable(premiumPostIds);

  final InMemoryContentPostStore _store;
  final Set<String> _premiumPostIds;
  int _requestSequence = 0;

  @override
  Future<DiscoveryFeedPage> listDiscoveryFeedPage({
    required String category,
    String? channelId,
    String? identity,
    String? type,
    String? subCategory,
    int limit = 20,
    String? cursor,
    String sort = kFeedSortRecommend,
    String? sessionId,
    String? feedRequestId,
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    throwIfCloudOperationInterrupted(
      cancellation: cancellation,
      deadlineAt: deadlineAt,
    );
    final normalizedChannel = channelId?.trim() ?? '';
    final channelRouted = normalizedChannel.isNotEmpty;
    final routeCategory = channelRouted ? normalizedChannel : category.trim();
    final resolvedIdentity = channelRouted
        ? null
        : (identity?.trim().isNotEmpty == true
              ? identity!.trim()
              : DiscoveryFeedRouteRegistry.identityForCategory(routeCategory));
    final resolvedType = channelRouted
        ? null
        : _normalizedContentType(
            type?.trim().isNotEmpty == true
                ? type
                : DiscoveryFeedRouteRegistry.routeForSurface(
                    routeCategory,
                  )?.type,
          );

    var items = _store.posts
        .where(
          (post) =>
              (resolvedIdentity == null ||
                  resolvedIdentity.isEmpty ||
                  post.identity == resolvedIdentity) &&
              (resolvedType == null || post.type == resolvedType),
        )
        .toList(growable: false);
    if (routeCategory == 'premium' || routeCategory == 'premium_stream') {
      items = items
          .where(
            (post) =>
                _premiumPostIds.contains(post.id) ||
                post.supplySource == 'data_engineering',
          )
          .toList(growable: false);
    }

    final offset = int.tryParse(cursor?.trim() ?? '') ?? 0;
    final safeOffset = offset.clamp(0, items.length);
    final safeLimit = limit <= 0 ? items.length : limit;
    final end = (safeOffset + safeLimit).clamp(0, items.length);
    final pageItems = items.sublist(safeOffset, end);
    _requestSequence += 1;
    throwIfCloudOperationInterrupted(
      cancellation: cancellation,
      deadlineAt: deadlineAt,
    );
    return DiscoveryFeedPage(
      items: pageItems,
      nextCursor: end < items.length ? '$end' : null,
      feedRequestId: feedRequestId?.trim().isNotEmpty == true
          ? feedRequestId!.trim()
          : 'feed-request-test-$_requestSequence',
      policyDigest:
          'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      objectCards: _objectCards(
        channelId: normalizedChannel,
        cursor: cursor,
        itemCount: pageItems.length,
      ),
    );
  }

  List<FeedObjectCard> _objectCards({
    required String channelId,
    required String? cursor,
    required int itemCount,
  }) {
    if (channelId != 'recommend' ||
        cursor?.trim().isNotEmpty == true ||
        itemCount < 8) {
      return const <FeedObjectCard>[];
    }
    return const <FeedObjectCard>[
      FeedObjectCard(
        objectKind: 'entity_homepage',
        objectId: 'homepage_sight_west_lake',
        title: '西湖',
        subtitle: '杭州 · 风景名胜',
        tagRefs: <String>['Topic/旅行/杭州'],
        reasonText: 'affinity',
        recallPath: 'entity_affinity_card',
        anchorIndex: 8,
      ),
    ];
  }
}

/// 仅实现单帖详情读取；删除状态与写替身共享同一个对象级 store。
class InMemoryContentPostDetailReader implements ContentPostDetailReader {
  const InMemoryContentPostDetailReader(this._store);

  final InMemoryContentPostStore _store;

  @override
  Future<ContentPostDetailPayload> getPost({
    required String postId,
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    throwIfCloudOperationInterrupted(
      cancellation: cancellation,
      deadlineAt: deadlineAt,
    );
    final normalized = postId.trim();
    if (_store.deletedPostIds.contains(normalized)) {
      _throwContentFailure(
        postId: normalized,
        statusCode: 410,
        code: ContentErrorCode.contentDeleted,
      );
    }
    final detail = _store.detailById(normalized);
    if (detail == null) {
      _throwContentFailure(
        postId: normalized,
        statusCode: 404,
        code: ContentErrorCode.postNotFound,
      );
    }
    return detail;
  }
}

/// 仅实现作者作品查询，不合成不存在的用户作品。
class InMemoryContentAuthorPostsReader implements ContentAuthorPostsReader {
  const InMemoryContentAuthorPostsReader(this._store);

  final InMemoryContentPostStore _store;

  @override
  Future<CursorPage<ContentPostViewData>> listUserPosts({
    required String userId,
    String? identity,
    String? type,
    String? visibility,
    String? cursor,
    int limit = ContentAuthorPostsQuery.defaultLimit,
  }) async {
    final normalizedType = _normalizedContentType(type);
    final normalizedIdentity = identity?.trim() ?? '';
    final matches = _store.posts
        .where(
          (post) =>
              post.authorId == userId.trim() &&
              (normalizedIdentity.isEmpty ||
                  post.identity == normalizedIdentity) &&
              (normalizedType == null || post.type == normalizedType),
        )
        .toList(growable: false);
    final offset = int.tryParse(cursor?.trim() ?? '') ?? 0;
    final safeOffset = offset.clamp(0, matches.length);
    final safeLimit = limit <= 0 ? matches.length : limit;
    final end = (safeOffset + safeLimit).clamp(0, matches.length);
    return CursorPage<ContentPostViewData>(
      items: matches.sublist(safeOffset, end),
      nextCursor: end < matches.length ? '$end' : null,
    );
  }
}

/// 仅实现 Post 删除命令。
class InMemoryContentPostDeleteCommandWriter
    implements ContentPostDeleteCommandWriter {
  const InMemoryContentPostDeleteCommandWriter(this._store);

  final InMemoryContentPostStore _store;

  @override
  Future<PostDeletionReceipt> deletePost({
    required String postId,
    required String idempotencyKey,
  }) async {
    final normalizedPostId = postId.trim();
    final normalizedKey = idempotencyKey.trim();
    if (normalizedPostId.isEmpty || normalizedKey.isEmpty) {
      throw ArgumentError(
        'DeletePost requires postId and caller-owned idempotencyKey',
      );
    }
    final replayed = !_store.deletionKeys.add(normalizedKey);
    _store.deletedPostIds.add(normalizedPostId);
    return PostDeletionReceipt(
      postId: normalizedPostId,
      status: PostStatus.deleted,
      replayed: replayed,
    );
  }
}

/// 仅实现内容运行配置读取。
class InMemoryContentConfigRepository implements ContentConfigRepository {
  InMemoryContentConfigRepository({AppConfigSlice? config})
    : _config = config ?? _defaultConfig();

  final AppConfigSlice _config;

  @override
  Future<AppConfigSlice> getAppConfig() async => _config;

  @override
  bool get requiresResolvedPersonaForMutations => false;
}

Never _throwContentFailure({
  required String postId,
  required int statusCode,
  required ContentErrorCode code,
}) {
  throw CloudErrorMapper.fromStatusCode(
    statusCode,
    body:
        '{"code":"${code.code}","userMessage":"${ContentErrorMessages.zh[code]}"}',
    requestPath: canonicalRemoteApiPath(
      AppCloudOperationIds.contentPostGetPost,
      pathParameters: <String, String>{'postId': postId},
    ),
  );
}

String? _normalizedContentType(String? type) {
  return switch (type?.trim().toLowerCase() ?? '') {
    '' => null,
    'photo' => 'image',
    'note' => 'article',
    final value => value,
  };
}

AppConfigSlice _defaultConfig() {
  return testAppConfigSlice(
    content: const <String, Object?>{
      'comment': <String, Object?>{
        'max_length': 500,
        'reply_preview_count': 1,
        'reply_expand_page_size': 10,
        'fold_line_count': 3,
        'attachment': <String, Object?>{'max_images': 1},
      },
      'feature_flags': <String, Object?>{
        'enable_create_action_entry': true,
        'enable_unified_create_editor': true,
        'enable_identity_based_surfaces': true,
        'enable_identity_share_template': true,
        'enable_article_distribution_profiles': true,
        'enable_article_book_reader': true,
        'enable_article_page_curl': true,
        'enable_assistant_content_identity_index': true,
      },
      'gray_release': <String, Object?>{
        'experiment_bucket': 'local_story_enabled',
        'current_stage': '100%',
        'canary_matrix': <Object?>[
          <String, Object?>{'stage': '100%', 'rolloutPercent': 100},
        ],
      },
    },
  );
}
