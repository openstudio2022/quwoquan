import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_kind_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_representative_actor.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_target.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_kind_mapping.dart';

/// 交集句式合同工具。
///
/// 展示路径只做合同复核和 fail-closed；历史 spans 合成函数仅保留给 alpha
/// fixture 归一化入口使用，不再被可见 UI 用来补主句。

final RegExp _rawInteractionStatsPattern = RegExp(r'[0-9０-９]+\s*(赞|评|转|转发)');
final RegExp _countSubjectPattern = RegExp(r'[0-9０-９]+\s*(人|位)');

const String intersectionDisplayBindingExplicitLink = 'explicit_link';
const String intersectionDisplayBindingHostImplicit = 'host_implicit';
const String intersectionDisplayBindingHostPlain = 'host_plain';
const String intersectionDisplayBindingHidden = 'hidden';

const Set<String> _bannedDisplayStatementFragments = <String>{
  '共同好友',
  '都来这里互动过',
  '在这里互动过',
  '同读者',
  '相近主题',
  '这条记录',
  '这篇内容',
  '当前内容',
  'TA的内容',
  '相关圈子',
  '我的'
      '连接',
  '我的'
      '影响'
      '力',
  '你和这里',
  '你和这个圈子',
  '你们有共同',
  '为你推荐的相关内容',
  '最近在看这些',
};

/// 统一页面展示前，对交集句做一次“只读云侧主句”的收口。
///
/// 约束：
/// - 用户可见主句只认云侧 `primaryText`；
/// - 不再补 spans、不改写主句；
/// - 云侧未下发 `primaryText/primarySpans` 或合同不完整时，由
///   [displayReadyIntersectionReason] fail-closed。
IntersectionReason normalizeDisplayReason(
  IntersectionReason reason, {
  String kind = '',
  String contextObjectName = '',
  IntersectionTarget? contextObjectTarget,
}) {
  return reason;
}

/// 返回可展示的云侧交集句；不合格则返回 null。
IntersectionReason? displayReadyIntersectionReason(
  IntersectionReason reason, {
  IntersectionTarget? contextObjectTarget,
}) {
  return isDisplayableIntersectionReason(
        reason,
        contextObjectTarget: contextObjectTarget,
      )
      ? reason
      : null;
}

bool isDisplayableIntersectionReason(
  IntersectionReason reason, {
  IntersectionTarget? contextObjectTarget,
}) {
  final primary = reason.primaryText.trim();
  final binding = _normalizedDisplayBinding(reason.displayBinding);
  if (binding == intersectionDisplayBindingHidden) {
    return false;
  }
  if (!_displayStatementTextAllowed(reason, primary)) {
    return false;
  }
  final spans = reason.primarySpans;
  if (spans.isEmpty) {
    // primaryText 是云侧结论句真相源。结构化 spans 缺省时只降级为纯文本，
    // 不推断 target、不合成链接；hidden/banned/representative 规则仍已在上方执行。
    return true;
  }
  if (spans.map((span) => span.text).join() != primary) {
    return false;
  }
  final reasonTarget = _targetForReasonObject(reason);
  if (!_displayObjectTargetAllowed(reasonTarget)) {
    return false;
  }
  final isHostReason =
      contextObjectTarget != null &&
      _sameIntersectionTarget(contextObjectTarget, reasonTarget);
  var hasReasonObjectTarget = false;
  for (final span in spans) {
    final role = span.role.trim();
    final target = span.target;
    if (role == 'count' && target != null) {
      if (reason.actorEvidenceCompleteness.trim() != 'complete' ||
          target.routeId.trim() != 'myIntersections') {
        return false;
      }
    }
    if (role == 'object') {
      if (!_displayObjectTargetAllowed(target)) {
        return false;
      }
      if (contextObjectTarget != null &&
          _sameIntersectionTarget(target!, contextObjectTarget)) {
        return false;
      }
      if (_sameIntersectionTarget(target!, reasonTarget)) {
        hasReasonObjectTarget = true;
      }
    }
  }
  switch (binding) {
    case intersectionDisplayBindingExplicitLink:
      if (isHostReason) {
        return false;
      }
      return hasReasonObjectTarget;
    case intersectionDisplayBindingHostImplicit:
    case intersectionDisplayBindingHostPlain:
      return isHostReason && !hasReasonObjectTarget;
    default:
      return false;
  }
}

