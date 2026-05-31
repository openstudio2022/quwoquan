import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';

enum EdgeBackDirection { leading, trailing }

enum AppRoutePageKind {
  shellRoot,
  drillDown,
  fullscreenDialog,
  transparentModal,
  customTransition,
  noTransition,
}

enum AppBackDisposition { popRoute, guardRootExit, ignoreRoot, delegateToGuard }

enum AppBackGuardDecision { allowPop, handled, blocked }

class AppRouteContext {
  const AppRouteContext({
    required this.location,
    required this.canPop,
    required this.isBottomNavRoot,
    this.hasPageGuard = false,
  });

  final String location;
  final bool canPop;
  final bool isBottomNavRoot;
  final bool hasPageGuard;
}

class AppRoutePageSpec<T> {
  const AppRoutePageSpec({
    required this.key,
    required this.child,
    this.kind = AppRoutePageKind.drillDown,
    this.fullscreenDialog = false,
    this.name,
    this.arguments,
    this.restorationId,
    this.maintainState = true,
  });

  final LocalKey key;
  final Widget child;
  final AppRoutePageKind kind;
  final bool fullscreenDialog;
  final String? name;
  final Object? arguments;
  final String? restorationId;
  final bool maintainState;
}

abstract class AppBackGuard {
  Future<AppBackGuardDecision> handleBack();
}

abstract class NativeBackNavigationPolicy {
  Set<EdgeBackDirection> get supportedBackEdges;
  Duration get rootExitGuardWindow;
  bool shouldGuardRootExit(AppRouteContext context);
  AppBackDisposition resolveBack(AppRouteContext context);
  Page<T> buildPage<T>(AppRoutePageSpec<T> spec);
}

class IosNativeBackNavigationPolicy implements NativeBackNavigationPolicy {
  const IosNativeBackNavigationPolicy();

  @override
  Set<EdgeBackDirection> get supportedBackEdges => const {
    EdgeBackDirection.leading,
  };

  @override
  Duration get rootExitGuardWindow => const Duration(seconds: 2);

  @override
  bool shouldGuardRootExit(AppRouteContext context) => false;

  @override
  AppBackDisposition resolveBack(AppRouteContext context) {
    if (context.hasPageGuard) {
      return AppBackDisposition.delegateToGuard;
    }
    if (context.canPop) {
      return AppBackDisposition.popRoute;
    }
    return AppBackDisposition.ignoreRoot;
  }

  @override
  Page<T> buildPage<T>(AppRoutePageSpec<T> spec) {
    if (spec.kind == AppRoutePageKind.noTransition ||
        spec.kind == AppRoutePageKind.shellRoot) {
      return NoTransitionPage<T>(key: spec.key, child: spec.child);
    }
    return CupertinoPage<T>(
      key: spec.key,
      name: spec.name,
      arguments: spec.arguments,
      restorationId: spec.restorationId,
      maintainState: spec.maintainState,
      fullscreenDialog:
          spec.fullscreenDialog ||
          spec.kind == AppRoutePageKind.fullscreenDialog,
      child: spec.child,
    );
  }
}

class AndroidNativeBackNavigationPolicy implements NativeBackNavigationPolicy {
  const AndroidNativeBackNavigationPolicy();

  @override
  Set<EdgeBackDirection> get supportedBackEdges => const {
    EdgeBackDirection.leading,
    EdgeBackDirection.trailing,
  };

  @override
  Duration get rootExitGuardWindow => const Duration(seconds: 2);

  @override
  bool shouldGuardRootExit(AppRouteContext context) {
    return context.isBottomNavRoot && !context.canPop && !context.hasPageGuard;
  }

  @override
  AppBackDisposition resolveBack(AppRouteContext context) {
    if (context.hasPageGuard) {
      return AppBackDisposition.delegateToGuard;
    }
    if (context.canPop) {
      return AppBackDisposition.popRoute;
    }
    if (shouldGuardRootExit(context)) {
      return AppBackDisposition.guardRootExit;
    }
    return AppBackDisposition.ignoreRoot;
  }

