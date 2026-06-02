import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_dimension_tally.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_inbox_summary.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';

/// 交集 Repository（三层模式：Abstract → Mock → Remote）。
///
/// 对应云侧路由（contracts/metadata/content/post/service.yaml）：
///   GET  /v1/content/intersections/summary   我的交集聚合摘要
///   GET  /v1/content/intersections           我的交集分维度列表（自上次新增在前）
///   POST /v1/content/intersections/visit      推进已读水位，清零未读红点
///   GET  /v1/content/feed/intersections       首页/频道交集推荐（事实+概率混排）
///   POST /v1/content/intersections/exposure   曝光上报（写跨会话冷却集）
abstract class IntersectionRepository {
  Future<IntersectionInboxSummary> getMyIntersectionSummary();

  Future<List<IntersectionReason>> listMyIntersections({
    String? dimension,
    int limit = 50,
  });

  Future<void> markIntersectionsVisited({String? dimension});

  Future<List<IntersectionReason>> getFeedIntersections({
    String? channel,
    int limit = 4,
  });

  Future<void> reportExposure({required List<String> objectIds});
}

/// Mock 实现：本地 canonical 交集数据，不发 HTTP。
///
/// 未读语义与云侧一致：每个维度维护已读水位（lastVisited），新增 = `freshAt > 水位`。
/// 打开列表（[markIntersectionsVisited]）即推进水位 → 该维度 newCount 归零。
class MockIntersectionRepository implements IntersectionRepository {
  MockIntersectionRepository();

  final Map<String, DateTime> _watermark = <String, DateTime>{};
  final List<String> _exposed = <String>[];

  static const Map<String, String> _dimensionLabels = <String, String>{
    'identity': '身份',
    'location': '足迹',
    'content': '内容',
    'relationship': '关系',
    'interest': '兴趣',
  };

  @override
  Future<IntersectionInboxSummary> getMyIntersectionSummary() async {
    final reasons = _inboxReasons;
    final byDimension = <String, List<IntersectionReason>>{};
    for (final reason in reasons) {
      byDimension.putIfAbsent(reason.dimension, () => <IntersectionReason>[]);
      byDimension[reason.dimension]!.add(reason);
    }
    final tallies = <IntersectionDimensionTally>[];
    var totalNew = 0;
    byDimension.forEach((dimension, items) {
      final watermark = _watermark[dimension];
      final newCount = items.where((r) => _isNew(r, watermark)).length;
      totalNew += newCount;
      tallies.add(
        IntersectionDimensionTally(
          dimension: dimension,
          label: _dimensionLabels[dimension] ?? dimension,
          count: items.length,
          newCount: newCount,
        ),
      );
    });
    tallies.sort((a, b) {
      final byNew = b.newCount.compareTo(a.newCount);
      if (byNew != 0) return byNew;
      return b.count.compareTo(a.count);
    });
    return IntersectionInboxSummary(
      totalCount: reasons.length,
      totalNewCount: totalNew,
      dimensions: tallies,
      generatedAt: DateTime.now().toUtc().toIso8601String(),
    );
  }

  @override
  Future<List<IntersectionReason>> listMyIntersections({
    String? dimension,
    int limit = 50,
  }) async {
    final wanted = (dimension ?? '').trim();
    final items = _inboxReasons
        .where((r) => wanted.isEmpty || r.dimension == wanted)
        .toList(growable: false);
    final watermark = wanted.isEmpty ? null : _watermark[wanted];
    items.sort((a, b) {
      final aNew = _isNew(a, watermark) ? 1 : 0;
      final bNew = _isNew(b, watermark) ? 1 : 0;
      if (aNew != bNew) return bNew.compareTo(aNew);
      return b.strength.compareTo(a.strength);
    });
    if (items.length <= limit) return items;
    return items.sublist(0, limit);
  }

  @override
  Future<void> markIntersectionsVisited({String? dimension}) async {
    final now = DateTime.now().toUtc();
    final wanted = (dimension ?? '').trim();
    if (wanted.isEmpty) {
      for (final key in _dimensionLabels.keys) {
        _watermark[key] = now;
      }
      return;
    }
    _watermark[wanted] = now;
  }

  @override
  Future<List<IntersectionReason>> getFeedIntersections({
    String? channel,
    int limit = 4,
  }) async {
    final wanted = (channel ?? '').trim();
    final pool = _channelReasons[wanted] ?? _channelReasons['recommend']!;
    final items = pool
        .where((r) => !_exposed.contains(r.actionTargetId))
        .toList(growable: false);
    if (items.length <= limit) return items;
    return items.sublist(0, limit);
  }

