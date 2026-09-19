import 'dart:async';

import 'package:uuid/uuid.dart';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/config/app_content_source.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/errors/content_capability_unavailable.dart';
import 'package:quwoquan_app/runtime/di/actor_interaction_partition.dart';
import 'package:quwoquan_app/runtime/di/app_providers_content_runtime.dart';
import 'package:quwoquan_app/runtime/di/app_providers_operations.dart';
import 'package:quwoquan_app/runtime/di/app_providers_content_facets.dart';
import 'package:quwoquan_app/runtime/di/post_interaction_state_dependencies.dart';
import 'package:quwoquan_app/runtime/di/user_relationship_state_dependencies.dart';
import 'package:quwoquan_app/runtime/platform/storage/client_interaction_state_store.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/state_sync/client_state_sync.dart';
import 'package:quwoquan_app/runtime/transport/state_sync/client_state_sync_outbox_engine.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/persona_relationship_facets.dart';
import 'package:quwoquan_app/service/content_service/content/content_reaction/application/public/content_post_reaction_ports.dart';

const String _clientStateSyncOutboxStorageKey = 'client_state_sync_outbox';

/// 启动 scope 授予的本地 command 能力。在线与未装配环境恒为 false；
/// ProviderScope 销毁后授权随代际一并失效，不使用进程级布尔开关。
final localCommandExecutionEnabledProvider = Provider<bool>((ref) => false);

final class ClientStateSyncRuntimeDependencies {
  const ClientStateSyncRuntimeDependencies({
    required this.readConfig,
    required this.readPersistedState,
    required this.writePersistedState,
    required this.executeEntry,
    required this.recoverEntry,
    this.prepareFollowEvidence,
    this.preparePostEvidence,
  });

  final ClientStateSyncConfigReader readConfig;
  final ClientStateSyncOutboxReader readPersistedState;
  final ClientStateSyncOutboxWriter writePersistedState;
  final ClientStateSyncEntryExecutor executeEntry;
  final ClientStateSyncEntryRecoverer recoverEntry;
  final Future<ClientStateSyncPreparedEvidence> Function(
    String personaId,
    String sourceSurfaceId,
  )?
  prepareFollowEvidence;
  final Future<ClientStateSyncPreparedEvidence> Function(String postId)?
  preparePostEvidence;
}

/// Test suites may replace this single typed boundary with fixed config,
/// storage and executor callbacks. Production always maps to the canonical
/// object ports below.
final clientStateSyncRuntimeDependenciesProvider =
    Provider<ClientStateSyncRuntimeDependencies>((ref) {
      final partition = ref.watch(actorInteractionPartitionProvider);
      final storageKey = partition.boxName(_clientStateSyncOutboxStorageKey);
      final networkAllowed = CloudRuntimeConfig.networkAccessAllowed;
      final localCommandExecution = ref.watch(
        localCommandExecutionEnabledProvider,
      );
      return ClientStateSyncRuntimeDependencies(
        readConfig: () =>
            ref.read(contentRuntimeConfigProvider).clientStateSync,
        readPersistedState: () => readPersistedInteractionMap(storageKey),
        writePersistedState: (value) {
          if ((!networkAllowed && !localCommandExecution) || !ref.mounted) {
            throw contentCapabilityUnavailable('client_state_sync');
          }
          return writePersistedInteractionMap(storageKey, value);
        },
        executeEntry: (entry) {
          if ((!networkAllowed && !localCommandExecution) || !ref.mounted) {
            throw contentCapabilityUnavailable('client_state_sync');
          }
          return _executeClientStateSyncEntry(ref, entry);
        },
        recoverEntry: (entry) {
          if ((!networkAllowed && !localCommandExecution) || !ref.mounted) {
            throw contentCapabilityUnavailable('client_state_sync');
          }
          return _recoverClientStateSyncEntry(ref, entry);
        },
        prepareFollowEvidence: (personaId, sourceSurfaceId) async {
          final surface = AppUiSurfaces.byId[sourceSurfaceId];
          if (surface == null) throw StateError('invalid source surface');
          final basis = await ref
              .read(personaRelationshipDurableCommandWriterProvider(surface))
              .getMutationBasis(personaId);
          return ClientStateSyncPreparedEvidence(
            idempotencyKey: const Uuid().v4(),
            mutationBasis: basis.mutationBasis,
            expectedVersion: basis.expectedVersion,
            actorRef: partition.key,
            canonicalObjectId: basis.targetPersonaId,
          );
        },
        preparePostEvidence: (postId) async {
          final basis = await ref
              .read(contentPostReactionFacetProvider)
              .getReactionState(
                GetContentPostReactionStateQuery(postId: postId),
              );
          return ClientStateSyncPreparedEvidence(
            idempotencyKey: const Uuid().v4(),
            mutationBasis: basis.mutationBasis,
            expectedVersion: basis.version,
            actorRef: partition.key,
          );
        },
      );
    });