bool _displayStatementTextAllowed(IntersectionReason reason, String text) {
  final primary = text.trim();
  if (primary.isEmpty) {
    return false;
  }
  if (_rawInteractionStatsPattern.hasMatch(primary)) {
    return false;
  }
  for (final fragment in _bannedDisplayStatementFragments) {
    if (primary.contains(fragment)) {
      return false;
    }
  }
  if (_displayStatementNeedsRepresentative(reason, primary) &&
      !_hasMeaningfulRepresentativeActor(reason)) {
    return false;
  }
  return true;
}

bool _displayObjectTargetAllowed(IntersectionTarget? target) {
  if (target == null || target.objectId.trim().isEmpty) {
    return false;
  }
  switch (target.objectType.trim()) {
    case 'user':
    case 'circle':
    case 'homepage':
    case 'post':
    case 'task':
      return true;
    default:
      return false;
  }
}

String _normalizedDisplayBinding(String raw) {
  switch (raw.trim()) {
    case intersectionDisplayBindingHostImplicit:
      return intersectionDisplayBindingHostImplicit;
    case intersectionDisplayBindingHostPlain:
      return intersectionDisplayBindingHostPlain;
    case intersectionDisplayBindingHidden:
      return intersectionDisplayBindingHidden;
    case intersectionDisplayBindingExplicitLink:
    case '':
      return intersectionDisplayBindingExplicitLink;
    default:
      return intersectionDisplayBindingHidden;
  }
}

IntersectionTarget _targetForReasonObject(IntersectionReason reason) {
  final objectKind = reason.objectKind.trim();
  final routeId = intersectionRouteIdForObjectKind(objectKind);
  final objectId = reason.actionTargetId.trim().isNotEmpty
      ? reason.actionTargetId.trim()
      : reason.relationObjectId.trim();
  return IntersectionTarget(
    objectType: _objectTypeForTarget(objectKind: objectKind, routeId: routeId),
    objectId: objectId,
    objectKind: objectKind,
    routeId: routeId,
  );
}

bool _sameIntersectionTarget(
  IntersectionTarget? left,
  IntersectionTarget? right,
) {
  if (left == null || right == null) {
    return false;
  }
  final leftId = left.objectId.trim();
  final rightId = right.objectId.trim();
  if (leftId.isEmpty || rightId.isEmpty || leftId != rightId) {
    return false;
  }
  final leftType = left.objectType.trim();
  final rightType = right.objectType.trim();
  if (leftType.isNotEmpty && rightType.isNotEmpty && leftType != rightType) {
    return false;
  }
  return true;
}

bool _displayStatementNeedsRepresentative(
  IntersectionReason reason,
  String text,
) {
  if (reason.actorEvidenceTotalCount > 1 || reason.actorEvidence.length > 1) {
    return true;
  }
  return text.contains('等') || _countSubjectPattern.hasMatch(text);
}

bool _hasMeaningfulRepresentativeActor(IntersectionReason reason) {
  final actor = reason.representativeActor;
  if (actor == null) {
    return false;
  }
  final name = actor.displayName.trim();
  if (name.isEmpty || name.startsWith('一位') || name == '用户') {
    return false;
  }
  if (!_isMeaningfulRelationLabel(actor.relationLabel)) {
    return false;
  }
  final target = actor.target;
  return target != null &&
      target.objectType.trim() == 'user' &&
      target.objectId.trim().isNotEmpty;
}

