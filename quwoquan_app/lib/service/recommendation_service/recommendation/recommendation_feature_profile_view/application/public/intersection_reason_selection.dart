import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/domain/intersection_action_keys.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/domain/intersection_statement_synthesizer.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 内容与对象展示面共用的渐进式交集解析结果：首屏只消费 [reason]，用户主动
/// 展开证据后才消费 [primaryHint]。两者来自同一 canonical reason。
final class IntersectionDisplayResolution {
  const IntersectionDisplayResolution({required this.reason, this.primaryHint});

  final IntersectionReason reason;
  final IntersectionActionHint? primaryHint;
}

IntersectionDisplayResolution? resolveIntersectionDisplay(
  List<IntersectionReason>? reasons, {
  IntersectionTarget? contextObjectTarget,
  DateTime? now,
}) {
  if (reasons == null || reasons.isEmpty) return null;
  for (final candidate in reasons) {
    final reason = displayReadyIntersectionReason(
      candidate,
      contextObjectTarget: contextObjectTarget,
    );
    if (reason == null || _isExpired(reason, now: now)) {
      continue;
    }
    return IntersectionDisplayResolution(
      reason: reason,
      primaryHint: primaryDisplayableIntersectionActionHint(
        reason.actionHints,
        contextObjectTarget: contextObjectTarget,
        evidenceReason: reason,
      ),
    );
  }
  return null;
}

/// 返回最强可展示证据组的稳定 kind，供跨页面高亮意图复用。
String? primaryIntersectionReasonKind(
  List<IntersectionReason>? reasons, {
  IntersectionTarget? contextObjectTarget,
}) {
  final reason = resolveIntersectionDisplay(
    reasons,
    contextObjectTarget: contextObjectTarget,
  )?.reason;
  if (reason == null) return null;
  final kind = resolvedIntersectionReasonKind(reason).trim();
  return kind.isEmpty ? null : kind;
}

bool isDeferredIntersectionActionHint(IntersectionActionHint hint) {
  IntersectionActionKey key;
  try {
    key = IntersectionActionKey.fromWire(hint.actionKey.trim(), 'actionKey');
  } on FormatException {
    return false;
  }
  return intersectionActionPolicyFor(key)?.tier == IntersectionActionTier.heavy;
}

/// 漏斗归因用的 sourceRef 只有这一份口径（首页卡 / 沉浸页 / 收件箱同用）：
/// 优先取锚点证据组的 sourceRef，其次是云侧回填的 kind，最后才是 reason.source。
String sourceRefForReason(IntersectionReason reason) {
  for (final point in reason.intersectionPoints) {
    final sourceRef = point.sourceRef.trim();
    if (sourceRef.isNotEmpty) return sourceRef;
  }
  final resolved = resolvedIntersectionReasonKind(reason).trim();
  return resolved.isNotEmpty ? resolved : reason.source.trim();
}

/// 人对象判定只有这一份：message 分发的 target 校验与约伴受邀者派生都消费它。
/// 只消费 canonical 身份（objectKind / wire objectType），不从 routeId 形态反推。
bool isPersonIntersectionTarget(IntersectionTarget target) {
  return target.objectKind.trim() == 'person' ||
      target.objectType.trim() == 'user';
}

/// assistant 分发在 navigator 侧要求 reason 的 intersectionId / evidenceId / kind 与
/// 上下文对象的 objectType / objectId 全部非空；展示门与之同源，避免「可展示但分发
/// missingTarget」。无页面宿主的触点（收件箱）以 reason 自身对象作上下文，与其
/// 传给 navigator 的 contextObjectTarget 一致。
bool _assistantDispatchable(
  IntersectionReason? evidenceReason,
  IntersectionTarget? contextObjectTarget,
) {
  if (evidenceReason == null) return false;
  final context = contextObjectTarget ?? targetForReasonObject(evidenceReason);
  return evidenceReason.intersectionId.trim().isNotEmpty &&
      evidenceReason.pointSummarySnapshotId.trim().isNotEmpty &&
      evidenceReason.kind.trim().isNotEmpty &&
      context.objectType.trim().isNotEmpty &&
      context.objectId.trim().isNotEmpty;
}

