import 'package:quwoquan_app/cloud/runtime/cloud_api_query_defaults.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_action_hint.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_dimension_tally.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_inbox_summary.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_kind_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_point.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_target.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_visual.g.dart';
import 'package:quwoquan_app/cloud/runtime/recommendation/intersection_action_keys.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_fact_items.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_repository.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_visit_writer.dart';
import 'package:quwoquan_app/core/constants/discovery_feed_text_constants.dart';
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';

/// Alpha-only 交集读写适配器。
///
/// 数据只来自构建期生成的 immutable [AlphaFixtureBundle]，不会在设备运行时
/// 回读仓库相对路径。Production composition 不依赖 alpha runner。
class AlphaIntersectionRepository
    implements IntersectionRepository, IntersectionVisitWriter {
  AlphaIntersectionRepository({AlphaFixtureSeedReader? fixtures})
    : _fixtures = fixtures ?? alphaFixtureSeedReader;

  final AlphaFixtureSeedReader _fixtures;
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
      final newCount = items
          .where((reason) => _isNew(reason, watermark))
          .length;
      final strengthenedCount = items
          .where((reason) => reason.lifecycleState.trim() == 'strengthened')
          .length;
      final reactivatedCount = items
          .where((reason) => reason.lifecycleState.trim() == 'reactivated')
          .length;
      totalNew += newCount;
      totalStrengthened += strengthenedCount;
      totalReactivated += reactivatedCount;

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
      filterDefaultInboxLifecycle(
        _inboxReasons
            .where((reason) {
              if (wanted.isNotEmpty && reason.dimension != wanted) return false;
              if (wantedFilter == 'fact' &&
                  reason.intersectionClass != 'fact') {
                return false;
              }
              if (wantedSourceRef.isNotEmpty &&
                  reason.source != wantedSourceRef) {
                return false;
              }
              if (wantedTimeBucket.isNotEmpty &&
                  timeBucketForIntersection(reason) != wantedTimeBucket) {
                return false;
              }
              return true;
            })
            .toList(growable: false),
      ),
    );
    final watermark = wanted.isEmpty ? null : _watermark[wanted];
    items.sort((a, b) {
      final aNew = _isNew(a, watermark) ? 1 : 0;
      final bNew = _isNew(b, watermark) ? 1 : 0;
      if (aNew != bNew) return bNew.compareTo(aNew);
      return compareIntersectionRank(a, b);
    });
    return items.length <= limit ? items : items.sublist(0, limit);
  }

  @override
  Future<void> markIntersectionsVisited({String? dimension}) async {
    final now = DateTime.now().toUtc();
    final wanted = (dimension ?? '').trim();
    if (wanted.isEmpty) {
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
    final rawObjectIntersections = _intersectionSeed['objectIntersections'];
    if (rawObjectIntersections is! Map<Object?, Object?>) {
      throw const FormatException(
        'content/intersection_core.objectIntersections must be an object',
      );
    }
    final entries = rawObjectIntersections[objectId];
    if (entries == null) return const <IntersectionReason>[];
    final reasons = _decodeReasons(
      entries,
      context: 'objectIntersections.$objectId',
    );
    // 对象页合同与云侧 Reader 输出口同构（host_plain）：seed 是 canonical
    // explicit_link 形态，直出会被端侧宿主 self-link 校验整批淘汰（V1）。
    final hostTarget = IntersectionTarget(
      objectType: _objectTypeForHost(objectType),
      objectId: objectId,
    );
    final projected = reasons
        .map((reason) => applyHostPlainDisplayContext(reason, hostTarget))
        .toList(growable: false);
    return projected.length <= limit ? projected : projected.sublist(0, limit);
  }

  static String _objectTypeForHost(String objectType) {
    switch (objectType.trim()) {
      case 'user':
      case 'person':
        return 'user';
      case 'circle':
        return 'circle';
      case 'post':
      case 'content':
        return 'post';
      default:
        return 'homepage';
    }
  }

  Map<String, Object?> get _intersectionSeed =>
      _fixtures.requireSeedSet('content', 'intersection_core');

  List<IntersectionReason> get _inboxReasons => _decodeReasons(
    _intersectionSeed['inboxReasons'],
    context: 'inboxReasons',
  );

  List<IntersectionReason> _decodeReasons(
    Object? raw, {
    required String context,
  }) {
    if (raw is! List<Object?>) {
      throw FormatException(
        'content/intersection_core.$context must be an array',
      );
    }
    return raw
        .map((entry) {
          if (entry is! Map<Object?, Object?>) {
            throw FormatException(
              'content/intersection_core.$context item must be an object',
            );
          }
          final map = entry.map(
            (key, value) => MapEntry(key.toString(), value),
          );
          final agoHours = map.remove('freshAgoHours');
          var reason = IntersectionReason.fromMap(map);
          if (agoHours is num) {
            reason = reason.copyWith(
              freshAt: DateTime.now()
                  .toUtc()
                  .subtract(Duration(hours: agoHours.toInt()))
                  .toIso8601String(),
            );
          }
          if (reason.intersectionPoints.isEmpty) {
            throw FormatException(
              'content/intersection_core.$context '
              '${reason.intersectionId} must contain intersectionPoints',
            );
          }
          reason = _withPointSummary(reason, reason.intersectionPoints);
          return reason;
        })
        .toList(growable: false);
  }

  bool _isNew(IntersectionReason reason, DateTime? watermark) {
    if (watermark == null) return reason.freshAt.isNotEmpty;
    final fresh = DateTime.tryParse(reason.freshAt);
    return fresh != null && fresh.isAfter(watermark);
  }

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
    final firstPointCount = sample.intersectionPoints.first.count;
    final count = newCount > 0 ? newCount : firstPointCount;
    final who = name.isEmpty ? '有人' : name;
    final whoSpan = _objectSpanOrPlain(who, sample);
    final countSpan = _countSpan('$count', dimension);

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

  static IntersectionTextSpan _objectSpanOrPlain(
    String text,
    IntersectionReason sample,
  ) {
    final objectId = sample.actionTargetId.trim();
    final name = sample.displayName.trim();
    if (objectId.isEmpty || name.isEmpty) return _plain(text);
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

  static List<IntersectionVisual> _sampleVisualsFor(
    List<IntersectionReason> items,
  ) {
    final visuals = <IntersectionVisual>[];
    for (final item in items) {
      final url = item.avatarUrl.trim();
      final name = item.displayName.trim();
      if (url.isEmpty && name.isEmpty) continue;
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
      if (visuals.length >= 3) break;
    }
    return visuals;
  }

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
      if (names.length >= 4) break;
    }
    return names.join('、');
  }

  static IntersectionReason _withPointSummary(
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
      actionHints: reason.actionHints.isNotEmpty
          ? reason.actionHints.map(_hydrateActionHint).toList(growable: false)
          : _actionHintsFor(reason, visible),
      rankState: 'fresh',
    );
  }

  static List<IntersectionActionHint> _actionHintsFor(
    IntersectionReason reason,
    List<IntersectionPoint> points,
  ) {
    final sourceRef = points.first.sourceRef.trim();
    final key =
        IntersectionKindMetadata.of(sourceRef)?.primaryActionKey ??
        IntersectionActionKeys.askAssistant;
    final metadata = IntersectionActionKeyMeta.of(key);
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
        actionTier: metadata?.tier ?? 'light',
        requiredGates: metadata?.requiredGates ?? const <String>[],
        targetAvailability: metadata?.targetAvailability ?? 'available',
        dispatch: metadata?.dispatch ?? 'assistant',
      ),
    ];
  }

  static IntersectionActionHint _hydrateActionHint(
    IntersectionActionHint hint,
  ) {
    final metadata = IntersectionActionKeyMeta.of(hint.actionKey);
    if (metadata == null) return hint;
    return hint.copyWith(
      actionTier: metadata.tier,
      requiredGates: metadata.requiredGates,
      targetAvailability: metadata.targetAvailability,
      dispatch: metadata.dispatch,
    );
  }
}

final class _BriefStatement {
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