  @override
  Future<void> reportExposure({required List<String> objectIds}) async {
    for (final id in objectIds) {
      if (id.trim().isEmpty || _exposed.contains(id)) continue;
      _exposed.add(id);
    }
  }

  bool _isNew(IntersectionReason reason, DateTime? watermark) {
    if (watermark == null) return reason.freshAt.isNotEmpty;
    final fresh = DateTime.tryParse(reason.freshAt);
    if (fresh == null) return false;
    return fresh.isAfter(watermark);
  }

  static String _isoMinusHours(int hours) =>
      DateTime.now().toUtc().subtract(Duration(hours: hours)).toIso8601String();

  /// canonical 我的交集 inbox（覆盖 5 维度，含事实/概率混样、头像/名字/新鲜度）。
  static List<IntersectionReason> get _inboxReasons => <IntersectionReason>[
    IntersectionReason(
      dimension: 'relationship',
      intersectionId: 'ix_rel_1',
      intersectionClass: 'fact',
      label: '共同好友',
      displayName: '林清越',
      avatarUrl:
          'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=100',
      sharedCount: 4,
      strength: 0.9,
      relationKind: 'person',
      actionType: 'view',
      actionTargetId: 'u_lin',
      source: 'relationship',
      freshAt: _isoMinusHours(3),
    ),
    IntersectionReason(
      dimension: 'relationship',
      intersectionId: 'ix_rel_2',
      intersectionClass: 'fact',
      label: '互相关注',
      displayName: '周屿',
      avatarUrl:
          'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=100',
      sharedCount: 2,
      strength: 0.7,
      relationKind: 'person',
      actionType: 'view',
      actionTargetId: 'u_zhou',
      source: 'relationship',
      freshAt: _isoMinusHours(96),
    ),
    IntersectionReason(
      dimension: 'identity',
      intersectionId: 'ix_id_1',
      intersectionClass: 'fact',
      label: '同校',
      displayName: '新东方校友',
      avatarUrl:
          'https://images.unsplash.com/photo-1523050854058-8df90110c9f1?w=100',
      sharedCount: 3,
      strength: 0.82,
      relationKind: 'org',
      actionType: 'view',
      actionTargetId: 'hp_xdf_alumni',
      source: 'identity',
      freshAt: _isoMinusHours(10),
    ),
    IntersectionReason(
      dimension: 'content',
      intersectionId: 'ix_ct_1',
      intersectionClass: 'fact',
      label: '共看内容',
      displayName: '黄金投资圈',
      avatarUrl:
          'https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=100',
      sharedCount: 8,
      strength: 0.88,
      relationKind: 'circle',
      actionType: 'join',
      actionTargetId: 'circle_gold_invest',
      source: 'content',
      freshAt: _isoMinusHours(30),
    ),
    IntersectionReason(
      dimension: 'location',
      intersectionId: 'ix_loc_1',
      intersectionClass: 'fact',
      label: '同游',
      displayName: '西湖',
      avatarUrl:
          'https://images.unsplash.com/photo-1606767341197-3d8e6f0a2a9b?w=100',
      sharedCount: 5,
      strength: 0.76,
      relationKind: 'place',
      actionType: 'view',
      actionTargetId: 'hp_west_lake',
      source: 'location',
      freshAt: _isoMinusHours(2),
    ),
    IntersectionReason(
      dimension: 'interest',
      intersectionId: 'ix_int_1',
      intersectionClass: 'affinity',
      label: '可能合得来',
      displayName: '陆衡',
      avatarUrl:
          'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100',
      sharedCount: 0,
      strength: 0.61,
      confidenceLabel: '推荐',
      modelReasonBucket: 'friend_suggestion',
      relationKind: 'person',
      actionType: 'view',
      actionTargetId: 'u_lu',
      source: 'interest',
      freshAt: _isoMinusHours(20),
    ),
  ];

