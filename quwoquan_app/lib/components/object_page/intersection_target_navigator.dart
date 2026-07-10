import 'package:flutter/widgets.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_action_hint.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_kind_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_target.g.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/core/models/start_group_chat_route_extra.dart';

const bool _defaultIntersectionCommerceActionsEnabled = bool.fromEnvironment(
  'INTERSECTION_COMMERCE_ACTIONS_ENABLED',
);

/// 交集导航归因（埋点上下文），由展示面在构造导航器时透传。
///
/// 不承载任何人类可读结论句，只携带可观测/归因标识，供 [IntersectionTargetNavigator.open]
/// 在跳转时上报（contentBehaviorTracker.trackClick）。
class IntersectionNavAttribution {
  const IntersectionNavAttribution({
    this.intersectionId = '',
    this.dimension = '',
    this.intersectionClass = '',
    this.sourceRef = '',
    this.tagRefs = const <String>[],
    this.evidenceId = '',
  });

  final String intersectionId;
  final String dimension;
  final String intersectionClass;
  final String sourceRef;
  final List<String> tagRefs;
  final String evidenceId;
}

/// 导航埋点回调：把命中的 [IntersectionTarget] 与归因透传给展示面（通常接 tracker）。
typedef IntersectionNavTrack =
    void Function(
      IntersectionTarget target,
      IntersectionNavAttribution attribution,
    );

enum IntersectionActionDispatchStatus {
  opened,
  deferred,
  unsupported,
  missingTarget,
  missingRouter,
  featureDisabled,
}

class IntersectionActionDispatchResult {
  const IntersectionActionDispatchResult(this.status);

  final IntersectionActionDispatchStatus status;

  bool get didOpen => status == IntersectionActionDispatchStatus.opened;
}

/// 统一交集导航器（统一交互子契约 · A–E 横切复用，Phase 0 §20.7）。
///
/// 把云侧 [IntersectionTarget]（objectType + objectId + objectKind + routeId）映射为
/// codegen 路由
/// （[AppRoutePaths]）跳转，端侧不硬编码 path。`routeId` 为云侧「路由逻辑名」闭集
/// （userProfile / circleDetail / homepageDetail / workBrowser / myIntersections），缺省 / 未知时
/// 由 objectKind 经 codegen [intersectionRouteIdForObjectKind]（registry.objectKinds.routeId）
/// 反查；objectKind 不可导航（content/tag/未知）时视为不可点击（返回 null）。
///
/// 不可解析（target 缺省 / objectId 空 / 不可导航 objectKind）时静默不跳转（优雅降级，
/// 不抛错、不崩溃）。埋点经构造时注入的 [onTrack] 透传，导航器本身不依赖 Riverpod，
/// 便于 A–E 复用与组件测试。
class IntersectionTargetNavigator {
  const IntersectionTargetNavigator({
    this.onTrack,
    this.commerceActionsEnabled = _defaultIntersectionCommerceActionsEnabled,
  });

  final IntersectionNavTrack? onTrack;
  final bool commerceActionsEnabled;

  /// 把对象页交集行 [IntersectionReason] 归一为统一导航 [IntersectionTarget]。
  ///
  /// objectKind 一等字段为真相源（旧 relationKind 对象类型桥接已删除，§23 去桥接）；
  /// 交由 [resolvePath] / [open] 经 codegen objectKind→routeId 统一映射。A–E 各展示位
  /// 共用此方法，端不再各自手写 `switch(kind) → context.push(...)` 复制导航逻辑。
  ///
  /// `actionTargetId` 为空时返回空 objectId 的 target，[resolvePath] 据此判定不可路由（优雅降级）。
  static IntersectionTarget targetForReason(IntersectionReason reason) {
    final objectKind = reason.objectKind.trim();
    final routeId = intersectionRouteIdForObjectKind(objectKind);
    return IntersectionTarget(
      objectType: _objectTypeForTarget(
        objectKind: objectKind,
        routeId: routeId,
      ),
      objectId: reason.actionTargetId.trim(),
      objectKind: objectKind,
      routeId: routeId,
    );
  }

