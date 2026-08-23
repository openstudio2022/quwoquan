// Code generated from canonical domain contracts. DO NOT EDIT.
// ContractGraph SHA256: e1ab11a794ec2c40267fa9f217db7841a15176dd0fe692c983f7fcf0cb7a180e

library;


final class IntersectionActionHint {
  const IntersectionActionHint({
    required this.actionKey,
    required this.label,
    this.target,
    required this.isPrimary,
    required this.priority,
    required this.actionTier,
    required this.requiredGates,
    required this.dispatch,
  });

  final String actionKey;
  final String label;
  final IntersectionTarget? target;
  final bool isPrimary;
  final int priority;
  final String actionTier;
  final List<String> requiredGates;
  final String dispatch;

  factory IntersectionActionHint.fromWire(Map<String, Object?> map, [String path = "IntersectionActionHint"]) {
    _rejectUnknownFields(map, const <String>{"actionKey", "label", "target", "isPrimary", "priority", "actionTier", "requiredGates", "dispatch"}, path);
    return IntersectionActionHint(
      actionKey: _requiredString(map["actionKey"], '$path.actionKey'),
      label: _requiredString(map["label"], '$path.label'),
      target: map["target"] == null ? null : IntersectionTarget.fromWire(_requiredObject(map["target"], '$path.target'), '$path.target'),
      isPrimary: _requiredBool(map["isPrimary"], '$path.isPrimary'),
      priority: _requiredInt(map["priority"], '$path.priority'),
      actionTier: _requiredString(map["actionTier"], '$path.actionTier'),
      requiredGates: List<String>.unmodifiable(_requiredList(map["requiredGates"], '$path.requiredGates').asMap().entries.map((entry) => _requiredString(entry.value, '$path.requiredGates' + '[${entry.key}]'))),
      dispatch: _requiredString(map["dispatch"], '$path.dispatch'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "actionKey": actionKey,
    "label": label,
    if (target != null) "target": target!.toWire(),
    "isPrimary": isPrimary,
    "priority": priority,
    "actionTier": actionTier,
    "requiredGates": requiredGates.map((value) => value).toList(growable: false),
    "dispatch": dispatch,
  };
}

final class IntersectionActorEvidence {
  const IntersectionActorEvidence({
    required this.actorId,
    required this.displayName,
    required this.avatarUrl,
    required this.relationLabel,
    required this.relationSourceRef,
    required this.relationObjectId,
    required this.relationObjectName,
    required this.sourcePointId,
    required this.sourceRef,
    required this.actionSummaryText,
    required this.likeCount,
    required this.commentCount,
    required this.shareCount,
    required this.privacyState,
    this.target,
    required this.evidenceRank,
    required this.snapshotVersion,
    required this.sortKey,
  });

  final String actorId;
  final String displayName;
  final String avatarUrl;
  final String relationLabel;
  final String relationSourceRef;
  final String relationObjectId;
  final String relationObjectName;
  final String sourcePointId;
  final String sourceRef;
  final String actionSummaryText;
  final int likeCount;
  final int commentCount;
  final int shareCount;
  final String privacyState;
  final IntersectionTarget? target;
  final int evidenceRank;
  final String snapshotVersion;
  final int sortKey;

  factory IntersectionActorEvidence.fromWire(Map<String, Object?> map, [String path = "IntersectionActorEvidence"]) {
    _rejectUnknownFields(map, const <String>{"actorId", "displayName", "avatarUrl", "relationLabel", "relationSourceRef", "relationObjectId", "relationObjectName", "sourcePointId", "sourceRef", "actionSummaryText", "likeCount", "commentCount", "shareCount", "privacyState", "target", "evidenceRank", "snapshotVersion", "sortKey"}, path);
    return IntersectionActorEvidence(
      actorId: _requiredString(map["actorId"], '$path.actorId'),
      displayName: _requiredString(map["displayName"], '$path.displayName'),
      avatarUrl: _requiredString(map["avatarUrl"], '$path.avatarUrl'),
      relationLabel: _requiredString(map["relationLabel"], '$path.relationLabel'),
      relationSourceRef: _requiredString(map["relationSourceRef"], '$path.relationSourceRef'),
      relationObjectId: _requiredString(map["relationObjectId"], '$path.relationObjectId'),
      relationObjectName: _requiredString(map["relationObjectName"], '$path.relationObjectName'),
      sourcePointId: _requiredString(map["sourcePointId"], '$path.sourcePointId'),
      sourceRef: _requiredString(map["sourceRef"], '$path.sourceRef'),
      actionSummaryText: _requiredString(map["actionSummaryText"], '$path.actionSummaryText'),
      likeCount: _requiredInt(map["likeCount"], '$path.likeCount'),
      commentCount: _requiredInt(map["commentCount"], '$path.commentCount'),
      shareCount: _requiredInt(map["shareCount"], '$path.shareCount'),
      privacyState: _requiredString(map["privacyState"], '$path.privacyState'),
      target: map["target"] == null ? null : IntersectionTarget.fromWire(_requiredObject(map["target"], '$path.target'), '$path.target'),
      evidenceRank: _requiredInt(map["evidenceRank"], '$path.evidenceRank'),
      snapshotVersion: _requiredString(map["snapshotVersion"], '$path.snapshotVersion'),
      sortKey: _requiredInt(map["sortKey"], '$path.sortKey'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "actorId": actorId,
    "displayName": displayName,
    "avatarUrl": avatarUrl,
    "relationLabel": relationLabel,
    "relationSourceRef": relationSourceRef,
    "relationObjectId": relationObjectId,
    "relationObjectName": relationObjectName,
    "sourcePointId": sourcePointId,
    "sourceRef": sourceRef,
    "actionSummaryText": actionSummaryText,
    "likeCount": likeCount,
    "commentCount": commentCount,
    "shareCount": shareCount,
    "privacyState": privacyState,
    if (target != null) "target": target!.toWire(),
    "evidenceRank": evidenceRank,
    "snapshotVersion": snapshotVersion,
    "sortKey": sortKey,
  };
}

final class IntersectionDimensionTally {
  const IntersectionDimensionTally({
    required this.dimension,
    required this.label,
    required this.count,
    required this.newCount,
    required this.briefText,
    required this.subtitleText,
    required this.briefSpans,
    required this.sampleVisuals,
    required this.sourceRef,
    required this.countObjectKind,
    required this.strengthenedCount,
    required this.reactivatedCount,
    required this.iconKey,
  });

  final String dimension;
  final String label;
  final int count;
  final int newCount;
  final String briefText;
  final String subtitleText;
  final List<IntersectionTextSpan> briefSpans;
  final List<IntersectionVisual> sampleVisuals;
  final String sourceRef;
  final String countObjectKind;
  final int strengthenedCount;
  final int reactivatedCount;
  final String iconKey;

  factory IntersectionDimensionTally.fromWire(Map<String, Object?> map, [String path = "IntersectionDimensionTally"]) {
    _rejectUnknownFields(map, const <String>{"dimension", "label", "count", "newCount", "briefText", "subtitleText", "briefSpans", "sampleVisuals", "sourceRef", "countObjectKind", "strengthenedCount", "reactivatedCount", "iconKey"}, path);
    return IntersectionDimensionTally(
      dimension: _requiredString(map["dimension"], '$path.dimension'),
      label: _requiredString(map["label"], '$path.label'),
      count: _requiredInt(map["count"], '$path.count'),
      newCount: _requiredInt(map["newCount"], '$path.newCount'),
      briefText: _requiredString(map["briefText"], '$path.briefText'),
      subtitleText: _requiredString(map["subtitleText"], '$path.subtitleText'),
      briefSpans: List<IntersectionTextSpan>.unmodifiable(_requiredList(map["briefSpans"], '$path.briefSpans').asMap().entries.map((entry) => IntersectionTextSpan.fromWire(_requiredObject(entry.value, '$path.briefSpans' + '[${entry.key}]'), '$path.briefSpans' + '[${entry.key}]'))),
      sampleVisuals: List<IntersectionVisual>.unmodifiable(_requiredList(map["sampleVisuals"], '$path.sampleVisuals').asMap().entries.map((entry) => IntersectionVisual.fromWire(_requiredObject(entry.value, '$path.sampleVisuals' + '[${entry.key}]'), '$path.sampleVisuals' + '[${entry.key}]'))),
      sourceRef: _requiredString(map["sourceRef"], '$path.sourceRef'),
      countObjectKind: _requiredString(map["countObjectKind"], '$path.countObjectKind'),
      strengthenedCount: _requiredInt(map["strengthenedCount"], '$path.strengthenedCount'),
      reactivatedCount: _requiredInt(map["reactivatedCount"], '$path.reactivatedCount'),
      iconKey: _requiredString(map["iconKey"], '$path.iconKey'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "dimension": dimension,
    "label": label,
    "count": count,
    "newCount": newCount,
    "briefText": briefText,
    "subtitleText": subtitleText,
    "briefSpans": briefSpans.map((value) => value.toWire()).toList(growable: false),
    "sampleVisuals": sampleVisuals.map((value) => value.toWire()).toList(growable: false),
    "sourceRef": sourceRef,
    "countObjectKind": countObjectKind,
    "strengthenedCount": strengthenedCount,
    "reactivatedCount": reactivatedCount,
    "iconKey": iconKey,
  };
}

final class IntersectionInboxSummary {
  const IntersectionInboxSummary({
    required this.totalCount,
    required this.totalNewCount,
    required this.dimensions,
    required this.generatedAt,
    required this.totalStrengthenedCount,
    required this.totalReactivatedCount,
  });

  final int totalCount;
  final int totalNewCount;
  final List<IntersectionDimensionTally> dimensions;
  final String generatedAt;
  final int totalStrengthenedCount;
  final int totalReactivatedCount;

  factory IntersectionInboxSummary.fromWire(Map<String, Object?> map, [String path = "IntersectionInboxSummary"]) {
    _rejectUnknownFields(map, const <String>{"totalCount", "totalNewCount", "dimensions", "generatedAt", "totalStrengthenedCount", "totalReactivatedCount"}, path);
    return IntersectionInboxSummary(
      totalCount: _requiredInt(map["totalCount"], '$path.totalCount'),
      totalNewCount: _requiredInt(map["totalNewCount"], '$path.totalNewCount'),
      dimensions: List<IntersectionDimensionTally>.unmodifiable(_requiredList(map["dimensions"], '$path.dimensions').asMap().entries.map((entry) => IntersectionDimensionTally.fromWire(_requiredObject(entry.value, '$path.dimensions' + '[${entry.key}]'), '$path.dimensions' + '[${entry.key}]'))),
      generatedAt: _requiredString(map["generatedAt"], '$path.generatedAt'),
      totalStrengthenedCount: _requiredInt(map["totalStrengthenedCount"], '$path.totalStrengthenedCount'),
      totalReactivatedCount: _requiredInt(map["totalReactivatedCount"], '$path.totalReactivatedCount'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "totalCount": totalCount,
    "totalNewCount": totalNewCount,
    "dimensions": dimensions.map((value) => value.toWire()).toList(growable: false),
    "generatedAt": generatedAt,
    "totalStrengthenedCount": totalStrengthenedCount,
    "totalReactivatedCount": totalReactivatedCount,
  };
}

final class IntersectionPoint {
  const IntersectionPoint({
    required this.pointId,
    required this.pointClass,
    required this.dimension,
    required this.label,
    required this.displayText,
    required this.sourceRef,
    required this.visibility,
    required this.count,
    required this.sampleText,
    required this.sampleAvatarUrls,
    required this.sampleVisuals,
  });

  final String pointId;
  final String pointClass;
  final String dimension;
  final String label;
  final String displayText;
  final String sourceRef;
  final String visibility;
  final int count;
  final String sampleText;
  final List<String> sampleAvatarUrls;
  final List<IntersectionVisual> sampleVisuals;

  factory IntersectionPoint.fromWire(Map<String, Object?> map, [String path = "IntersectionPoint"]) {
    _rejectUnknownFields(map, const <String>{"pointId", "pointClass", "dimension", "label", "displayText", "sourceRef", "visibility", "count", "sampleText", "sampleAvatarUrls", "sampleVisuals"}, path);
    return IntersectionPoint(
      pointId: _requiredString(map["pointId"], '$path.pointId'),
      pointClass: _requiredString(map["pointClass"], '$path.pointClass'),
      dimension: _requiredString(map["dimension"], '$path.dimension'),
      label: _requiredString(map["label"], '$path.label'),
      displayText: _requiredString(map["displayText"], '$path.displayText'),
      sourceRef: _requiredString(map["sourceRef"], '$path.sourceRef'),
      visibility: _requiredString(map["visibility"], '$path.visibility'),
      count: _requiredInt(map["count"], '$path.count'),
      sampleText: _requiredString(map["sampleText"], '$path.sampleText'),
      sampleAvatarUrls: List<String>.unmodifiable(_requiredList(map["sampleAvatarUrls"], '$path.sampleAvatarUrls').asMap().entries.map((entry) => _requiredString(entry.value, '$path.sampleAvatarUrls' + '[${entry.key}]'))),
      sampleVisuals: List<IntersectionVisual>.unmodifiable(_requiredList(map["sampleVisuals"], '$path.sampleVisuals').asMap().entries.map((entry) => IntersectionVisual.fromWire(_requiredObject(entry.value, '$path.sampleVisuals' + '[${entry.key}]'), '$path.sampleVisuals' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "pointId": pointId,
    "pointClass": pointClass,
    "dimension": dimension,
    "label": label,
    "displayText": displayText,
    "sourceRef": sourceRef,
    "visibility": visibility,
    "count": count,
    "sampleText": sampleText,
    "sampleAvatarUrls": sampleAvatarUrls.map((value) => value).toList(growable: false),
    "sampleVisuals": sampleVisuals.map((value) => value.toWire()).toList(growable: false),
  };
}

final class IntersectionPropagationPath {
  const IntersectionPropagationPath({
    required this.pathKind,
    required this.hopCount,
    required this.secondarySpreadCount,
    required this.summaryText,
    this.summaryTarget,
    required this.nodes,
  });

  final String pathKind;
  final int hopCount;
  final int secondarySpreadCount;
  final String summaryText;
  final IntersectionTarget? summaryTarget;
  final List<IntersectionVisual> nodes;

  factory IntersectionPropagationPath.fromWire(Map<String, Object?> map, [String path = "IntersectionPropagationPath"]) {
    _rejectUnknownFields(map, const <String>{"pathKind", "hopCount", "secondarySpreadCount", "summaryText", "summaryTarget", "nodes"}, path);
    return IntersectionPropagationPath(
      pathKind: _requiredString(map["pathKind"], '$path.pathKind'),
      hopCount: _requiredInt(map["hopCount"], '$path.hopCount'),
      secondarySpreadCount: _requiredInt(map["secondarySpreadCount"], '$path.secondarySpreadCount'),
      summaryText: _requiredString(map["summaryText"], '$path.summaryText'),
      summaryTarget: map["summaryTarget"] == null ? null : IntersectionTarget.fromWire(_requiredObject(map["summaryTarget"], '$path.summaryTarget'), '$path.summaryTarget'),
      nodes: List<IntersectionVisual>.unmodifiable(_requiredList(map["nodes"], '$path.nodes').asMap().entries.map((entry) => IntersectionVisual.fromWire(_requiredObject(entry.value, '$path.nodes' + '[${entry.key}]'), '$path.nodes' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "pathKind": pathKind,
    "hopCount": hopCount,
    "secondarySpreadCount": secondarySpreadCount,
    "summaryText": summaryText,
    if (summaryTarget != null) "summaryTarget": summaryTarget!.toWire(),
    "nodes": nodes.map((value) => value.toWire()).toList(growable: false),
  };
}

final class IntersectionReason {
  const IntersectionReason({
    required this.kind,
    required this.vertical,
    required this.dimension,
    required this.tagRefs,
    required this.relationKind,
    required this.objectKind,
    required this.relationObjectId,
    required this.strength,
    required this.primaryText,
    required this.primaryTextL10nKey,
    required this.displayBinding,
    required this.secondaryText,
    required this.weightTier,
    required this.actionType,
    required this.actionTargetId,
    required this.source,
    required this.intersectionId,
    required this.intersectionClass,
    required this.avatarUrl,
    required this.displayName,
    required this.confidenceLabel,
    required this.modelReasonBucket,
    required this.freshAt,
    required this.expiresAt,
    required this.intersectionPoints,
    required this.pointSummarySnapshotId,
    required this.actorEvidenceTotalCount,
    required this.actorEvidenceCompleteness,
    required this.actorEvidence,
    required this.factPointCount,
    required this.recommendedPointCount,
    required this.totalPointCount,
    required this.dimensionPointSummary,
    required this.pointClassLabel,
    required this.connectionSummary,
    required this.lastRecommendedAt,
    required this.seenAt,
    required this.rankState,
    required this.primarySpans,
    required this.sampleVisuals,
    this.representativeActor,
    required this.actionHints,
    required this.lifecycleState,
    required this.previousStrength,
    required this.strengthDelta,
    required this.edgeWeight,
    required this.iconKey,
    required this.tone,
    this.typeVisual,
    this.objectVisual,
    required this.timeBucket,
    required this.dedupeKey,
    required this.anchorUserWeight,
    required this.mutualCount,
    required this.moment,
    required this.subjectId,
    required this.subjectContext,
  });

  final String kind;
  final String vertical;
  final String dimension;
  final List<String> tagRefs;
  final String relationKind;
  final String objectKind;
  final String relationObjectId;
  final double strength;
  final String primaryText;
  final String primaryTextL10nKey;
  final String displayBinding;
  final String secondaryText;
  final String weightTier;
  final String actionType;
  final String actionTargetId;
  final String source;
  final String intersectionId;
  final String intersectionClass;
  final String avatarUrl;
  final String displayName;
  final String confidenceLabel;
  final String modelReasonBucket;
  final String freshAt;
  final String expiresAt;
  final List<IntersectionPoint> intersectionPoints;
  final String pointSummarySnapshotId;
  final int actorEvidenceTotalCount;
  final String actorEvidenceCompleteness;
  final List<IntersectionActorEvidence> actorEvidence;
  final int factPointCount;
  final int recommendedPointCount;
  final int totalPointCount;
  final List<IntersectionDimensionTally> dimensionPointSummary;
  final String pointClassLabel;
  final String connectionSummary;
  final String lastRecommendedAt;
  final String seenAt;
  final String rankState;
  final List<IntersectionTextSpan> primarySpans;
  final List<IntersectionVisual> sampleVisuals;
  final IntersectionRepresentativeActor? representativeActor;
  final List<IntersectionActionHint> actionHints;
  final String lifecycleState;
  final double previousStrength;
  final double strengthDelta;
  final double edgeWeight;
  final String iconKey;
  final String tone;
  final IntersectionVisual? typeVisual;
  final IntersectionVisual? objectVisual;
  final String timeBucket;
  final String dedupeKey;
  final double anchorUserWeight;
  final int mutualCount;
  final String moment;
  final String subjectId;
  final String subjectContext;

  factory IntersectionReason.fromWire(Map<String, Object?> map, [String path = "IntersectionReason"]) {
    _rejectUnknownFields(map, const <String>{"kind", "vertical", "dimension", "tagRefs", "relationKind", "objectKind", "relationObjectId", "strength", "primaryText", "primaryTextL10nKey", "displayBinding", "secondaryText", "weightTier", "actionType", "actionTargetId", "source", "intersectionId", "intersectionClass", "avatarUrl", "displayName", "confidenceLabel", "modelReasonBucket", "freshAt", "expiresAt", "intersectionPoints", "pointSummarySnapshotId", "actorEvidenceTotalCount", "actorEvidenceCompleteness", "actorEvidence", "factPointCount", "recommendedPointCount", "totalPointCount", "dimensionPointSummary", "pointClassLabel", "connectionSummary", "lastRecommendedAt", "seenAt", "rankState", "primarySpans", "sampleVisuals", "representativeActor", "actionHints", "lifecycleState", "previousStrength", "strengthDelta", "edgeWeight", "iconKey", "tone", "typeVisual", "objectVisual", "timeBucket", "dedupeKey", "anchorUserWeight", "mutualCount", "moment", "subjectId", "subjectContext"}, path);
    return IntersectionReason(
      kind: _requiredString(map["kind"], '$path.kind'),
      vertical: _requiredString(map["vertical"], '$path.vertical'),
      dimension: _requiredString(map["dimension"], '$path.dimension'),
      tagRefs: List<String>.unmodifiable(_requiredList(map["tagRefs"], '$path.tagRefs').asMap().entries.map((entry) => _requiredString(entry.value, '$path.tagRefs' + '[${entry.key}]'))),
      relationKind: _requiredString(map["relationKind"], '$path.relationKind'),
      objectKind: _requiredString(map["objectKind"], '$path.objectKind'),
      relationObjectId: _requiredString(map["relationObjectId"], '$path.relationObjectId'),
      strength: _requiredDouble(map["strength"], '$path.strength'),
      primaryText: _requiredString(map["primaryText"], '$path.primaryText'),
      primaryTextL10nKey: _requiredString(map["primaryTextL10nKey"], '$path.primaryTextL10nKey'),
      displayBinding: _requiredString(map["displayBinding"], '$path.displayBinding'),
      secondaryText: _requiredString(map["secondaryText"], '$path.secondaryText'),
      weightTier: _requiredString(map["weightTier"], '$path.weightTier'),
      actionType: _requiredString(map["actionType"], '$path.actionType'),
      actionTargetId: _requiredString(map["actionTargetId"], '$path.actionTargetId'),
      source: _requiredString(map["source"], '$path.source'),
      intersectionId: _requiredString(map["intersectionId"], '$path.intersectionId'),
      intersectionClass: _requiredString(map["intersectionClass"], '$path.intersectionClass'),
      avatarUrl: _requiredString(map["avatarUrl"], '$path.avatarUrl'),
      displayName: _requiredString(map["displayName"], '$path.displayName'),
      confidenceLabel: _requiredString(map["confidenceLabel"], '$path.confidenceLabel'),
      modelReasonBucket: _requiredString(map["modelReasonBucket"], '$path.modelReasonBucket'),
      freshAt: _requiredString(map["freshAt"], '$path.freshAt'),
      expiresAt: _requiredString(map["expiresAt"], '$path.expiresAt'),
      intersectionPoints: List<IntersectionPoint>.unmodifiable(_requiredList(map["intersectionPoints"], '$path.intersectionPoints').asMap().entries.map((entry) => IntersectionPoint.fromWire(_requiredObject(entry.value, '$path.intersectionPoints' + '[${entry.key}]'), '$path.intersectionPoints' + '[${entry.key}]'))),
      pointSummarySnapshotId: _requiredString(map["pointSummarySnapshotId"], '$path.pointSummarySnapshotId'),
      actorEvidenceTotalCount: _requiredInt(map["actorEvidenceTotalCount"], '$path.actorEvidenceTotalCount'),
      actorEvidenceCompleteness: _requiredString(map["actorEvidenceCompleteness"], '$path.actorEvidenceCompleteness'),
      actorEvidence: List<IntersectionActorEvidence>.unmodifiable(_requiredList(map["actorEvidence"], '$path.actorEvidence').asMap().entries.map((entry) => IntersectionActorEvidence.fromWire(_requiredObject(entry.value, '$path.actorEvidence' + '[${entry.key}]'), '$path.actorEvidence' + '[${entry.key}]'))),
      factPointCount: _requiredInt(map["factPointCount"], '$path.factPointCount'),
      recommendedPointCount: _requiredInt(map["recommendedPointCount"], '$path.recommendedPointCount'),
      totalPointCount: _requiredInt(map["totalPointCount"], '$path.totalPointCount'),
      dimensionPointSummary: List<IntersectionDimensionTally>.unmodifiable(_requiredList(map["dimensionPointSummary"], '$path.dimensionPointSummary').asMap().entries.map((entry) => IntersectionDimensionTally.fromWire(_requiredObject(entry.value, '$path.dimensionPointSummary' + '[${entry.key}]'), '$path.dimensionPointSummary' + '[${entry.key}]'))),
      pointClassLabel: _requiredString(map["pointClassLabel"], '$path.pointClassLabel'),
      connectionSummary: _requiredString(map["connectionSummary"], '$path.connectionSummary'),
      lastRecommendedAt: _requiredString(map["lastRecommendedAt"], '$path.lastRecommendedAt'),
      seenAt: _requiredString(map["seenAt"], '$path.seenAt'),
      rankState: _requiredString(map["rankState"], '$path.rankState'),
      primarySpans: List<IntersectionTextSpan>.unmodifiable(_requiredList(map["primarySpans"], '$path.primarySpans').asMap().entries.map((entry) => IntersectionTextSpan.fromWire(_requiredObject(entry.value, '$path.primarySpans' + '[${entry.key}]'), '$path.primarySpans' + '[${entry.key}]'))),
      sampleVisuals: List<IntersectionVisual>.unmodifiable(_requiredList(map["sampleVisuals"], '$path.sampleVisuals').asMap().entries.map((entry) => IntersectionVisual.fromWire(_requiredObject(entry.value, '$path.sampleVisuals' + '[${entry.key}]'), '$path.sampleVisuals' + '[${entry.key}]'))),
      representativeActor: map["representativeActor"] == null ? null : IntersectionRepresentativeActor.fromWire(_requiredObject(map["representativeActor"], '$path.representativeActor'), '$path.representativeActor'),
      actionHints: List<IntersectionActionHint>.unmodifiable(_requiredList(map["actionHints"], '$path.actionHints').asMap().entries.map((entry) => IntersectionActionHint.fromWire(_requiredObject(entry.value, '$path.actionHints' + '[${entry.key}]'), '$path.actionHints' + '[${entry.key}]'))),
      lifecycleState: _requiredString(map["lifecycleState"], '$path.lifecycleState'),
      previousStrength: _requiredDouble(map["previousStrength"], '$path.previousStrength'),
      strengthDelta: _requiredDouble(map["strengthDelta"], '$path.strengthDelta'),
      edgeWeight: _requiredDouble(map["edgeWeight"], '$path.edgeWeight'),
      iconKey: _requiredString(map["iconKey"], '$path.iconKey'),
      tone: _requiredString(map["tone"], '$path.tone'),
      typeVisual: map["typeVisual"] == null ? null : IntersectionVisual.fromWire(_requiredObject(map["typeVisual"], '$path.typeVisual'), '$path.typeVisual'),
      objectVisual: map["objectVisual"] == null ? null : IntersectionVisual.fromWire(_requiredObject(map["objectVisual"], '$path.objectVisual'), '$path.objectVisual'),
      timeBucket: _requiredString(map["timeBucket"], '$path.timeBucket'),
      dedupeKey: _requiredString(map["dedupeKey"], '$path.dedupeKey'),
      anchorUserWeight: _requiredDouble(map["anchorUserWeight"], '$path.anchorUserWeight'),
      mutualCount: _requiredInt(map["mutualCount"], '$path.mutualCount'),
      moment: _requiredString(map["moment"], '$path.moment'),
      subjectId: _requiredString(map["subjectId"], '$path.subjectId'),
      subjectContext: _requiredString(map["subjectContext"], '$path.subjectContext'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "kind": kind,
    "vertical": vertical,
    "dimension": dimension,
    "tagRefs": tagRefs.map((value) => value).toList(growable: false),
    "relationKind": relationKind,
    "objectKind": objectKind,
    "relationObjectId": relationObjectId,
    "strength": strength,
    "primaryText": primaryText,
    "primaryTextL10nKey": primaryTextL10nKey,
    "displayBinding": displayBinding,
    "secondaryText": secondaryText,
    "weightTier": weightTier,
    "actionType": actionType,
    "actionTargetId": actionTargetId,
    "source": source,
    "intersectionId": intersectionId,
    "intersectionClass": intersectionClass,
    "avatarUrl": avatarUrl,
    "displayName": displayName,
    "confidenceLabel": confidenceLabel,
    "modelReasonBucket": modelReasonBucket,
    "freshAt": freshAt,
    "expiresAt": expiresAt,
    "intersectionPoints": intersectionPoints.map((value) => value.toWire()).toList(growable: false),
    "pointSummarySnapshotId": pointSummarySnapshotId,
    "actorEvidenceTotalCount": actorEvidenceTotalCount,
    "actorEvidenceCompleteness": actorEvidenceCompleteness,
    "actorEvidence": actorEvidence.map((value) => value.toWire()).toList(growable: false),
    "factPointCount": factPointCount,
    "recommendedPointCount": recommendedPointCount,
    "totalPointCount": totalPointCount,
    "dimensionPointSummary": dimensionPointSummary.map((value) => value.toWire()).toList(growable: false),
    "pointClassLabel": pointClassLabel,
    "connectionSummary": connectionSummary,
    "lastRecommendedAt": lastRecommendedAt,
    "seenAt": seenAt,
    "rankState": rankState,
    "primarySpans": primarySpans.map((value) => value.toWire()).toList(growable: false),
    "sampleVisuals": sampleVisuals.map((value) => value.toWire()).toList(growable: false),
    if (representativeActor != null) "representativeActor": representativeActor!.toWire(),
    "actionHints": actionHints.map((value) => value.toWire()).toList(growable: false),
    "lifecycleState": lifecycleState,
    "previousStrength": previousStrength,
    "strengthDelta": strengthDelta,
    "edgeWeight": edgeWeight,
    "iconKey": iconKey,
    "tone": tone,
    if (typeVisual != null) "typeVisual": typeVisual!.toWire(),
    if (objectVisual != null) "objectVisual": objectVisual!.toWire(),
    "timeBucket": timeBucket,
    "dedupeKey": dedupeKey,
    "anchorUserWeight": anchorUserWeight,
    "mutualCount": mutualCount,
    "moment": moment,
    "subjectId": subjectId,
    "subjectContext": subjectContext,
  };
}

final class IntersectionRepresentativeActor {
  const IntersectionRepresentativeActor({
    required this.actorId,
    required this.displayName,
    required this.avatarUrl,
    required this.relationLabel,
    required this.privacyState,
    this.target,
    required this.evidenceRank,
    required this.snapshotVersion,
  });

  final String actorId;
  final String displayName;
  final String avatarUrl;
  final String relationLabel;
  final String privacyState;
  final IntersectionTarget? target;
  final int evidenceRank;
  final String snapshotVersion;

  factory IntersectionRepresentativeActor.fromWire(Map<String, Object?> map, [String path = "IntersectionRepresentativeActor"]) {
    _rejectUnknownFields(map, const <String>{"actorId", "displayName", "avatarUrl", "relationLabel", "privacyState", "target", "evidenceRank", "snapshotVersion"}, path);
    return IntersectionRepresentativeActor(
      actorId: _requiredString(map["actorId"], '$path.actorId'),
      displayName: _requiredString(map["displayName"], '$path.displayName'),
      avatarUrl: _requiredString(map["avatarUrl"], '$path.avatarUrl'),
      relationLabel: _requiredString(map["relationLabel"], '$path.relationLabel'),
      privacyState: _requiredString(map["privacyState"], '$path.privacyState'),
      target: map["target"] == null ? null : IntersectionTarget.fromWire(_requiredObject(map["target"], '$path.target'), '$path.target'),
      evidenceRank: _requiredInt(map["evidenceRank"], '$path.evidenceRank'),
      snapshotVersion: _requiredString(map["snapshotVersion"], '$path.snapshotVersion'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "actorId": actorId,
    "displayName": displayName,
    "avatarUrl": avatarUrl,
    "relationLabel": relationLabel,
    "privacyState": privacyState,
    if (target != null) "target": target!.toWire(),
    "evidenceRank": evidenceRank,
    "snapshotVersion": snapshotVersion,
  };
}

final class IntersectionTarget {
  const IntersectionTarget({
    required this.objectType,
    required this.objectId,
    required this.objectKind,
    required this.routeId,
  });

  final String objectType;
  final String objectId;
  final String objectKind;
  final String routeId;

  factory IntersectionTarget.fromWire(Map<String, Object?> map, [String path = "IntersectionTarget"]) {
    _rejectUnknownFields(map, const <String>{"objectType", "objectId", "objectKind", "routeId"}, path);
    return IntersectionTarget(
      objectType: _requiredString(map["objectType"], '$path.objectType'),
      objectId: _requiredString(map["objectId"], '$path.objectId'),
      objectKind: _requiredString(map["objectKind"], '$path.objectKind'),
      routeId: _requiredString(map["routeId"], '$path.routeId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "objectType": objectType,
    "objectId": objectId,
    "objectKind": objectKind,
    "routeId": routeId,
  };
}

final class IntersectionTextSpan {
  const IntersectionTextSpan({
    required this.text,
    required this.role,
    this.target,
    this.visual,
  });

  final String text;
  final String role;
  final IntersectionTarget? target;
  final IntersectionVisual? visual;

  factory IntersectionTextSpan.fromWire(Map<String, Object?> map, [String path = "IntersectionTextSpan"]) {
    _rejectUnknownFields(map, const <String>{"text", "role", "target", "visual"}, path);
    return IntersectionTextSpan(
      text: _requiredString(map["text"], '$path.text'),
      role: _requiredString(map["role"], '$path.role'),
      target: map["target"] == null ? null : IntersectionTarget.fromWire(_requiredObject(map["target"], '$path.target'), '$path.target'),
      visual: map["visual"] == null ? null : IntersectionVisual.fromWire(_requiredObject(map["visual"], '$path.visual'), '$path.visual'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "text": text,
    "role": role,
    if (target != null) "target": target!.toWire(),
    if (visual != null) "visual": visual!.toWire(),
  };
}

final class IntersectionVisual {
  const IntersectionVisual({
    required this.assetKind,
    required this.imageUrl,
    required this.displayName,
    this.target,
  });

  final String assetKind;
  final String imageUrl;
  final String displayName;
  final IntersectionTarget? target;

  factory IntersectionVisual.fromWire(Map<String, Object?> map, [String path = "IntersectionVisual"]) {
    _rejectUnknownFields(map, const <String>{"assetKind", "imageUrl", "displayName", "target"}, path);
    return IntersectionVisual(
      assetKind: _requiredString(map["assetKind"], '$path.assetKind'),
      imageUrl: _requiredString(map["imageUrl"], '$path.imageUrl'),
      displayName: _requiredString(map["displayName"], '$path.displayName'),
      target: map["target"] == null ? null : IntersectionTarget.fromWire(_requiredObject(map["target"], '$path.target'), '$path.target'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "assetKind": assetKind,
    "imageUrl": imageUrl,
    "displayName": displayName,
    if (target != null) "target": target!.toWire(),
  };
}

Map<String, Object?> _requiredObject(Object? value, String path) {
  if (value is! Map<Object?, Object?>) {
    throw FormatException('$path must be an object');
  }
  final result = <String, Object?>{};
  for (final entry in value.entries) {
    final key = entry.key;
    if (key is! String) {
      throw FormatException('$path contains a non-string field name');
    }
    result[key] = entry.value;
  }
  return result;
}

void _rejectUnknownFields(
  Map<String, Object?> value,
  Set<String> allowed,
  String path,
) {
  final unknown = value.keys.where((key) => !allowed.contains(key)).toList()
    ..sort();
  if (unknown.isNotEmpty) {
    throw FormatException('$path contains unknown fields: ${unknown.join(', ')}');
  }
}

String _requiredString(Object? value, String path) {
  if (value is! String) throw FormatException('$path must be a string');
  return value;
}

int _requiredInt(Object? value, String path) {
  if (value is! int) throw FormatException('$path must be an int');
  return value;
}

double _requiredDouble(Object? value, String path) {
  if (value is! num) throw FormatException('$path must be a number');
  return value.toDouble();
}

bool _requiredBool(Object? value, String path) {
  if (value is! bool) throw FormatException('$path must be a bool');
  return value;
}

List<Object?> _requiredList(Object? value, String path) {
  if (value is! List<Object?>) {
    throw FormatException('$path must be a list');
  }
  return value;
}
