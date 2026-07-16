import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/contract_fixture_runtime_loader.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_api_query_defaults.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/recommendation_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/recommendation_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_dimension_tally.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_action_hint.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_inbox_summary.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_kind_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_point.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_representative_actor.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_target.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_visual.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/recommendation/intersection_action_keys.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_fact_items.dart';
import 'package:quwoquan_app/core/constants/discovery_feed_text_constants.dart';

/// 交集 Repository（三层模式：Abstract → Mock → Remote）。
///
/// 对应云侧路由（contracts/metadata/content/post/service.yaml）：
///   GET  /v1/content/intersections/summary   我的交集聚合摘要
///   GET  /v1/content/intersections           我的交集分维度列表（自上次新增在前）
///   POST /v1/recommendation/intersections/visit 推进已读水位，清零未读红点
abstract class IntersectionRepository {
  Future<IntersectionInboxSummary> getMyIntersectionSummary();

  Future<List<IntersectionReason>> listMyIntersections({
    String? dimension,
    String? filter,
    String? sourceRef,
    String? timeBucket,
    String? cursor,
    int limit = CloudApiQueryDefaults.intersectionListLimit,
  });

  Future<void> markIntersectionsVisited({String? dimension});

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
    var totalStrengthened = 0;
    var totalReactivated = 0;
    byDimension.forEach((dimension, items) {
      final watermark = _watermark[dimension];
      final newCount = items.where((r) => _isNew(r, watermark)).length;
      totalNew += newCount;
      // 生命周期态分桶计数（§21.3）：strengthened/reactivated 驱动弱标，不进结论句。
      final strengthenedCount = items
          .where((r) => r.lifecycleState.trim() == 'strengthened')
          .length;
      final reactivatedCount = items
          .where((r) => r.lifecycleState.trim() == 'reactivated')
          .length;
      totalStrengthened += strengthenedCount;
      totalReactivated += reactivatedCount;
      // 模拟云侧同源产出：briefText 与 briefSpans 由同一组片段拼装，
      // 因此 join(briefSpans.text) == briefText 恒成立（G2 单通道不变量）。
      final statement = _briefStatementFor(dimension, items, newCount);
      final sample = items.isNotEmpty ? items.first : null;
      tallies.add(
        IntersectionDimensionTally(
          dimension: dimension,
          label: DiscoveryFeedText.intersectionDimensionShortLabel(dimension),
          count: items.length,
          newCount: newCount,
          strengthenedCount: strengthenedCount,
          reactivatedCount: reactivatedCount,
          briefText: statement.text,
          briefSpans: statement.spans,
          sampleVisuals: _sampleVisualsFor(items),
          sourceRef: sample?.source.trim() ?? '',
          countObjectKind: sample?.objectKind.trim() ?? '',
          subtitleText: _subtitleTextFor(items),
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
      totalStrengthenedCount: totalStrengthened,
      totalReactivatedCount: totalReactivated,
      dimensions: tallies,
      generatedAt: DateTime.now().toUtc().toIso8601String(),
    );
  }

  @override
  Future<List<IntersectionReason>> listMyIntersections({
    String? dimension,
    String? filter,
    String? sourceRef,
    String? timeBucket,
    String? cursor,
    int limit = CloudApiQueryDefaults.intersectionListLimit,
  }) async {
    final wanted = (dimension ?? '').trim();
    final wantedFilter = (filter ?? '').trim();
    final wantedSourceRef = (sourceRef ?? '').trim();
    final wantedTimeBucket = (timeBucket ?? '').trim();
    final items = rankAndDedupeIntersections(
      filterDefaultInboxLifecycle(_inboxReasons)
          .where((r) {
            if (wanted.isNotEmpty && r.dimension != wanted) return false;
            if (wantedFilter == 'fact' && r.intersectionClass != 'fact') {
              return false;
            }
            if (wantedSourceRef.isNotEmpty && r.source != wantedSourceRef) {
              return false;
            }
            if (wantedTimeBucket.isNotEmpty &&
                timeBucketForIntersection(r) != wantedTimeBucket) {
              return false;
            }
            return true;
          })
          .toList(growable: false),
    );
    final watermark = wanted.isEmpty ? null : _watermark[wanted];
    items.sort((a, b) {
      final aNew = _isNew(a, watermark) ? 1 : 0;
      final bNew = _isNew(b, watermark) ? 1 : 0;
      if (aNew != bNew) return bNew.compareTo(aNew);
      return compareIntersectionRank(a, b);
    });
    if (items.length <= limit) return items;
    return items.sublist(0, limit);
  }

  @override
  Future<void> markIntersectionsVisited({String? dimension}) async {
    final now = DateTime.now().toUtc();
    final wanted = (dimension ?? '').trim();
    if (wanted.isEmpty) {
      // 维度闭集真相源 = codegen intersectionDimensionKeys（registry.dimensions），
      // 端不再维护第二份维度键表。
      for (final key in intersectionDimensionKeys) {
        _watermark[key] = now;
      }
      return;
    }
    _watermark[wanted] = now;
  }

  @override
  Future<List<IntersectionReason>> getObjectIntersections({
    required String objectId,
    required String objectType,
    int limit = CloudApiQueryDefaults.objectIntersectionsLimit,
  }) async {
    // 对象页「你们的交集」唯一真相源 = contract fixture（intersection_core.objectIntersections，
    // 与 alpha/beta/gamma seed 同源，自带 primaryText/primarySpans/intersectionPoints）。
    // 无可解析对象交集时返回空（不造假、不回退硬编码证据组——N3 已删除 _objectEvidenceGroups
    // 第二真相源，mock 与 remote 同走 IntersectionReason 真实下发）。
    final seeded = _seedObjectIntersections(objectId);
    if (seeded.isEmpty) return const <IntersectionReason>[];
    return seeded.length <= limit ? seeded : seeded.sublist(0, limit);
  }

  /// 对象页「你们的交集」seed 真相源（intersection_core.objectIntersections，按 objectId 索引）。
  /// 自带 primarySpans/intersectionPoints；命中即直出（与 inbox 同一 hydrate 管线收敛点摘要）。
  static List<IntersectionReason> _seedObjectIntersections(String objectId) {
    final seed = ContractFixtureRuntimeLoader.contentSeedSet(
      'intersection_core',
    );
    if (seed == null) return const <IntersectionReason>[];
    final raw = seed['objectIntersections'];
    if (raw is! Map) return const <IntersectionReason>[];
    final entries = raw[objectId];
    if (entries is! List) return const <IntersectionReason>[];
    return entries
        .whereType<Map>()
        .map((entry) {
          final map = Map<String, dynamic>.from(entry);
          var reason = IntersectionReason.fromMap(map);
          reason = reason.intersectionPoints.isNotEmpty
              ? _withPoints(reason, reason.intersectionPoints)
              : _withDefaultPointSummary(reason);
          return reason;
        })
        .toList(growable: false);
  }

  bool _isNew(IntersectionReason reason, DateTime? watermark) {
    if (watermark == null) return reason.freshAt.isNotEmpty;
    final fresh = DateTime.tryParse(reason.freshAt);
    if (fresh == null) return false;
    return fresh.isAfter(watermark);
  }

  static String _isoMinusHours(int hours) =>
      DateTime.now().toUtc().subtract(Duration(hours: hours)).toIso8601String();

  /// 模拟云侧实例化动态简报句 + 结构化富文本切分（mock 内模拟云端下发，端不在 UI 拼装）。
  ///
  /// briefText 与 briefSpans 由同一组片段拼装，[_BriefStatement] 构造时即令
  /// `join(spans.text) == text`，保证 G2 单通道不变量恒成立。
  static _BriefStatement _briefStatementFor(
    String dimension,
    List<IntersectionReason> items,
    int newCount,
  ) {
    if (items.isEmpty) {
      return const _BriefStatement(text: '', spans: <IntersectionTextSpan>[]);
    }
    final sample = items.first;
    final name = sample.displayName.trim();
    final firstPointCount = sample.intersectionPoints.isNotEmpty
        ? sample.intersectionPoints.first.count
        : sample.totalPointCount;
    final n = newCount > 0 ? newCount : firstPointCount;
    final who = name.isEmpty ? '有人' : name;
    final whoSpan = _objectSpanOrPlain(who, sample);
    final countSpan = _countSpan('$n', dimension);

    switch (dimension) {
      case 'relationship':
        return newCount > 0
            ? _BriefStatement.of(<IntersectionTextSpan>[
                whoSpan,
                _plain(' 等 '),
                countSpan,
                _plain(' 位与你新增了关系'),
              ])
            : _BriefStatement.of(<IntersectionTextSpan>[
                _plain('你和 '),
                whoSpan,
                _plain(' 等 '),
                countSpan,
                _plain(' 人相识'),
              ]);
      case 'identity':
        return _BriefStatement.of(<IntersectionTextSpan>[
          whoSpan,
          _plain(' 等 '),
          countSpan,
          _plain(' 位同校同行的人'),
        ]);
      case 'content':
        return _BriefStatement.of(<IntersectionTextSpan>[
          _plain('你和 '),
          countSpan,
          _plain(' 人都在看「'),
          whoSpan,
          _plain('」'),
        ]);
      case 'location':
        return _BriefStatement.of(<IntersectionTextSpan>[
          countSpan,
          _plain(' 位与你去过「'),
          whoSpan,
          _plain('」'),
        ]);
      case 'interest':
        return _BriefStatement.of(<IntersectionTextSpan>[
          _plain('为你推荐 '),
          countSpan,
          _plain(' 个可能合得来的对象'),
        ]);
      default:
        if (name.isEmpty) {
          return const _BriefStatement(
            text: '',
            spans: <IntersectionTextSpan>[],
          );
        }
        return _BriefStatement.of(<IntersectionTextSpan>[
          whoSpan,
          _plain(' 等 '),
          countSpan,
          _plain(' 项与你有关'),
        ]);
    }
  }

  static IntersectionTextSpan _plain(String text) =>
      IntersectionTextSpan(text: text, role: 'plain');

  /// 名字片段：有可点击对象时为 object span（进对象主页），否则降级为 plain。
  static IntersectionTextSpan _objectSpanOrPlain(
    String text,
    IntersectionReason sample,
  ) {
    final objectId = sample.actionTargetId.trim();
    final name = sample.displayName.trim();
    if (objectId.isEmpty || name.isEmpty) {
      return _plain(text);
    }
    final objectKind = _objectKindForReason(sample);
    return IntersectionTextSpan(
      text: text,
      role: 'object',
      target: IntersectionTarget(
        objectId: objectId,
        objectKind: objectKind,
        routeId: intersectionRouteIdForObjectKind(objectKind),
      ),
    );
  }

  /// 数字片段：进同维度证据组下钻列表（myIntersections?dimension=...，sourceRef 拖拽过滤）。
  static IntersectionTextSpan _countSpan(String text, String dimension) {
    return IntersectionTextSpan(
      text: text,
      role: 'count',
      target: IntersectionTarget(
        objectId: dimension,
        routeId: 'myIntersections',
      ),
    );
  }

  /// 维度样本视觉（最多 3 个，对象级 assetKind，不以用户头像冒充非用户对象）。
  static List<IntersectionVisual> _sampleVisualsFor(
    List<IntersectionReason> items,
  ) {
    final visuals = <IntersectionVisual>[];
    for (final item in items) {
      final url = item.avatarUrl.trim();
      final name = item.displayName.trim();
      if (url.isEmpty && name.isEmpty) {
        continue;
      }
      final objectKind = _objectKindForReason(item);
      final objectId = item.actionTargetId.trim();
      visuals.add(
        IntersectionVisual(
          assetKind:
              UnifiedObjectKind.fromWire(objectKind)?.assetKind ?? 'avatar',
          imageUrl: url,
          displayName: name,
          target: objectId.isEmpty
              ? null
              : IntersectionTarget(
                  objectId: objectId,
                  objectKind: objectKind,
                  routeId: intersectionRouteIdForObjectKind(objectKind),
                ),
        ),
      );
      if (visuals.length >= 3) {
        break;
      }
    }
    return visuals;
  }

  /// reason 的对象类型：objectKind 一等字段为真相源；缺省回退 person（旧 relationKind
  /// 对象类型桥接已删除，§23 去桥接）。
  static String _objectKindForReason(IntersectionReason reason) {
    final objectKind = reason.objectKind.trim();
    return objectKind.isNotEmpty ? objectKind : 'person';
  }

  static String _subtitleTextFor(List<IntersectionReason> items) {
    final names = <String>[];
    for (final item in items) {
      final secondary = item.secondaryText.trim();
      final displayName = item.displayName.trim();
      if (secondary.isNotEmpty) {
        names.add(secondary);
      } else if (displayName.isNotEmpty) {
        names.add(displayName);
      }
      if (names.length >= 4) {
        break;
      }
    }
    return names.join('、');
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
            label: DiscoveryFeedText.intersectionDimensionShortLabel(entry.key),
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
      representativeActor:
          reason.representativeActor ??
          _representativeActorFor(reason, visible),
      actionHints: reason.actionHints.isNotEmpty
          ? reason.actionHints.map(_hydrateActionHint).toList(growable: false)
          : _actionHintsFor(reason, visible),
      rankState: 'fresh',
    );
  }

  static IntersectionRepresentativeActor? _representativeActorFor(
    IntersectionReason reason,
    List<IntersectionPoint> points,
  ) {
    final point = points.isEmpty ? null : points.first;
    final name = (point?.sampleText.trim().isNotEmpty ?? false)
        ? point!.sampleText.trim()
        : reason.displayName.trim();
    final avatarUrl = (point?.sampleAvatarUrls.isNotEmpty ?? false)
        ? point!.sampleAvatarUrls.first.trim()
        : reason.avatarUrl.trim();
    if (name.isEmpty && avatarUrl.isEmpty) {
      return null;
    }
    final target = reason.actionTargetId.trim().isEmpty
        ? null
        : IntersectionTarget(
            objectId: reason.actionTargetId.trim(),
            objectKind: reason.objectKind.trim().isEmpty
                ? 'person'
                : reason.objectKind.trim(),
            routeId: intersectionRouteIdForObjectKind(reason.objectKind),
          );
    return IntersectionRepresentativeActor(
      actorId: target?.objectKind == 'person' ? target!.objectId : '',
      displayName: name.isEmpty ? '一位用户' : name,
      avatarUrl: avatarUrl,
      relationLabel: _relationLabelFor(point?.sourceRef ?? reason.source),
      privacyState: name.startsWith('一位') ? 'anonymous' : 'visible',
      target: target,
      evidenceRank: 0,
      snapshotVersion: reason.intersectionId,
    );
  }

  static List<IntersectionActionHint> _actionHintsFor(
    IntersectionReason reason,
    List<IntersectionPoint> points,
  ) {
    final sourceRef = points.isEmpty
        ? reason.source.trim()
        : points.first.sourceRef.trim();
    // 行动 actionKey 真相源 = codegen IntersectionKindMetadata.primaryActionKey
    // （registry.actionHintsByKind）；端不再按 kind 硬编码 switch（曾与注册表漂移）。
    final key =
        IntersectionKindMetadata.of(sourceRef)?.primaryActionKey ??
        IntersectionActionKeys.askAssistant;
    final meta = IntersectionActionKeyMeta.of(key);
    return <IntersectionActionHint>[
      IntersectionActionHint(
        actionKey: key,
        label: DiscoveryFeedText.intersectionActionLabel(key),
        target: reason.actionTargetId.trim().isEmpty
            ? null
            : IntersectionTarget(
                objectId: reason.actionTargetId.trim(),
                objectKind: reason.objectKind.trim(),
                routeId: intersectionRouteIdForObjectKind(reason.objectKind),
              ),
        isPrimary: true,
        priority: 1,
        actionTier: meta?.tier ?? 'light',
        requiredGates: meta?.requiredGates ?? const <String>[],
        targetAvailability: meta?.targetAvailability ?? 'available',
        dispatch: meta?.dispatch ?? 'assistant',
      ),
    ];
  }

  static IntersectionActionHint _hydrateActionHint(
    IntersectionActionHint hint,
  ) {
    final meta = IntersectionActionKeyMeta.of(hint.actionKey);
    if (meta == null) {
      return hint;
    }
    return hint.copyWith(
      actionTier: meta.tier,
      requiredGates: meta.requiredGates,
      targetAvailability: meta.targetAvailability,
      dispatch: meta.dispatch,
    );
  }

  static String _relationLabelFor(String sourceRef) {
    switch (sourceRef.trim()) {
      case 'commonContact':
        return '共同联系人';
      case 'sharedCircle':
      case 'coMemberCircle':
        return '同圈成员';
      case 'sameSchool':
      case 'sameMajor':
      case 'alumni':
        return '校友';
      default:
        return '代表人';
    }
  }

  static IntersectionReason _withDefaultPointSummary(
    IntersectionReason reason,
  ) {
    final pointClass = reason.intersectionClass == 'affinity'
        ? 'recommended'
        : 'fact';
    // 证据组短句名词来自云侧 primaryText（结论句），connectionSummary 仅作回落；
    // count 经 totalPointCount 中转原始共同实例数、sampleText=displayName、头像簇=[avatarUrl]。
    final shortLabel = reason.primaryText.trim().isNotEmpty
        ? reason.primaryText.trim()
        : reason.connectionSummary.trim();
    return _withPoints(reason, <IntersectionPoint>[
      _point(
        id: '${reason.intersectionId}_point',
        pointClass: pointClass,
        dimension: reason.dimension,
        label: shortLabel,
        displayText: shortLabel,
        sourceRef: reason.source,
        count: reason.totalPointCount,
        sampleText: reason.displayName,
        sampleAvatarUrls: reason.avatarUrl.trim().isNotEmpty
            ? <String>[reason.avatarUrl.trim()]
            : const <String>[],
      ),
    ]);
  }

  /// Contract fixture（intersection_core）优先：与 alpha/beta/gamma seed 同源。
  /// `freshAgoHours` 为相对小时数，运行时转 freshAt，保证「新增」语义稳定。
  static List<IntersectionReason>? _fixtureReasons({String? channel}) {
    final seed = ContractFixtureRuntimeLoader.contentSeedSet(
      'intersection_core',
    );
    if (seed == null) return null;
    Object? raw;
    if (channel == null) {
      raw = seed['inboxReasons'];
    } else {
      final channels = seed['channelReasons'];
      if (channels is! Map) return null;
      raw = channels[channel] ?? channels['recommend'];
    }
    if (raw is! List) return null;
    final reasons = raw
        .whereType<Map>()
        .map((entry) {
          final map = Map<String, dynamic>.from(entry);
          final agoHours = map.remove('freshAgoHours');
          var reason = IntersectionReason.fromMap(map);
          if (agoHours is num) {
            reason = reason.copyWith(freshAt: _isoMinusHours(agoHours.toInt()));
          }
          // fixture 自带 point 级 sourceRef（注册表标准 kind）时直接消费，
          // 仅缺省时回退合成单 point（防旧 fixture 漂移）。
          reason = reason.intersectionPoints.isNotEmpty
              ? _withPoints(reason, reason.intersectionPoints)
              : _withDefaultPointSummary(reason);
          return channel == null ? normalizeInboxReason(reason) : reason;
        })
        .toList(growable: false);
    return reasons.isEmpty ? null : reasons;
  }

  /// canonical 我的交集 inbox（覆盖 5 维度，含事实/概率混样、头像/名字/新鲜度）。
  /// Contract fixture 可用时与 seed 同源；否则回退行内 canonical 数据。
  static List<IntersectionReason> get _inboxReasons =>
      _fixtureReasons() ?? fallbackInboxReasons();
}

/// Remote 实现：调用 content-service 交集 API。
class RemoteIntersectionRepository implements IntersectionRepository {
  RemoteIntersectionRepository({
    CloudHttpClient? httpClient,
    String? baseUrl,
    String? currentUserId,
  }) : _httpClient = httpClient ?? CloudHttpClient(),
       _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim(),
       _currentUserId =
           (currentUserId ??
                   const String.fromEnvironment('APP_CURRENT_USER_ID'))
               .trim();

