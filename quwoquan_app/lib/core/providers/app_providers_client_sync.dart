import 'dart:async';
import 'dart:developer' as developer;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:uuid/uuid.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/assistant/capabilities/assistant_presentation_capability_catalog.dart';
import 'package:quwoquan_app/application/assistant/learning/assistant_learning_fact_outbox.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_trace_context_store.dart';
import 'package:quwoquan_app/assistant/infrastructure/infrastructure.dart'
    show AppLogService, AppLogType, AppLogLevel, AppLogContext;
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/context/actor_queue_partition.dart';
import 'package:quwoquan_app/core/di/generated_operation_client_dependencies.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/platform/platform_target.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';
import 'package:quwoquan_app/cloud/remote/assistant/assistant_learning_fact_remote.dart';
import 'package:quwoquan_app/cloud/remote/assistant/assistant_skill_catalog_remote.dart';
import 'package:quwoquan_app/cloud/remote/assistant/assistant_skill_activity_remote.dart';
import 'package:quwoquan_app/cloud/remote/assistant/assistant_skill_consent_remote.dart';
import 'package:quwoquan_app/cloud/remote/assistant/assistant_skill_data_control_remote.dart';
import 'package:quwoquan_app/cloud/remote/assistant/assistant_skill_subscription_remote.dart';
import 'package:quwoquan_app/cloud/remote/assistant/assistant_skill_user_setting_remote.dart';
import 'package:quwoquan_app/cloud/remote/entity/homepage/homepage_command_remote.dart';
import 'package:quwoquan_app/cloud/services/entity/entity_repository.dart';
import 'package:quwoquan_app/cloud/services/entity/remote/homepage_query_remote.dart';
import 'package:quwoquan_app/integration/external_integration/connector_connection/application/connector_management_facet.dart';
import 'package:quwoquan_app/notification/notification_delivery/notification/application/notification_facets.dart';
import 'package:quwoquan_app/notification/notification_delivery/notification/adapters/app_message_facets_remote.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/models/client_state_sync.dart';
import 'package:quwoquan_app/core/services/cache/cache_telemetry_sink.dart';
import 'package:quwoquan_app/core/di/ops_event_dependencies.dart';
import 'package:quwoquan_app/runtime/di/integration_dependencies.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_reporter.dart';
import 'package:quwoquan_app/core/platform/platform_providers.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    hide ContentDiscoveryFeedQuery;
import 'package:quwoquan_app/core/providers/app_providers_app_state.dart';
import 'package:quwoquan_app/core/providers/app_providers_chat_search.dart';
import 'package:quwoquan_app/core/providers/app_providers_content_facets.dart';
import 'package:quwoquan_app/core/providers/app_providers_content_runtime.dart';
import 'package:quwoquan_app/core/providers/app_providers_interaction_state.dart';
import 'package:quwoquan_app/core/providers/app_providers_operations.dart';
class ClientStateSyncOutboxNotifier
    extends Notifier<ClientStateSyncOutboxState> {
  Timer? _flushTimer;
  final Map<String, bool> _inFlightDesiredValues = <String, bool>{};
  bool _terminallyPurged = false;

  @override
  ClientStateSyncOutboxState build() {
    unawaited(_hydratePersistedState());
    ref.onDispose(() {
      _flushTimer?.cancel();
      _inFlightDesiredValues.clear();
    });
    return const ClientStateSyncOutboxState();
  }

  Future<void> _hydratePersistedState() async {
    final raw = await readPersistedInteractionMap(
      clientStateSyncOutboxStorageKey,
    );
    if (!ref.mounted || _terminallyPurged) {
      return;
    }
    if (raw == null) {
      return;
    }
    try {
      state = state.copyWith(
        entries: _dropResolvedEntries(
          ClientStateSyncOutboxState.fromMap(raw).entries,
        ),
      );
    } on FormatException {
      state = const ClientStateSyncOutboxState();
      await writePersistedInteractionMap(
        clientStateSyncOutboxStorageKey,
        state.toMap(),
      );
    }
    _scheduleNextFlush();
  }

  void enqueueFollow({
    required String personaId,
    required bool currentFollowing,
    required bool shouldFollow,
    required String sourceSurfaceId,
    bool flushImmediately = false,
  }) {
    _upsertEntry(
      objectType: 'profile',
      objectId: personaId,
      intentType: 'follow',
      currentBoolValue: currentFollowing,
      desiredBoolValue: shouldFollow,
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
    _upsertEntry(
      objectType: 'post',
      objectId: postId,
      intentType: 'like',
      currentBoolValue: currentLiked,
      desiredBoolValue: isLiked,
      flushImmediately: flushImmediately,
    );
  }

  Future<void> flushNow() async {
    if (_terminallyPurged) {
      return;
    }
    final config = ref.read(contentRuntimeConfigProvider).clientStateSync;
    final now = DateTime.now();
    final dueKeys = state.entries
        .where(
          (entry) =>
              !_isInFlight(entry.coalesceKey) &&
              entry.hasPendingDelta &&
              !entry.nextFlushAt.isAfter(now),
        )
        .take(config.maxBatchSize)
        .map((entry) => entry.coalesceKey)
        .toList(growable: false);
    if (dueKeys.isEmpty) {
      _scheduleNextFlush();
      return;
    }

    for (final coalesceKey in dueKeys) {
      if (_terminallyPurged) {
        break;
      }
      final entry = _entryForKey(coalesceKey);
      if (entry == null ||
          _isInFlight(coalesceKey) ||
          !entry.hasPendingDelta ||
          entry.nextFlushAt.isAfter(DateTime.now())) {
        continue;
      }
      _inFlightDesiredValues[coalesceKey] = entry.desiredBoolValue;
      try {
        await _flushEntry(entry);
        if (_terminallyPurged) {
          continue;
        }
        _onFlushSucceeded(
          coalesceKey: coalesceKey,
          flushedDesiredBoolValue: entry.desiredBoolValue,
        );
      } catch (_) {
        if (!_terminallyPurged) {
          _onFlushFailed(coalesceKey: coalesceKey, config: config);
        }
      } finally {
        _inFlightDesiredValues.remove(coalesceKey);
      }
    }
    if (_terminallyPurged) {
      return;
    }
    unawaited(_persistState());
    _scheduleNextFlush();
  }

  Future<void> _flushEntry(ClientStateSyncOutboxEntry entry) async {
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
        final repo = ref.read(contentPostReactionFacetProvider);
        if (entry.desiredBoolValue) {
          await repo.likePost(LikeContentPostCommand(postId: entry.objectId));
        } else {
          await repo.unlikePost(
            UnlikeContentPostCommand(postId: entry.objectId),
          );
        }
        return;
    }
  }

  void _upsertEntry({
    required String objectType,
    required String objectId,
    required String intentType,
    required bool? currentBoolValue,
    required bool desiredBoolValue,
    String sourceSurfaceId = '',
    required bool flushImmediately,
  }) {
    if (_terminallyPurged) {
      return;
    }
    final config = ref.read(contentRuntimeConfigProvider).clientStateSync;
    final now = DateTime.now();
    final coalesceKey = '$objectType:$intentType:$objectId';
    final existingEntry = _entryForKey(coalesceKey);
    final confirmedBoolValue =
        existingEntry?.confirmedBoolValue ?? currentBoolValue;
    if (!_isInFlight(coalesceKey) &&
        confirmedBoolValue != null &&
        confirmedBoolValue == desiredBoolValue) {
      _removeEntry(coalesceKey);
      unawaited(_persistState());
      _scheduleNextFlush();
      return;
    }
    _replaceEntry(
      ClientStateSyncOutboxEntry(
        coalesceKey: coalesceKey,
        objectType: objectType,
        objectId: objectId,
        intentType: intentType,
        desiredBoolValue: desiredBoolValue,
        sourceSurfaceId: sourceSurfaceId,
        nextFlushAt: flushImmediately ? now : now.add(config.flushDelay),
        confirmedBoolValue: confirmedBoolValue,
        retryCount: existingEntry?.retryCount ?? 0,
      ),
    );
    unawaited(_persistState());
    _scheduleNextFlush();
  }

  void _scheduleNextFlush() {
    _flushTimer?.cancel();
    if (_terminallyPurged || state.entries.isEmpty) return;
    final wakeTimes = state.entries
        .where(
          (entry) => !_isInFlight(entry.coalesceKey) && entry.hasPendingDelta,
        )
        .map((entry) => entry.nextFlushAt)
        .toList(growable: false);
    if (wakeTimes.isEmpty) {
      return;
    }
    final nextWakeAt = wakeTimes.reduce((a, b) => a.isBefore(b) ? a : b);
    final delay = nextWakeAt.difference(DateTime.now());
    _flushTimer = Timer(delay.isNegative ? Duration.zero : delay, () {
      flushNow();
    });
  }

  bool _isInFlight(String coalesceKey) {
    return _inFlightDesiredValues.containsKey(coalesceKey);
  }

  ClientStateSyncOutboxEntry? _entryForKey(String coalesceKey) {
    for (final entry in state.entries.reversed) {
      if (entry.coalesceKey == coalesceKey) {
        return entry;
      }
    }
    return null;
  }

  void _replaceEntry(ClientStateSyncOutboxEntry entry) {
    final nextEntries = List<ClientStateSyncOutboxEntry>.from(state.entries)
      ..removeWhere((item) => item.coalesceKey == entry.coalesceKey)
      ..add(entry);
    state = state.copyWith(entries: nextEntries);
  }

  void _removeEntry(String coalesceKey) {
    state = state.copyWith(
      entries: state.entries
          .where((entry) => entry.coalesceKey != coalesceKey)
          .toList(growable: false),
    );
  }

  void _onFlushSucceeded({
    required String coalesceKey,
    required bool flushedDesiredBoolValue,
  }) {
    final currentEntry = _entryForKey(coalesceKey);
    if (currentEntry == null) {
      return;
    }
    final reconciledEntry = currentEntry.copyWith(
      confirmedBoolValue: flushedDesiredBoolValue,
      retryCount: 0,
    );
    if (!reconciledEntry.hasPendingDelta) {
      _removeEntry(coalesceKey);
      return;
    }
    _replaceEntry(reconciledEntry);
  }

  void _onFlushFailed({
    required String coalesceKey,
    required ClientStateSyncConfig config,
  }) {
    final currentEntry = _entryForKey(coalesceKey);
    if (currentEntry == null) {
      return;
    }
    if (!currentEntry.hasPendingDelta) {
      _removeEntry(coalesceKey);
      return;
    }
    _replaceEntry(
      currentEntry.copyWith(
        retryCount: currentEntry.retryCount + 1,
        nextFlushAt: DateTime.now().add(config.retryDelay),
      ),
    );
  }

  List<ClientStateSyncOutboxEntry> _dropResolvedEntries(
    List<ClientStateSyncOutboxEntry> entries,
  ) {
    return entries
        .where((entry) => entry.hasPendingDelta)
        .toList(growable: false);
  }

  Future<void> _persistState() async {
    if (_terminallyPurged) {
      return;
    }
    await writePersistedInteractionMap(
      clientStateSyncOutboxStorageKey,
      state.toMap(),
    );
  }

  void purgeForTerminalAccountClosure() {
    _terminallyPurged = true;
    _flushTimer?.cancel();
    _flushTimer = null;
    _inFlightDesiredValues.clear();
    state = const ClientStateSyncOutboxState();
  }
}

