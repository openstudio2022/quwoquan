import '../operation_request_payload.dart';
part '../generated/requests/content/author_impact_contracts.requests.g.dart';

/// A typed navigation target embedded in author-impact evidence.
final class AuthorImpactTargetProjection {
  const AuthorImpactTargetProjection({
    required this.objectType,
    required this.objectId,
    required this.objectKind,
    required this.routeId,
  });

  final String objectType;
  final String objectId;
  final String objectKind;
  final String routeId;
}

/// An object-level visual sample embedded in author-impact evidence.
final class AuthorImpactVisualProjection {
  const AuthorImpactVisualProjection({
    required this.assetKind,
    required this.imageUrl,
    required this.displayName,
    this.target,
  });

  final String assetKind;
  final String imageUrl;
  final String displayName;
  final AuthorImpactTargetProjection? target;
}

/// A structured interactive span in the server-authored conclusion sentence.
final class AuthorImpactTextSpanProjection {
  const AuthorImpactTextSpanProjection({
    required this.text,
    required this.role,
    this.target,
    this.visual,
  });

  final String text;
  final String role;
  final AuthorImpactTargetProjection? target;
  final AuthorImpactVisualProjection? visual;
}

/// A privacy-filtered representative actor supplied by the service.
final class AuthorImpactRepresentativeActorProjection {
  const AuthorImpactRepresentativeActorProjection({
    required this.actorId,
    required this.displayName,
    required this.avatarUrl,
    required this.relationLabel,
    required this.privacyState,
    required this.evidenceRank,
    required this.snapshotVersion,
    this.target,
  });

  final String actorId;
  final String displayName;
  final String avatarUrl;
  final String relationLabel;
  final String privacyState;
  final int evidenceRank;
  final String snapshotVersion;
  final AuthorImpactTargetProjection? target;
}

/// A server-authored next-action hint for an impact item.
final class AuthorImpactActionHintProjection {
  const AuthorImpactActionHintProjection({
    required this.actionKey,
    required this.label,
    required this.isPrimary,
    required this.priority,
    required this.actionTier,
    required this.requiredGates,
    required this.targetAvailability,
    required this.dispatch,
    this.target,
  });

  final String actionKey;
  final String label;
  final bool isPrimary;
  final int priority;
  final String actionTier;
  final List<String> requiredGates;
  final String targetAvailability;
  final String dispatch;
  final AuthorImpactTargetProjection? target;
}

/// A verifiable downstream propagation path for one impact item.
final class AuthorImpactPropagationPathProjection {
  const AuthorImpactPropagationPathProjection({
    required this.pathKind,
    required this.hopCount,
    required this.secondarySpreadCount,
    required this.summaryText,
    required this.nodes,
    this.summaryTarget,
  });

  final String pathKind;
  final int hopCount;
  final int secondarySpreadCount;
  final String summaryText;
  final List<AuthorImpactVisualProjection> nodes;
  final AuthorImpactTargetProjection? summaryTarget;
}

/// One server-aggregated author-impact fact.
final class AuthorImpactItemProjection {
  const AuthorImpactItemProjection({
    required this.helpType,
    required this.action,
    required this.intersectionDimension,
    required this.tagRef,
    required this.source,
    required this.count,
    required this.primaryText,
    required this.subtitleText,
    required this.impactId,
    required this.primarySpans,
    required this.sampleVisuals,
    required this.actionHints,
    required this.evidenceSnapshotId,
    required this.countObjectKind,
    required this.iconKey,
    required this.freshAt,
    required this.timeBucket,
    required this.lifecycleState,
    required this.previousStrength,
    required this.strengthDelta,
    this.representativeActor,
    this.countTarget,
    this.propagationPath,
  });

