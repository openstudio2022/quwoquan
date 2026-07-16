part of 'app_providers.dart';

class ClientStateSyncOutboxNotifier
    extends Notifier<ClientStateSyncOutboxState> {
  Timer? _flushTimer;
  final Map<String, bool> _inFlightDesiredValues = <String, bool>{};

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
    final raw = await _readPersistedInteractionMap(
      _clientStateSyncOutboxStorageKey,
    );
    if (!ref.mounted) {
      return;
    }
    if (raw == null) {
      return;
    }
    state = state.copyWith(
      entries: _dropResolvedEntries(
        ClientStateSyncOutboxState.fromMap(raw).entries,
      ),
    );
    _scheduleNextFlush();
  }

  void enqueueFollow({
    required String subAccountId,
    required bool currentFollowing,
    required bool shouldFollow,
    bool flushImmediately = false,
  }) {
    _upsertEntry(
      objectType: 'profile',
      objectId: subAccountId,
      intentType: 'follow',
      currentBoolValue: currentFollowing,
      desiredBoolValue: shouldFollow,
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
        _onFlushSucceeded(
          coalesceKey: coalesceKey,
          flushedDesiredBoolValue: entry.desiredBoolValue,
        );
      } catch (_) {
        _onFlushFailed(coalesceKey: coalesceKey, config: config);
      } finally {
        _inFlightDesiredValues.remove(coalesceKey);
      }
    }
    unawaited(_persistState());
    _scheduleNextFlush();
  }

  Future<void> _flushEntry(ClientStateSyncOutboxEntry entry) async {
    switch ('${entry.objectType}:${entry.intentType}') {
      case 'profile:follow':
        final repo = ref.read(userProfileRepositoryProvider);
        final activeContext = await ref.read(
          activePersonaContextProvider.future,
        );
        if (entry.desiredBoolValue) {
          await repo.followUser(
            entry.objectId,
            ownerUserId: activeContext.ownerUserId,
            subAccountId: activeContext.subAccountId,
            subAccountContextVersion: activeContext.contextVersion,
          );
        } else {
          await repo.unfollowUser(
            entry.objectId,
            ownerUserId: activeContext.ownerUserId,
            subAccountId: activeContext.subAccountId,
            subAccountContextVersion: activeContext.contextVersion,
          );
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
    required bool flushImmediately,
  }) {
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
    if (state.entries.isEmpty) return;
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
    await _writePersistedInteractionMap(
      _clientStateSyncOutboxStorageKey,
      state.toMap(),
    );
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

final assistantRepositoryProvider = Provider<AssistantRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  final accountId = ref.watch(resolvedOwnerUserIdProvider).trim();
  final personaId = ref.watch(currentUserIdProvider).trim();
  final consentActorScope = '$accountId/$personaId';
  return cloudRepositoryImplForMode(
    mode,
    remote: () => RemoteAssistantRepository(
      httpClient: ref.watch(cloudHttpClientProvider),
      consentActorScope: consentActorScope,
    ),
    mock: () => MockAssistantRepository(
      store: AssistantConsentStore(actorScope: consentActorScope),
    ),
  );
});

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
  final personaId = persona?.subAccountId.trim() ?? '';
  return CloudOperationInvocationContext(
    surfaceId: AppUiSurfaces.personalAssistantDialog.id,
    clientPageId: clientPageId,
    routeId: AppUiSurfaces.personalAssistantDialog.routeId,
    actor: CloudOperationActorContext(
      accountId: accountId.isEmpty ? null : accountId,
      personaId: personaId.isEmpty ? null : personaId,
    ),
  );
}

final personalContentAccessProvider =
    NotifierProvider<PersonalContentAccessNotifier, PersonalContentAccessState>(
      PersonalContentAccessNotifier.new,
    );

final assistantPersonalContentAccessGrantedProvider = Provider<bool>((ref) {
  return ref.watch(personalContentAccessProvider).granted;
});

final assistantContentIdentityIndexEnabledProvider = Provider<bool>((ref) {
  final consentGranted = ref.watch(
    assistantPersonalContentAccessGrantedProvider,
  );
  final featureFlag = ref.watch(
    contentFeatureFlagProvider('enable_assistant_content_identity_index'),
  );
  return consentGranted && featureFlag;
});

final cacheTelemetrySinkProvider = Provider<CacheTelemetrySink>((ref) {
  return const _AppLogCacheTelemetrySink();
});

class _AppLogCacheTelemetrySink implements CacheTelemetrySink {
  const _AppLogCacheTelemetrySink();