final userRelationshipStateProvider =
    NotifierProvider<UserRelationshipStateNotifier, UserRelationshipState>(
      UserRelationshipStateNotifier.new,
    );

final postInteractionStateProvider =
    NotifierProvider<PostInteractionStateNotifier, PostInteractionState>(
      PostInteractionStateNotifier.new,
    );

final clientStateSyncOutboxProvider =
    NotifierProvider<ClientStateSyncOutboxNotifier, ClientStateSyncOutboxState>(
      ClientStateSyncOutboxNotifier.new,
    );

/// assistant 域共享 Remote 实例：8 个窄 Facet provider 共用同一个
/// [RemoteAssistantRepository]（一个类实现多个窄面，与 content 域同构）。
final _assistantRemoteProvider = Provider<RemoteAssistantRepository>((ref) {
  return RemoteAssistantRepository(
    operationClient: ref.watch(generatedCloudOperationClientProvider),
    presentationCapabilities: ref.watch(
      assistantPresentationCapabilitySnapshotFactoryProvider,
    ),
    invocationContext:
        (clientPageId, {idempotencyKey, networkSurface = false}) =>
            _assistantOperationInvocationContext(
              ref,
              clientPageId: clientPageId,
              idempotencyKey: idempotencyKey,
              networkSurface: networkSurface,
            ),
  );
});

