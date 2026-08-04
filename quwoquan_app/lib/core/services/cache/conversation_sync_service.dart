import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_sync_repository.dart';
import 'package:quwoquan_app/core/services/cache/conversation_cache_record.dart';
import 'package:quwoquan_app/core/services/cache/conversation_cache_service.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_store.dart';
import 'package:quwoquan_app/core/services/cache/local_search_namespace.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show UserSyncPatchKind;

/// 会话列表同步引擎
///
/// 从云端拉取全量会话 ID + 分拆时间戳，与本地缓存逐项比较：
/// - `settingsUpdatedAt` 变化 → 需批量拉取完整会话数据
/// - `lastMessageAt` 变化但 settings 未变 → 仅更新列表展示字段
/// - 30 秒防抖，避免切 Tab 频繁触发
class ConversationSyncService {
  ConversationSyncService({
    required this.repo,
    required this.cache,
    required this.userSyncRepository,
    required this.store,
    required this.personaContextLoader,
  });

  final ChatRepository repo;
  final ConversationCacheService cache;
  final UserSyncRepository userSyncRepository;
  final LocalChatSearchStore store;
  final PersonaContextLoader personaContextLoader;

  bool _syncing = false;
  bool _syncingUserPatches = false;
  bool _lastFullSyncFailed = false;
  final Map<String, DateTime> _lastSyncTimeByNamespace = <String, DateTime>{};
  static const _minSyncInterval = Duration(seconds: 30);
  String? _activeNamespaceKey;
  Object? _lastAvatarPatchSyncError;
  StackTrace? _lastAvatarPatchSyncStackTrace;
  DateTime? _lastAvatarPatchSyncFailedAt;
  int? _lastAvatarPatchSyncFailedAfterSeq;

  Object? get lastAvatarPatchSyncError => _lastAvatarPatchSyncError;
  StackTrace? get lastAvatarPatchSyncStackTrace =>
      _lastAvatarPatchSyncStackTrace;
  DateTime? get lastAvatarPatchSyncFailedAt => _lastAvatarPatchSyncFailedAt;
  int? get lastAvatarPatchSyncFailedAfterSeq =>
      _lastAvatarPatchSyncFailedAfterSeq;
  bool get hasAvatarPatchSyncFailure => _lastAvatarPatchSyncError != null;

  /// 执行增量同步，返回是否有数据变更
  Future<bool> sync({bool force = false}) async {
    if (_syncing) return false;
    final namespace = await _resolveNamespace();
    if (namespace == null) {
      return false;
    }
    _activateNamespace(namespace);
    final lastSyncTime = _lastSyncTimeByNamespace[namespace.key];
    if (!force &&
        lastSyncTime != null &&
        DateTime.now().difference(lastSyncTime) < _minSyncInterval) {
      return false;
    }

    _syncing = true;
    _lastSyncTimeByNamespace[namespace.key] = DateTime.now();
    _lastFullSyncFailed = false;
    try {
      final timestamps = await repo.getConversationTimestamps();
      final cloudIds = <String>{};
      final needFetchIds = <String>[];
      var hasChanges = false;

      for (final ts in timestamps) {
        final id = ts.conversationId.trim();
        if (id.isEmpty) continue;
        cloudIds.add(id);

        final cloudSettingsUpdatedAt = ts.settingsUpdatedAt
            .toUtc()
            .toIso8601String();
        final cloudLastMessageAt = ts.lastMessageAt.toUtc().toIso8601String();
        final localSettingsTs = cache.getSettingsTimestamp(id);
        final localMessageTs = cache.getMessageTimestamp(id);

        if (localSettingsTs == null ||
            localSettingsTs != cloudSettingsUpdatedAt) {
          needFetchIds.add(id);
          hasChanges = true;
        } else if (localMessageTs != cloudLastMessageAt) {
          cache.applyListPatch(
            id,
            ConversationListPatch(
              lastMessagePreview: ts.lastMessagePreview,
              lastMessageAt: cloudLastMessageAt,
              unreadCount: ts.unreadCount,
            ),
          );
          hasChanges = true;
        }
      }

      final localAll = cache.getAll();
      for (final local in localAll) {
        final localId = local.id;
        if (localId.isNotEmpty && !cloudIds.contains(localId)) {
          cache.remove(localId);
          hasChanges = true;
        }
      }

      if (needFetchIds.isNotEmpty) {
        const batchSize = 50;
        for (var i = 0; i < needFetchIds.length; i += batchSize) {
          final batch = needFetchIds.sublist(
            i,
            i + batchSize > needFetchIds.length
                ? needFetchIds.length
                : i + batchSize,
          );
          final conversations = await repo.batchGetConversations(batch);
          cache.putAll(
            conversations.map(ConversationCacheRecord.fromConversationViewData),
          );
        }
      }

      return hasChanges;
    } catch (_) {
      _lastFullSyncFailed = true;
      return false;
    } finally {
      _syncing = false;
    }
  }