  @override
  void record(String eventName, Map<String, Object?> attributes) {
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

/// Homepage Repository（主页搜索、详情、认领与治理）
final homepageRepositoryProvider = Provider<HomepageRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  return cloudRepositoryImplForMode(
    mode,
    remote: () => RemoteHomepageRepository(
      httpClient: ref.watch(cloudHttpClientProvider),
    ),
    mock: MockHomepageRepository.new,
  );
});

/// Chat Repository（按业务对象组织的端侧入口）
final chatRepositoryProvider = Provider<ChatRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  final ownerUserId = ref.watch(resolvedOwnerUserIdProvider);
  return cloudRepositoryImplForMode(
    mode,
    remote: () => RemoteChatRepository(
      httpClient: ref.watch(cloudHttpClientProvider),
      mergeRequestContext: (base) async {
        final ctx = ref.read(activePersonaContextProvider).asData?.value;
        final resolvedOwnerUserId = ctx?.ownerUserId.trim() ?? '';
        return CloudRequestHeaders.withOwnerSubAccountContext(
          base,
          ownerUserId: resolvedOwnerUserId.isNotEmpty
              ? resolvedOwnerUserId
              : ownerUserId,
          subAccountId: ctx?.subAccountId ?? '',
          subAccountContextVersion: ctx?.personaContextVersion ?? '',
        );
      },
    ),
    mock: MockChatRepository.new,
  );
});

/// Message command production composition is Remote-only. Alpha and tests
/// override this Facet from their separate composition roots.
final chatMessageCommandWriterProvider = Provider<ChatMessageCommandWriter>((
  ref,
) {
  return RemoteChatMessageCommandWriter(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId, idempotencyKey) {
      final accountId = ref.read(resolvedOwnerUserIdProvider).trim();
      final persona = ref.read(activePersonaContextProvider).asData?.value;
      final personaId = persona?.subAccountId.trim() ?? '';
      return CloudOperationInvocationContext(
        surfaceId: AppUiSurfaces.chatDetail.id,
        clientPageId: clientPageId,
        routeId: AppUiSurfaces.chatDetail.routeId,
        actor: CloudOperationActorContext(
          accountId: accountId.isEmpty ? null : accountId,
          personaId: personaId.isEmpty ? null : personaId,
        ),
        idempotencyKey: idempotencyKey,
      );
    },
  );
});

/// Production realtime 连接：固定 Remote-only。
/// Alpha fixture 只能由独立 runner 在 composition root 覆盖整个 notifier。
final realtimeConnectionManagerProvider =
    NotifierProvider<RealtimeConnectionNotifier, TransportState>(
      () => RealtimeConnectionNotifier(
        currentUserIdResolver: (ref) => ref.watch(currentUserIdProvider).trim(),
      ),
    );

/// 会话缓存（按 namespace 隔离，支持列表增量监听）
final conversationCacheProvider = Provider<ConversationCacheService>((ref) {
  return ConversationCacheService();
});

/// 用户资料缓存（LRU 内存 200 条 + 磁盘持久化无 TTL）
final userProfileCacheProvider = Provider<UserProfileCacheService>((ref) {
  return UserProfileCacheService(persistToPreferences: true);
});

final postObjectCacheProvider = Provider<PostObjectCacheService>((ref) {
  final profile = ref.watch(appResourceCacheProfileProvider);
  return PostObjectCacheService(
    maxMemoryEntries: profile.maxPostObjectCacheEntries,
  );
});

final contentQuerySnapshotStoreProvider = Provider<ContentQuerySnapshotStore>((
  ref,
) {
  return ContentQuerySnapshotStore(
    persistToPreferences: true,
    telemetrySink: ref.watch(cacheTelemetrySinkProvider),
  );
});

final cacheManagementServiceProvider = Provider<CacheManagementService>((ref) {
  Future<void> clearEphemeralResources() async {
    await AppImageCacheController.clearTemporaryImages();
    await ref.read(mediaDownloadCacheProvider).clear();
  }

  Future<void> clearAllRebuildableResources() async {
    await AppImageCacheController.clearAllRebuildableImages();
    await ref.read(mediaDownloadCacheProvider).clear();
  }

  return CacheManagementService(
    postCache: ref.watch(postObjectCacheProvider),
    querySnapshotStore: ref.watch(contentQuerySnapshotStoreProvider),
    userProfileCache: ref.watch(userProfileCacheProvider),
    conversationCache: ref.watch(conversationCacheProvider),
    clearTemporaryImages: clearEphemeralResources,
    clearAllRebuildableImages: clearAllRebuildableResources,
  );
});

