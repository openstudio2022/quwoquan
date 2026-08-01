// ignore_for_file: prefer_initializing_formals

import 'package:quwoquan_app/core/services/cache/content_cache_services.dart';
import 'package:quwoquan_app/core/services/cache/conversation_cache_service.dart';
import 'package:quwoquan_app/core/services/cache/user_profile_cache_service.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';

enum CacheClearLevel {
  temporaryMedia,
  offlineContent,
  searchAndBrowseHistory,
  allRebuildable,
}

class CacheUsageEstimate {
  const CacheUsageEstimate({
    required this.postObjects,
    required this.querySnapshots,
    required this.userProfiles,
    required this.conversations,
  });

  final int postObjects;
  final int querySnapshots;
  final int userProfiles;
  final int conversations;

  int get totalTrackedObjects =>
      postObjects + querySnapshots + userProfiles + conversations;
}

class CacheClearResult {
  const CacheClearResult({
    required this.level,
    required this.objectsRemoved,
    required this.protectedObjects,
    this.resourceBytesCleared = true,
  });

  final CacheClearLevel level;
  final int objectsRemoved;
  final int protectedObjects;
  final bool resourceBytesCleared;
}

class CacheManagementService {
  CacheManagementService({
    required PostObjectCacheService postCache,
    required ContentQuerySnapshotStore querySnapshotStore,
    required UserProfileCacheService userProfileCache,
    required ConversationCacheService conversationCache,
    Future<void> Function()? clearTemporaryImages,
    Future<void> Function()? clearAllRebuildableImages,
    required Future<void> Function() clearAccountScopedPersistence,
  }) : _postCache = postCache,
       _querySnapshotStore = querySnapshotStore,
       _userProfileCache = userProfileCache,
       _conversationCache = conversationCache,
       _clearTemporaryImages =
           clearTemporaryImages ?? AppImageCacheController.clearTemporaryImages,
       _clearAllRebuildableImages =
           clearAllRebuildableImages ??
           AppImageCacheController.clearAllRebuildableImages,
       _clearAccountScopedPersistence = clearAccountScopedPersistence;

  final PostObjectCacheService _postCache;
  final ContentQuerySnapshotStore _querySnapshotStore;
  final UserProfileCacheService _userProfileCache;
  final ConversationCacheService _conversationCache;
  final Future<void> Function() _clearTemporaryImages;
  final Future<void> Function() _clearAllRebuildableImages;
  final Future<void> Function() _clearAccountScopedPersistence;

  CacheUsageEstimate estimateUsage() {
    return CacheUsageEstimate(
      postObjects: _postCache.detailCount + _postCache.projectionCount,
      querySnapshots: _querySnapshotStore.count,
      userProfiles: _userProfileCache.entryCount,
      conversations: _conversationCache.activeDiskCount,
    );
  }

  Future<CacheClearResult> clear(
    CacheClearLevel level, {
    Set<String> protectedUserIds = const <String>{},
  }) async {
    switch (level) {
      case CacheClearLevel.temporaryMedia:
        await _clearTemporaryImages();
        return CacheClearResult(
          level: level,
          objectsRemoved: 0,
          protectedObjects: _protectedObjectCount(protectedUserIds),
        );
      case CacheClearLevel.offlineContent:
        await _clearTemporaryImages();
        final removed =
            _postCache.clearRecentDetails() + _querySnapshotStore.clearAll();
        await _querySnapshotStore.flushPersistence();
        return CacheClearResult(
          level: level,
          objectsRemoved: removed,
          protectedObjects: _protectedObjectCount(protectedUserIds),
        );
      case CacheClearLevel.searchAndBrowseHistory:
        final removed = _querySnapshotStore.clearAll();
        await _querySnapshotStore.flushPersistence();
        return CacheClearResult(
          level: level,
          objectsRemoved: removed,
          protectedObjects: _protectedObjectCount(protectedUserIds),
          resourceBytesCleared: false,
        );
      case CacheClearLevel.allRebuildable:
        await _clearAllRebuildableImages();
        final removed =
            _postCache.clearAllRebuildable() +
            _querySnapshotStore.clearAll() +
            _userProfileCache.clearRebuildable(
              protectedUserIds: protectedUserIds,
            );
        await _querySnapshotStore.flushPersistence();
        return CacheClearResult(
          level: level,
          objectsRemoved: removed,
          protectedObjects: _protectedObjectCount(protectedUserIds),
        );
    }
  }

  /// 云侧账号已进入 closed 终态后的本地隐私清理。
  ///
  /// 与用户主动“清缓存”不同，这里不保留会话或当前用户资料；所有数据均可由
  /// 未注销账号重新从 Remote 权威构建。
  Future<void> clearForTerminalAccountClosure() async {
    await _querySnapshotStore.ensureHydrated();
    _postCache.clearAllRebuildable();
    _querySnapshotStore.clearAll();
    _conversationCache.clearAllNamespaces();
    await Future.wait<void>(<Future<void>>[
      _clearAllRebuildableImages(),
      _clearAccountScopedPersistence(),
      _userProfileCache.clearAllForTerminalAccountClosure(),
      _querySnapshotStore.flushPersistence(),
    ]);
    if (_postCache.detailCount != 0 ||
        _postCache.projectionCount != 0 ||
        _querySnapshotStore.count != 0 ||
        _userProfileCache.entryCount != 0 ||
        _userProfileCache.memoryCount != 0 ||
        _conversationCache.totalEntryCount != 0) {
      throw StateError('terminal account closure cache verification failed');
    }
  }

  int _protectedObjectCount(Set<String> protectedUserIds) {
    return protectedUserIds.length + _conversationCache.activeDiskCount;
  }
}