  /// 各频道交集推荐（事实优先 + 概率补充），补齐 campus/travel。
  static Map<String, List<IntersectionReason>> get _channelReasons =>
      <String, List<IntersectionReason>>{
        'recommend': <IntersectionReason>[
          _inboxReasons[0],
          _inboxReasons[3],
          _inboxReasons[5],
        ],
        'campus': <IntersectionReason>[
          IntersectionReason(
            dimension: 'identity',
            intersectionId: 'ix_campus_1',
            intersectionClass: 'fact',
            label: '同专业',
            displayName: '苏黎',
            avatarUrl:
                'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=100',
            sharedCount: 6,
            strength: 0.84,
            relationKind: 'person',
            actionType: 'view',
            actionTargetId: 'u_su',
            source: 'identity',
            freshAt: _isoMinusHours(5),
          ),
          IntersectionReason(
            dimension: 'interest',
            intersectionId: 'ix_campus_2',
            intersectionClass: 'affinity',
            label: '同社团可能',
            displayName: '吉他社',
            avatarUrl:
                'https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=100',
            sharedCount: 0,
            strength: 0.58,
            confidenceLabel: '推荐',
            modelReasonBucket: 'circle_discovery',
            relationKind: 'circle',
            actionType: 'join',
            actionTargetId: 'circle_guitar',
            source: 'interest',
            freshAt: _isoMinusHours(40),
          ),
        ],
        'travel': <IntersectionReason>[
          IntersectionReason(
            dimension: 'location',
            intersectionId: 'ix_travel_1',
            intersectionClass: 'fact',
            label: '同目的地',
            displayName: '大理',
            avatarUrl:
                'https://images.unsplash.com/photo-1469474968028-56623f02e42e?w=100',
            sharedCount: 7,
            strength: 0.81,
            relationKind: 'place',
            actionType: 'view',
            actionTargetId: 'hp_dali',
            source: 'location',
            freshAt: _isoMinusHours(8),
          ),
          IntersectionReason(
            dimension: 'interest',
            intersectionId: 'ix_travel_2',
            intersectionClass: 'affinity',
            label: '可能同好',
            displayName: '徒步旅人',
            avatarUrl:
                'https://images.unsplash.com/photo-1454496522488-7a8e488e8606?w=100',
            sharedCount: 0,
            strength: 0.55,
            confidenceLabel: '推荐',
            modelReasonBucket: 'travel_affinity',
            relationKind: 'person',
            actionType: 'view',
            actionTargetId: 'u_hiker',
            source: 'interest',
            freshAt: _isoMinusHours(60),
          ),
        ],
      };
}

/// Remote 实现：调用 content-service 交集 API。
class RemoteIntersectionRepository implements IntersectionRepository {
  RemoteIntersectionRepository({CloudHttpClient? httpClient, String? baseUrl})
    : _httpClient = httpClient ?? CloudHttpClient(),
      _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();

  final CloudHttpClient _httpClient;
  final String _baseUrl;

  Uri _uri(String path, [Map<String, String>? query]) => Uri.parse(
    '$_baseUrl$path',
  ).replace(queryParameters: (query == null || query.isEmpty) ? null : query);

  @override
  Future<IntersectionInboxSummary> getMyIntersectionSummary() async {
    final decoded = await _httpClient.getJson(
      _uri(ContentApiMetadata.getMyIntersectionSummaryPath),
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.getMyIntersectionSummary,
      ),
    );
    final obj = CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.getMyIntersectionSummary,
    );
    return IntersectionInboxSummary.fromMap(obj);
  }

  @override
  Future<List<IntersectionReason>> listMyIntersections({
    String? dimension,
    int limit = 50,
  }) async {
    final query = <String, String>{'limit': '$limit'};
    if ((dimension ?? '').trim().isNotEmpty) {
      query['dimension'] = dimension!.trim();
    }
    final decoded = await _httpClient.getJson(
      _uri(ContentApiMetadata.listMyIntersectionsPath, query),
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.listMyIntersections,
      ),
    );
    final obj = CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.listMyIntersections,
    );
    return CloudResponseDecoder.mapList(obj, 'items')
        .map(IntersectionReason.fromMap)
        .toList(growable: false);
  }

  @override
  Future<void> markIntersectionsVisited({String? dimension}) async {
    final body = <String, dynamic>{
      'dimension': (dimension ?? '').trim(),
    };
    await _httpClient.postJson(
      _uri(ContentApiMetadata.markIntersectionsVisitedPath),
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.markIntersectionsVisited,
      ),
      body: body,
    );
  }

  @override
  Future<List<IntersectionReason>> getFeedIntersections({
    String? channel,
    int limit = 4,
  }) async {
    final query = <String, String>{'limit': '$limit'};
    if ((channel ?? '').trim().isNotEmpty) {
      query['channel'] = channel!.trim();
    }
    final decoded = await _httpClient.getJson(
      _uri(ContentApiMetadata.getFeedIntersectionsPath, query),
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.getFeedIntersections,
      ),
    );
    final obj = CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.getFeedIntersections,
    );
    return CloudResponseDecoder.mapList(obj, 'items')
        .map(IntersectionReason.fromMap)
        .toList(growable: false);
  }

  @override
  Future<void> reportExposure({required List<String> objectIds}) async {
    final body = <String, dynamic>{'objectIds': objectIds};
    await _httpClient.postJson(
      _uri(ContentApiMetadata.reportIntersectionExposurePath),
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.reportIntersectionExposure,
      ),
      body: body,
    );
  }
}