  final String helpType;
  final String action;
  final String intersectionDimension;
  final String tagRef;
  final String source;
  final int count;
  final String primaryText;
  final String subtitleText;
  final String impactId;
  final List<AuthorImpactTextSpanProjection> primarySpans;
  final List<AuthorImpactVisualProjection> sampleVisuals;
  final AuthorImpactRepresentativeActorProjection? representativeActor;
  final List<AuthorImpactActionHintProjection> actionHints;
  final AuthorImpactTargetProjection? countTarget;
  final String evidenceSnapshotId;
  final String countObjectKind;
  final AuthorImpactPropagationPathProjection? propagationPath;
  final String iconKey;
  final String freshAt;
  final String timeBucket;
  final String lifecycleState;
  final double previousStrength;
  final double strengthDelta;
}

/// Typed author-impact summary returned by the generated operation client.
final class AuthorImpactSummaryProjection {
  const AuthorImpactSummaryProjection({
    required this.authorId,
    required this.total,
    required this.items,
  });

  final String authorId;
  final int total;
  final List<AuthorImpactItemProjection> items;
}

/// One privacy-safe, content-anchored impact evidence row.
final class AuthorImpactEvidenceItemProjection {
  const AuthorImpactEvidenceItemProjection({
    required this.evidenceId,
    required this.impactId,
    required this.helpType,
    required this.action,
    required this.intersectionDimension,
    required this.occurredAt,
    required this.summaryText,
    required this.actionHints,
    this.sampleVisual,
    this.representativeActor,
    this.contentTarget,
  });

  final String evidenceId;
  final String impactId;
  final String helpType;
  final String action;
  final String intersectionDimension;
  final String occurredAt;
  final String summaryText;
  final AuthorImpactVisualProjection? sampleVisual;
  final AuthorImpactRepresentativeActorProjection? representativeActor;
  final List<AuthorImpactActionHintProjection> actionHints;
  final AuthorImpactTargetProjection? contentTarget;
}

/// Typed evidence page returned by the generated operation client.
final class AuthorImpactEvidencePageProjection {
  const AuthorImpactEvidencePageProjection({
    required this.impactId,
    required this.evidenceSnapshotId,
    required this.totalCount,
    required this.items,
    required this.nextCursor,
    required this.hasMore,
  });

  final String impactId;
  final String evidenceSnapshotId;
  final int totalCount;
  final List<AuthorImpactEvidenceItemProjection> items;
  final String nextCursor;
  final bool hasMore;
}

AuthorImpactSummaryProjection decodeAuthorImpactSummaryProjection(
  Object? response,
) {
  final root = _expectObject(response, 'Author impact summary response');
  return AuthorImpactSummaryProjection(
    authorId: _textOrEmpty(root['authorId']),
    total: _intOrZero(root['total']),
    items: _objectList(
      root['items'],
      'Author impact summary items',
    ).map(_decodeAuthorImpactItem).toList(growable: false),
  );
}

AuthorImpactEvidencePageProjection decodeAuthorImpactEvidencePageProjection(
  Object? response,
) {
  final root = _expectObject(response, 'Author impact evidence page response');
  return AuthorImpactEvidencePageProjection(
    impactId: _textOrEmpty(root['impactId']),
    evidenceSnapshotId: _textOrEmpty(root['evidenceSnapshotId']),
    totalCount: _intOrZero(root['totalCount']),
    items: _objectList(
      root['items'],
      'Author impact evidence page items',
    ).map(_decodeAuthorImpactEvidenceItem).toList(growable: false),
    nextCursor: _textOrEmpty(root['nextCursor']),
    hasMore: _boolOrFalse(root['hasMore']),
  );
}