  final CloudHttpClient _httpClient;
  final String _baseUrl;
  final String _currentUserId;

  Uri _uri(String path, [Map<String, String>? query]) => Uri.parse(
    '$_baseUrl$path',
  ).replace(queryParameters: (query == null || query.isEmpty) ? null : query);

  Map<String, String> _headers(String pageId) =>
      CloudRequestHeaders.withOwnerSubAccountContext(
        CloudRequestHeaders.forPage(pageId),
        ownerUserId: _currentUserId,
        subAccountId: _currentUserId,
      );

  @override
  Future<IntersectionInboxSummary> getMyIntersectionSummary() async {
    final decoded = await _httpClient.getJson(
      _uri(ContentApiMetadata.getMyIntersectionSummaryPath),
      headers: _headers(ContentRequestPageIds.getMyIntersectionSummary),
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
    String? filter,
    String? sourceRef,
    String? timeBucket,
    String? cursor,
    int limit = CloudApiQueryDefaults.intersectionListLimit,
  }) async {
    final query = <String, String>{'limit': '$limit'};
    if ((dimension ?? '').trim().isNotEmpty) {
      query['dimension'] = dimension!.trim();
    }
    if ((filter ?? '').trim().isNotEmpty) {
      query['filter'] = filter!.trim();
    }
    if ((sourceRef ?? '').trim().isNotEmpty) {
      query['sourceRef'] = sourceRef!.trim();
    }
    if ((timeBucket ?? '').trim().isNotEmpty) {
      query['timeBucket'] = timeBucket!.trim();
    }
    if ((cursor ?? '').trim().isNotEmpty) {
      query['cursor'] = cursor!.trim();
    }
    final decoded = await _httpClient.getJson(
      _uri(ContentApiMetadata.listMyIntersectionsPath, query),
      headers: _headers(ContentRequestPageIds.listMyIntersections),
    );
    final obj = CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.listMyIntersections,
    );
    final parsed = CloudResponseDecoder.mapList(
      obj,
      'items',
    ).map(IntersectionReason.fromMap).toList(growable: false);
    // §22.3：expired/archived 默认列表显隐规则端侧单源（mock 与 remote 一致）。
    return filterDefaultInboxLifecycle(parsed);
  }

  @override
  Future<void> markIntersectionsVisited({String? dimension}) async {
    final body = <String, dynamic>{'dimension': (dimension ?? '').trim()};
    await _httpClient.postJson(
      _uri(RecommendationApiMetadata.markRecommendationIntersectionsVisitedPath),
      headers: _headers(
        RecommendationRequestPageIds.markRecommendationIntersectionsVisited,
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
      headers: _headers(ContentRequestPageIds.getObjectIntersections),
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

/// 简报句结构化结果：文本 + 富文本切分，构造即保证 join(spans.text) == text。
class _BriefStatement {
  const _BriefStatement({required this.text, required this.spans});

  factory _BriefStatement.of(List<IntersectionTextSpan> spans) {
    return _BriefStatement(
      text: spans.map((span) => span.text).join(),
      spans: spans,
    );
  }

  final String text;
  final List<IntersectionTextSpan> spans;
}
