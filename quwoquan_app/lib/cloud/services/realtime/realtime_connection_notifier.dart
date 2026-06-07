import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/realtime/mock/mock_realtime_connection_delegate.dart';
import 'package:quwoquan_app/cloud/services/realtime/remote_realtime_connection_delegate.dart';
import 'package:quwoquan_app/cloud/services/realtime/realtime_connection_delegate.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/di/cloud_repository_binding.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';

typedef RealtimeCurrentUserIdResolver = String Function(Ref ref);

/// UI 唯一入口：按 [AppDataSourceMode] 透明切换 Mock / Remote delegate。
class RealtimeConnectionNotifier extends Notifier<TransportState> {
  RealtimeConnectionNotifier({
    RealtimeCurrentUserIdResolver? currentUserIdResolver,
  }) : _currentUserIdResolver =
           currentUserIdResolver ?? _defaultCurrentUserIdResolver;

  static String _defaultCurrentUserIdResolver(Ref ref) {
    final authSession = ref.read(authSessionControllerProvider);
    final activeSubAccountId = authSession.activeSubAccountId.trim();
    if (activeSubAccountId.isNotEmpty) {
      return activeSubAccountId;
    }
    return authSession.ownerId.trim();
  }

  final RealtimeCurrentUserIdResolver _currentUserIdResolver;
  RealtimeConnectionDelegate? _delegate;

  @override
  TransportState build() {
    final mode = ref.watch(appDataSourceModeProvider);
    _silentlyDisposeDelegate(_delegate);
    _delegate = cloudRepositoryImplForMode(
      mode,
      remote: () => RemoteRealtimeConnectionDelegate(
        read: ref.read,
        currentUserIdResolver: () => _currentUserIdResolver(ref),
        onStateChanged: _syncDelegateState,
      ),
      mock: () => MockRealtimeConnectionDelegate(
        read: ref.read,
        onStateChanged: _syncDelegateState,
      ),
    );
    ref.onDispose(() {
      _silentlyDisposeDelegate(_delegate);
      _delegate = null;
    });
    return _delegate!.state;
  }

  void _syncDelegateState() {
    final delegate = _delegate;
    if (delegate != null && state != delegate.state) {
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

  void onEnterChatDetail(String conversationId) {
    _delegate?.onEnterChatDetail(conversationId);
    _syncDelegateState();
  }

  void onLeaveChatDetail() {
    _delegate?.onLeaveChatDetail();
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
        current?.onLeaveChatDetail();
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