AuthorImpactItemProjection _decodeAuthorImpactItem(Map<Object?, Object?> item) {
  return AuthorImpactItemProjection(
    helpType: _textOrEmpty(item['helpType']),
    action: _textOrEmpty(item['action']),
    intersectionDimension: _textOrEmpty(item['intersectionDimension']),
    tagRef: _textOrEmpty(item['tagRef']),
    source: _textOrEmpty(item['source']),
    count: _intOrZero(item['count']),
    primaryText: _textOrEmpty(item['primaryText']),
    subtitleText: _textOrEmpty(item['subtitleText']),
    impactId: _textOrEmpty(item['impactId']),
    primarySpans: _objectList(
      item['primarySpans'],
      'Author impact primary spans',
    ).map(_decodeTextSpan).toList(growable: false),
    sampleVisuals: _objectList(
      item['sampleVisuals'],
      'Author impact sample visuals',
    ).map(_decodeVisual).toList(growable: false),
    representativeActor: _optionalObject(
      item['representativeActor'],
      'Author impact representative actor',
      _decodeRepresentativeActor,
    ),
    actionHints: _objectList(
      item['actionHints'],
      'Author impact action hints',
    ).map(_decodeActionHint).toList(growable: false),
    countTarget: _optionalObject(
      item['countTarget'],
      'Author impact count target',
      _decodeTarget,
    ),
    evidenceSnapshotId: _textOrEmpty(item['evidenceSnapshotId']),
    countObjectKind: _textOrEmpty(item['countObjectKind']),
    propagationPath: _optionalObject(
      item['propagationPath'],
      'Author impact propagation path',
      _decodePropagationPath,
    ),
    iconKey: _textOrEmpty(item['iconKey']),
    freshAt: _textOrEmpty(item['freshAt']),
    timeBucket: _textOrEmpty(item['timeBucket']),
    lifecycleState: _textOrEmpty(item['lifecycleState']),
    previousStrength: _doubleOrZero(item['previousStrength']),
    strengthDelta: _doubleOrZero(item['strengthDelta']),
  );
}

AuthorImpactEvidenceItemProjection _decodeAuthorImpactEvidenceItem(
  Map<Object?, Object?> item,
) {
  return AuthorImpactEvidenceItemProjection(
    evidenceId: _textOrEmpty(item['evidenceId']),
    impactId: _textOrEmpty(item['impactId']),
    helpType: _textOrEmpty(item['helpType']),
    action: _textOrEmpty(item['action']),
    intersectionDimension: _textOrEmpty(item['intersectionDimension']),
    occurredAt: _textOrEmpty(item['occurredAt']),
    summaryText: _textOrEmpty(item['summaryText']),
    sampleVisual: _optionalObject(
      item['sampleVisual'],
      'Author impact evidence sample visual',
      _decodeVisual,
    ),
    representativeActor: _optionalObject(
      item['representativeActor'],
      'Author impact evidence representative actor',
      _decodeRepresentativeActor,
    ),
    actionHints: _objectList(
      item['actionHints'],
      'Author impact evidence action hints',
    ).map(_decodeActionHint).toList(growable: false),
    contentTarget: _optionalObject(
      item['contentTarget'],
      'Author impact evidence content target',
      _decodeTarget,
    ),
  );
}

AuthorImpactTargetProjection _decodeTarget(Map<Object?, Object?> target) {
  return AuthorImpactTargetProjection(
    objectType: _textOrEmpty(target['objectType']),
    objectId: _textOrEmpty(target['objectId']),
    objectKind: _textOrEmpty(target['objectKind']),
    routeId: _textOrEmpty(target['routeId']),
  );
}

AuthorImpactVisualProjection _decodeVisual(Map<Object?, Object?> visual) {
  return AuthorImpactVisualProjection(
    assetKind: _textOrEmpty(visual['assetKind']),
    imageUrl: _textOrEmpty(visual['imageUrl']),
    displayName: _textOrEmpty(visual['displayName']),
    target: _optionalObject(
      visual['target'],
      'Author impact visual target',
      _decodeTarget,
    ),
  );
}

AuthorImpactTextSpanProjection _decodeTextSpan(Map<Object?, Object?> span) {
  return AuthorImpactTextSpanProjection(
    text: _textOrEmpty(span['text']),
    role: _textOrEmpty(span['role'], fallback: 'plain'),
    target: _optionalObject(
      span['target'],
      'Author impact span target',
      _decodeTarget,
    ),
    visual: _optionalObject(
      span['visual'],
      'Author impact span visual',
      _decodeVisual,
    ),
  );
}

