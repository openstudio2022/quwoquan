import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/di/app_providers_content_facets.dart';
import 'package:quwoquan_app/runtime/di/app_providers_content_runtime.dart';
import 'package:quwoquan_app/runtime/di/app_providers_operations.dart';
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
    );
    ref.onDispose(_engine.dispose);
    unawaited(_engine.hydrate());
    return _engine.state;
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