Future<ClientStateSyncReceipt> _executeClientStateSyncEntry(
  Ref ref,
  ClientStateSyncOutboxEntry entry,
) async {
  switch ('${entry.objectType}:${entry.intentType}') {
    case 'profile:follow':
      final surface = AppUiSurfaces.byId[entry.sourceSurfaceId.trim()];
      if (surface == null) throw StateError('关注同步缺少有效 source surface');
      final writer = ref.read(
        personaRelationshipDurableCommandWriterProvider(surface),
      );
      final evidence = PersonaRelationshipMutationEvidence(
        idempotencyKey: entry.idempotencyKey,
        mutationBasis: entry.mutationBasis,
        expectedVersion: entry.expectedVersion,
      );
      final result = entry.desiredBoolValue
          ? await writer.followWithEvidence(
              entry.objectId,
              sourceSurfaceId: entry.sourceSurfaceId,
              evidence: evidence,
            )
          : await writer.unfollowWithEvidence(
              entry.objectId,
              evidence: evidence,
            );
      return ClientStateSyncReceipt(
        outcome: ClientStateSyncReceiptOutcome.committed,
        replayed: result.idempotentReplay,
        committedVersion: entry.expectedVersion + 1,
        changed: !result.idempotentReplay,
      );
    case 'post:like':
      final writer = ref.read(contentPostReactionDurableFacetProvider);
      final evidence = ContentReactionMutationEvidence(
        idempotencyKey: entry.idempotencyKey,
        mutationBasis: entry.mutationBasis,
        expectedVersion: entry.expectedVersion,
      );
      final result = entry.desiredBoolValue
          ? await writer.likePostWithEvidence(
              entry.objectId,
              evidence: evidence,
            )
          : await writer.unlikePostWithEvidence(
              entry.objectId,
              evidence: evidence,
            );
      return ClientStateSyncReceipt(
        outcome: ClientStateSyncReceiptOutcome.committed,
        replayed: result.replayed,
        committedVersion: result.version,
        changed: result.changed,
      );
    default:
      throw StateError(
        'unsupported client state sync entry: ${entry.objectType}:${entry.intentType}',
      );
  }
}

Future<ClientStateSyncReceipt> _recoverClientStateSyncEntry(
  Ref ref,
  ClientStateSyncOutboxEntry entry,
) async {
  if (entry.objectType == 'post' && entry.intentType == 'like') {
    final value = await ref
        .read(contentPostReactionDurableFacetProvider)
        .recoverPost(
          entry.objectId,
          operation: entry.desiredBoolValue ? 'LikePost' : 'UnlikePost',
          idempotencyKey: entry.idempotencyKey,
        );
    return _contentRecoveryReceipt(value);
  }
  if (entry.objectType != 'profile' || entry.intentType != 'follow') {
    throw StateError('unsupported recovery entry');
  }
  final surface = AppUiSurfaces.byId[entry.sourceSurfaceId.trim()];
  if (surface == null) {
    throw StateError('invalid source surface');
  }
  final writer = ref.read(
    personaRelationshipDurableCommandWriterProvider(surface),
  );
  final operation = entry.desiredBoolValue
      ? PersonaRelationshipMutationAction.follow
      : PersonaRelationshipMutationAction.unfollow;
  final recovered = await writer.recover(
    entry.objectId,
    operation: operation,
    idempotencyKey: entry.idempotencyKey,
  );
  return _relationshipRecoveryReceipt(recovered);
}

ClientStateSyncReceipt _contentRecoveryReceipt(
  ContentReactionCommandRecoverySlice value,
) {
  final outcome = switch (value.outcome) {
    ContentReactionReceiptOutcome.committed =>
      ClientStateSyncReceiptOutcome.committed,
    ContentReactionReceiptOutcome.rejected =>
      ClientStateSyncReceiptOutcome.rejected,
    ContentReactionReceiptOutcome.expired =>
      ClientStateSyncReceiptOutcome.expired,
    ContentReactionReceiptOutcome.historyUnavailable =>
      ClientStateSyncReceiptOutcome.historyUnavailable,
  };
  return ClientStateSyncReceipt(
    outcome: outcome,
    replayed: value.replayed,
    committedVersion: value.committedVersion,
    changed: value.changed,
  );
}

