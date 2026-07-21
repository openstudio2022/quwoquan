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
    required String sourceSurfaceId,
    bool flushImmediately = false,
  }) {
    _upsertEntry(
      objectType: 'profile',
      objectId: subAccountId,
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

/// assistant 域共享 Remote 实例：8 个窄 Facet provider 共用同一个
/// [RemoteAssistantRepository]（一个类实现多个窄面，与 content 域同构）。
final _assistantRemoteProvider = Provider<RemoteAssistantRepository>((ref) {
  final accountId = ref.watch(resolvedOwnerUserIdProvider).trim();
  final personaId = ref.watch(currentUserIdProvider).trim();
  final consentActorScope = '$accountId/$personaId';
  return RemoteAssistantRepository(
    httpClient: ref.watch(cloudHttpClientProvider),
    consentActorScope: consentActorScope,
  );
});

/// Production composition is Remote-only. Alpha/test adapters must override
/// these Facets from their physically separate composition root.
final assistantConversationRunFacetProvider =
    Provider<AssistantConversationRunFacet>(
      (ref) => ref.watch(_assistantRemoteProvider),
    );

final assistantSkillSubscriptionFacetProvider =
    Provider<AssistantSkillSubscriptionFacet>(
      (ref) => ref.watch(_assistantRemoteProvider),
    );

final assistantSkillConsentFacetProvider = Provider<AssistantSkillConsentFacet>(
  (ref) => ref.watch(_assistantRemoteProvider),
);

final assistantLearningAppendFacetProvider =
    Provider<AssistantLearningAppendFacet>(
      (ref) => ref.watch(_assistantRemoteProvider),
    );

final assistantPersonalizationFacetProvider =
    Provider<AssistantPersonalizationFacet>(
      (ref) => ref.watch(_assistantRemoteProvider),
    );

final assistantPersonalDataFacetProvider = Provider<AssistantPersonalDataFacet>(
  (ref) => ref.watch(_assistantRemoteProvider),
);

final assistantPreferenceFactFacetProvider =
    Provider<AssistantPreferenceFactFacet>(
      (ref) => ref.watch(_assistantRemoteProvider),
    );

final assistantXiaoquSearchFacetProvider = Provider<AssistantXiaoquSearchFacet>(
  (ref) => ref.watch(_assistantRemoteProvider),
);

final assistantCreationSuggestFacetProvider =
    Provider<AssistantCreationSuggestFacet>(
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
  final personaId = persona?.subAccountId.trim() ?? '';
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

/// Homepage facet bundle 只在 composition root 聚合同一 Remote 实例。
/// 页面只能注入下方的窄 Query / CommandWriter capability。
final homepageFacetSetProvider = Provider<HomepageFacetSet>((ref) {
  final commandWriter = ref.watch(_homepageCommandWriterProvider);
  return HomepageFacetProjectionAdapter(
    query: ref.watch(_homepageQueryAdapterProvider),
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
  final personaId = session.activeSubAccountId.trim();
  return CloudOperationActorContext(
    accountId: accountId.isEmpty ? null : accountId,
    personaId: personaId.isEmpty ? null : personaId,
  );
});

final _homepageQueryAdapterProvider = Provider<RemoteHomepageQueryAdapter>((
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

/// Chat 域 production 组合根：单一 Remote 实例实现全部对象级 Facet，
/// 下方对象 provider 只做类型收窄。production 恒为 Remote-only；alpha runner
/// 与测试只覆盖本组合根即可让全部对象 Facet 走 Mock。
final chatRepositoryCompositionProvider = Provider<ChatRepository>((ref) {
  final ownerUserId = ref.watch(resolvedOwnerUserIdProvider);
  final client = ref.watch(generatedCloudOperationClientProvider);

  CloudOperationInvocationContext invocationContext(
    AppUiSurface surface,
    String clientPageId, {
    String? idempotencyKey,
  }) {
    final persona = ref.read(activePersonaContextProvider).asData?.value;
    final resolvedOwnerUserId = persona?.ownerUserId.trim() ?? '';
    final accountId = resolvedOwnerUserId.isNotEmpty
        ? resolvedOwnerUserId
        : ownerUserId.trim();
    final personaId = persona?.subAccountId.trim() ?? '';
    return CloudOperationInvocationContext(
      surfaceId: surface.id,
      routeId: surface.routeId,
      clientPageId: clientPageId,
      actor: CloudOperationActorContext(
        accountId: accountId.isEmpty ? null : accountId,
        personaId: personaId.isEmpty ? null : personaId,
      ),
      idempotencyKey: idempotencyKey,
    );
  }

  final conversationQuery = RemoteChatConversationQuery(
    client: client,
    invocationContext: (clientPageId) {
      final surface = switch (clientPageId) {
        ChatRequestPageIds.getConversation ||
        ChatRequestPageIds.getReceipts => AppUiSurfaces.chatDetail,
        ChatRequestPageIds.getGroupHome => AppUiSurfaces.chatAnnouncement,
        _ => AppUiSurfaces.chatList,
      };
      return invocationContext(surface, clientPageId);
    },
  );
  final settingsConversationQuery = RemoteChatConversationQuery(
    client: client,
    invocationContext: (clientPageId) =>
        invocationContext(AppUiSurfaces.chatSettings, clientPageId),
  );
  final conversationCommandWriter = RemoteChatConversationCommandWriter(
    client: client,
    invocationContext: (clientPageId, idempotencyKey) {
      final surface = switch (clientPageId) {
        ChatRequestPageIds.createConversation => AppUiSurfaces.startGroupChat,
        ChatRequestPageIds.updateConversationTitle =>
          AppUiSurfaces.chatSettings,
        ChatRequestPageIds.updateAnnouncement => AppUiSurfaces.chatAnnouncement,
        _ => AppUiSurfaces.chatManage,
      };
      return invocationContext(
        surface,
        clientPageId,
        idempotencyKey: idempotencyKey,
      );
    },
  );
  final contactQuery = RemoteChatContactQuery(
    client: client,
    invocationContext: (clientPageId) {
      final surface = switch (clientPageId) {
        ChatRequestPageIds.listGroupCandidates ||
        ChatRequestPageIds.listSelectableGroupConversations ||
        ChatRequestPageIds.listSelectableGroupContactMembers =>
          AppUiSurfaces.startGroupChat,
        _ => AppUiSurfaces.chatList,
      };
      return invocationContext(surface, clientPageId);
    },
  );
  final messageHomeQuery = RemoteChatMessageHomeQuery(
    client: client,
    invocationContext: (clientPageId) =>
        invocationContext(AppUiSurfaces.chatList, clientPageId),
  );
  final membershipQuery = RemoteChatConversationMembershipQuery(
    client: client,
    invocationContext: (clientPageId) =>
        invocationContext(AppUiSurfaces.chatManage, clientPageId),
  );
  final memberSearchQuery = RemoteChatConversationMembershipQuery(
    client: client,
    invocationContext: (clientPageId) =>
        invocationContext(AppUiSurfaces.chatDetail, clientPageId),
  );
  final membershipCommandWriter = RemoteChatConversationMembershipCommandWriter(
    client: client,
    invocationContext: (clientPageId, idempotencyKey) {
      final surface = switch (clientPageId) {
        ChatRequestPageIds.addMembers => AppUiSurfaces.chatAddMembers,
        ChatRequestPageIds.inviteAssistant ||
        ChatRequestPageIds.removeAssistant => AppUiSurfaces.chatDetail,
        ChatRequestPageIds.transferOwnership =>
          AppUiSurfaces.chatTransferOwnership,
        ChatRequestPageIds.updateGroupAdmins => AppUiSurfaces.chatAdmins,
        _ => AppUiSurfaces.chatSettings,
      };
      return invocationContext(
        surface,
        clientPageId,
        idempotencyKey: idempotencyKey,
      );
    },
  );
  final userStateCommandWriter = RemoteChatConversationUserStateCommandWriter(
    client: client,
    invocationContext: (clientPageId, idempotencyKey) {
      final surface = clientPageId == ChatRequestPageIds.markAsRead
          ? AppUiSurfaces.chatDetail
          : AppUiSurfaces.chatSettings;
      return invocationContext(
        surface,
        clientPageId,
        idempotencyKey: idempotencyKey,
      );
    },
  );
  final messageQuery = RemoteChatMessageQuery(
    client: client,
    invocationContext: (clientPageId) =>
        invocationContext(AppUiSurfaces.chatDetail, clientPageId),
  );
  final messageMutationWriter = RemoteChatMessageMutationWriter(
    client: client,
    invocationContext: (clientPageId, idempotencyKey) => invocationContext(
      AppUiSurfaces.chatDetail,
      clientPageId,
      idempotencyKey: idempotencyKey,
    ),
  );

  return RemoteChatRepository(
    conversationQuery: conversationQuery,
    settingsConversationQuery: settingsConversationQuery,
    conversationCommandWriter: conversationCommandWriter,
    contactQuery: contactQuery,
    inboxQuery: contactQuery,
    messageHomeQuery: messageHomeQuery,
    membershipQuery: membershipQuery,
    memberSearchQuery: memberSearchQuery,
    membershipCommandWriter: membershipCommandWriter,
    userStateCommandWriter: userStateCommandWriter,
    messageQuery: messageQuery,
    messageMutationWriter: messageMutationWriter,
  );
});

/// Chat 会话对象查询/命令 Facet（收件箱、消息首页、会话生命周期）。
final chatConversationRepositoryProvider = Provider<ChatConversationRepository>(
  (ref) => ref.watch(chatRepositoryCompositionProvider),
);

/// Chat 消息对象 Facet（历史、同步、撤回、已读、回执）。
final chatMessageRepositoryProvider = Provider<ChatMessageRepository>(
  (ref) => ref.watch(chatRepositoryCompositionProvider),
);

/// Chat 成员名册对象 Facet。
final chatMemberRepositoryProvider = Provider<ChatMemberRepository>(
  (ref) => ref.watch(chatRepositoryCompositionProvider),
);

/// Chat 联系人数据面 Facet（联系人列表 / 联系首页 / 候选源）。
final chatContactRepositoryProvider = Provider<ChatContactRepository>(
  (ref) => ref.watch(chatRepositoryCompositionProvider),
);

/// 「从群聊中选择联系人」二级流程 Facet。
final chatGroupSelectionRepositoryProvider =
    Provider<ChatGroupSelectionRepository>(
      (ref) => ref.watch(chatRepositoryCompositionProvider),
    );

/// 群治理 Facet（群设置 / 转让 / 管理员 / 解散）。
final chatGroupAdminRepositoryProvider = Provider<ChatGroupAdminRepository>(
  (ref) => ref.watch(chatRepositoryCompositionProvider),
);

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
    repo: ref.watch(chatRepositoryCompositionProvider),
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

final userSyncRepositoryProvider = Provider<UserSyncRepository>((ref) {
  final ownerUserId = ref.watch(resolvedOwnerUserIdProvider);
  return RemoteUserSyncRepository(
    httpClient: ref.watch(cloudHttpClientProvider),
    mergeRequestContext: (base) async {
      return CloudRequestHeaders.withOwnerSubAccountContext(
        base,
        ownerUserId: ownerUserId,
      );
    },
  );
});

final followingSubjectRepositoryProvider = Provider<FollowingSubjectRepository>(
  (ref) {
    final facet = RemoteFollowingSubjectFacet(
      client: ref.watch(generatedCloudOperationClientProvider),
      invocationContext: (clientPageId) => _locationInvocationContext(
        ref,
        surface: AppUiSurfaces.homeFeed,
        clientPageId: clientPageId,
      ),
    );
    return RemoteFollowingSubjectRepository(query: facet, visitWriter: facet);
  },
);

/// 当前活动分身上下文。production 只消费对象级 PersonaQuery；alpha/test
/// 必须在独立 composition root 显式 override personaQueryProvider。
final activePersonaContextProvider =
    FutureProvider<ActivePersonaContextViewData>((ref) {
      return ref
          .read(personaQueryProvider(AppUiSurfaces.appShell))
          .getActivePersonaContext();
    });

/// ContactDiscovery Repository（通讯录批量哈希匹配）
final contactDiscoveryRepositoryProvider = Provider<ContactDiscoveryRepository>(
  (ref) {
    final facet = RemoteContactDiscoveryFacet(
      client: ref.watch(generatedCloudOperationClientProvider),
      invocationContext: (clientPageId) => _locationInvocationContext(
        ref,
        surface: AppUiSurfaces.addContactPhone,
        clientPageId: clientPageId,
      ),
    );
    return RemoteContactDiscoveryRepository(commandWriter: facet, query: facet);
  },
);

/// Behavior Repository（行为上报，驱动实时推荐）
final behaviorRepositoryProvider = Provider<BehaviorRepository>((ref) {
  final feedSessionNotifier = ref.read(feedSessionProvider.notifier);
  final accountId = ref.watch(resolvedOwnerUserIdProvider).trim();
  final personaId = ref.watch(currentUserIdProvider).trim();
  final repo = RemoteBehaviorRepository(
    httpClient: ref.watch(cloudHttpClientProvider),
    queuePartition: ActorQueuePartition(
      environment: CloudRuntimeConfig.appRuntimeEnv,
      accountId: accountId,
      personaId: personaId,
      deviceId: CloudRequestHeaders.deviceActorId ?? '',
    ),
    queueStorage: ref.watch(actorQueueStorageProvider),
    feedSessionIdProvider: () => feedSessionNotifier.sessionId,
  );
  ref.onDispose(repo.dispose);
  return repo;
});

/// 推荐反馈唯一上报端口。采集/计算 Tracker 只能依赖该端口。
final behaviorReporterProvider = Provider<BehaviorReporter>(
  (ref) => ref.watch(behaviorRepositoryProvider),
);

/// Content Engagement Tracker（统一深度行为追踪 SDK）
final contentEngagementTrackerProvider = Provider<ContentEngagementTracker>((
  ref,
) {
  final tracker = ContentEngagementTracker(
    reporter: ref.watch(behaviorReporterProvider),
  );
  ref.onDispose(() => tracker.dispose());
  return tracker;
});

/// Lightweight OpsEvent journey funnel tracker（无完整 Behavior schema 的页面场景）
final journeyEventTrackerProvider = Provider<JourneyEventTracker>((ref) {
  return JourneyEventTracker(
    telemetryReporter: ref.watch(appTelemetryReporterProvider),
  );
});

/// 群聊创建、提及、水位与治理漏斗使用 metadata 生成的受限事件，不复用
/// 可以携带业务对象标识的通用 product_action。
final chatInteractionTelemetryTrackerProvider =
    Provider<ChatInteractionTelemetryTracker>((ref) {
      return ChatInteractionTelemetryTracker(
        telemetryReporter: ref.watch(appTelemetryReporterProvider),
      );
    });

/// Intersection Repository（读面；Mock 收敛归 R-ID10）
final intersectionRepositoryProvider = Provider<IntersectionRepository>(
  (ref) => RemoteIntersectionRepository(
    httpClient: ref.watch(cloudHttpClientProvider),
    currentUserId: ref.watch(currentUserIdProvider),
  ),
);

/// IntersectionVisitState typed 写面（content/intersection_visit_state 对象）：
/// production Remote-only；alpha/test 经 override 注入 Mock 同构替身。
final intersectionVisitWriterProvider = Provider<IntersectionVisitWriter>((
  ref,
) {
  return RemoteIntersectionVisitWriter(
    httpClient: ref.watch(cloudHttpClientProvider),
  );
});

final activePersonaContextLoaderProvider = Provider<PersonaContextLoader>((
  ref,
) {
  return ref
      .read(personaQueryProvider(AppUiSurfaces.appShell))
      .getActivePersonaContext;
});

final localChatSearchSyncProvider = Provider<LocalChatSearchSyncService>((ref) {
  return LocalChatSearchSyncService(
    chatRepository: ref.watch(chatRepositoryCompositionProvider),
    conversationCache: ref.watch(conversationCacheProvider),
    store: ref.watch(localChatSearchStoreProvider),
    personaContextLoader: ref.watch(activePersonaContextLoaderProvider),
    telemetrySink: ref.watch(cacheTelemetrySinkProvider),
  );
});

final _canonicalSearchQueryProvider = Provider<CanonicalSearchQueryFacet>((
  ref,
) {
  return RemoteCanonicalSearchQuery(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId) => _locationInvocationContext(
      ref,
      surface: AppUiSurfaces.globalSearchNetworkResults,
      clientPageId: clientPageId,
    ),
  );
});

/// 两阶段搜索：result 只走 search-service canonical Remote；suggest 在 Remote
/// 结果上合并账号隔离的本地联系人/会话/消息索引。本地对象绝不进入结果页。
/// alpha/test 通过 ProviderScope override 该对象级 Repository。
final searchRepositoryProvider = Provider<SearchRepository>((ref) {
  return HybridSearchRepository(
    RemoteSearchRepository(
      remoteQuery: ref.watch(_canonicalSearchQueryProvider),
    ),
    ref.watch(localChatSearchStoreProvider),
    ref.watch(localChatSearchSyncProvider),
    ref.watch(activePersonaContextLoaderProvider),
    ref.watch(cacheTelemetrySinkProvider),
  );
});

/// RelationshipCapability Repository（关系能力位投影，用户主页五态按钮矩阵 + RTC 门禁）
final relationshipCapabilityRepositoryProvider =
    Provider<RelationshipCapabilityRepository>((ref) {
      return RemoteRelationshipCapabilityRepository(
        query: ref.watch(
          _personaRelationshipRemoteProvider(AppUiSurfaces.userProfile),
        ),
      );
    });

/// Greeting Repository（打招呼请求箱）
final greetingRepositoryProvider = Provider<GreetingRepository>((ref) {
  final facet = ref.watch(
    _greetingRequestRemoteProvider(AppUiSurfaces.userProfile),
  );
  return RemoteGreetingRepository(commandWriter: facet, query: facet);
});

/// TagCatalogQuery（标签层级/解析/维度/联想/校验/搜索/相关）：
/// production Remote-only（08 Mock 隔离），alpha 经 override 注入 AlphaTagFacet。
final tagCatalogQueryProvider = Provider<TagCatalogQuery>((ref) {
  return RemoteGeneratedTagCatalogQuery(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId) => _locationInvocationContext(
      ref,
      surface: AppUiSurfaces.profileCareerInterests,
      clientPageId: clientPageId,
    ),
    nonAppCommercialQuery: RemoteTagCatalogQuery(
      httpClient: ref.watch(cloudHttpClientProvider),
    ),
  );
});

/// TagGraphQuery（共享标签/反向索引/共现/相关对象/多标签搜索）：
/// production Remote-only，alpha 经 override 注入 AlphaTagFacet。
final tagGraphQueryProvider = Provider<TagGraphQuery>((ref) {
  return RemoteTagGraphQuery(httpClient: ref.watch(cloudHttpClientProvider));
});

/// Media Upload Manager（统一媒体上传队列 + 并发 + 重试 + 离线恢复）
final mediaUploadManagerProvider = Provider<MediaUploadManager>((ref) {
  final coordinator = ContentMediaUploadCoordinator(
    media: ref.watch(chatDetailContentMediaFacetProvider),
    telemetry: ref.watch(appTelemetryReporterProvider),
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