  @override
  Page<T> buildPage<T>(AppRoutePageSpec<T> spec) {
    if (spec.kind == AppRoutePageKind.noTransition ||
        spec.kind == AppRoutePageKind.shellRoot) {
      return NoTransitionPage<T>(key: spec.key, child: spec.child);
    }
    return MaterialPage<T>(
      key: spec.key,
      name: spec.name,
      arguments: spec.arguments,
      restorationId: spec.restorationId,
      maintainState: spec.maintainState,
      fullscreenDialog:
          spec.fullscreenDialog ||
          spec.kind == AppRoutePageKind.fullscreenDialog,
      child: spec.child,
    );
  }
}

NativeBackNavigationPolicy nativeBackNavigationPolicyForPlatform([
  TargetPlatform? platform,
]) {
  final effectivePlatform = platform ?? defaultTargetPlatform;
  return switch (effectivePlatform) {
    TargetPlatform.iOS ||
    TargetPlatform.macOS => const IosNativeBackNavigationPolicy(),
    TargetPlatform.android ||
    TargetPlatform.fuchsia ||
    TargetPlatform.linux ||
    TargetPlatform.windows => const AndroidNativeBackNavigationPolicy(),
  };
}

Page<T> appRoutePage<T>({
  required GoRouterState state,
  required Widget child,
  AppRoutePageKind kind = AppRoutePageKind.drillDown,
  bool fullscreenDialog = false,
  NativeBackNavigationPolicy? policy,
}) {
  final effectivePolicy = policy ?? nativeBackNavigationPolicyForPlatform();
  return effectivePolicy.buildPage<T>(
    AppRoutePageSpec<T>(
      key: state.pageKey,
      child: child,
      kind: kind,
      fullscreenDialog: fullscreenDialog,
      name: state.name,
      arguments: state.extra,
    ),
  );
}

bool isBottomNavRootLocation(String location) {
  final path = Uri.tryParse(location)?.path ?? location;
  return path == AppRoutePaths.home ||
      path == AppRoutePaths.circles ||
      path == AppRoutePaths.chat ||
      path == AppRoutePaths.profile;
}

class AppNativeBackScope extends StatefulWidget {
  const AppNativeBackScope({
    super.key,
    required this.router,
    required this.child,
    this.policy,
    this.onExitRequested,
  });

  final GoRouter router;
  final Widget child;
  final NativeBackNavigationPolicy? policy;
  final Future<void> Function()? onExitRequested;

  @override
  State<AppNativeBackScope> createState() => _AppNativeBackScopeState();
}

class _AppNativeBackScopeState extends State<AppNativeBackScope> {
  DateTime? _lastRootBackAt;

  NativeBackNavigationPolicy get _policy =>
      widget.policy ?? nativeBackNavigationPolicyForPlatform();

  @override
  Widget build(BuildContext context) {
    return BackButtonListener(
      onBackButtonPressed: _handleBackButton,
      child: widget.child,
    );
  }

  Future<bool> _handleBackButton() async {
    final location = widget.router.routeInformationProvider.value.uri.path;
    final canPop =
        widget.router.routerDelegate.navigatorKey.currentState?.canPop() ??
        false;
    final routeContext = AppRouteContext(
      location: location,
      canPop: canPop,
      isBottomNavRoot: isBottomNavRootLocation(location),
    );
    final disposition = _policy.resolveBack(routeContext);
    switch (disposition) {
      case AppBackDisposition.popRoute:
      case AppBackDisposition.delegateToGuard:
        _lastRootBackAt = null;
        return false;
      case AppBackDisposition.ignoreRoot:
        _lastRootBackAt = null;
        return true;
      case AppBackDisposition.guardRootExit:
        return _handleRootExitGuard();
    }
  }

  Future<bool> _handleRootExitGuard() async {
    final now = DateTime.now();
    final last = _lastRootBackAt;
    final withinGuardWindow =
        last != null && now.difference(last) <= _policy.rootExitGuardWindow;
    if (withinGuardWindow) {
      _lastRootBackAt = null;
      final exitRequested = widget.onExitRequested;
      if (exitRequested != null) {
        await exitRequested();
      } else {
        await SystemNavigator.pop();
      }
      return true;
    }
    _lastRootBackAt = now;
    if (mounted) {
      AppToast.show(
        context,
        UITextConstants.edgeBackExitPrompt,
        duration: _policy.rootExitGuardWindow,
      );
    }
    return true;
  }
}