final assistantPresentationCapabilitySnapshotFactoryProvider =
    Provider<AssistantPresentationCapabilitySnapshotFactory>((ref) {
      return (surfacePolicy) =>
          _assistantPresentationCapabilities(ref, surfacePolicy);
    });

AssistantPresentationCapabilitySnapshot _assistantPresentationCapabilities(
  Ref ref,
  AssistantPresentationSurfacePolicy surfacePolicy,
) {
  final appearance = ref.read(appearanceSnapshotProvider);
  final viewportWidth = appearance.responsiveState.size.width;
  if (!viewportWidth.isFinite || viewportWidth <= 0) {
    throw StateError(
      'Assistant presentation viewport is unavailable before the App shell snapshot',
    );
  }
  final networkClass = ref.read(appTelemetryContextProvider).networkClass;
  return AssistantPresentationCapabilitySnapshot(
    surfacePolicy: surfacePolicy,
    viewportClass: AssistantPresentationViewportClass.fromWidth(
      viewportWidth,
      compactBelow: AppSpacing.markdownCompactBreakpoint,
      expandedFrom: AppSpacing.expandedBreakpoint,
    ),
    platform: platformWireName(ref.read(platformTargetProvider)),
    darkTheme: appearance.isDark,
    textScale: appearance.textScaleFactor,
    reducedMotion: appearance.disableAnimations,
    offline: networkClass == 'none',
    // No canonical MediaAssetRef -> delivery URL resolver is wired into the
    // Assistant renderer yet, so production must not advertise media nodes.
    mediaEnabled: false,
    // The personal Assistant page owns typed preference/tool continuation
    // handlers. Global network search owns no presentation action handler.
    actionsEnabled:
        surfacePolicy == AssistantPresentationSurfacePolicy.personal,
  );
}

