import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/contract_fixture_runtime_loader.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';

/// 我的足迹条目（云侧只读契约 GET /v1/content/footprint 的端侧映射）。
///
/// `action` 与 `type` 的语义映射由云侧唯一定义（footprintTypeActions），
/// 端侧只透传 type 枚举字符串并展示云端下发数据，不解析 action 语义。
class FootprintEntry {
  const FootprintEntry({
    required this.postId,
    required this.action,
    required this.occurredAt,
    this.post,
  });

  final String postId;
  final String action;
  final String occurredAt;
  final PostBaseDto? post;

  factory FootprintEntry.fromMap(Map<String, dynamic> map) {
    PostBaseDto? post;
    final rawPost = map['post'];
    if (rawPost is Map) {
      post = postBaseDtoFromMap(Map<String, dynamic>.from(rawPost));
    }
    return FootprintEntry(
      postId: (map['postId'] ?? '').toString(),
      action: (map['action'] ?? '').toString(),
      occurredAt: (map['occurredAt'] ?? '').toString(),
      post: post,
    );
  }
}

/// 我的足迹只读 Repository（WP1·T5）。
///
/// 足迹是自动形成的私有消费轨迹（viewed/liked/commented/shared），
/// 仅本人可见、只读、不产生交集与影响事实；没有写接口。
abstract class FootprintRepository {
  Future<CursorPage<FootprintEntry>> getMyFootprint({
    String? type,
    String? cursor,
    int limit = GeneratedPostRuntimeMetadata.feedDefaultLimit,
  });
}

/// Mock 实现：contract fixture（footprint_core）单一真相源；
/// postRef join content_discovery_core.posts，不复制第二套内容数据。
class MockFootprintRepository implements FootprintRepository {
  @override
  Future<CursorPage<FootprintEntry>> getMyFootprint({
    String? type,
    String? cursor,
    int limit = GeneratedPostRuntimeMetadata.feedDefaultLimit,
  }) async {
    final seed = ContractFixtureRuntimeLoader.contentSeedSet('footprint_core');
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
      final postRef = (item['postRef'] ?? item['postId'] ?? '').toString();
      final postMap = postsById[postRef];
      entries.add(
        FootprintEntry(
          postId: postRef,
          action: (item['action'] ?? '').toString(),
          occurredAt: _isoMinusHours(item['occurredAgoHours']),
          post: postMap != null ? postBaseDtoFromMap(postMap) : null,
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
    final seed = ContractFixtureRuntimeLoader.contentSeedSet();
    final rawPosts = seed?['posts'];
    final byId = <String, Map<String, dynamic>>{};
    if (rawPosts is List) {
      for (final raw in rawPosts.whereType<Map>()) {
        final map = raw.cast<String, dynamic>();
        final id = (map['postId'] ?? map['id'] ?? '').toString();
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

/// Remote 实现：metadata codegen 的 path/operation/page id 单一真相源。
class RemoteFootprintRepository implements FootprintRepository {
  RemoteFootprintRepository({CloudHttpClient? httpClient, String? baseUrl})
    : _httpClient = httpClient ?? CloudHttpClient(),
      _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();

  final CloudHttpClient _httpClient;
  final String _baseUrl;

  @override
  Future<CursorPage<FootprintEntry>> getMyFootprint({
    String? type,
    String? cursor,
    int limit = GeneratedPostRuntimeMetadata.feedDefaultLimit,
  }) async {
    final query = <String, String>{'limit': '$limit'};
    if (type?.trim().isNotEmpty == true) {
      query['type'] = type!.trim();
    }
    if (cursor?.isNotEmpty == true) {
      query['cursor'] = cursor!;
    }
    final uri = Uri.parse(
      '$_baseUrl${ContentApiMetadata.getMyFootprintPath}',
    ).replace(queryParameters: query);
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.getMyFootprint,
      ),
    );
    final rawPage = CloudResponseDecoder.asCursorPage(
      decoded,
      context: ContentRequestPageIds.getMyFootprint,
    );
    return CursorPage<FootprintEntry>(
      items: rawPage.items.map(FootprintEntry.fromMap).toList(growable: false),
      nextCursor: rawPage.nextCursor,
    );
  }
}