/// 会话同步引擎
final conversationSyncProvider = Provider<ConversationSyncService>((ref) {
  return ConversationSyncService(
    repo: ref.watch(chatRepositoryProvider),
    cache: ref.watch(conversationCacheProvider),
    userSyncRepository: ref.watch(userSyncRepositoryProvider),
    store: ref.watch(localChatSearchStoreProvider),
    personaContextLoader: ref.read(activePersonaContextLoaderProvider),
  );
});

final localChatSearchStoreProvider = Provider<LocalChatSearchStore>((ref) {
  return LocalChatSearchStore.shared;
});

final localCircleGroupSnapshotStoreProvider =
    Provider<LocalCircleGroupSnapshotStore>((ref) {
      return LocalCircleGroupSnapshotStore.shared;
    });

/// User Repository（按业务对象组织的端侧入口）
final userRepositoryProvider = Provider<UserRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  final ownerUserId = ref.watch(resolvedOwnerUserIdProvider);
  return cloudRepositoryImplForMode(
    mode,
    remote: () => RemoteUserRepository(
      httpClient: ref.watch(cloudHttpClientProvider),
      mergeRequestContext: (base) async {
        return CloudRequestHeaders.withOwnerSubAccountContext(
          base,
          ownerUserId: ownerUserId,
        );
      },
    ),
    mock: MockUserRepository.new,
  );
});

final userSyncRepositoryProvider = Provider<UserSyncRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  final ownerUserId = ref.watch(resolvedOwnerUserIdProvider);
  return cloudRepositoryImplForMode(
    mode,
    remote: () => RemoteUserSyncRepository(
      httpClient: ref.watch(cloudHttpClientProvider),
      mergeRequestContext: (base) async {
        return CloudRequestHeaders.withOwnerSubAccountContext(
          base,
          ownerUserId: ownerUserId,
        );
      },
    ),
    mock: MockUserSyncRepository.new,
  );
});

final followingSubjectRepositoryProvider = Provider<FollowingSubjectRepository>(
  (ref) {
    final mode = ref.watch(appDataSourceModeProvider);
    return cloudRepositoryImplForMode(
      mode,
      remote: () => RemoteFollowingSubjectRepository(
        httpClient: ref.watch(cloudHttpClientProvider),
      ),
      mock: MockFollowingSubjectRepository.new,
    );
  },
);

/// 当前活动分身上下文。只有 mock 模式允许本地回退；remote 模式必须显式失败，避免关键写路径静默降级到 user。
final activePersonaContextProvider =
    FutureProvider<ActivePersonaContextViewData>((ref) async {
      final mode = ref.read(appDataSourceModeProvider);
      try {
        return await ref.read(userRepositoryProvider).getActivePersonaContext();
      } catch (_) {
        if (mode == AppDataSourceMode.remote) {
          rethrow;
        }
        final currentUser = ref.read(userDataProvider);
        final fallbackId = currentUser?.id.isNotEmpty == true
            ? currentUser!.id
            : ref.read(currentUserIdProvider);
        return ActivePersonaContextViewData.fallback(
          subAccountId:
              currentUser?.metadata?['subAccountId']?.toString() ?? fallbackId,
          ownerUserId:
              currentUser?.metadata?['ownerUserId']?.toString() ?? fallbackId,
          subjectType:
              currentUser?.metadata?['subjectType']?.toString() ?? 'owner',
          displayName:
              currentUser?.displayName ?? currentUser?.username ?? fallbackId,
          avatarUrl: currentUser?.avatarUrlOrAvatar ?? '',
          personaContextVersion:
              currentUser?.metadata?['personaContextVersion']?.toString() ?? '',
        );
      }
    });

/// ContactDiscovery Repository（通讯录批量哈希匹配）
final contactDiscoveryRepositoryProvider = Provider<ContactDiscoveryRepository>(
  (ref) {
    final mode = ref.watch(appDataSourceModeProvider);
    return cloudRepositoryImplForMode(
      mode,
      remote: () => RemoteContactDiscoveryRepository(
        httpClient: ref.watch(cloudHttpClientProvider),
      ),
      mock: MockContactDiscoveryRepository.new,
    );
  },
);