ClientStateSyncReceipt _relationshipRecoveryReceipt(
  PersonaRelationshipCommandRecoverySlice value,
) {
  final outcome = switch (value.outcome) {
    PersonaRelationshipReceiptOutcome.committed =>
      ClientStateSyncReceiptOutcome.committed,
    PersonaRelationshipReceiptOutcome.rejected =>
      ClientStateSyncReceiptOutcome.rejected,
    PersonaRelationshipReceiptOutcome.expired =>
      ClientStateSyncReceiptOutcome.expired,
    PersonaRelationshipReceiptOutcome.historyUnavailable =>
      ClientStateSyncReceiptOutcome.historyUnavailable,
  };
  return ClientStateSyncReceipt(
    outcome: outcome,
    replayed: value.replayed,
    committedVersion: value.committedVersion,
    changed: value.changed,
  );
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
  late ClientStateSyncRuntimeDependencies _dependencies;

  bool get _localCommandExecution =>
      ref.read(localCommandExecutionEnabledProvider);

  bool get _isBundledContent =>
      CloudRuntimeConfig.isHydrated &&
      CloudRuntimeConfig.contentSource == AppContentSource.bundledSnapshot;

  void _requireRemoteWrites() {
    if (_isBundledContent && !_localCommandExecution) {
      throw contentCapabilityUnavailable('client_state_sync');
    }
  }

  @override
  ClientStateSyncOutboxState build() {
    if (_isBundledContent && !_localCommandExecution) {
      return const ClientStateSyncOutboxState();
    }
    final dependencies = ref.watch(clientStateSyncRuntimeDependenciesProvider);
    _dependencies = dependencies;
    var active = true;
    final engine = ClientStateSyncOutboxEngine(
      readConfig: dependencies.readConfig,
      readPersistedState: dependencies.readPersistedState,
      writePersistedState: dependencies.writePersistedState,
      executeEntry: dependencies.executeEntry,
      recoverEntry: dependencies.recoverEntry,
      onStateChanged: (nextState) {
        if (active && ref.mounted) {
          state = nextState;
        }
      },
      onTerminalFailure: (entry) {
        if (!active || !ref.mounted) {
          return;
        }
        _rollbackOptimisticState(entry);
        ref
            .read(clientStateSyncTerminalFailureProvider.notifier)
            .publish(entry);
      },
    );
    _engine = engine;
    ref.onDispose(() {
      active = false;
      engine.dispose();
    });
    unawaited(engine.hydrate());
    return engine.state;
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

  Future<String> enqueueFollow({
    required String personaId,
    required bool currentFollowing,
    required bool shouldFollow,
    required String sourceSurfaceId,
    bool flushImmediately = false,
  }) async {
    _requireRemoteWrites();
    try {
      final prepare = _dependencies.prepareFollowEvidence;
      if (prepare == null) {
        throw StateError('follow evidence preparer unavailable');
      }
      final evidence = await prepare(personaId, sourceSurfaceId);
      final canonicalPersonaId = evidence.canonicalObjectId.trim().isEmpty
          ? personaId
          : evidence.canonicalObjectId.trim();
      await _engine.enqueueFollow(
        personaId: canonicalPersonaId,
        currentFollowing: currentFollowing,
        shouldFollow: shouldFollow,
        sourceSurfaceId: sourceSurfaceId,
        idempotencyKey: evidence.idempotencyKey,
        mutationBasis: evidence.mutationBasis,
        expectedVersion: evidence.expectedVersion,
        actorRef: evidence.actorRef,
        flushImmediately: flushImmediately,
      );
      return canonicalPersonaId;
    } catch (_) {
      ref
          .read(userRelationshipStateProvider.notifier)
          .setFollowing(personaId, currentFollowing);
      rethrow;
    }
  }

  Future<void> enqueuePostLike({
    required String postId,
    required bool currentLiked,
    required bool isLiked,
    bool flushImmediately = false,
  }) async {
    _requireRemoteWrites();
    final prepare = _dependencies.preparePostEvidence;
    if (prepare == null) {
      throw StateError('post evidence preparer unavailable');
    }
    final evidence = await prepare(postId);
    await _engine.enqueuePostLike(
      postId: postId,
      currentLiked: currentLiked,
      isLiked: isLiked,
      idempotencyKey: evidence.idempotencyKey,
      mutationBasis: evidence.mutationBasis,
      expectedVersion: evidence.expectedVersion,
      actorRef: evidence.actorRef,
      flushImmediately: flushImmediately,
    );
  }

  Future<void> flushNow() async {
    if (_isBundledContent && !_localCommandExecution) return;
    await _engine.flushNow();
  }

  void purgeForTerminalAccountClosure() {
    if (_isBundledContent) return;
    _engine.purgeForTerminalAccountClosure();
  }
}
