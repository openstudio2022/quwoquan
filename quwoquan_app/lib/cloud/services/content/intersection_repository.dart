import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_api_query_defaults.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_dimension_tally.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_inbox_summary.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_point.g.dart';
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
    int limit = CloudApiQueryDefaults.intersectionListLimit,
  });

  Future<void> markIntersectionsVisited({String? dimension});

  Future<List<IntersectionReason>> getFeedIntersections({
    String? channel,
    int limit = CloudApiQueryDefaults.intersectionFeedLimit,
  });

  Future<void> reportExposure({required List<String> objectIds});

  /// 对象页「我与该对象」的关系类交集（共同关注/联系人来过/关注的人加入等，§2 闭集）。
  /// 与 tag-service 标签交集在 provider 层合并；维度/证据组 kind 为开放字符串。
  /// objectType: user | circle | entity（开放字符串，未知类型返回空）。
  Future<List<IntersectionReason>> getObjectIntersections({
    required String objectId,
    required String objectType,
    int limit = CloudApiQueryDefaults.objectIntersectionsLimit,
  });
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
          briefText: _briefTextFor(dimension, items, newCount),
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
    int limit = CloudApiQueryDefaults.intersectionListLimit,
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
    int limit = CloudApiQueryDefaults.intersectionFeedLimit,
  }) async {
    final wanted = (channel ?? '').trim();
    final pool = _channelReasons[wanted] ?? _channelReasons['recommend']!;
    final items = pool.map(_withExposureState).toList(growable: false);
    items.sort((a, b) {
      final aSeen = a.rankState == 'seen' ? 1 : 0;
      final bSeen = b.rankState == 'seen' ? 1 : 0;
      if (aSeen != bSeen) return aSeen.compareTo(bSeen);
      return b.strength.compareTo(a.strength);
    });
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

  @override
  Future<List<IntersectionReason>> getObjectIntersections({
    required String objectId,
    required String objectType,
    int limit = CloudApiQueryDefaults.objectIntersectionsLimit,
  }) async {
    final groups = _objectEvidenceGroups(objectType);
    if (groups.isEmpty) return const <IntersectionReason>[];
    final isRecommended = groups.every((g) => g.pointClass == 'recommended');
    final reason = _withPoints(
      IntersectionReason(
        dimension: groups.first.dimension,
        intersectionId: 'objix_${objectType}_$objectId',
        intersectionClass: isRecommended ? 'affinity' : 'fact',
        relationKind: _relationKindForObjectType(objectType),
        relationObjectId: objectId,
        actionType: 'view_object',
        actionTargetId: objectId,
        source: 'relationship',
        connectionSummary: _connectionSummaryFor(objectType, groups),
      ),
      groups
          .take(limit)
          .map(
            (g) => _point(
              id: 'objix_${objectId}_${g.kind}',
              pointClass: g.pointClass,
              dimension: g.dimension,
              label: g.label,
              displayText: g.label,
              sourceRef: g.kind,
              count: g.count,
              sampleText: g.sampleText,
              sampleAvatarUrls: g.avatars,
            ),
          )
          .toList(growable: false),
    );
    return <IntersectionReason>[reason];
  }

  String _relationKindForObjectType(String objectType) {
    switch (objectType) {
      case 'circle':
        return 'circle';
      case 'entity':
      case 'homepage':
        return 'place';
      default:
        return 'person';
    }
  }

  /// 云侧实例化连接说明（mock 模拟云端下发，端不在 UI 拼装）。
  String _connectionSummaryFor(
    String objectType,
    List<_EvidenceSeed> groups,
  ) {
    final samples = groups
        .where((g) => g.sampleText.trim().isNotEmpty)
        .take(2)
        .map((g) => g.sampleText.trim())
        .toList(growable: false);
    if (samples.isEmpty) return '';
    final joined = samples.join('、');
    return '$joined 把你们连在一起';
  }

  /// §2 证据组闭集 + contact/mutual/following 三层关系分层（按对象类型）。
  /// 维度为开放字符串，kind 同 §9.7 映射总表；展示真相源为证据组。
  List<_EvidenceSeed> _objectEvidenceGroups(String objectType) {
    switch (objectType) {
      case 'circle':
        return const <_EvidenceSeed>[
          _EvidenceSeed(
            kind: 'friendInCircle',
            dimension: 'relationship',
            label: '关注的人在这',
            count: 6,
            sampleText: '周屿',
            avatars: <String>[
              'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=100',
              'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=100',
            ],
          ),
          _EvidenceSeed(
            kind: 'contactInCircle',
            dimension: 'relationship',
            label: '联系人在这',
            count: 3,
            sampleText: '老同学 李航',
            avatars: <String>[
              'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100',
            ],
          ),
          _EvidenceSeed(
            kind: 'friendActiveHere',
            dimension: 'relationship',
            label: '关注的人常来',
            count: 3,
            sampleText: '林清越',
            avatars: <String>[
              'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=100',
            ],
          ),
          _EvidenceSeed(
            kind: 'sharedTagSample',
            dimension: 'interest',
            label: '都聊摄影',
            count: 0,
            sampleText: '',
          ),
          _EvidenceSeed(
            kind: 'affinity',
            dimension: 'interest',
            label: '你可能感兴趣',
            count: 0,
            sampleText: '',
            pointClass: 'recommended',
          ),
        ];
      case 'entity':
      case 'homepage':
        return const <_EvidenceSeed>[
          _EvidenceSeed(
            kind: 'friendVisited',
            dimension: 'location',
            label: '关注的人来过',
            count: 9,
            sampleText: '周屿',
            avatars: <String>[
              'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=100',
              'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=100',
              'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100',
            ],
          ),
          _EvidenceSeed(
            kind: 'contactVisited',
            dimension: 'location',
            label: '联系人来过',
            count: 4,
            sampleText: '同事 苏黎',
            avatars: <String>[
              'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=100',
            ],
          ),
          _EvidenceSeed(
            kind: 'friendJoinedRelatedCircle',
            dimension: 'relationship',
            label: '关注的人加入',
            count: 6,
            sampleText: '校友摄影圈',
            avatars: <String>[
              'https://images.unsplash.com/photo-1499952127939-9bbf5af6c51c?w=100',
            ],
          ),
          _EvidenceSeed(
            kind: 'youInteracted',
            dimension: 'location',
            label: '你来过',
            count: 3,
            sampleText: '',
          ),
          _EvidenceSeed(
            kind: 'affinity',
            dimension: 'interest',
            label: '可能想去',
            count: 0,
            sampleText: '',
            pointClass: 'recommended',
          ),
        ];
      case 'user':
        return const <_EvidenceSeed>[
          _EvidenceSeed(
            kind: 'mutualFriend',
            dimension: 'relationship',
            label: '共同关注',
            count: 4,
            sampleText: '林清越',
            avatars: <String>[
              'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=100',
              'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=100',
            ],
          ),
          _EvidenceSeed(
            kind: 'commonContact',
            dimension: 'relationship',
            label: '共同联系人',
            count: 2,
            sampleText: '老同学 李航',
            avatars: <String>[
              'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100',
            ],
          ),
          _EvidenceSeed(
            kind: 'commonFollow',
            dimension: 'relationship',
            label: '共同关注',
            count: 6,
            sampleText: '摄影师 陈漫',
            avatars: <String>[
              'https://images.unsplash.com/photo-1535713875002-d1d0cf377fde?w=100',
            ],
          ),
          _EvidenceSeed(
            kind: 'coLiked',
            dimension: 'content',
            label: '都赞过',
            count: 3,
            sampleText: '故宫夜景',
          ),
          _EvidenceSeed(
            kind: 'sharedTagSample',
            dimension: 'interest',
            label: '都爱摄影',
            count: 0,
            sampleText: '',
          ),
          _EvidenceSeed(
            kind: 'affinity',
            dimension: 'interest',
            label: '可能合得来',
            count: 0,
            sampleText: '',
            pointClass: 'recommended',
          ),
        ];
      default:
        return const <_EvidenceSeed>[];
    }
  }

  bool _isNew(IntersectionReason reason, DateTime? watermark) {
    if (watermark == null) return reason.freshAt.isNotEmpty;
    final fresh = DateTime.tryParse(reason.freshAt);
    if (fresh == null) return false;
    return fresh.isAfter(watermark);
  }

  IntersectionReason _withExposureState(IntersectionReason reason) {
    if (!_exposed.contains(reason.actionTargetId)) {
      return reason.copyWith(rankState: 'fresh');
    }
    return reason.copyWith(
      rankState: 'seen',
      seenAt: DateTime.now().toUtc().toIso8601String(),
    );
  }

  static String _isoMinusHours(int hours) =>
      DateTime.now().toUtc().subtract(Duration(hours: hours)).toIso8601String();

  /// 模拟云侧实例化动态简报句（mock 内模拟云端下发，端不在 UI 拼装）。
  static String _briefTextFor(
    String dimension,
    List<IntersectionReason> items,
    int newCount,
  ) {
    if (items.isEmpty) return '';
    final sample = items.first;
    final name = sample.displayName.trim();
    final n = newCount > 0 ? newCount : sample.sharedCount;
    final who = name.isEmpty ? '有人' : name;
    switch (dimension) {
      case 'relationship':
        return newCount > 0 ? '$who 等 $n 位与你新增了关系' : '你和 $who 等 $n 人相识';
      case 'identity':
        return '$who 等 $n 位同校同行的人';
      case 'content':
        return '你和 $n 人都在看「$who」';
      case 'location':
        return '$n 位与你去过「$who」';
      case 'interest':
        return '为你推荐 $n 个可能合得来的对象';
      default:
        return name.isEmpty ? '' : '$who 等 $n 项与你有关';
    }
  }

  static IntersectionPoint _point({
    required String id,
    required String pointClass,
    required String dimension,
    required String label,
    required String displayText,
    String sourceRef = '',
    int count = 0,
    String sampleText = '',
    List<String> sampleAvatarUrls = const <String>[],
  }) {
    return IntersectionPoint(
      pointId: id,
      pointClass: pointClass,
      dimension: dimension,
      label: label,
      displayText: displayText,
      sourceRef: sourceRef,
      visibility: 'public',
      count: count,
      sampleText: sampleText,
      sampleAvatarUrls: sampleAvatarUrls,
    );
  }

  static IntersectionReason _withPoints(
    IntersectionReason reason,
    List<IntersectionPoint> points,
  ) {
    final visible = points
        .where((point) => point.visibility != 'hidden')
        .toList(growable: false);
    final factCount = visible
        .where((point) => point.pointClass != 'recommended')
        .length;
    final recommendedCount = visible.length - factCount;
    final byDimension = <String, int>{};
    for (final point in visible) {
      byDimension[point.dimension] = (byDimension[point.dimension] ?? 0) + 1;
    }
    final summary = byDimension.entries
        .map(
          (entry) => IntersectionDimensionTally(
            dimension: entry.key,
            label: _dimensionLabels[entry.key] ?? entry.key,
            count: entry.value,
          ),
        )
        .toList(growable: false);
    return reason.copyWith(
      intersectionPoints: visible,
      pointSummarySnapshotId: reason.intersectionId,
      factPointCount: factCount,
      recommendedPointCount: recommendedCount,
      totalPointCount: visible.length,
      dimensionPointSummary: summary,
      pointClassLabel: recommendedCount > 0 && factCount == 0 ? '推荐交集' : '事实交集',
      recommendationTraceId: reason.intersectionId,
      rankState: 'fresh',
    );
  }

  static IntersectionReason _withDefaultPointSummary(
    IntersectionReason reason,
  ) {
    final pointClass = reason.intersectionClass == 'affinity'
        ? 'recommended'
        : 'fact';
    // 证据组短句名词优先 label（如「共同关注」），displayText 仅作回落；
    // count=sharedCount、sampleText=displayName、头像簇=[avatarUrl] 让交集可感知。
    final shortLabel = reason.label.trim().isNotEmpty
        ? reason.label.trim()
        : reason.displayText.trim();
    return _withPoints(reason, <IntersectionPoint>[
      _point(
        id: '${reason.intersectionId}_point',
        pointClass: pointClass,
        dimension: reason.dimension,
        label: shortLabel,
        displayText: shortLabel,
        sourceRef: reason.source,
        count: reason.sharedCount,
        sampleText: reason.displayName,
        sampleAvatarUrls: reason.avatarUrl.trim().isNotEmpty
            ? <String>[reason.avatarUrl.trim()]
            : const <String>[],
      ),
    ]);
  }

  static List<IntersectionReason> _withDefaultPointSummaries(
    List<IntersectionReason> reasons,
  ) {
    return reasons.map(_withDefaultPointSummary).toList(growable: false);
  }

  /// canonical 我的交集 inbox（覆盖 5 维度，含事实/概率混样、头像/名字/新鲜度）。
  static List<IntersectionReason>
  get _inboxReasons => _withDefaultPointSummaries(<IntersectionReason>[
    IntersectionReason(
      dimension: 'relationship',
      intersectionId: 'ix_rel_1',
      intersectionClass: 'fact',
      label: '共同关注',
      displayName: '林清越',
      displayText: '4 位共同关注',
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
      displayText: '你们互相关注',
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
      displayText: '同校校友',
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
      displayText: '共看黄金内容',
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
      displayText: '有相同旅行足迹',
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
      displayText: '可能合得来',
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
  ]);

  /// 各频道交集推荐（事实优先 + 概率补充），补齐 campus/travel。
  static Map<String, List<IntersectionReason>>
  get _channelReasons => <String, List<IntersectionReason>>{
    'recommend': <IntersectionReason>[
      _inboxReasons[0],
      _inboxReasons[3],
      _inboxReasons[5],
    ],
    'campus': _withDefaultPointSummaries(<IntersectionReason>[
      IntersectionReason(
        dimension: 'identity',
        intersectionId: 'ix_campus_1',
        intersectionClass: 'fact',
        label: '同专业',
        displayName: '苏黎',
        displayText: '同专业同校',
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
        displayText: '推荐加入社团',
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
    ]),
    'travel': _withDefaultPointSummaries(<IntersectionReason>[
      IntersectionReason(
        dimension: 'location',
        intersectionId: 'ix_travel_1',
        intersectionClass: 'fact',
        label: '同目的地',
        displayName: '大理',
        displayText: '有相同目的地',
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
        label: '兴趣相近',
        displayName: '徒步旅人',
        displayText: '可能喜欢相同路线',
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
    ]),
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
    int limit = CloudApiQueryDefaults.intersectionListLimit,
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
    return CloudResponseDecoder.mapList(
      obj,
      'items',
    ).map(IntersectionReason.fromMap).toList(growable: false);
  }

  @override
  Future<void> markIntersectionsVisited({String? dimension}) async {
    final body = <String, dynamic>{'dimension': (dimension ?? '').trim()};
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
    int limit = CloudApiQueryDefaults.intersectionFeedLimit,
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
    return CloudResponseDecoder.mapList(
      obj,
      'items',
    ).map(IntersectionReason.fromMap).toList(growable: false);
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

  @override
  Future<List<IntersectionReason>> getObjectIntersections({
    required String objectId,
    required String objectType,
    int limit = CloudApiQueryDefaults.objectIntersectionsLimit,
  }) async {
    final query = <String, String>{
      'objectId': objectId,
      'objectType': objectType,
      'limit': '$limit',
    };
    final decoded = await _httpClient.getJson(
      _uri(ContentApiMetadata.getObjectIntersectionsPath, query),
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.getObjectIntersections,
      ),
    );
    final obj = CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.getObjectIntersections,
    );
    return CloudResponseDecoder.mapList(
      obj,
      'items',
    ).map(IntersectionReason.fromMap).toList(growable: false);
  }
}

/// 对象页关系证据组 mock 种子（§2 闭集 + 三层关系分层）。
class _EvidenceSeed {
  const _EvidenceSeed({
    required this.kind,
    required this.dimension,
    required this.label,
    required this.count,
    required this.sampleText,
    this.avatars = const <String>[],
    this.pointClass = 'fact',
  });

  final String kind;
  final String dimension;
  final String label;
  final int count;
  final String sampleText;
  final List<String> avatars;
  final String pointClass;
}