CloudOperationInvocationContext _assistantOperationInvocationContext(
  Ref ref, {
  required String clientPageId,
  String? idempotencyKey,
  bool networkSurface = false,
}) {
  final accountId = ref.read(resolvedOwnerUserIdProvider).trim();
  final personaId = ref.read(currentUserIdProvider).trim();
  return CloudOperationInvocationContext(
    surfaceId: networkSurface
        ? AppUiSurfaces.globalSearchNetworkResults.id
        : AppUiSurfaces.personalAssistantDialog.id,
    routeId: networkSurface
        ? AppUiSurfaces.globalSearchNetworkResults.routeId
        : AppUiSurfaces.personalAssistantDialog.routeId,
    clientPageId: clientPageId,
    actor: CloudOperationActorContext(
      accountId: accountId.isEmpty ? null : accountId,
      personaId: personaId.isEmpty ? null : personaId,
    ),
    idempotencyKey: idempotencyKey,
  );
}

CloudOperationInvocationContext _assistantSkillCenterInvocationContext(
  Ref ref, {
  required String clientPageId,
  String? idempotencyKey,
}) {
  final accountId = ref.read(resolvedOwnerUserIdProvider).trim();
  final personaId = ref.read(currentUserIdProvider).trim();
  return CloudOperationInvocationContext(
    surfaceId: AppUiSurfaces.assistantSkills.id,
    routeId: AppUiSurfaces.assistantSkills.routeId,
    clientPageId: clientPageId,
    actor: CloudOperationActorContext(
      accountId: accountId.isEmpty ? null : accountId,
      personaId: personaId.isEmpty ? null : personaId,
    ),
    idempotencyKey: idempotencyKey,
  );
}

/// Production composition is Remote-only. Alpha/test adapters must override
/// these Facets from their physically separate composition root.
final assistantSessionRunFacetProvider = Provider<AssistantSessionRunFacet>(
  (ref) => ref.watch(_assistantRemoteProvider),
);

final assistantRunControlFacetProvider = Provider<AssistantRunControlFacet>(
  (ref) => ref.watch(_assistantRemoteProvider),
);

final assistantSkillSubscriptionFacetProvider =
    Provider<AssistantSkillSubscriptionFacet>(
      (ref) => RemoteAssistantSkillSubscriptionAdapter(
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId, {idempotencyKey}) =>
            _assistantSkillCenterInvocationContext(
              ref,
              clientPageId: clientPageId,
              idempotencyKey: idempotencyKey,
            ),
      ),
    );

