import 'package:flutter/widgets.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_kind_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_target.g.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';

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

/// 统一交集导航器（统一交互子契约 · A–E 横切复用，Phase 0 §20.7）。
///
/// 把云侧 [IntersectionTarget]（objectId + objectKind + routeId）映射为 codegen 路由
/// （[AppRoutePaths]）跳转，端侧不硬编码 path。`routeId` 为云侧「路由逻辑名」闭集
/// （userProfile / circleDetail / homepageDetail / myIntersections），缺省 / 未知时
/// 由 objectKind 经 codegen [intersectionRouteIdForObjectKind]（registry.objectKinds.routeId）
/// 反查；objectKind 不可导航（content/tag/未知）时视为不可点击（返回 null）。
///
/// 不可解析（target 缺省 / objectId 空 / 不可导航 objectKind）时静默不跳转（优雅降级，
/// 不抛错、不崩溃）。埋点经构造时注入的 [onTrack] 透传，导航器本身不依赖 Riverpod，
/// 便于 A–E 复用与组件测试。
class IntersectionTargetNavigator {
  const IntersectionTargetNavigator({this.onTrack});

  final IntersectionNavTrack? onTrack;

  /// 把对象页交集行 [IntersectionReason] 归一为统一导航 [IntersectionTarget]。
  ///
  /// objectKind 一等字段为真相源（旧 relationKind 对象类型桥接已删除，§23 去桥接）；
  /// 交由 [resolvePath] / [open] 经 codegen objectKind→routeId 统一映射。A–E 各展示位
  /// 共用此方法，端不再各自手写 `switch(kind) → context.push(...)` 复制导航逻辑。
  ///
  /// `actionTargetId` 为空时返回空 objectId 的 target，[resolvePath] 据此判定不可路由（优雅降级）。
  static IntersectionTarget targetForReason(IntersectionReason reason) {
    return IntersectionTarget(
      objectId: reason.actionTargetId.trim(),
      objectKind: reason.objectKind.trim(),
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
      case 'myIntersections':
        return AppRoutePaths.myIntersections(
          dimension: id,
          sourceRef: ref.isEmpty ? null : ref,
        );
      default:
        return null;
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
}
