import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_kind_metadata.g.dart';

/// 交集句式合同工具。
///
/// 端侧不再合成任何交集文案：主句、称谓、维度标签、行动标签全部直出云侧字段。
/// 这里只保留「云侧下发的句子是否满足展示合同」的 fail-closed 复核，以及
/// span 与 target 的结构归一。

final RegExp _rawInteractionStatsPattern = RegExp(r'[0-9０-９]+\s*(赞|评|转|转发)');
final RegExp _countSubjectPattern = RegExp(r'[0-9０-９]+\s*(人|位)');

const String intersectionDisplayBindingExplicitLink = 'explicit_link';
const String intersectionDisplayBindingHostImplicit = 'host_implicit';
const String intersectionDisplayBindingHostPlain = 'host_plain';
const String intersectionDisplayBindingHidden = 'hidden';

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

/// Host display context is owned by the Recommendation projection. App callers
/// may validate the result but must not rewrite canonical wire objects.
IntersectionReason applyHostPlainDisplayContext(
  IntersectionReason reason,
  IntersectionTarget hostTarget,
) {
  return reason;
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
      // 归一后不会走到这里；真走到了也按「能渲染就渲染」处理，
      // 指向宿主对象的 span 已在上面被剔除。
      return true;
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
  if (_displayStatementNeedsRepresentative(reason, primary) &&
      !_hasMeaningfulRepresentativeActor(reason)) {
    return false;
  }
  return true;
}

/// 对象 target 是否可作为可点对象。
///
/// 只看结构（有 objectId），不再按 objectType 白名单放行。objectType 是**开放词汇**
/// （每个垂类主页一个值），云侧登记新垂类后端侧若还按闭集校验，整条 reason 会被静默
/// 丢弃——本该只是「少一个蓝字」的降级，变成内容消失。
bool _displayObjectTargetAllowed(IntersectionTarget? target) =>
    target != null && target.objectId.trim().isNotEmpty;

/// 归一 displayBinding；只有云侧**显式** hidden 才隐藏。
///
/// 未知取值按 explicit_link 处理：新增 binding 语义时端侧最多绑错链接样式，
/// 不会让整条交集在既有客户端上凭空消失。
String _normalizedDisplayBinding(String raw) {
  final binding = raw.trim();
  if (binding == intersectionDisplayBindingHidden) {
    return intersectionDisplayBindingHidden;
  }
  if (binding == intersectionDisplayBindingHostImplicit ||
      binding == intersectionDisplayBindingHostPlain) {
    return binding;
  }
  return intersectionDisplayBindingExplicitLink;
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

/// 代表人是否可被端侧当成「具名可点的人」。
///
/// 只看结构：有名字、有指向用户的可导航 target。称谓是否体面、名字是否匿名占位，
/// 由云侧按注册表判定后才下发——端侧再拿一份词表复核，就会在云侧改文案时
/// 把合法的句子静默丢掉。
bool _hasMeaningfulRepresentativeActor(IntersectionReason reason) {
  final actor = reason.representativeActor;
  if (actor == null || actor.displayName.trim().isEmpty) {
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