  /// 解析 [target] → codegen 路由 path；不可路由返回 null。
  ///
  /// [sourceRef] 仅在下钻「我的交集」维度列表（routeId == myIntersections）时附加证据组过滤。
  static String? resolvePath(
    IntersectionTarget? target, {
    String sourceRef = '',
    String? sourceTheme,
  }) {
    if (target == null) {
      return null;
    }
    final id = target.objectId.trim();
    if (id.isEmpty) {
      return null;
    }
    final ref = sourceRef.trim();
    // routeId 真相源：target.routeId（云侧下发）优先；缺省时由 objectKind 经 codegen
    // 反查（registry.objectKinds.routeId），端不再硬编码 objectKind 闭集与 routeId 兜底 switch。
    var route = target.routeId.trim();
    if (route.isEmpty) {
      route = intersectionRouteIdForObjectKind(target.objectKind.trim());
    }
    switch (route) {
      case 'userProfile':
        return AppRoutePaths.userProfile(username: id);
      case 'circleDetail':
        return AppRoutePaths.circleDetail(id: id, sourceTheme: sourceTheme);
      case 'homepageDetail':
        return AppRoutePaths.homepageDetail(id: id, sourceTheme: sourceTheme);
      case 'workBrowser':
      case 'postDetail':
      case 'contentDetail':
        return AppRoutePaths.workBrowser(workId: id, sourceTheme: sourceTheme);
      case 'myIntersections':
        return AppRoutePaths.myIntersections(
          dimension: id,
          sourceRef: ref.isEmpty ? null : ref,
        );
      default:
        return null;
    }
  }