/// Behavior Repository（行为上报，驱动实时推荐）
final behaviorRepositoryProvider = Provider<BehaviorRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  if (mode == AppDataSourceMode.remote) {
    final feedSessionNotifier = ref.read(feedSessionProvider.notifier);
    final accountId = ref.watch(resolvedOwnerUserIdProvider).trim();
    final personaId = ref.watch(currentUserIdProvider).trim();
    final repo = RemoteBehaviorRepository(
      httpClient: ref.watch(cloudHttpClientProvider),
      eventRepository: ref.watch(opsEventRepositoryProvider),
      currentUserId: personaId,
      queuePartition: ActorQueuePartition(
        environment: CloudRuntimeConfig.appRuntimeEnv,
        accountId: accountId,
        personaId: personaId,
        deviceId: CloudRequestHeaders.deviceActorId ?? '',
      ),
      queueStorage: ref.watch(actorQueueStorageProvider),
      experimentBucket: ref
          .watch(contentRuntimeConfigProvider)
          .experimentBucket,
      feedSessionIdProvider: () => feedSessionNotifier.sessionId,
    );
    ref.onDispose(repo.dispose);
    return repo;
  }
  return MockBehaviorRepository();
});

/// Content Engagement Tracker（统一深度行为追踪 SDK）
final contentEngagementTrackerProvider = Provider<ContentEngagementTracker>((
  ref,
) {
  final tracker = ContentEngagementTracker(
    repository: ref.watch(behaviorRepositoryProvider),
  );
  ref.onDispose(() => tracker.dispose());
  return tracker;
});

/// Lightweight OpsEvent journey funnel tracker（无完整 Behavior schema 的页面场景）
final journeyEventTrackerProvider = Provider<JourneyEventTracker>((ref) {
  return JourneyEventTracker(
    eventRepository: ref.watch(opsEventRepositoryProvider),
  );
});

/// UserProfile Repository（用户主页：帖子 / 作品集 / 生活记录）
final userProfileRepositoryProvider = Provider<UserProfileRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  return cloudRepositoryImplForMode(
    mode,
    remote: () => RemoteUserProfileRepository(
      httpClient: ref.watch(cloudHttpClientProvider),
    ),
    mock: () => const MockUserProfileRepository(),
  );
});

/// Block Repository（拉黑/取消拉黑用户）
final blockRepositoryProvider = Provider<BlockRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  return cloudRepositoryImplForMode(
    mode,
    remote: () =>
        RemoteBlockRepository(httpClient: ref.watch(cloudHttpClientProvider)),
    mock: MockBlockRepository.new,
  );
});

/// Intersection Repository
final intersectionRepositoryProvider = Provider<IntersectionRepository>(
  (ref) => cloudRepositoryImplForMode(
    ref.watch(appDataSourceModeProvider),
    remote: () => RemoteIntersectionRepository(
      httpClient: ref.watch(cloudHttpClientProvider),
      currentUserId: ref.watch(currentUserIdProvider),
    ),
    mock: MockIntersectionRepository.new,
  ),
);

/// KeywordBlock Repository（屏蔽词设置）
final keywordBlockRepositoryProvider = Provider<KeywordBlockRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  return cloudRepositoryImplForMode(
    mode,
    remote: () => RemoteKeywordBlockRepository(
      httpClient: ref.watch(cloudHttpClientProvider),
    ),
    mock: MockKeywordBlockRepository.new,
  );
});

/// Circle Repository（圈子管理、成员、存储、Feed）
final circleRepositoryProvider = Provider<CircleRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  return cloudRepositoryImplForMode(
    mode,
    remote: () =>
        RemoteCircleRepository(httpClient: ref.watch(cloudHttpClientProvider)),
    mock: MockCircleRepository.new,
  );
});

final activePersonaContextLoaderProvider = Provider<PersonaContextLoader>((
  ref,
) {
  return ref.read(userRepositoryProvider).getActivePersonaContext;
});

final localChatSearchSyncProvider = Provider<LocalChatSearchSyncService>((ref) {
  return LocalChatSearchSyncService(
    chatRepository: ref.watch(chatRepositoryProvider),
    conversationCache: ref.watch(conversationCacheProvider),
    store: ref.watch(localChatSearchStoreProvider),
    personaContextLoader: ref.watch(activePersonaContextLoaderProvider),
  );
});

