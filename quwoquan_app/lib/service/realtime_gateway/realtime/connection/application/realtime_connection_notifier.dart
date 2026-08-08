import 'package:flutter/foundation.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/application/public/realtime_conversation_lifecycle.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/domain/realtime_connection_delegate.dart';

typedef RealtimeCurrentUserIdResolver = String Function(Ref ref);
typedef RealtimeConnectionDelegateFactory =
    RealtimeConnectionDelegate Function({
      required Ref ref,
      required RealtimeConnectionStateListener onStateChanged,
      required RealtimeCurrentUserIdResolver currentUserIdResolver,
    });

/// `realtime.connection` 的 session facade：只在 WebSocket/LongPoll 连接期间存在，
/// 不是持久业务聚合，因此不拥有 presentation，也不被登记为页面物理 owner。
///
/// 需要展示连接状态的页面只消费 `TransportState`（本 provider 的公开读取面）或
/// [RealtimeConversationLifecycle]，由该页面所属业务对象的 presentation 承载 UI。
///
/// application 层只接受 typed delegate factory；production Remote 构造由
/// `runtime/di/realtime_dependencies.dart` 注入。测试如需 typed double，同样必须从
/// 独立 composition root 显式注入 factory，不存在运行时 mode 或失败回退。
class RealtimeConnectionNotifier extends Notifier<TransportState>
    implements RealtimeConversationLifecycle {
  RealtimeConnectionNotifier({
    RealtimeCurrentUserIdResolver? currentUserIdResolver,
    required this._delegateFactory,
  }) : _currentUserIdResolver =
           currentUserIdResolver ?? _defaultCurrentUserIdResolver;

  static String _defaultCurrentUserIdResolver(Ref ref) {
    final authSession = ref.read(authSessionControllerProvider);
    if (!authSession.isAuthenticated) {
      return '';
    }
    final activePersonaId = authSession.activePersonaId.trim();
    if (activePersonaId.isNotEmpty) {
      return activePersonaId;
    }
    return authSession.ownerId.trim();
  }

  final RealtimeCurrentUserIdResolver _currentUserIdResolver;
  final RealtimeConnectionDelegateFactory _delegateFactory;
  RealtimeConnectionDelegate? _delegate;
  bool _isAppForeground = false;

  @override
  TransportState build() {
    _silentlyDisposeDelegate(_delegate);
    _delegate = _delegateFactory(
      ref: ref,
      onStateChanged: _syncDelegateState,
      currentUserIdResolver: _currentUserIdResolver,
    );
    ref.listen<AuthSessionState>(authSessionControllerProvider, (
      previous,
      next,
    ) {
      if (!next.isAuthenticated) {
        _delegate?.onAppBackground();
        _syncDelegateState();
        return;
      }
      if (_isAppForeground && !(previous?.isAuthenticated ?? false)) {
        _delegate?.onAppForeground();
        _syncDelegateState();
      }
    });
    ref.onDispose(() {
      _silentlyDisposeDelegate(_delegate);
      _delegate = null;
    });
    return _delegate!.state;
  }

  void _syncDelegateState() {
    if (!ref.mounted) {
      return;
    }
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
    if (!ref.mounted) {
      return;
    }
    _isAppForeground = true;
    if (ref.read(authSessionControllerProvider).isAuthenticated) {
      _delegate?.onAppForeground();
    } else {
      // Realtime endpoints require a bearer issued for an explicitly
      // authenticated account. Trusted anonymous/guest sessions must not
      // start LongPoll or WebSocket transports.
      _delegate?.onAppBackground();
    }
    _syncDelegateState();
  }

  void onAppBackground() {
    _isAppForeground = false;
    _delegate?.onAppBackground();
    _syncDelegateState();
  }

  @override
  void onEnterConversation(String conversationId) {
    if (!ref.mounted) {
      return;
    }
    if (!ref.read(authSessionControllerProvider).isAuthenticated) {
      return;
    }
    _delegate?.onEnterConversation(conversationId);
    _syncDelegateState();
  }

  @override
  void onLeaveConversation() {
    if (!ref.mounted) {
      return;
    }
    if (!ref.read(authSessionControllerProvider).isAuthenticated) {
      _delegate?.onAppBackground();
      _syncDelegateState();
      return;
    }
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
