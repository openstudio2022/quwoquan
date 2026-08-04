import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_kind_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_api_query_defaults.dart';
import 'package:quwoquan_app/cloud/runtime/recommendation/intersection_action_keys.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_fact_items.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_repository.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_visit_writer.dart';

import '../object_scenario_seed_reader.dart';
import '../../../fixtures/intersection_fixtures.dart';

/// local_contract 交集读写替身。
///
/// 数据按需读取 canonical content-service 场景；production composition 与 UAT
/// 不可达本文件。
class AlphaIntersectionRepository
    implements IntersectionRepository, IntersectionVisitWriter {
  AlphaIntersectionRepository({ObjectScenarioSeedReader? fixtures})
    : _fixtures = fixtures ?? objectScenarioSeedReader;

  final ObjectScenarioSeedReader _fixtures;
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
        intersectionDimensionTallyFixture(
          dimension: dimension,
          label: _fixtureDimensionLabel(dimension),
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
          iconKey: intersectionIconKeyByDimension[dimension] ?? 'attention',
        ),
      );
    });
    tallies.sort((a, b) {
      final byNew = b.newCount.compareTo(a.newCount);
      if (byNew != 0) return byNew;
      return b.count.compareTo(a.count);
    });

    return intersectionInboxSummaryFixture(
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
  Future<void> markIntersectionsVisited({
    IntersectionDimension? dimension,
  }) async {
    final now = DateTime.now().toUtc();
    final wanted = dimension?.wireName ?? '';
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
    // explicit_link 形态，直出会被端侧宿主 self-link 校验整批淘汰。
    final hostTarget = intersectionTargetFixture(
      objectType: _objectTypeForHost(objectType),
      objectId: objectId,
      objectKind: _objectKindForObjectType(objectType),
      routeId: intersectionRouteIdForObjectKind(
        _objectKindForObjectType(objectType),
      ),
    );
    final projected = reasons
        .map((reason) => _projectHostPlainFixture(reason, hostTarget))
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
          final freshAt = agoHours is num
              ? DateTime.now()
                    .toUtc()
                    .subtract(Duration(hours: agoHours.toInt()))
                    .toIso8601String()
              : '';
          var reason = _intersectionReasonFromScenarioSeed(
            map,
            freshAt: freshAt,
          );
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
      intersectionTextSpanFixture(text: text, role: 'plain');

  static IntersectionTextSpan _objectSpanOrPlain(
    String text,
    IntersectionReason sample,
  ) {
    final objectId = sample.actionTargetId.trim();
    final name = sample.displayName.trim();
    if (objectId.isEmpty || name.isEmpty) return _plain(text);
    final objectKind = _objectKindForReason(sample);
    return intersectionTextSpanFixture(
      text: text,
      role: 'object',
      target: intersectionTargetFixture(
        objectType: _objectTypeForKind(objectKind),
        objectId: objectId,
        objectKind: objectKind,
        routeId: intersectionRouteIdForObjectKind(objectKind),
      ),
    );
  }

  static IntersectionTextSpan _countSpan(String text, String dimension) {
    return intersectionTextSpanFixture(
      text: text,
      role: 'count',
      target: intersectionTargetFixture(
        objectType: 'dimension',
        objectId: dimension,
        objectKind: 'tag',
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
        intersectionVisualFixture(
          assetKind:
              UnifiedObjectKind.fromWire(objectKind)?.assetKind ?? 'avatar',
          imageUrl: url,
          displayName: name,
          target: objectId.isEmpty
              ? null
              : intersectionTargetFixture(
                  objectType: _objectTypeForKind(objectKind),
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
          (entry) => intersectionDimensionTallyFixture(
            dimension: entry.key,
            label: _fixtureDimensionLabel(entry.key),
            count: entry.value,
            newCount: 0,
            briefText: '',
            subtitleText: '',
            briefSpans: const <IntersectionTextSpan>[],
            sampleVisuals: const <IntersectionVisual>[],
            sourceRef: '',
            countObjectKind: '',
            strengthenedCount: 0,
            reactivatedCount: 0,
            iconKey: intersectionIconKeyByDimension[entry.key] ?? 'attention',
          ),
        )
        .toList(growable: false);
    return copyIntersectionReasonFixture(
      reason,
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
        _fixturePrimaryActionKeys[sourceRef] ??
        IntersectionActionKeys.askAssistant;
    final metadata = IntersectionActionKeyMeta.of(key);
    return <IntersectionActionHint>[
      intersectionActionHintFixture(
        actionKey: key,
        label: _fixtureActionLabel(key),
        target: reason.actionTargetId.trim().isEmpty
            ? null
            : intersectionTargetFixture(
                objectType: _objectTypeForKind(reason.objectKind),
                objectId: reason.actionTargetId.trim(),
                objectKind: reason.objectKind.trim(),
                routeId: intersectionRouteIdForObjectKind(reason.objectKind),
              ),
        isPrimary: true,
        priority: 1,
        actionTier: metadata?.tier ?? 'light',
        requiredGates: metadata?.requiredGates ?? const <String>[],
        dispatch: metadata?.dispatch ?? 'assistant',
      ),
    ];
  }

  static IntersectionActionHint _hydrateActionHint(
    IntersectionActionHint hint,
  ) {
    final metadata = IntersectionActionKeyMeta.of(hint.actionKey);
    if (metadata == null) return hint;
    return intersectionActionHintFixture(
      actionKey: hint.actionKey,
      label: hint.label,
      target: hint.target,
      isPrimary: hint.isPrimary,
      priority: hint.priority,
      actionTier: metadata.tier,
      requiredGates: metadata.requiredGates,
      dispatch: metadata.dispatch,
    );
  }
}

IntersectionReason _intersectionReasonFromScenarioSeed(
  Map<String, Object?> seed, {
  required String freshAt,
}) {
  final points = _seedObjectList(
    seed['intersectionPoints'],
  ).map(_intersectionPointFromScenarioSeed).toList(growable: false);
  final spans = _seedObjectList(
    seed['primarySpans'],
  ).map(_intersectionTextSpanFromScenarioSeed).toList(growable: false);
  final actorEvidence = _seedObjectList(
    seed['actorEvidence'],
  ).map(_intersectionActorEvidenceFromScenarioSeed).toList(growable: false);
  final representativeActorSeed = _seedObject(seed['representativeActor']);

  return intersectionReasonFixture(
    kind: _seedString(seed, 'kind'),
    vertical: _seedString(seed, 'vertical'),
    dimension: _seedString(seed, 'dimension'),
    tagRefs: _seedStringList(seed['tagRefs']),
    relationKind: _seedString(seed, 'relationKind'),
    objectKind: _seedString(seed, 'objectKind'),
    relationObjectId: _seedString(seed, 'relationObjectId'),
    strength: _seedDouble(seed, 'strength'),
    primaryText: _seedString(seed, 'primaryText'),
    primaryTextL10nKey: _seedString(seed, 'primaryTextL10nKey'),
    displayBinding: _seedString(
      seed,
      'displayBinding',
      fallback: intersectionDisplayBindingExplicitLink,
    ),
    secondaryText: _seedString(seed, 'secondaryText'),
    weightTier: _seedString(seed, 'weightTier'),
    actionType: _seedString(seed, 'actionType'),
    actionTargetId: _seedString(seed, 'actionTargetId'),
    source: _seedString(seed, 'source'),
    intersectionId: _seedString(seed, 'intersectionId'),
    intersectionClass: _seedString(seed, 'intersectionClass'),
    avatarUrl: _seedString(seed, 'avatarUrl'),
    displayName: _seedString(seed, 'displayName'),
    confidenceLabel: _seedString(seed, 'confidenceLabel'),
    modelReasonBucket: _seedString(seed, 'modelReasonBucket'),
    freshAt: freshAt,
    expiresAt: _seedString(seed, 'expiresAt'),
    intersectionPoints: points,
    actorEvidenceTotalCount: _seedInt(seed, 'actorEvidenceTotalCount'),
    actorEvidenceCompleteness: _seedString(seed, 'actorEvidenceCompleteness'),
    actorEvidence: actorEvidence,
    totalPointCount: points.length,
    connectionSummary: _seedString(seed, 'connectionSummary'),
    primarySpans: spans,
    representativeActor: representativeActorSeed == null
        ? null
        : _intersectionRepresentativeActorFromScenarioSeed(
            representativeActorSeed,
          ),
    lifecycleState: _seedString(seed, 'lifecycleState'),
    previousStrength: _seedDouble(seed, 'previousStrength'),
    strengthDelta: _seedDouble(seed, 'strengthDelta'),
    iconKey: _seedString(seed, 'iconKey'),
  );
}

IntersectionPoint _intersectionPointFromScenarioSeed(
  Map<String, Object?> seed,
) {
  return intersectionPointFixture(
    pointId: _seedString(seed, 'pointId'),
    pointClass: _seedString(seed, 'pointClass'),
    dimension: _seedString(seed, 'dimension'),
    label: _seedString(seed, 'label'),
    displayText: _seedString(seed, 'displayText'),
    sourceRef: _seedString(seed, 'sourceRef'),
    visibility: _seedString(seed, 'visibility', fallback: 'public'),
    count: _seedInt(seed, 'count'),
    sampleText: _seedString(seed, 'sampleText'),
    sampleAvatarUrls: _seedStringList(seed['sampleAvatarUrls']),
    sampleVisuals: _seedObjectList(
      seed['sampleVisuals'],
    ).map(_intersectionVisualFromScenarioSeed).toList(growable: false),
  );
}

IntersectionActorEvidence _intersectionActorEvidenceFromScenarioSeed(
  Map<String, Object?> seed,
) {
  final targetSeed = _seedObject(seed['target']);
  return intersectionActorEvidenceFixture(
    actorId: _seedString(seed, 'actorId'),
    displayName: _seedString(seed, 'displayName'),
    avatarUrl: _seedString(seed, 'avatarUrl'),
    relationLabel: _seedString(seed, 'relationLabel'),
    relationSourceRef: _seedString(seed, 'relationSourceRef'),
    relationObjectId: _seedString(seed, 'relationObjectId'),
    relationObjectName: _seedString(seed, 'relationObjectName'),
    sourcePointId: _seedString(seed, 'sourcePointId'),
    sourceRef: _seedString(seed, 'sourceRef'),
    actionSummaryText: _seedString(seed, 'actionSummaryText'),
    likeCount: _seedInt(seed, 'likeCount'),
    commentCount: _seedInt(seed, 'commentCount'),
    shareCount: _seedInt(seed, 'shareCount'),
    privacyState: _seedString(seed, 'privacyState'),
    target: targetSeed == null
        ? null
        : _intersectionTargetFromScenarioSeed(targetSeed),
    evidenceRank: _seedInt(seed, 'evidenceRank'),
    snapshotVersion: _seedString(seed, 'snapshotVersion'),
    sortKey: _seedInt(seed, 'sortKey'),
  );
}

IntersectionRepresentativeActor
_intersectionRepresentativeActorFromScenarioSeed(Map<String, Object?> seed) {
  final targetSeed = _seedObject(seed['target']);
  return intersectionRepresentativeActorFixture(
    actorId: _seedString(seed, 'actorId'),
    displayName: _seedString(seed, 'displayName'),
    avatarUrl: _seedString(seed, 'avatarUrl'),
    relationLabel: _seedString(seed, 'relationLabel'),
    privacyState: _seedString(seed, 'privacyState'),
    target: targetSeed == null
        ? null
        : _intersectionTargetFromScenarioSeed(targetSeed),
    evidenceRank: _seedInt(seed, 'evidenceRank'),
    snapshotVersion: _seedString(seed, 'snapshotVersion'),
  );
}

IntersectionTextSpan _intersectionTextSpanFromScenarioSeed(
  Map<String, Object?> seed,
) {
  final targetSeed = _seedObject(seed['target']);
  final visualSeed = _seedObject(seed['visual']);
  return intersectionTextSpanFixture(
    text: _seedString(seed, 'text'),
    role: _seedString(seed, 'role'),
    target: targetSeed == null
        ? null
        : _intersectionTargetFromScenarioSeed(targetSeed),
    visual: visualSeed == null
        ? null
        : _intersectionVisualFromScenarioSeed(visualSeed),
  );
}

IntersectionVisual _intersectionVisualFromScenarioSeed(
  Map<String, Object?> seed,
) {
  final targetSeed = _seedObject(seed['target']);
  return intersectionVisualFixture(
    assetKind: _seedString(seed, 'assetKind'),
    imageUrl: _seedString(seed, 'imageUrl'),
    displayName: _seedString(seed, 'displayName'),
    target: targetSeed == null
        ? null
        : _intersectionTargetFromScenarioSeed(targetSeed),
  );
}

IntersectionTarget _intersectionTargetFromScenarioSeed(
  Map<String, Object?> seed,
) {
  return intersectionTargetFixture(
    objectType: _seedString(seed, 'objectType'),
    objectId: _seedString(seed, 'objectId'),
    objectKind: _seedString(seed, 'objectKind'),
    routeId: _seedString(seed, 'routeId'),
  );
}

IntersectionReason _projectHostPlainFixture(
  IntersectionReason source,
  IntersectionTarget hostTarget,
) {
  final spans = source.primarySpans
      .map((span) {
        final target = span.target;
        if (target == null || target.objectId != hostTarget.objectId) {
          return span;
        }
        return intersectionTextSpanFixture(
          text: span.text,
          role: 'plain',
          visual: span.visual,
        );
      })
      .toList(growable: false);
  return copyIntersectionReasonFixture(
    source,
    displayBinding: intersectionDisplayBindingHostPlain,
    primarySpans: spans,
  );
}

String _seedString(
  Map<String, Object?> seed,
  String key, {
  String fallback = '',
}) {
  final value = seed[key];
  return value is String ? value : fallback;
}

int _seedInt(Map<String, Object?> seed, String key) {
  final value = seed[key];
  return value is num ? value.toInt() : 0;
}

double _seedDouble(Map<String, Object?> seed, String key) {
  final value = seed[key];
  return value is num ? value.toDouble() : 0;
}

List<String> _seedStringList(Object? value) {
  if (value is! List<Object?>) return const <String>[];
  return value.whereType<String>().toList(growable: false);
}

List<Map<String, Object?>> _seedObjectList(Object? value) {
  if (value is! List<Object?>) return const <Map<String, Object?>>[];
  return value
      .map(_seedObject)
      .whereType<Map<String, Object?>>()
      .toList(growable: false);
}

Map<String, Object?>? _seedObject(Object? value) {
  if (value is! Map<Object?, Object?>) return null;
  return value.map((key, item) => MapEntry(key.toString(), item));
}

String _objectKindForObjectType(String objectType) {
  switch (objectType.trim()) {
    case 'user':
    case 'person':
      return 'person';
    case 'circle':
      return 'circle';
    case 'post':
    case 'content':
      return 'content';
    default:
      return 'place';
  }
}

String _objectTypeForKind(String objectKind) {
  switch (objectKind.trim()) {
    case 'person':
      return 'user';
    case 'circle':
      return 'circle';
    case 'content':
      return 'post';
    case 'tag':
      return 'tag';
    default:
      return 'homepage';
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

/// 替身自持的展示文案：模拟云侧按注册表渲染后下发的 `tally.label` / `hint.label`。
/// 端侧 production 树不得再有同名表——那是本轮要消灭的第二真相源。
const Map<String, String> _fixtureDimensionLabels = <String, String>{
  'identity': '身份',
  'location': '地点',
  'content': '内容',
  'relationship': '关系',
  'interest': '兴趣',
};

String _fixtureDimensionLabel(String dimension) =>
    _fixtureDimensionLabels[dimension.trim()] ?? dimension;

const Map<String, String> _fixtureActionLabels = <String, String>{
  'follow_person': '关注',
  'greet_person': '打招呼',
  'message_person': '发消息',
  'view_shared_people': '查看共同关注',
  'join_circle': '加入圈子',
  'open_discussion': '进入讨论',
  'open_content': '查看内容',
  'open_object': '进入主页',
  'follow_object': '关注对象',
  'open_route': '查看路线',
  'create_followup': '写续篇',
  'ask_assistant': '解释这条交集',
  'start_gathering': '发起结伴',
};

String _fixtureActionLabel(String actionKey) =>
    _fixtureActionLabels[actionKey.trim()] ??
    _fixtureActionLabels['ask_assistant']!;

/// 替身自持的 kind → 主行动映射：模拟云侧按注册表 `actionHintsByKind` 选出的首个
/// actionKey。端侧 production 树不再编译逐 kind 行动表——那份表在线上随 reason 下发。
const Map<String, String> _fixturePrimaryActionKeys = <String, String>{
  'sharedFollowees': 'follow_person',
  'commonFollower': 'follow_person',
  'sameIndustry': 'message_person',
  'sharedCircle': 'join_circle',
  'coCommented': 'open_content',
  'coSharedContent': 'open_content',
  'coLiked': 'open_content',
  'coVisitedEntity': 'open_object',
  'sharedEntityAttention': 'open_object',
  'coWishlistedEntity': 'start_gathering',
  'sharedTagSample': 'open_object',
  'followeeInObject': 'join_circle',
  'followeeVisited': 'open_object',
  'followeeViewedObject': 'open_object',
  'followeeViewing': 'open_content',
  'followeeDiscussedThis': 'open_discussion',
};