final assistantSkillCatalogFacetProvider = Provider<AssistantSkillCatalogFacet>(
  (ref) => RemoteAssistantSkillCatalogAdapter(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId) =>
        _assistantSkillCenterInvocationContext(ref, clientPageId: clientPageId),
  ),
);

final assistantSkillUserSettingFacetProvider =
    Provider<AssistantSkillUserSettingFacet>(
      (ref) => RemoteAssistantSkillUserSettingAdapter(
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId, {idempotencyKey}) =>
            _assistantSkillCenterInvocationContext(
              ref,
              clientPageId: clientPageId,
              idempotencyKey: idempotencyKey,
            ),
      ),
    );

final assistantSkillConsentFacetProvider = Provider<AssistantSkillConsentFacet>(
  (ref) {
    final accountId = ref.watch(resolvedOwnerUserIdProvider).trim();
    final consentAccountId = accountId;
    final remote = RemoteAssistantSkillConsentAdapter(
      client: ref.watch(generatedCloudOperationClientProvider),
      invocationContext: (clientPageId, {idempotencyKey}) =>
          _assistantSkillCenterInvocationContext(
            ref,
            clientPageId: clientPageId,
            idempotencyKey: idempotencyKey,
          ),
    );
    return AssistantConsentStore.decorateRemoteSuccess(
      accountId: consentAccountId,
      remote: remote,
    );
  },
);

final assistantSkillActivityQueryProvider =
    Provider<AssistantSkillActivityQuery>(
      (ref) => RemoteAssistantSkillActivityAdapter(
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId) =>
            _assistantSkillCenterInvocationContext(
              ref,
              clientPageId: clientPageId,
            ),
      ),
    );

final assistantSkillDataControlFacetProvider =
    Provider<AssistantSkillDataControlFacet>(
      (ref) => RemoteAssistantSkillDataControlAdapter(
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId, {idempotencyKey}) =>
            _assistantSkillCenterInvocationContext(
              ref,
              clientPageId: clientPageId,
              idempotencyKey: idempotencyKey,
            ),
      ),
    );

final assistantConnectorManagementFacetProvider =
    Provider<ConnectorManagementFacet>((ref) {
      return IntegrationProductionComposition.generatedAdapter<
        ConnectorManagementFacet
      >(
        IntegrationProductionAdapter.connectorManagement,
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (String clientPageId, {String? idempotencyKey}) =>
            _assistantSkillCenterInvocationContext(
              ref,
              clientPageId: clientPageId,
              idempotencyKey: idempotencyKey,
            ),
      );
    });

final assistantLearningFactAppendFacetProvider =
    Provider<AssistantLearningFactAppendFacet>(
      (ref) => RemoteAssistantLearningFactAppendAdapter(
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId, {required idempotencyKey}) =>
            _assistantOperationInvocationContext(
              ref,
              clientPageId: clientPageId,
              idempotencyKey: idempotencyKey,
            ),
      ),
    );

final assistantLearningFactOutboxEnvironmentProvider = Provider<String>(
  (_) => CloudRuntimeConfig.appRuntimeEnv,
);

final assistantLearningFactOutboxProvider =
    NotifierProvider<AssistantLearningFactOutboxNotifier, int>(
      AssistantLearningFactOutboxNotifier.new,
    );

final class AssistantLearningFactOutboxNotifier extends Notifier<int> {
  static const Duration _retryInterval = Duration(seconds: 15);

  late AssistantLearningFactOutbox _outbox;
  Timer? _retryTimer;

  @override
  int build() {
    final accountId = ref.watch(resolvedOwnerUserIdProvider).trim();
    final personaId = ref.watch(currentUserIdProvider).trim();
    _outbox = AssistantLearningFactOutbox(
      ActorQueuePartition(
        environment: ref.watch(assistantLearningFactOutboxEnvironmentProvider),
        accountId: accountId,
        personaId: personaId,
        deviceId: CloudRequestHeaders.deviceActorId ?? '',
      ),
      ref.watch(actorQueueStorageProvider),
      ref.watch(assistantLearningFactAppendFacetProvider),
    );
    ref.onDispose(_outbox.dispose);
    ref.onDispose(() => _retryTimer?.cancel());
    unawaited(_restoreAndFlush());
    return 0;
  }