/// 交集 kind/sourceRef 的展示级解析顺序：
/// `reason.kind` -> `reason.source`（仅非维度名）-> `intersectionPoints.sourceRef`。
/// 仅用于图标/高亮/埋点 fallback，用户可见主句仍以云侧 `primaryText` 为准。
String resolvedIntersectionReasonKind(IntersectionReason reason) =>
    _resolvedReasonKind(reason);

/// 按 kind 闭集模板生成「代表人在数字前」结构化富文本（G2 模拟，端不在 UI 拼装）。
///
/// 句式真相：与既有 fixture primaryText 同形（评审一致），但把代表人 / 数字 / 对象切成
/// 可点 span。数字前可点代表人（纯文本蓝字）仅当 fixture/云侧给出与对象不同的可见 person。
List<IntersectionTextSpan> buildInboxStatementSpans(
  IntersectionReason reason,
  String kind,
) {
  return buildDisplayStatementSpans(reason, kind);
}

/// 面向内容 post / 视频书 / 四主页的统一主句模板。
///
/// 设计目标：
/// - 主语尽量回答“这些人和我是什么关系”；
/// - 谓语尽量回答“他们具体做了什么”；
/// - 宾语尽量落到可点击对象；若对象仍是“这里/这些主题/相同内容”等泛词，则宁可不重写。
List<IntersectionTextSpan> buildDisplayStatementSpans(
  IntersectionReason reason,
  String kind, {
  String contextObjectName = '',
  IntersectionTarget? contextObjectTarget,
}) {
  final resolvedKind = kind.trim().isNotEmpty
      ? kind.trim()
      : _resolvedReasonKind(reason);
  final n = _displayCount(reason);
  final dimension = reason.dimension.trim();
  final relationLabel = _normalizedRelationLabel(reason, resolvedKind);
  final repActor = _visibleRepresentativeActor(reason);
  final subject = _subjectSpans(
    repActor: repActor,
    relationLabel: relationLabel,
    count: n,
    dimension: dimension,
  );
  final object = _resolvedDisplayObject(
    reason,
    resolvedKind,
    contextObjectName: contextObjectName,
    contextObjectTarget: contextObjectTarget,
  );
  final actionPhrase = _resolvedActionPhrase(reason, resolvedKind);
  if (object != null &&
      subject.isNotEmpty &&
      contextObjectTarget != null &&
      actionPhrase.isNotEmpty) {
    return <IntersectionTextSpan>[...subject, _plain(actionPhrase), object];
  }

  switch (resolvedKind) {
    case 'sharedFollowees':
      if (object == null || subject.isEmpty) {
        return const <IntersectionTextSpan>[];
      }
      return <IntersectionTextSpan>[...subject, _plain('也关注了'), object];
    case 'followeeInObject':
      if (object == null || subject.isEmpty) {
        return const <IntersectionTextSpan>[];
      }
      return <IntersectionTextSpan>[...subject, _plain('在'), object];
    case 'followeeVisited':
      if (object == null || subject.isEmpty) {
        return const <IntersectionTextSpan>[];
      }
      return <IntersectionTextSpan>[...subject, _plain('来过'), object];
    case 'followeeViewing':
      if (object == null || subject.isEmpty) {
        return const <IntersectionTextSpan>[];
      }
      return <IntersectionTextSpan>[...subject, _plain('正在看'), object];
    case 'followeeDiscussedThis':
      if (object == null || subject.isEmpty) {
        return const <IntersectionTextSpan>[];
      }
      return <IntersectionTextSpan>[...subject, _plain('正在讨论'), object];
    case 'sharedCircle':
    case 'coMemberCircle':
      if (object == null || subject.isEmpty) {
        return const <IntersectionTextSpan>[];
      }
      return <IntersectionTextSpan>[...subject, _plain('都加入了'), object];
    case 'sharedEntityAttention':
      if (object == null || subject.isEmpty) {
        return const <IntersectionTextSpan>[];
      }
      return <IntersectionTextSpan>[...subject, _plain('也关注了'), object];
    case 'coVisitedEntity':
      if (object == null || subject.isEmpty) {
        return const <IntersectionTextSpan>[];
      }
      return <IntersectionTextSpan>[...subject, _plain('都去过'), object];
    case 'coWishlistedEntity':
      if (object == null || subject.isEmpty) {
        return const <IntersectionTextSpan>[];
      }
      return <IntersectionTextSpan>[...subject, _plain('都想去'), object];
    case 'coLiked':
    case 'coCommented':
    case 'sharedDiscussion':
    case 'coSharedContent':
    case 'coCreatedContent':
      if (object == null || subject.isEmpty || actionPhrase.isEmpty) {
        return const <IntersectionTextSpan>[];
      }
      return <IntersectionTextSpan>[...subject, _plain(actionPhrase), object];
    case 'sameSchool':
    case 'sameDepartment':
    case 'sameMajor':
    case 'sameCohort':
    case 'alumni':
    case 'alumniHere':
      if (object == null || subject.isEmpty) {
        return const <IntersectionTextSpan>[];
      }
      return <IntersectionTextSpan>[...subject, _plain('都来自'), object];
    case 'sameCompany':
    case 'sameTeam':
      if (object == null || subject.isEmpty) {
        return const <IntersectionTextSpan>[];
      }
      return <IntersectionTextSpan>[...subject, _plain('都在'), object];
    case 'sameIndustry':
      if (object == null || subject.isEmpty) {
        return const <IntersectionTextSpan>[];
      }
      return <IntersectionTextSpan>[...subject, _plain('都做过'), object];
    case 'commonFollower':
      if (object == null) return const <IntersectionTextSpan>[];
      return _objectThenCount(
        object,
        object.text,
        n,
        dimension,
        mid: '有',
        tail: '位共同关注者',
      );
    case 'commonContact':
      if (object == null) return const <IntersectionTextSpan>[];
      return _objectThenCount(
        object,
        object.text,
        n,
        dimension,
        mid: '有',
        tail: '位共同联系人',
      );
    case 'sharedTagSample':
      if (object == null || subject.isEmpty) {
        return const <IntersectionTextSpan>[];
      }
      return <IntersectionTextSpan>[...subject, _plain('都关注'), object];
    case 'affinity':
      if (object == null) return const <IntersectionTextSpan>[];
      return <IntersectionTextSpan>[_plain('推荐认识：'), object, _plain('和你兴趣相近')];
    default:
      if (reason.primarySpans.isNotEmpty) {
        return reason.primarySpans;
      }
      return const <IntersectionTextSpan>[];
  }
}