  Future<bool> syncAvatarPatches({
    int? hintedLatestSyncSeq,
    bool force = false,
  }) async {
    if (_syncingUserPatches) return false;
    final namespace = await _resolveNamespace();
    if (namespace == null) {
      return false;
    }
    _activateNamespace(namespace);
    _syncingUserPatches = true;
    int? observedLastSeq;
    try {
      await store.ensureReady();
      var lastSeq = await store.lastUserSyncSeq(namespace: namespace);
      observedLastSeq = lastSeq;
      final originalLastSeq = lastSeq;
      if (!force &&
          hintedLatestSyncSeq != null &&
          hintedLatestSyncSeq > 0 &&
          hintedLatestSyncSeq <= lastSeq) {
        return false;
      }
      var changed = false;
      var hasMore = true;
      var guard = 0;
      while (hasMore && guard < 20) {
        guard += 1;
        final result = await userSyncRepository.pull(
          afterSeq: lastSeq,
          limit: 200,
        );
        if (result.requiresResync) {
          final changedByFullSync = await sync(force: true);
          if (_lastFullSyncFailed) {
            _recordAvatarPatchSyncFailure(
              StateError('conversation avatar patch requires full resync'),
              StackTrace.current,
              originalLastSeq,
            );
            return false;
          }
          if (result.latestSyncSeq > lastSeq) {
            lastSeq = result.latestSyncSeq;
            await store.saveUserSyncSeq(namespace: namespace, syncSeq: lastSeq);
          }
          _clearAvatarPatchSyncFailure();
          return changed || changedByFullSync;
        }
        if (result.patches.isEmpty) {
          if (result.latestSyncSeq > lastSeq) {
            lastSeq = result.latestSyncSeq;
            await store.saveUserSyncSeq(namespace: namespace, syncSeq: lastSeq);
          }
          break;
        }
        for (final patch in result.patches) {
          if (patch.syncSeq <= lastSeq) {
            continue;
          }
          await _applyPatch(namespace, patch);
          lastSeq = patch.syncSeq;
          observedLastSeq = lastSeq;
          changed = true;
        }
        await store.saveUserSyncSeq(namespace: namespace, syncSeq: lastSeq);
        hasMore = result.hasMore;
      }
      _clearAvatarPatchSyncFailure();
      return changed;
    } catch (error, stackTrace) {
      _recordAvatarPatchSyncFailure(error, stackTrace, observedLastSeq);
      return false;
    } finally {
      _syncingUserPatches = false;
    }
  }

  Future<void> _applyPatch(
    LocalSearchNamespace namespace,
    UserSyncPatch patch,
  ) async {
    switch (patch.kind) {
      case UserSyncPatchKind.conversationAvatarUpdated:
        final payload = patch.conversationAvatarUpdated;
        if (payload == null || patch.userAvatarUpdated != null) {
          throw StateError(
            'conversation avatar patch payload does not match its kind',
          );
        }
        final conversationId = payload.conversationId.trim();
        final avatarUrl = payload.avatarUrl.trim();
        if (conversationId.isEmpty) {
          throw StateError('conversation avatar patch missing conversationId');
        }
        if (avatarUrl.isEmpty) {
          throw StateError('conversation avatar patch missing avatarUrl');
        }
        cache.applyAvatarPatch(
          conversationId,
          ConversationAvatarPatch(
            avatarUrl: avatarUrl,
            groupAvatarVersion: payload.groupAvatarVersion,
            groupAvatarSourceHash: payload.groupAvatarSourceHash,
          ),
        );
        await store.updateConversationAvatar(
          namespace: namespace,
          conversationId: conversationId,
          avatarUrl: avatarUrl,
          groupAvatarVersion: payload.groupAvatarVersion,
          groupAvatarSourceHash: payload.groupAvatarSourceHash,
        );
        return;
      case UserSyncPatchKind.userAvatarUpdated:
        final payload = patch.userAvatarUpdated;
        if (payload == null || patch.conversationAvatarUpdated != null) {
          throw StateError('user avatar patch payload does not match its kind');
        }
        final userId = payload.userId.trim();
        final avatarUrl = payload.avatarUrl.trim();
        if (userId.isEmpty || avatarUrl.isEmpty) {
          throw StateError('user avatar patch missing userId or avatarUrl');
        }
        await store.updateContactAvatar(
          namespace: namespace,
          userId: userId,
          avatarUrl: avatarUrl,
          avatarVersion: payload.avatarVersion,
        );
        return;
    }
  }

  Future<LocalSearchNamespace?> _resolveNamespace() async {
    try {
      final context = await personaContextLoader();
      return LocalSearchNamespace.fromActivePersonaContext(context);
    } catch (_) {
      return null;
    }
  }

  void _activateNamespace(LocalSearchNamespace namespace) {
    if (_activeNamespaceKey == namespace.key) {
      return;
    }
    if (_activeNamespaceKey == null) {
      _activeNamespaceKey = namespace.key;
      cache.activateNamespace(namespace.key);
      return;
    }
    _activeNamespaceKey = namespace.key;
    cache.activateNamespace(namespace.key);
  }

  void _recordAvatarPatchSyncFailure(
    Object error,
    StackTrace stackTrace,
    int? afterSeq,
  ) {
    _lastAvatarPatchSyncError = error;
    _lastAvatarPatchSyncStackTrace = stackTrace;
    _lastAvatarPatchSyncFailedAt = DateTime.now();
    _lastAvatarPatchSyncFailedAfterSeq = afterSeq;
  }

  void _clearAvatarPatchSyncFailure() {
    _lastAvatarPatchSyncError = null;
    _lastAvatarPatchSyncStackTrace = null;
    _lastAvatarPatchSyncFailedAt = null;
    _lastAvatarPatchSyncFailedAfterSeq = null;
  }
}