  Future<bool> enqueue(AssistantLearningFactAppendCommand fact) async {
    final persisted = await _outbox.enqueue(fact);
    if (!ref.mounted) {
      return persisted;
    }
    final pendingCount = await _outbox.pendingCount();
    if (!ref.mounted) {
      return persisted;
    }
    state = pendingCount;
    _scheduleRetry(pendingCount);
    if (persisted && ref.mounted) {
      unawaited(flush());
    }
    return persisted;
  }

  Future<void> flush() async {
    try {
      await _outbox.flush();
      if (!ref.mounted) {
        return;
      }
      final pendingCount = await _outbox.pendingCount();
      if (ref.mounted) {
        state = pendingCount;
        _scheduleRetry(pendingCount);
      }
    } catch (error, stackTrace) {
      developer.log(
        'assistant learning fact outbox flush failed',
        name: 'assistant_learning_fact_outbox',
        error: error,
        stackTrace: stackTrace,
      );
    }
  }

  Future<void> _restoreAndFlush() async {
    try {
      if (!ref.mounted) {
        return;
      }
      final pendingCount = await _outbox.pendingCount();
      if (!ref.mounted) {
        return;
      }
      state = pendingCount;
      _scheduleRetry(pendingCount);
      if (pendingCount > 0) {
        await flush();
      }
    } catch (error, stackTrace) {
      developer.log(
        'assistant learning fact outbox restore failed',
        name: 'assistant_learning_fact_outbox',
        error: error,
        stackTrace: stackTrace,
      );
    }
  }

  void _scheduleRetry(int pendingCount) {
    _retryTimer?.cancel();
    _retryTimer = null;
    if (pendingCount <= 0 || !ref.mounted) {
      return;
    }
    _retryTimer = Timer(_retryInterval, () {
      if (ref.mounted) {
        unawaited(flush());
      }
    });
  }
}

final assistantPersonalizationFacetProvider =
    Provider<AssistantPersonalizationFacet>(
      (ref) => ref.watch(_assistantRemoteProvider),
    );

final assistantPersonalDataFacetProvider = Provider<AssistantPersonalDataFacet>(
  (ref) => ref.watch(_assistantRemoteProvider),
);

final assistantPreferenceFacetProvider = Provider<AssistantPreferenceFacet>(
  (ref) => ref.watch(_assistantRemoteProvider),
);

final assistantSearchRunFacetProvider = Provider<AssistantSearchRunFacet>(
  (ref) => ref.watch(_assistantRemoteProvider),
);

final assistantCreationRunFacetProvider = Provider<AssistantCreationRunFacet>(
  (ref) => ref.watch(_assistantRemoteProvider),
);

final _remoteAppMessageAdapterProvider = Provider<RemoteAppMessageAdapter>((
  ref,
) {
  return RemoteAppMessageAdapter(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId) =>
        _notificationInvocationContext(ref, clientPageId: clientPageId),
  );
});

/// Production composition is Remote-only. Alpha/test adapters must override
/// these Facets from their physically separate composition root.
final appMessageQueryProvider = Provider<AppMessageQuery>(
  (ref) => ref.watch(_remoteAppMessageAdapterProvider),
);

final appMessageCommandWriterProvider = Provider<AppMessageCommandWriter>(
  (ref) => ref.watch(_remoteAppMessageAdapterProvider),
);

CloudOperationInvocationContext _notificationInvocationContext(
  Ref ref, {
  required String clientPageId,
}) {
  final accountId = ref.read(resolvedOwnerUserIdProvider).trim();
  final persona = ref.read(activePersonaContextProvider).asData?.value;
  final personaId = persona?.personaId.trim() ?? '';
  // AppMessage inbox 的宿主面是消息页通知维度（chatList surface）；
  // metadata ui_surfaces.yaml 已绑定对应 operation。
  return CloudOperationInvocationContext(
    surfaceId: AppUiSurfaces.chatList.id,
    clientPageId: clientPageId,
    routeId: AppUiSurfaces.chatList.routeId,
    actor: CloudOperationActorContext(
      accountId: accountId.isEmpty ? null : accountId,
      personaId: personaId.isEmpty ? null : personaId,
    ),
  );
}

final cacheTelemetrySinkProvider = Provider<CacheTelemetrySink>((ref) {
  return _AppCacheTelemetrySink(ref.watch(appTelemetryReporterProvider));
});

