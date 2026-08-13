import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/di/app_providers_content_facets.dart';
import 'package:quwoquan_app/runtime/di/app_providers_content_runtime.dart';
import 'package:quwoquan_app/runtime/di/app_providers_operations.dart';
import 'package:quwoquan_app/runtime/di/post_interaction_state_dependencies.dart';
import 'package:quwoquan_app/runtime/di/user_relationship_state_dependencies.dart';
import 'package:quwoquan_app/runtime/platform/storage/client_interaction_state_store.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/state_sync/client_state_sync.dart';
import 'package:quwoquan_app/runtime/transport/state_sync/client_state_sync_outbox_engine.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

const String _clientStateSyncOutboxStorageKey = 'client_state_sync_outbox';

final class ClientStateSyncRuntimeDependencies {
  const ClientStateSyncRuntimeDependencies({
    required this.readConfig,
    required this.readPersistedState,
    required this.writePersistedState,
    required this.executeEntry,
  });

  final ClientStateSyncConfigReader readConfig;
  final ClientStateSyncOutboxReader readPersistedState;
  final ClientStateSyncOutboxWriter writePersistedState;
  final ClientStateSyncEntryExecutor executeEntry;
}

/// Test suites may replace this single typed boundary with fixed config,
/// storage and executor callbacks. Production always maps to the canonical
/// object ports below.
final clientStateSyncRuntimeDependenciesProvider =
    Provider<ClientStateSyncRuntimeDependencies>((ref) {
      return ClientStateSyncRuntimeDependencies(
        readConfig: () =>
            ref.read(contentRuntimeConfigProvider).clientStateSync,
        readPersistedState: () =>
            readPersistedInteractionMap(_clientStateSyncOutboxStorageKey),
        writePersistedState: (value) => writePersistedInteractionMap(
          _clientStateSyncOutboxStorageKey,
          value,
        ),
        executeEntry: (entry) => _executeClientStateSyncEntry(ref, entry),
      );
    });

Future<void> _executeClientStateSyncEntry(
  Ref ref,
  ClientStateSyncOutboxEntry entry,
) async {
  switch ('${entry.objectType}:${entry.intentType}') {
    case 'profile:follow':
      final sourceSurfaceId = entry.sourceSurfaceId.trim();
      final surface = AppUiSurfaces.byId[sourceSurfaceId];
      if (surface == null) {
        throw StateError('关注同步缺少有效 source surface: ${entry.sourceSurfaceId}');
      }
      final writer = ref.read(
        personaRelationshipCommandWriterProvider(surface),
      );
      if (entry.desiredBoolValue) {
        await writer.follow(entry.objectId, sourceSurfaceId: sourceSurfaceId);
      } else {
        await writer.unfollow(entry.objectId);
      }
      return;
    case 'post:like':
      final writer = ref.read(contentPostReactionFacetProvider);
      if (entry.desiredBoolValue) {
        await writer.likePost(LikeContentPostCommand(postId: entry.objectId));
      } else {
        await writer.unlikePost(
          UnlikeContentPostCommand(postId: entry.objectId),
        );
      }
      return;
    default:
      throw StateError(
        'unsupported client state sync entry: '
        '${entry.objectType}:${entry.intentType}',
      );
  }
}

final clientStateSyncOutboxProvider =
    NotifierProvider<ClientStateSyncOutboxNotifier, ClientStateSyncOutboxState>(
      ClientStateSyncOutboxNotifier.new,
    );

/// 当前 outbox 中仍有待同步 like 意图的 postId 集合。
///
/// feed/详情以服务端 `viewerLiked` hydrate 本地点赞态时，这些 post 的本地
/// pending 意图优先，权威投影跳过它们，待 outbox flush 后由确认值收敛。
final pendingLikeSyncPostIdsProvider = Provider<Set<String>>((ref) {
  final outbox = ref.watch(clientStateSyncOutboxProvider);
  return <String>{
    for (final entry in outbox.entries)
      if (entry.objectType == 'post' &&
          entry.intentType == 'like' &&
          entry.hasPendingDelta)
        entry.objectId,
  };
});

/// outbox 终态失败通知（运行时瞬态，不持久化）。
///
/// 引擎放弃重试后由 [ClientStateSyncOutboxNotifier] 完成乐观态回滚并在此
/// 发布；壳层监听并以统一警示轻提示告知用户，消费后 [consume] 清空。
final clientStateSyncTerminalFailureProvider =
    NotifierProvider<
      ClientStateSyncTerminalFailureNotifier,
      ClientStateSyncOutboxEntry?
    >(ClientStateSyncTerminalFailureNotifier.new);

final class ClientStateSyncTerminalFailureNotifier
    extends Notifier<ClientStateSyncOutboxEntry?> {
  @override
  ClientStateSyncOutboxEntry? build() => null;

  void publish(ClientStateSyncOutboxEntry entry) {
    state = entry;
  }

  void consume() {
    state = null;
  }
}

final class ClientStateSyncOutboxNotifier
    extends Notifier<ClientStateSyncOutboxState> {
  late ClientStateSyncOutboxEngine _engine;

  @override
  ClientStateSyncOutboxState build() {
    final dependencies = ref.watch(clientStateSyncRuntimeDependenciesProvider);
    _engine = ClientStateSyncOutboxEngine(
      readConfig: dependencies.readConfig,
      readPersistedState: dependencies.readPersistedState,
      writePersistedState: dependencies.writePersistedState,
      executeEntry: dependencies.executeEntry,
      onStateChanged: (nextState) {
        if (ref.mounted) {
          state = nextState;
        }
      },
      onTerminalFailure: (entry) {
        if (!ref.mounted) {
          return;
        }
        _rollbackOptimisticState(entry);
        ref
            .read(clientStateSyncTerminalFailureProvider.notifier)
            .publish(entry);
      },
    );
    ref.onDispose(_engine.dispose);
    unawaited(_engine.hydrate());
    return _engine.state;
  }

  /// 终态失败回滚：乐观布尔态回到已确认值；计数由权威投影下次刷新收敛。
  void _rollbackOptimisticState(ClientStateSyncOutboxEntry entry) {
    final confirmed = entry.confirmedBoolValue ?? !entry.desiredBoolValue;
    switch ('${entry.objectType}:${entry.intentType}') {
      case 'post:like':
        ref
            .read(postInteractionStateProvider.notifier)
            .setLiked(entry.objectId, confirmed);
      case 'profile:follow':
        ref
            .read(userRelationshipStateProvider.notifier)
            .setFollowing(entry.objectId, confirmed);
    }
  }

  void enqueueFollow({
    required String personaId,
    required bool currentFollowing,
    required bool shouldFollow,
    required String sourceSurfaceId,
    bool flushImmediately = false,
  }) {
    _engine.enqueueFollow(
      personaId: personaId,
      currentFollowing: currentFollowing,
      shouldFollow: shouldFollow,
      sourceSurfaceId: sourceSurfaceId,
      flushImmediately: flushImmediately,
    );
  }

  void enqueuePostLike({
    required String postId,
    required bool currentLiked,
    required bool isLiked,
    bool flushImmediately = false,
  }) {
    _engine.enqueuePostLike(
      postId: postId,
      currentLiked: currentLiked,
      isLiked: isLiked,
      flushImmediately: flushImmediately,
    );
  }

  Future<void> flushNow() => _engine.flushNow();

  void purgeForTerminalAccountClosure() {
    _engine.purgeForTerminalAccountClosure();
  }
}