final searchRepositoryProvider = Provider<SearchRepository>((ref) {
  // 本地扇出 composite：内部子仓库（content/circle/user/entity/integration）在 remote
  // 模式下本身即 Remote 实现，叠加 chat/circle.group 本地命名空间检索。suggest 模式与
  // mock 模式都复用它；remote 结果模式由 RemoteSearchRepository 接管云侧 /v1/search。
  final localFanout = buildAppSearchRepository(
    circleRepository: ref.watch(circleRepositoryProvider),
    circleGroupQuery: ref.watch(globalSearchCircleGroupQueryProvider),
    contentPostSearchRepository: ref.watch(contentPostSearchRepositoryProvider),
    homepageRepository: ref.watch(homepageRepositoryProvider),
    locationSearchReader: ref.watch(globalSearchLocationReaderProvider),
    userProfileRepository: ref.watch(userProfileRepositoryProvider),
    localChatSearchStore: ref.watch(localChatSearchStoreProvider),
    localChatSearchSyncService: ref.watch(localChatSearchSyncProvider),
    localCircleGroupSnapshotStore: ref.watch(
      localCircleGroupSnapshotStoreProvider,
    ),
    personaContextLoader: ref.watch(activePersonaContextLoaderProvider),
  );
  final mode = ref.watch(appDataSourceModeProvider);
  return cloudRepositoryImplForMode(
    mode,
    remote: () => RemoteSearchRepository(
      httpClient: ref.watch(cloudHttpClientProvider),
      localFanout: localFanout,
    ),
    mock: () => localFanout,
  );
});

/// RTC Repository（实时通话：发起、接听、挂断、录制等）
final rtcRepositoryProvider = Provider<RtcRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  return cloudRepositoryImplForMode(
    mode,
    remote: () =>
        RemoteRtcRepository(httpClient: ref.watch(cloudHttpClientProvider)),
    mock: MockRtcRepository.new,
  );
});

/// RelationshipCapability Repository（关系能力位投影，用户主页五态按钮矩阵 + RTC 门禁）
final relationshipCapabilityRepositoryProvider =
    Provider<RelationshipCapabilityRepository>((ref) {
      final mode = ref.watch(appDataSourceModeProvider);
      return cloudRepositoryImplForMode(
        mode,
        remote: () => RemoteRelationshipCapabilityRepository(
          httpClient: ref.watch(cloudHttpClientProvider),
        ),
        mock: MockRelationshipCapabilityRepository.new,
      );
    });

/// CallSettings Repository（来电铃声与响铃偏好）
final callSettingsRepositoryProvider = Provider<CallSettingsRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  return cloudRepositoryImplForMode(
    mode,
    remote: () => RemoteCallSettingsRepository(
      httpClient: ref.watch(cloudHttpClientProvider),
    ),
    mock: MockCallSettingsRepository.new,
  );
});

/// AppearanceSettings Repository（外观与字号偏好）
final appearanceSettingsRepositoryProvider =
    Provider<AppearanceSettingsRepository>((ref) {
      final mode = ref.watch(appDataSourceModeProvider);
      return cloudRepositoryImplForMode(
        mode,
        remote: () => RemoteAppearanceSettingsRepository(
          httpClient: ref.watch(cloudHttpClientProvider),
        ),
        mock: MockAppearanceSettingsRepository.new,
      );
    });

/// Greeting Repository（打招呼请求箱）
final greetingRepositoryProvider = Provider<GreetingRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  return cloudRepositoryImplForMode(
    mode,
    remote: () => RemoteGreetingRepository(
      httpClient: ref.watch(cloudHttpClientProvider),
    ),
    mock: MockGreetingRepository.new,
  );
});

/// Tag Repository（标签体系查询、建议、校验与关系图谱）
final tagRepositoryProvider = Provider<TagRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  if (mode == AppDataSourceMode.remote) {
    return RemoteTagRepository(httpClient: ref.watch(cloudHttpClientProvider));
  }
  return MockTagRepository();
});

/// Media Upload Manager（统一媒体上传队列 + 并发 + 重试 + 离线恢复）
final mediaUploadManagerProvider = Provider<MediaUploadManager>((ref) {
  final coordinator = ContentMediaUploadCoordinator(
    media: ref.watch(chatDetailContentMediaFacetProvider),
    fileStorage: ref.watch(fileStorageGatewayProvider),
    uploadObject: ref.watch(contentMediaObjectUploadProvider),
  );
  final manager = MediaUploadManager(
    coordinator: coordinator,
    sourceReader: ref.watch(contentMediaSourceReaderProvider),
    uploadStream: ref.watch(contentMediaStreamObjectUploadProvider),
  );
  manager.startOfflineMonitor();
  ref.onDispose(manager.dispose);
  return manager;
});

/// Media Download Cache（LRU 媒体下载缓存，默认 200MB）
final mediaDownloadCacheProvider = Provider<MediaDownloadCache>((ref) {
  final profile = ref.watch(appResourceCacheProfileProvider);
  return MediaDownloadCache(
    maxCacheSizeMb: profile.maxMediaDownloadCacheSizeMb,
    maxConcurrentDownloads: profile.maxConcurrentMediaDownloads,
    telemetrySink: ref.watch(cacheTelemetrySinkProvider),
  );
});
