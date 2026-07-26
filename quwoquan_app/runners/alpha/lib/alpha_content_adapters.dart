/// alpha 设备运行时的 content 域薄实现：只回放 contract fixture bundle
/// （AlphaFixtureSeedReader 的 immutable typed seed），不携带第二套
/// 静态业务数据；生产组合根为 Remote-only，本文件仅由 alpha runner 装配。
library;

import 'package:quwoquan_app/cloud/content/models/content_behavior_batch_event_dto.dart';
import 'package:quwoquan_app/cloud/content/generated/content_errors.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/feed_object_card_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_app_config_wire.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_detail_payload.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/cloud/runtime/models/discovery_feed_page.dart';
import 'package:quwoquan_app/cloud/runtime/models/post_engagement_counters.dart';
import 'package:quwoquan_app/cloud/services/content/content_read_model_projection.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository_contract.dart';
import 'package:quwoquan_app/cloud/services/content/footprint_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';

/// contract fixture bundle 的 content 聚合回放实现。
final class AlphaContentRepository
    implements
        ContentReadRepository,
        ContentPostDetailReader,
        ContentAuthorPostsReader,
        ContentWriteRepository,
        ContentEngagementRepository,
        ContentConfigRepository {
  final Set<String> _deletedPostIds = <String>{};

  List<PostBaseDto> _seedPosts() {
    final raw = alphaFixtureSeedReader.contentSeedSet()?['posts'];
    if (raw is! List) {
      return const <PostBaseDto>[];
    }
    return raw
        .whereType<Map>()
        .map(
          (item) =>
              contentPostDtoFromReadModelMap(item.cast<String, dynamic>()),
        )
        .toList(growable: false);
  }

  Map<String, dynamic>? _seedPostWire(String postId) {
    final trimmed = postId.trim();
    if (trimmed.isEmpty) {
      return null;
    }
    final raw = alphaFixtureSeedReader.contentSeedSet()?['posts'];
    if (raw is! List) {
      return null;
    }
    for (final item in raw.whereType<Map>()) {
      final wire = item.cast<String, dynamic>();
      if ((wire['postId']?.toString() ?? '') == trimmed) {
        return contentPostWireFromReadModelMap(wire);
      }
    }
    return null;
  }

  Never _throwPostNotFound(String postId) {
    throw CloudErrorMapper.fromStatusCode(
      404,
      body:
          '{"code":"${ContentErrorCode.postNotFound.code}","userMessage":"${ContentErrorMessages.zh[ContentErrorCode.postNotFound]}"}',
      requestPath: ContentApiMetadata.getPostPath(postId: postId),
    );
  }

  /// home_feed_core seed（following/premium 池 id 与对象卡种子）。
  Map<String, dynamic>? _homeFeedSeed() => alphaFixtureSeedReader
      .contentSeedSet('home_feed_core')
      ?.cast<String, dynamic>();

  List<String> _homeFeedIdList(String key) {
    final raw = _homeFeedSeed()?[key];
    if (raw is! List) {
      return const <String>[];
    }
    return raw
        .map((item) => item.toString().trim())
        .where((id) => id.isNotEmpty)
        .toList(growable: false);
  }

  /// 与 Remote 同构的 channelId 路由（R12 Mock↔Remote 保真）：
  /// following 只回放关注池、premium fail-closed 只回放精品池（池空诚实空），
  /// travel 走 contentVertical 垂类过滤；其余频道走推荐主链路。
  List<PostBaseDto>? _routeChannelPosts(String channelId) {
    final visible = _seedPosts()
        .where((post) => !_deletedPostIds.contains(post.id))
        .toList(growable: false);
    switch (channelId) {
      case 'following':
        final pool = _homeFeedIdList('followingFeedPostIds').toSet();
        return visible
            .where((post) => pool.contains(post.id))
            .toList(growable: false);
      case 'premium':
      case 'premium_stream':
        final pool = _homeFeedIdList('featuredFeedPostIds').toSet();
        return visible
            .where((post) => pool.contains(post.id))
            .toList(growable: false);
      case 'travel':
      case 'travel_photography':
        return visible
            .where((post) => post.contentVertical == 'travel_photography')
            .toList(growable: false);
      default:
        return null;
    }
  }

  /// 对象卡种子（服务端 everyN=8 anchor 语义）：anchorIndex = everyN * 序位，
  /// 越界卡由服务端裁剪逻辑同构地丢弃（UI 编织层也会兜底）。
  List<FeedObjectCardDto> _seedObjectCards(int itemCount) {
    final raw = _homeFeedSeed()?['objectCards'];
    if (raw is! List || itemCount <= 0) {
      return const <FeedObjectCardDto>[];
    }
    const everyN = 8;
    final cards = <FeedObjectCardDto>[];
    for (final item in raw.whereType<Map>()) {
      final anchor = (cards.length + 1) * everyN;
      if (anchor > itemCount) {
        break;
      }
      cards.add(
        FeedObjectCardDto.fromMap(
          item.cast<String, dynamic>(),
        ).copyWith(anchorIndex: anchor),
      );
    }
    return cards;
  }

  @override
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
  }) async {
    cancellation?.throwIfCancelled();
    final channel = (channelId ?? '').trim().toLowerCase();
    List<PostBaseDto>? items = channel.isEmpty
        ? null
        : _routeChannelPosts(channel);
    if (items == null) {
      final requestedType = _normalizeFeedType(
        type ??
            GeneratedPostRuntimeMetadata.feedCategoryToRequestType[category],
      );
      final requestedIdentity = (identity ?? '').trim();
      items = _seedPosts()
          .where((post) => !_deletedPostIds.contains(post.id))
          .where((post) {
            if (requestedIdentity.isNotEmpty &&
                post.identity != requestedIdentity) {
              return false;
            }
            return requestedType == null || post.type == requestedType;
          })
          .toList(growable: false);
    }
    final offset = int.tryParse((cursor ?? '').trim()) ?? 0;
    final safeOffset = offset.clamp(0, items.length);
    final safeLimit = limit <= 0 ? items.length : limit;
    final end = (safeOffset + safeLimit).clamp(0, items.length);
    final pageItems = items.sublist(safeOffset, end).toList(growable: false);
    // 对象卡只在首页频道主链路（channelId 非空且非 following/premium 专线）
    // 附卡，与服务端 objectCards policy 的插卡面一致。
    final withObjectCards =
        channel.isNotEmpty &&
        channel != 'following' &&
        channel != 'premium' &&
        channel != 'premium_stream';
    return DiscoveryFeedPage(
      items: pageItems,
      nextCursor: end < items.length ? '$end' : null,
      feedRequestId: (feedRequestId?.trim().isNotEmpty == true)
          ? feedRequestId!.trim()
          : 'frq_alpha_${DateTime.now().microsecondsSinceEpoch}',
      rankingVersion: 'rec-alpha-fixture',
      reasonVersion: 'reason-alpha-fixture',
      objectCards: withObjectCards
          ? _seedObjectCards(pageItems.length)
          : const <FeedObjectCardDto>[],
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
    if (_deletedPostIds.contains(postId)) {
      _throwPostNotFound(postId);
    }
    final raw = _seedPostWire(postId);
    if (raw == null) {
      _throwPostNotFound(postId);
    }
    return ContentPostDetailPayload.fromWire(raw);
  }

  @override
  Future<ContentAppConfigWire> getAppConfig() async {
    return ContentAppConfigWire.fromResponseObject({
      'content': {
        'comment': {
          'max_length': 500,
          'reply_preview_count': 1,
          'reply_expand_page_size': 10,
          'fold_line_count': 3,
          'attachment': {'max_images': 1},
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
          'experiment_bucket': 'alpha_fixture',
          'current_stage': '100%',
          'canary_matrix': [
            {'stage': '100%', 'rolloutPercent': 100},
          ],
        },
      },
    });
  }

  @override
  Future<void> reportBehaviors({
    required List<ContentBehaviorBatchEventDto> events,
  }) async {}

  @override
  Future<PostEngagementCounters> getCounters({required String postId}) async {
    return const PostEngagementCounters(
      likeCount: 0,
      commentCount: 0,
      shareCount: 0,
    );
  }

  @override
  Future<void> deletePost({
    required String postId,
    required String idempotencyKey,
  }) async {
    if (postId.trim().isEmpty || idempotencyKey.trim().isEmpty) {
      throw ArgumentError(
        'DeletePost requires postId and caller-owned idempotencyKey',
      );
    }
    _deletedPostIds.add(postId);
  }

  @override
  Future<PostBaseDto> updatePostSettings({
    required String postId,
    required UpdatePostSettingsRequestWire body,
  }) async {
    return _mergedPostDto(postId, body.toWire());
  }

  @override
  Future<PostBaseDto> promotePostToWork({
    required String postId,
    required PromotePostToWorkRequestWire body,
  }) async {
    return _mergedPostDto(postId, {
      ...body.toWire(),
      'identity': 'work',
      'status': 'published',
    });
  }

  PostBaseDto _mergedPostDto(String postId, Map<String, dynamic> merge) {
    final wire = _seedPostWire(postId);
    if (wire == null) {
      _throwPostNotFound(postId);
    }
    final merged = <String, dynamic>{...wire, ...merge};
    final contentType = merged.remove('contentType')?.toString().trim();
    if (contentType?.isNotEmpty == true) {
      merged['type'] = contentType;
    }
    return postBaseDtoFromMap(merged);
  }

  @override
  Future<CursorPage<PostBaseDto>> listUserPosts({
    required String userId,
    String? identity,
    String? type,
    String? visibility,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final authorId = userId.trim();
    final requestedType = _normalizeFeedType(type);
    final requestedIdentity = (identity ?? '').trim();
    final items = _seedPosts()
        .where((post) => post.authorId == authorId)
        .where((post) {
          if (requestedIdentity.isNotEmpty &&
              post.identity != requestedIdentity) {
            return false;
          }
          return requestedType == null || post.type == requestedType;
        })
        .toList(growable: false);
    return CursorPage<PostBaseDto>(items: items, nextCursor: null);
  }

  @override
  bool get requiresResolvedPersonaForMutations => false;

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

/// footprint_core fixture 回放的足迹只读实现。
final class AlphaFootprintRepository implements FootprintRepository {
  @override
  Future<CursorPage<FootprintEntry>> getMyFootprint({
    String? type,
    String? cursor,
    int limit = GeneratedPostRuntimeMetadata.feedDefaultLimit,
  }) async {
    final seed = alphaFixtureSeedReader.contentSeedSet('footprint_core');
    final rawItems = seed?['items'];
    if (rawItems is! List) {
      return const CursorPage<FootprintEntry>(items: <FootprintEntry>[]);
    }
    final postsById = _discoveryPostsById();
    final normalizedType = (type ?? '').trim().toLowerCase();
    final entries = <FootprintEntry>[];
    for (final raw in rawItems.whereType<Map>()) {
      final item = raw.cast<String, dynamic>();
      final itemType = (item['type'] ?? '').toString().toLowerCase();
      if (normalizedType.isNotEmpty && itemType != normalizedType) {
        continue;
      }
      final postRef = (item['postRef'] ?? '').toString();
      final postMap = postsById[postRef];
      entries.add(
        FootprintEntry(
          postId: postRef,
          action: (item['action'] ?? '').toString(),
          occurredAt: _isoMinusHours(item['occurredAgoHours']),
          post: postMap != null
              ? contentPostDtoFromReadModelMap(postMap)
              : null,
        ),
      );
    }
    final start = int.tryParse(cursor ?? '') ?? 0;
    final window = entries.skip(start).take(limit).toList(growable: false);
    final nextOffset = start + window.length;
    return CursorPage<FootprintEntry>(
      items: window,
      nextCursor: nextOffset < entries.length ? '$nextOffset' : null,
    );
  }

  static Map<String, Map<String, dynamic>> _discoveryPostsById() {
    final seed = alphaFixtureSeedReader.contentSeedSet();
    final rawPosts = seed?['posts'];
    final byId = <String, Map<String, dynamic>>{};
    if (rawPosts is List) {
      for (final raw in rawPosts.whereType<Map>()) {
        final map = raw.cast<String, dynamic>();
        final id = (map['postId'] ?? '').toString();
        if (id.isNotEmpty) {
          byId[id] = map;
        }
      }
    }
    return byId;
  }

  static String _isoMinusHours(Object? agoHours) {
    final hours = agoHours is num ? agoHours.toInt() : 0;
    return DateTime.now()
        .toUtc()
        .subtract(Duration(hours: hours))
        .toIso8601String();
  }
}