bool isDisplayableIntersectionActionHint(
  IntersectionActionHint hint, {
  IntersectionTarget? contextObjectTarget,
  IntersectionReason? evidenceReason,
}) {
  if (hint.label.trim().isEmpty) return false;
  IntersectionActionKey key;
  try {
    key = IntersectionActionKey.fromWire(hint.actionKey.trim(), 'actionKey');
  } on FormatException {
    return false;
  }
  final policy = intersectionActionPolicyFor(key);
  if (policy == null || policy.dispatch.wireName != hint.dispatch.trim()) {
    return false;
  }
  final target = hint.target;
  if (target != null && !_hasCanonicalTargetIdentity(target)) return false;
  switch (policy.dispatch) {
    case IntersectionActionDispatch.assistant:
      return _assistantDispatchable(evidenceReason, contextObjectTarget);
    case IntersectionActionDispatch.navigate:
      if (target == null || target.objectId.trim().isEmpty) return false;
      if (!_targetRouteMatchesRegistry(target)) return false;
      if (key == IntersectionActionKey.openContent &&
          _sameTarget(target, contextObjectTarget)) {
        return false;
      }
      return true;
    case IntersectionActionDispatch.gathering:
      return target != null &&
          target.objectId.trim().isNotEmpty &&
          _targetRouteMatchesRegistry(target);
    case IntersectionActionDispatch.message:
      if (target == null || target.objectId.trim().isEmpty) return false;
      return isPersonIntersectionTarget(target) &&
          _targetRouteMatchesRegistry(target);
  }
}

/// target 身份合法 = objectKind 在闭集内，且 objectType 正是该 kind 登记的 canonical wire
/// objectType（kind → objectType 是单射；反向 objectTypeBindings 是多对一，school /
/// enterprise / route 等都收口到 `homepage`，用它反查判等会把合法 target 全部误拒）。
bool _hasCanonicalTargetIdentity(IntersectionTarget target) {
  final kindWire = target.objectKind.trim();
  final typeWire = target.objectType.trim();
  if (kindWire.isEmpty || typeWire.isEmpty) return false;
  IntersectionObjectKind kind;
  try {
    kind = IntersectionObjectKind.fromWire(kindWire, 'objectKind');
  } on FormatException {
    return false;
  }
  return canonicalIntersectionWireObjectTypeForObjectKind(kind) == typeWire;
}

bool _targetRouteMatchesRegistry(IntersectionTarget target) {
  IntersectionObjectKind kind;
  try {
    kind = IntersectionObjectKind.fromWire(
      target.objectKind.trim(),
      'objectKind',
    );
  } on FormatException {
    return false;
  }
  final canonicalRoute = canonicalIntersectionRouteIdForObjectKind(kind).trim();
  final route = target.routeId.trim();
  return canonicalRoute.isNotEmpty &&
      route.isNotEmpty &&
      route == canonicalRoute;
}

/// 从已通过 display-contract 的 actionHints 里选出唯一可执行主动作。
/// 全端只有这一份 fold；展示面（内容卡、沉浸页、对象页行、收件箱）一律经此处或
/// `resolveIntersectionDisplay` 取主行动，不得各自再写第二份。
IntersectionActionHint? primaryDisplayableIntersectionActionHint(
  List<IntersectionActionHint> hints, {
  IntersectionTarget? contextObjectTarget,
  IntersectionReason? evidenceReason,
}) {
  return hints
      .where(
        (hint) => isDisplayableIntersectionActionHint(
          hint,
          contextObjectTarget: contextObjectTarget,
          evidenceReason: evidenceReason,
        ),
      )
      .fold<IntersectionActionHint?>(
        null,
        (best, hint) =>
            best == null ||
                (hint.isPrimary && !best.isPrimary) ||
                (hint.isPrimary == best.isPrimary &&
                    hint.priority < best.priority)
            ? hint
            : best,
      );
}

bool _isExpired(IntersectionReason reason, {DateTime? now}) {
  final raw = reason.expiresAt.trim();
  if (raw.isEmpty) return false;
  final expiresAt = DateTime.tryParse(raw);
  return expiresAt == null ||
      !expiresAt.toUtc().isAfter((now ?? DateTime.now()).toUtc());
}

bool _sameTarget(IntersectionTarget? left, IntersectionTarget? right) {
  if (left == null || right == null) return false;
  final leftId = left.objectId.trim();
  final rightId = right.objectId.trim();
  if (leftId.isEmpty || leftId != rightId) return false;
  final leftRoute = left.routeId.trim();
  final rightRoute = right.routeId.trim();
  return leftRoute.isEmpty || rightRoute.isEmpty || leftRoute == rightRoute;
}