int _displayCount(IntersectionReason reason) {
  if (reason.actorEvidenceTotalCount > 0) {
    return reason.actorEvidenceTotalCount;
  }
  final mutual = intersectionMutualCountOf(reason);
  if (mutual > 0) {
    return mutual;
  }
  if (reason.actorEvidence.isNotEmpty) {
    return reason.actorEvidence.length;
  }
  return mutual;
}

String _resolvedReasonKind(IntersectionReason reason) {
  final candidates = <String>[
    reason.kind.trim(),
    reason.source.trim(),
    for (final point in reason.intersectionPoints) point.sourceRef.trim(),
  ];
  for (final candidate in candidates) {
    if (candidate.isEmpty) continue;
    if (IntersectionKindMetadata.of(candidate) != null) {
      return candidate;
    }
  }
  for (final candidate in candidates) {
    if (candidate.isEmpty) continue;
    if (candidate != reason.dimension.trim()) {
      return candidate;
    }
  }
  return '';
}

IntersectionTarget? _contentContextTarget(
  String name,
  IntersectionTarget? target,
) {
  if (name.trim().isEmpty || target == null || target.objectId.trim().isEmpty) {
    return null;
  }
  return target;
}

IntersectionTextSpan? _resolvedDisplayObject(
  IntersectionReason reason,
  String kind, {
  String contextObjectName = '',
  IntersectionTarget? contextObjectTarget,
}) {
  final contextTarget = _contentContextTarget(
    contextObjectName,
    contextObjectTarget,
  );
  if (_prefersContextObject(kind, reason) && contextTarget != null) {
    return _objectSpanFromTarget(contextObjectName, contextTarget);
  }

  final name = _concreteObjectName(reason.displayName);
  final objectKind = reason.objectKind.trim().isNotEmpty
      ? reason.objectKind.trim()
      : (IntersectionKindMetadata.of(kind)?.objectKind ?? '');
  final objectId = reason.actionTargetId.trim();
  final objectSpan = _objectSpanOf(name, objectId, objectKind);
  if (objectSpan.role != 'plain' || objectSpan.text.trim().isNotEmpty) {
    return objectSpan.text.trim().isEmpty ? null : objectSpan;
  }

  if (contextTarget != null &&
      (_prefersContextObject(kind, reason) ||
          _interactionActionParts(reason).isNotEmpty)) {
    return _objectSpanFromTarget(contextObjectName, contextTarget);
  }
  return null;
}