class _AppCacheTelemetrySink implements CacheTelemetrySink {
  const _AppCacheTelemetrySink(this._telemetry);

  final AppTelemetryRecorder _telemetry;

  @override
  void record(String eventName, Map<String, Object?> attributes) {
    if (eventName == 'cache.hit.source') {
      final source = (attributes['source'] ?? '').toString().trim();
      final cacheClass = (attributes['cacheClass'] ?? '').toString().trim();
      unawaited(
        _telemetry.record(
          AppTelemetryPayload.homeFeedCacheReadOutcome(
            cacheSource: AppTelemetryValueCacheSource.values.contains(source)
                ? source
                : AppTelemetryValueCacheSource.unknown,
            cacheClass: cacheClass.isEmpty ? 'unknown' : cacheClass,
            result: 'hit',
            surfaceId: 'home_feed',
          ),
        ),
      );
    }
    final traceStore = AppTraceContextStore.instance;
    unawaited(
      AppLogService.instance.writeEvent(
        logType: AppLogType.perf,
        level: AppLogLevel.info,
        context: AppLogContext(
          sessionId: traceStore.sessionId,
          requestId: traceStore.newRequestId(),
          sourceDomain: 'runtime',
          component: 'local_cache',
          target: 'cache',
          action: eventName,
        ),
        payload: <String, dynamic>{
          'kind': eventName,
          ...attributes.map((key, value) => MapEntry(key, value)),
        },
        summaryPayload: <String, dynamic>{
          'kind': eventName,
          ...attributes.map((key, value) => MapEntry(key, value)),
        },
      ),
    );
  }
}

/// Homepage facet bundle 只在 composition root 聚合同一 Remote 实例。
/// 页面只能注入下方的窄 Query / CommandWriter capability。
final homepageFacetSetProvider = Provider<HomepageFacetSet>((ref) {
  final commandWriter = ref.watch(_homepageCommandWriterProvider);
  return HomepageFacetProjectionAdapter(
    query: ref.watch(homepageQueryAdapterProvider),
    candidateWriter: commandWriter,
    claimRequestWriter: commandWriter,
    statusReportWriter: commandWriter,
  );
});

final homepageQueryProvider = Provider<HomepageQuery>(
  (ref) => ref.watch(homepageFacetSetProvider),
);

final homepageCommandWriterProvider = Provider<HomepageCommandWriter>(
  (ref) => ref.watch(homepageFacetSetProvider),
);

final homepageQueryActorContextProvider = Provider<CloudOperationActorContext>((
  ref,
) {
  final session = ref.watch(authSessionControllerProvider);
  final accountId = ref.watch(resolvedOwnerUserIdProvider).trim();
  final personaId = session.activePersonaId.trim();
  return CloudOperationActorContext(
    accountId: accountId.isEmpty ? null : accountId,
    personaId: personaId.isEmpty ? null : personaId,
  );
});

final homepageQueryAdapterProvider = Provider<RemoteHomepageQueryAdapter>((
  ref,
) {
  final actorContext = ref.watch(homepageQueryActorContextProvider);
  return RemoteHomepageQueryAdapter(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId, surface, {cancellation, deadlineAt}) {
      final appSurface = switch (surface) {
        HomepageQuerySurface.picker => AppUiSurfaces.homepagePicker,
        HomepageQuerySurface.detail => AppUiSurfaces.homepageDetail,
        HomepageQuerySurface.introduction => AppUiSurfaces.homepageIntroduction,
      };
      return CloudOperationInvocationContext(
        surfaceId: appSurface.id,
        routeId: appSurface.routeId,
        clientPageId: clientPageId,
        cancellation: cancellation,
        deadlineAt: deadlineAt,
        actor: actorContext,
      );
    },
  );
});

/// production 命令写面只绑定 generated Remote adapter；不含 fixture 回退。
final _homepageCommandWriterProvider = Provider<RemoteHomepageCommandWriter>((
  ref,
) {
  final actorContext = ref.watch(homepageQueryActorContextProvider);
  return RemoteHomepageCommandWriter(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId, surface) =>
        CloudOperationInvocationContext(
          surfaceId: surface.id,
          routeId: surface.routeId,
          clientPageId: clientPageId,
          idempotencyKey: const Uuid().v4(),
          actor: actorContext,
        ),
  );
});