AuthorImpactRepresentativeActorProjection _decodeRepresentativeActor(
  Map<Object?, Object?> actor,
) {
  return AuthorImpactRepresentativeActorProjection(
    actorId: _textOrEmpty(actor['actorId']),
    displayName: _textOrEmpty(actor['displayName']),
    avatarUrl: _textOrEmpty(actor['avatarUrl']),
    relationLabel: _textOrEmpty(actor['relationLabel']),
    privacyState: _textOrEmpty(actor['privacyState'], fallback: 'visible'),
    evidenceRank: _intOrZero(actor['evidenceRank']),
    snapshotVersion: _textOrEmpty(actor['snapshotVersion']),
    target: _optionalObject(
      actor['target'],
      'Author impact representative actor target',
      _decodeTarget,
    ),
  );
}

AuthorImpactActionHintProjection _decodeActionHint(Map<Object?, Object?> hint) {
  return AuthorImpactActionHintProjection(
    actionKey: _textOrEmpty(hint['actionKey']),
    label: _textOrEmpty(hint['label']),
    isPrimary: _boolOrFalse(hint['isPrimary']),
    priority: _intOrZero(hint['priority']),
    actionTier: _textOrEmpty(hint['actionTier'], fallback: 'light'),
    requiredGates: _textList(
      hint['requiredGates'],
      'Author impact action hint required gates',
    ),
    targetAvailability: _textOrEmpty(
      hint['targetAvailability'],
      fallback: 'available',
    ),
    dispatch: _textOrEmpty(hint['dispatch'], fallback: 'navigate'),
    target: _optionalObject(
      hint['target'],
      'Author impact action hint target',
      _decodeTarget,
    ),
  );
}

AuthorImpactPropagationPathProjection _decodePropagationPath(
  Map<Object?, Object?> path,
) {
  return AuthorImpactPropagationPathProjection(
    pathKind: _textOrEmpty(path['pathKind']),
    hopCount: _intOrZero(path['hopCount']),
    secondarySpreadCount: _intOrZero(path['secondarySpreadCount']),
    summaryText: _textOrEmpty(path['summaryText']),
    summaryTarget: _optionalObject(
      path['summaryTarget'],
      'Author impact propagation summary target',
      _decodeTarget,
    ),
    nodes: _objectList(
      path['nodes'],
      'Author impact propagation nodes',
    ).map(_decodeVisual).toList(growable: false),
  );
}

Map<Object?, Object?> _expectObject(Object? value, String context) {
  if (value is Map<Object?, Object?>) {
    return value;
  }
  throw FormatException('$context must be an object');
}

List<Map<Object?, Object?>> _objectList(Object? value, String context) {
  if (value == null) {
    return const <Map<Object?, Object?>>[];
  }
  if (value is! List) {
    throw FormatException('$context must be a list');
  }
  return value
      .map((entry) => _expectObject(entry, '$context item'))
      .toList(growable: false);
}

T? _optionalObject<T>(
  Object? value,
  String context,
  T Function(Map<Object?, Object?>) decode,
) {
  if (value == null) {
    return null;
  }
  return decode(_expectObject(value, context));
}

String _textOrEmpty(Object? value, {String fallback = ''}) {
  if (value == null) {
    return fallback;
  }
  if (value is! String) {
    throw const FormatException('Expected a string value');
  }
  final normalized = value.trim();
  return normalized.isEmpty ? fallback : normalized;
}

int _intOrZero(Object? value) {
  if (value == null) {
    return 0;
  }
  if (value is num) {
    return value.toInt();
  }
  throw const FormatException('Expected an integer value');
}

double _doubleOrZero(Object? value) {
  if (value == null) {
    return 0;
  }
  if (value is num) {
    return value.toDouble();
  }
  throw const FormatException('Expected a numeric value');
}

bool _boolOrFalse(Object? value) {
  if (value == null) {
    return false;
  }
  if (value is bool) {
    return value;
  }
  throw const FormatException('Expected a boolean value');
}

List<String> _textList(Object? value, String context) {
  if (value == null) {
    return const <String>[];
  }
  if (value is! List) {
    throw FormatException('$context must be a list');
  }
  return value
      .map((entry) {
        if (entry is! String) {
          throw FormatException('$context must contain strings');
        }
        return entry.trim();
      })
      .where((entry) => entry.isNotEmpty)
      .toList(growable: false);
}