  static String _objectTypeForTarget({
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

  /// [target] 是否可点击跳转（用于 UI 决定是否赋予点击态）。
  bool canNavigate(IntersectionTarget? target, {String sourceRef = ''}) =>
      resolvePath(target, sourceRef: sourceRef) != null;

  /// 跳转到 [target] 对应对象页 / 维度列表页；不可路由时静默返回 false（不导航、不上报）。
  bool open(
    BuildContext context,
    IntersectionTarget? target, {
    String sourceRef = '',
    IntersectionNavAttribution? attribution,
  }) {
    final path = resolvePath(
      target,
      sourceRef: sourceRef,
      sourceTheme: uiErrorAppearanceRouteValueFor(context),
    );
    if (path == null || target == null) {
      return false;
    }
    final router = GoRouter.maybeOf(context);
    if (router == null) {
      return false;
    }
    if (attribution != null) {
      onTrack?.call(target, attribution);
    }
    router.push(path);
    return true;
  }

  /// 按云侧 actionHint 的 M0.7 `dispatch` 分发行动。
  ///
  /// 本方法只消费 codegen/DTO 字段，不维护第二套 actionKey 分类，也不在本通用交集组件内
  /// 重造多领域写操作与登录续接：
  /// - `targetAvailability=deferred`：能力尚未上线，不可执行（展示面据此不渲染 pill）；
  /// - `assistant`：打开小艺会话（会话页自行处理登录）；
  /// - `navigate`：导航到承接页（userProfile/circleDetail/homepageDetail/我的交集）。
  ///   `requiredGates`（login 等）不在本层拦截——承接页复用既有 gate + AuthContinuation
  ///   续接完成关注 / 加入 / 讨论等写操作（§15 登录入口无死循环），避免在交集组件内
  ///   重造第二套登录逻辑（R24），也避免登录用户看不到行动入口；
  /// - `companion`：进入既有发起群聊页作为「结伴同行」最薄承接，必须携带
  ///   target/attribution route extra；无对象上下文时不执行，避免退化成普通建群；
  /// - `commerce`：仅在 `INTERSECTION_COMMERCE_ACTIONS_ENABLED=true` 且 target 可路由时
  ///   执行；真实渠道未接入时默认 featureDisabled，不伪造交易；
  /// - `message` / `connect`：需要专属私信/破冰状态机，端侧尚无真实
  ///   卡内 handler 时不可执行，宁可不执行也不伪装成对象下钻（§24.10 诚实红线）。
  IntersectionActionDispatchResult openActionHint(
    BuildContext context,
    IntersectionActionHint hint, {
    String sourceRef = '',
    IntersectionNavAttribution? attribution,
  }) {
    if (hint.targetAvailability.trim() == 'deferred') {
      return const IntersectionActionDispatchResult(
        IntersectionActionDispatchStatus.deferred,
      );
    }

    switch (hint.dispatch.trim()) {
      case 'assistant':
        return _openAssistant(context);
      case 'navigate':
        return open(
              context,
              hint.target,
              sourceRef: sourceRef,
              attribution: attribution,
            )
            ? const IntersectionActionDispatchResult(
                IntersectionActionDispatchStatus.opened,
              )
            : const IntersectionActionDispatchResult(
                IntersectionActionDispatchStatus.missingTarget,
              );
      case 'message':
      case 'connect':
        return const IntersectionActionDispatchResult(
          IntersectionActionDispatchStatus.unsupported,
        );
      case 'companion':
        return _openCompanion(context, hint, attribution);
      case 'commerce':
        return _openCommerce(
          context,
          hint,
          sourceRef: sourceRef,
          attribution: attribution,
        );
      default:
        return open(
              context,
              hint.target,
              sourceRef: sourceRef,
              attribution: attribution,
            )
            ? const IntersectionActionDispatchResult(
                IntersectionActionDispatchStatus.opened,
              )
            : const IntersectionActionDispatchResult(
                IntersectionActionDispatchStatus.missingTarget,
              );
    }
  }

  IntersectionActionDispatchResult _openAssistant(BuildContext context) {
    final router = GoRouter.maybeOf(context);
    if (router == null) {
      return const IntersectionActionDispatchResult(
        IntersectionActionDispatchStatus.missingRouter,
      );
    }
    router.push(
      AppRoutePaths.chatDetail(id: AppConceptConstants.assistantConversationId),
    );
    return const IntersectionActionDispatchResult(
      IntersectionActionDispatchStatus.opened,
    );
  }

  IntersectionActionDispatchResult _openCompanion(
    BuildContext context,
    IntersectionActionHint hint,
    IntersectionNavAttribution? attribution,
  ) {
    final target = hint.target;
    if (target == null || target.objectId.trim().isEmpty) {
      return const IntersectionActionDispatchResult(
        IntersectionActionDispatchStatus.missingTarget,
      );
    }
    final router = GoRouter.maybeOf(context);
    if (router == null) {
      return const IntersectionActionDispatchResult(
        IntersectionActionDispatchStatus.missingRouter,
      );
    }
    if (attribution != null) {
      onTrack?.call(target, attribution);
    }
    router.push(
      AppRoutePaths.startGroupChat,
      extra: StartGroupChatRouteExtra(
        actionKey: hint.actionKey.trim(),
        actionLabel: hint.label.trim(),
        targetObjectId: target.objectId.trim(),
        targetObjectKind: target.objectKind.trim(),
        targetRouteId: target.routeId.trim(),
        intersectionId: attribution?.intersectionId.trim() ?? '',
        dimension: attribution?.dimension.trim() ?? '',
        intersectionClass: attribution?.intersectionClass.trim() ?? '',
        sourceRef: attribution?.sourceRef.trim() ?? '',
        evidenceId: attribution?.evidenceId.trim() ?? '',
      ),
    );
    return const IntersectionActionDispatchResult(
      IntersectionActionDispatchStatus.opened,
    );
  }

  IntersectionActionDispatchResult _openCommerce(
    BuildContext context,
    IntersectionActionHint hint, {
    required String sourceRef,
    IntersectionNavAttribution? attribution,
  }) {
    if (!commerceActionsEnabled) {
      return const IntersectionActionDispatchResult(
        IntersectionActionDispatchStatus.featureDisabled,
      );
    }
    return open(
          context,
          hint.target,
          sourceRef: sourceRef,
          attribution: attribution,
        )
        ? const IntersectionActionDispatchResult(
            IntersectionActionDispatchStatus.opened,
          )
        : const IntersectionActionDispatchResult(
            IntersectionActionDispatchStatus.missingTarget,
          );
  }
}