bool _prefersContextObject(String kind, IntersectionReason reason) {
  const contentKinds = <String>{
    'coLiked',
    'coCommented',
    'sharedDiscussion',
    'coSharedContent',
    'coCreatedContent',
    'followeeViewing',
    'followeeDiscussedThis',
  };
  if (!contentKinds.contains(kind)) {
    return false;
  }
  final objectKind = reason.objectKind.trim();
  if (objectKind == 'content') {
    return true;
  }
  final name = _concreteObjectName(reason.displayName);
  return name.isEmpty || objectKind == 'person' || objectKind == 'tag';
}

String _concreteObjectName(String raw) {
  final name = raw.trim();
  if (name.isEmpty) return '';
  switch (name) {
    case '同游':
    case '同好':
    case '同校':
    case '这里':
    case '这个对象':
    case '这些内容':
    case '这些主题':
    case '相同内容':
    case '相同的人':
      return '';
    default:
      return name;
  }
}

String _resolvedActionPhrase(IntersectionReason reason, String kind) {
  final parts = _interactionActionParts(reason);
  if (parts.isNotEmpty) {
    if (parts.length == 1) return parts.first;
    if (parts.length == 2) return '${parts[0]}和${parts[1]}';
    return '${parts[0]}、${parts[1]}并${parts[2]}';
  }
  switch (kind) {
    case 'coLiked':
      return '都赞过';
    case 'coCommented':
      return '都评论过';
    case 'sharedDiscussion':
      return '都讨论过';
    case 'coSharedContent':
      return '都转发过';
    case 'coCreatedContent':
      return '都共创过';
    default:
      return '';
  }
}

List<String> _interactionActionParts(IntersectionReason reason) {
  if (reason.actorEvidence.isEmpty) {
    return const <String>[];
  }
  var hasLike = false;
  var hasComment = false;
  var hasShare = false;
  for (final actor in reason.actorEvidence) {
    hasLike =
        hasLike || actor.likeCount > 0 || actor.actionSummaryText.contains('赞');
    hasComment =
        hasComment ||
        actor.commentCount > 0 ||
        actor.actionSummaryText.contains('评') ||
        actor.actionSummaryText.contains('讨论');
    hasShare =
        hasShare ||
        actor.shareCount > 0 ||
        actor.actionSummaryText.contains('转发') ||
        actor.actionSummaryText.contains('分享');
  }
  final parts = <String>[];
  if (hasLike) parts.add('赞过');
  if (hasComment) parts.add('评论过');
  if (hasShare) parts.add('转发过');
  return parts;
}

