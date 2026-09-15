import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/feed_session_provider.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart';
import 'package:quwoquan_app/runtime/di/signed_media_delivery_dependencies.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/application/public/content_activation_identity.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/content_cache_services.dart';

/// production 内容缓存与短签资源的唯一身份切换边界。
final contentCacheLifecycleCoordinatorProvider =
    Provider<ContentCacheLifecycleCoordinator>((ref) {
      final coordinator = ContentCacheLifecycleCoordinator(
        isCurrent: () => ref.mounted,
        postCache: ref.watch(postObjectCacheProvider),
        querySnapshotStore: ref.watch(contentQuerySnapshotStoreProvider),
        clearSignedMediaDelivery: () =>
            ref.read(signedMediaDeliveryCoordinatorProvider).clearAll(),
        clearMediaDownloads: () => ref.read(mediaDownloadCacheProvider).clear(),
        resetFeedSession: () =>
            ref.read(feedSessionProvider.notifier).invalidate(),
        clearIsolationIdentity: ref
            .read(contentCacheIsolationIdentityProvider.notifier)
            .clear,
      );
      ref.listen<AuthSessionState>(
        authSessionControllerProvider,
        coordinator.handleSessionChange,
        fireImmediately: true,
      );
      ref.onDispose(() {
        coordinator.dispose();
      });
      return coordinator;
    });

/// 账号/Persona/release tuple 变化时统一清理全部可重建内容状态。
final class ContentCacheLifecycleCoordinator {
  ContentCacheLifecycleCoordinator({
    required PostObjectCacheService postCache,
    required ContentQuerySnapshotStore querySnapshotStore,
    required void Function() clearSignedMediaDelivery,
    required void Function() clearIsolationIdentity,
    Future<void> Function()? clearMediaDownloads,
    void Function()? resetFeedSession,
    bool Function()? isCurrent,
  }) : this._(
         postCache,
         querySnapshotStore,
         clearSignedMediaDelivery,
         clearIsolationIdentity,
         clearMediaDownloads,
         resetFeedSession,
         isCurrent,
       );

  ContentCacheLifecycleCoordinator._(
    this._postCache,
    this._querySnapshotStore,
    this._clearSignedMediaDelivery,
    this._clearIsolationIdentity,
    this._clearMediaDownloads,
    this._resetFeedSession,
    this._isCurrent,
  );

  final PostObjectCacheService _postCache;
  final ContentQuerySnapshotStore _querySnapshotStore;
  final void Function() _clearSignedMediaDelivery;
  final void Function() _clearIsolationIdentity;
  final Future<void> Function()? _clearMediaDownloads;
  final void Function()? _resetFeedSession;
  String? _sessionIdentity;
  final bool Function()? _isCurrent;
  bool _disposed = false;
  bool get _active => !_disposed && (_isCurrent?.call() ?? true);

  /// 先封闭回调入口，再仅失效本协调器已持有的请求；不访问Ref。
  void dispose() {
    if (_disposed) return;
    _disposed = true;
    _postCache.clearNamespace();
    _querySnapshotStore.invalidateRequests();
  }

  void invalidatePendingRequests() {
    if (!_active) return;
    _postCache.clearNamespace();
    _querySnapshotStore.invalidateRequests();
  }

  ContentActivationIdentity? _activationIdentity;

  void handleSessionChange(AuthSessionState? previous, AuthSessionState next) {
    if (!_active) return;
    final nextIdentity = _sessionIdentityOf(next);
    final previousIdentity = previous == null
        ? _sessionIdentity
        : _sessionIdentityOf(previous);
    _sessionIdentity = nextIdentity;
    if (previousIdentity == null || previousIdentity == nextIdentity) {
      return;
    }
    clearRebuildableContent();
  }

  void handleActivationIdentity(ContentActivationIdentity? identity) {
    if (!_active) return;
    final previous = _activationIdentity;
    _activationIdentity = identity;
    if (previous == null || previous == identity) {
      return;
    }
    clearRebuildableContent();
  }

  void clearRebuildableContent() {
    if (!_active) return;
    _postCache.clearNamespace();
    if (!_active) return;
    _querySnapshotStore.clearAll();
    if (!_active) return;
    _resetFeedSession?.call();
    // 同步通知也可能重建provider；每个Ref闭包前复核，不能等异步异常后吞错。
    if (!_active) return;
    final clearDownloads = _clearMediaDownloads;
    if (clearDownloads != null) unawaited(clearDownloads());
    if (!_active) return;
    _clearSignedMediaDelivery();
    if (!_active) return;
    _clearIsolationIdentity();
    if (!_active) return;
    unawaited(_querySnapshotStore.flushPersistence());
  }

  static String _sessionIdentityOf(AuthSessionState session) {
    return <String>[
      session.hasTrustedSession ? 'trusted' : 'untrusted',
      session.isAuthenticated ? 'authenticated' : 'guest',
      session.ownerId.trim(),
      session.activePersonaId.trim(),
    ].join('|');
  }
}
