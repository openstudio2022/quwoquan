import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/app/navigation/page_access_log_util.dart';
import 'package:quwoquan_app/assistant/infrastructure/infrastructure.dart';
import 'package:quwoquan_app/cloud/services/ops/ops_event_repository.dart';
import 'package:quwoquan_app/core/services/visit_recorder_service.dart';

class _TrackedOverlay {
  const _TrackedOverlay({
    required this.location,
    required this.pageVisitId,
    required this.enterAt,
  });

  final String location;
  final String pageVisitId;
  final DateTime enterAt;
}

/// 根 [Navigator] 上全屏/模态路由的 pageAccess（与 [MainAppShell] Tab 埋点互补）。
class AppPageAccessNavigatorObserver extends NavigatorObserver {
  AppPageAccessNavigatorObserver._();
  static final AppPageAccessNavigatorObserver instance =
      AppPageAccessNavigatorObserver._();

  final List<_TrackedOverlay> _overlayStack = <_TrackedOverlay>[];
  VisitRecorderService? _visitRecorder;
  OpsEventRepository? _eventRepository;
  String _currentUserId = '';
  String _experimentBucket = '';

  void attachVisitRecorder(VisitRecorderService service) {
    _visitRecorder = service;
  }

  void attachEventReporter({
    required OpsEventRepository repository,
    required String currentUserId,
    required String experimentBucket,
  }) {
    _eventRepository = repository;
    _currentUserId = currentUserId.trim();
    _experimentBucket = experimentBucket.trim();
  }

  void _logOpenForRoute(Route<dynamic> route) {
    final loc = routeLocationFromSettings(route);
    if (loc == null || isShellTabLocation(loc)) return;
    final visitId = AppTraceContextStore.instance.newPageVisitId();
    _overlayStack.add(
      _TrackedOverlay(
        location: loc,
        pageVisitId: visitId,
        enterAt: DateTime.now(),
      ),
    );
    unawaited(
      writeAppPageAccessOpen(
        location: loc,
        pageVisitId: visitId,
        visitRecorder: _visitRecorder,
        eventRepository: _eventRepository,
        currentUserId: _currentUserId,
        experimentBucket: _experimentBucket,
      ),
    );
  }

  void _logReturnForRoute(Route<dynamic> route) {
    final loc = routeLocationFromSettings(route);
    if (loc == null || isShellTabLocation(loc)) return;
    if (_overlayStack.isEmpty) return;
    final t = _overlayStack.removeLast();
    unawaited(
      writeAppPageAccessReturn(
        location: t.location,
        pageVisitId: t.pageVisitId,
        enterAt: t.enterAt,
        eventRepository: _eventRepository,
        currentUserId: _currentUserId,
        experimentBucket: _experimentBucket,
      ),
    );
  }

  @override
  void didPush(Route<dynamic> route, Route<dynamic>? previousRoute) {
    _logOpenForRoute(route);
    super.didPush(route, previousRoute);
  }

  @override
  void didPop(Route<dynamic> route, Route<dynamic>? previousRoute) {
    _logReturnForRoute(route);
    super.didPop(route, previousRoute);
  }

  @override
  void didRemove(Route<dynamic> route, Route<dynamic>? previousRoute) {
    _logReturnForRoute(route);
    super.didRemove(route, previousRoute);
  }

  @override
  void didReplace({Route<dynamic>? newRoute, Route<dynamic>? oldRoute}) {
    if (oldRoute != null) {
      _logReturnForRoute(oldRoute);
    }
    if (newRoute != null) {
      _logOpenForRoute(newRoute);
    }
    super.didReplace(newRoute: newRoute, oldRoute: oldRoute);
  }
}
