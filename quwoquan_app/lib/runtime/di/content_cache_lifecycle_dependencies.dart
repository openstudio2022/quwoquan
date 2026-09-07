import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart';
import 'package:quwoquan_app/runtime/di/signed_media_delivery_dependencies.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/application/public/content_activation_identity.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/content_cache_services.dart';

/// production 内容缓存与短签资源的唯一身份切换边界。
final contentCacheLifecycleCoordinatorProvider =
    Provider<ContentCacheLifecycleCoordinator>((ref) {
      final coordinator = ContentCacheLifecycleCoordinator(
        postCache: ref.watch(postObjectCacheProvider),
        querySnapshotStore: ref.watch(contentQuerySnapshotStoreProvider),
        clearSignedMediaDelivery: () =>
            ref.read(signedMediaDeliveryCoordinatorProvider).clearAll(),
        clearIsolationIdentity: ref
            .read(contentCacheIsolationIdentityProvider.notifier)
            .clear,
      );
      ref.listen<AuthSessionState>(
        authSessionControllerProvider,
        coordinator.handleSessionChange,
        fireImmediately: true,
      );
      return coordinator;
    });

/// 账号/Persona/audience/release tuple 变化时统一清理全部可重建内容状态。
final class ContentCacheLifecycleCoordinator {
  ContentCacheLifecycleCoordinator({
    required PostObjectCacheService postCache,
    required ContentQuerySnapshotStore querySnapshotStore,
    required void Function() clearSignedMediaDelivery,
    required void Function() clearIsolationIdentity,
  }) : this._(
         postCache,
         querySnapshotStore,
         clearSignedMediaDelivery,
         clearIsolationIdentity,
       );

  ContentCacheLifecycleCoordinator._(
    this._postCache,
    this._querySnapshotStore,
    this._clearSignedMediaDelivery,
    this._clearIsolationIdentity,
  );

  final PostObjectCacheService _postCache;
  final ContentQuerySnapshotStore _querySnapshotStore;
  final void Function() _clearSignedMediaDelivery;
  final void Function() _clearIsolationIdentity;
  String? _sessionIdentity;
  ContentActivationIdentity? _activationIdentity;

  void handleSessionChange(AuthSessionState? previous, AuthSessionState next) {
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
    final previous = _activationIdentity;
    _activationIdentity = identity;
    if (previous == null || previous == identity) {
      return;
    }
    clearRebuildableContent();
  }

  void clearRebuildableContent() {
    _postCache.clearAllRebuildable();
    _querySnapshotStore.clearAll();
    _clearSignedMediaDelivery();
    _clearIsolationIdentity();
    unawaited(_querySnapshotStore.flushPersistence());
  }

  static String _sessionIdentityOf(AuthSessionState session) {
    return <String>[
      session.hasTrustedSession ? 'trusted' : 'untrusted',
      session.isAuthenticated ? 'authenticated' : 'guest',
      session.ownerId.trim(),
      session.activePersonaId.trim(),
      contentReleaseAudiencePartitionHintFromAccessToken(session.accessToken)
          .name,
    ].join('|');
  }
}