IntersectionTextSpan _objectSpanFromTarget(
  String objectName,
  IntersectionTarget target,
) {
  final normalizedName = objectName.trim();
  if (normalizedName.isEmpty) return _plain('');
  return IntersectionTextSpan(
    text: _formatObjectName(normalizedName, target.objectKind),
    role: 'object',
    target: target,
  );
}

String _formatObjectName(String name, String objectKind) {
  final trimmed = name.trim();
  if (trimmed.isEmpty) return '';
  if (objectKind == 'content' &&
      !trimmed.startsWith('《') &&
      !trimmed.endsWith('》')) {
    return '《$trimmed》';
  }
  return trimmed;
}

IntersectionRepresentativeActor? _visibleRepresentativeActor(
  IntersectionReason reason,
) {
  final actor = reason.representativeActor;
  if (actor != null) {
    final visible =
        actor.privacyState.trim().isEmpty ||
        actor.privacyState.trim() == 'visible';
    if (visible && actor.displayName.trim().isNotEmpty) {
      return actor;
    }
  }
  for (final evidence in reason.actorEvidence) {
    final visible =
        evidence.privacyState.trim().isEmpty ||
        evidence.privacyState.trim() == 'visible';
    if (!visible || evidence.displayName.trim().isEmpty) {
      continue;
    }
    return IntersectionRepresentativeActor(
      actorId: evidence.actorId,
      displayName: evidence.displayName,
      avatarUrl: evidence.avatarUrl,
      relationLabel: evidence.relationLabel,
      privacyState: evidence.privacyState,
      target: evidence.target,
      evidenceRank: evidence.evidenceRank,
      snapshotVersion: evidence.snapshotVersion,
    );
  }
  return null;
}

List<IntersectionTextSpan> _subjectSpans({
  required IntersectionRepresentativeActor? repActor,
  required String relationLabel,
  required int count,
  required String dimension,
}) {
  final repName = repActor?.displayName.trim() ?? '';
  final repId = repActor?.actorId.trim() ?? '';
  final repTarget = repActor?.target;
  final normalizedRelation = relationLabel.trim();
  final needsViewerPrefix = normalizedRelation.isEmpty;
  if (repName.isEmpty) {
    if (count <= 0) return const <IntersectionTextSpan>[];
    final unit = normalizedRelation.isEmpty ? '人' : '位$normalizedRelation';
    return <IntersectionTextSpan>[
      if (needsViewerPrefix) _plain('你和'),
      _countSpan(count, dimension),
      _plain(unit),
    ];
  }
  final spans = <IntersectionTextSpan>[];
  if (needsViewerPrefix) {
    spans.add(_plain('你和'));
  }
  if (!_isAnonymousRepresentative(repName) && normalizedRelation.isNotEmpty) {
    spans.add(_plain(normalizedRelation));
  }
  if (repTarget != null && repTarget.objectId.trim().isNotEmpty) {
    spans.add(
      IntersectionTextSpan(text: repName, role: 'object', target: repTarget),
    );
  } else {
    spans.add(_personSpan(repName, repId));
  }
  if (count > 1) {
    spans
      ..add(_plain('等'))
      ..add(_countSpan(count, dimension))
      ..add(_plain('人'));
  }
  return spans;
}

bool _isAnonymousRepresentative(String name) => name.trim().startsWith('一位');

String _normalizedRelationLabel(IntersectionReason reason, String kind) {
  final candidates = <String>[
    reason.representativeActor?.relationLabel.trim() ?? '',
    for (final actor in reason.actorEvidence) actor.relationLabel.trim(),
    _fallbackRelationLabel(kind),
  ];
  for (final candidate in candidates) {
    if (_isMeaningfulRelationLabel(candidate)) {
      return candidate;
    }
  }
  return _fallbackRelationLabel(kind);
}

bool _isMeaningfulRelationLabel(String raw) {
  final label = raw.trim();
  if (label.isEmpty) return false;
  const forbidden = <String>{
    '共同点赞',
    '共同讨论',
    '共同传播',
    '共同关注',
    '都关注此标签',
    '同行足迹',
    '同好',
  };
  return !forbidden.contains(label);
}

