import 'dart:developer' as developer;

import 'package:flutter/foundation.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/realtime/remote_realtime_connection_delegate.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_connection_delegate.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/core/di/ops_event_dependencies.dart';

typedef RealtimeCurrentUserIdResolver = String Function(Ref ref);
typedef RealtimeConnectionDelegateFactory =
    RealtimeConnectionDelegate Function({
      required Ref ref,
      required RealtimeConnectionStateListener onStateChanged,
      required RealtimeCurrentUserIdResolver currentUserIdResolver,
    });

/// UI 唯一入口。production 默认装配只能创建 Remote delegate。
///
/// alpha/test 如需 fixture，必须从独立 composition root 显式注入 factory；
/// production 不读取运行时 mode，也不存在失败回退或 Mock 热切换路径。
class RealtimeConnectionNotifier extends Notifier<TransportState> {
  RealtimeConnectionNotifier({
    RealtimeCurrentUserIdResolver? currentUserIdResolver,
    RealtimeConnectionDelegateFactory? delegateFactory,
  }) : _currentUserIdResolver =
           currentUserIdResolver ?? _defaultCurrentUserIdResolver,
       _delegateFactory = delegateFactory ?? _createRemoteDelegate;

  static String _defaultCurrentUserIdResolver(Ref ref) {
    final authSession = ref.read(authSessionControllerProvider);
    final activeSubAccountId = authSession.activeSubAccountId.trim();
    if (activeSubAccountId.isNotEmpty) {
      return activeSubAccountId;
    }
    return authSession.ownerId.trim();
  }

  final RealtimeCurrentUserIdResolver _currentUserIdResolver;
  final RealtimeConnectionDelegateFactory _delegateFactory;
  RealtimeConnectionDelegate? _delegate;

  static RealtimeConnectionDelegate _createRemoteDelegate({
    required Ref ref,
    required RealtimeConnectionStateListener onStateChanged,
    required RealtimeCurrentUserIdResolver currentUserIdResolver,
  }) {
    return RemoteRealtimeConnectionDelegate(
      read: ref.read,
      invalidate: ref.invalidate,
      currentUserIdResolver: () => currentUserIdResolver(ref),
      authTokenProvider: ProviderBackedCloudAuthTokenProvider(
        () => ref
            .read(authSessionControllerProvider.notifier)
            .accessTokenForRequest(),
      ),
      onStateChanged: onStateChanged,
      telemetryRecorder:
          ({
            required transport,
            required result,
            required durationMs,
            failReasonCode,
          }) async {
            try {
              await ref
                  .read(appTelemetryReporterProvider)
                  .record(
                    AppTelemetryPayload.realtimeConnectResult(
                      transport: transport,
                      result: result,
                      durationMs: durationMs,
                      failReasonCode: failReasonCode,
                    ),
                  );
            } catch (error, stackTrace) {
              developer.log(
                'realtime connect telemetry failed',
                name: 'RealtimeConnectionNotifier',
                error: error,
                stackTrace: stackTrace,
              );
            }
          },
    );
  }

  @override
  TransportState build() {
    _silentlyDisposeDelegate(_delegate);
    _delegate = _delegateFactory(
      ref: ref,
      onStateChanged: _syncDelegateState,
      currentUserIdResolver: _currentUserIdResolver,
    );
    ref.onDispose(() {
      _silentlyDisposeDelegate(_delegate);
      _delegate = null;
    });
    return _delegate!.state;
  }

  void _syncDelegateState() {
    final delegate = _delegate;
    if (delegate == null) {
      return;
    }
    final schedulerBinding = _schedulerBindingOrNull();
    if (schedulerBinding == null) {
      _applyDelegateState(delegate);
      return;
    }
    final phase = schedulerBinding.schedulerPhase;
    if (phase != SchedulerPhase.idle &&
        phase != SchedulerPhase.postFrameCallbacks) {
      schedulerBinding.addPostFrameCallback((_) {
        if (!ref.mounted || !identical(_delegate, delegate)) {
          return;
        }
        _applyDelegateState(delegate);
      });
      return;
    }
    _applyDelegateState(delegate);
  }

  SchedulerBinding? _schedulerBindingOrNull() {
    try {
      return SchedulerBinding.instance;
    } on FlutterError {
      // Pure provider/local-contract execution has no Flutter binding. There is
      // no widget build phase in that environment, so state can be applied
      // synchronously without weakening the production frame guard.
      return null;
    }
  }

  void _applyDelegateState(RealtimeConnectionDelegate delegate) {
    if (state != delegate.state) {
      state = delegate.state;
    }
  }

  void onAppForeground() {
    _delegate?.onAppForeground();
    _syncDelegateState();
  }

  void onAppBackground() {
    _delegate?.onAppBackground();
    _syncDelegateState();
  }

  void onEnterConversation(String conversationId) {
    _delegate?.onEnterConversation(conversationId);
    _syncDelegateState();
  }

  void onLeaveConversation() {
    _delegate?.onLeaveConversation();
    _syncDelegateState();
  }

  void _silentlyDisposeDelegate(RealtimeConnectionDelegate? delegate) {
    if (delegate == null) {
      return;
    }
    final current = _delegate;
    _delegate = null;
    try {
      if (current?.state == TransportState.active) {
        current?.onLeaveConversation();
      }
      if (current?.state != null &&
          current!.state != TransportState.disconnected) {
        current.onAppBackground();
      }
    } finally {
      current?.dispose();
    }
  }
}