String _fallbackRelationLabel(String kind) {
  switch (kind) {
    case 'commonContact':
      return '联系人';
    case 'sharedFollowees':
    case 'followeeInObject':
    case 'followeeVisited':
    case 'followeeViewing':
    case 'followeeDiscussedThis':
      return '你关注的人';
    case 'sameSchool':
    case 'sameDepartment':
    case 'sameMajor':
    case 'sameCohort':
    case 'alumni':
    case 'alumniHere':
      return '校友';
    case 'sameCompany':
    case 'sameTeam':
    case 'colleagueHere':
      return '同事';
    case 'sameIndustry':
      return '同行';
    case 'sharedCircle':
    case 'coMemberCircle':
      return '同圈成员';
    case 'coVisitedEntity':
    case 'coWishlistedEntity':
      return '同游伙伴';
    default:
      return '';
  }
}

/// 对象在前式：`你和[object][mid][N][tail]`（对象本身是人、数字落在末尾）。
List<IntersectionTextSpan> _objectThenCount(
  IntersectionTextSpan objectSpan,
  String objectName,
  int n,
  String dimension, {
  required String mid,
  required String tail,
}) {
  if (objectName.isEmpty) return const <IntersectionTextSpan>[];
  return <IntersectionTextSpan>[
    _plain('你和'),
    objectSpan,
    _plain(mid),
    _countSpan(n, dimension),
    _plain(tail),
  ];
}

IntersectionTextSpan _personSpan(String name, String id) {
  if (id.isEmpty) return _plain(name);
  return IntersectionTextSpan(
    text: name,
    role: 'object',
    target: IntersectionTarget(
      objectType: 'user',
      objectId: id,
      objectKind: 'person',
      routeId: 'userProfile',
    ),
  );
}

IntersectionTextSpan _objectSpanOf(String name, String id, String objectKind) {
  final normalizedName = _formatObjectName(name, objectKind);
  final routeId = intersectionRouteIdForObjectKind(objectKind);
  // 无 id 或无可导航 route（如 tag/content）时渲染纯文本，避免不可点的死蓝字。
  if (normalizedName.isEmpty) {
    return IntersectionTextSpan(text: '', role: 'plain');
  }
  if (id.isEmpty || routeId.isEmpty) return _plain(normalizedName);
  return IntersectionTextSpan(
    text: normalizedName,
    role: 'object',
    target: IntersectionTarget(
      objectType: _objectTypeForTarget(
        objectKind: objectKind,
        routeId: routeId,
      ),
      objectId: id,
      objectKind: objectKind,
      routeId: routeId,
    ),
  );
}

IntersectionTextSpan _countSpan(int n, String dimension) {
  return IntersectionTextSpan(
    text: '$n',
    role: 'count',
    target: IntersectionTarget(
      objectType: 'dimension',
      objectId: dimension,
      routeId: 'myIntersections',
    ),
  );
}

String _objectTypeForTarget({
  required String objectKind,
  required String routeId,
}) {
  switch (routeId.trim()) {
    case 'userProfile':
      return 'user';
    case 'circleDetail':
      return 'circle';
    case 'homepageDetail':
      return 'homepage';
    case 'workBrowser':
    case 'postDetail':
    case 'contentDetail':
      return 'post';
    case 'myIntersections':
      return 'dimension';
  }
  switch (objectKind.trim()) {
    case 'person':
      return 'user';
    case 'circle':
      return 'circle';
    case 'school':
    case 'place':
    case 'enterprise':
    case 'route':
    case 'photo_spot':
    case 'gear':
      return 'homepage';
    case 'content':
      return 'post';
    case 'tag':
      return 'tag';
    default:
      return '';
  }
}

IntersectionTextSpan _plain(String text) =>
    IntersectionTextSpan(text: text, role: 'plain');
