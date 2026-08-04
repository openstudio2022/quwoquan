import 'dart:async';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/media/media_download_cache.dart';
import 'package:quwoquan_app/cloud/media/media_upload_manager.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/context/actor_queue_partition.dart';
import 'package:quwoquan_app/core/di/generated_operation_client_dependencies.dart';
import 'package:quwoquan_app/core/services/search_recent_history_store.dart';
import 'package:quwoquan_app/tag/tag/tag_node_view/adapters/tag_catalog_remote.dart';
import 'package:quwoquan_app/tag/tag/tag_node_view/application/tag_catalog_query.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/core/providers/feed_session_provider.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/cloud/remote/chat/conversation/contact_remote.dart';
import 'package:quwoquan_app/cloud/remote/chat/conversation/conversation_membership_remote.dart';
import 'package:quwoquan_app/cloud/remote/chat/conversation/conversation_remote.dart';
import 'package:quwoquan_app/cloud/remote/chat/conversation/conversation_user_state_remote.dart';
import 'package:quwoquan_app/cloud/remote/chat/conversation/message_home_remote.dart';
import 'package:quwoquan_app/cloud/remote/chat/message/message_remote.dart';
import 'package:quwoquan_app/realtime/realtime/connection/domain/realtime_connection_delegate.dart';
import 'package:quwoquan_app/realtime/realtime/connection/presentation/realtime_connection_notifier.dart';
import 'package:quwoquan_app/realtime/realtime/connection/application/realtime_connection_operation_gateway.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/remote/user/contact_discovery/contact_discovery_remote.dart';
import 'package:quwoquan_app/application/content/media/content_media_upload_coordinator.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_repository.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_visit_writer.dart';
import 'package:quwoquan_app/cloud/services/user/contact_discovery_repository.dart';
import 'package:quwoquan_app/cloud/services/user/greeting_repository.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_sync_repository.dart';
import 'package:quwoquan_app/core/services/cache/conversation_cache_service.dart';
import 'package:quwoquan_app/core/services/cache/conversation_sync_service.dart';
import 'package:quwoquan_app/core/services/cache/cache_management_service.dart';
import 'package:quwoquan_app/core/services/cache/content_cache_services.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_store.dart';
import 'package:quwoquan_app/core/services/cache/local_search_namespace.dart';
import 'package:quwoquan_app/core/services/cache/local_chat_search_sync_service.dart';
import 'package:quwoquan_app/core/services/cache/local_circle_group_search_index.dart';
import 'package:quwoquan_app/core/services/cache/local_circle_group_snapshot_store.dart';
import 'package:quwoquan_app/core/services/cache/user_profile_cache_service.dart';
import 'package:quwoquan_app/core/di/ops_event_dependencies.dart';
import 'package:quwoquan_app/runtime/di/user_dependencies.dart';
import 'package:quwoquan_app/core/services/hybrid_search_repository.dart';
import 'package:quwoquan_app/core/services/location_place_read_query.dart';
import 'package:quwoquan_app/core/services/remote_search_repository.dart';
import 'package:quwoquan_app/core/services/search_repository.dart';
import 'package:quwoquan_app/application/search/search_operation_ports.dart';
import 'package:quwoquan_app/cloud/remote/search/search_query_remote.dart';
import 'package:quwoquan_app/core/trackers/content_engagement_tracker.dart';
import 'package:quwoquan_app/core/trackers/chat_interaction_telemetry_tracker.dart';
import 'package:quwoquan_app/core/trackers/journey_event_tracker.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    hide ContentDiscoveryFeedQuery;
import 'package:quwoquan_app/core/providers/app_providers_app_state.dart';
import 'package:quwoquan_app/core/providers/app_providers_circle_facets.dart';
import 'package:quwoquan_app/core/providers/app_providers_client_sync.dart';
import 'package:quwoquan_app/core/providers/app_providers_content_extras.dart';
import 'package:quwoquan_app/core/providers/app_providers_content_facets.dart';
import 'package:quwoquan_app/core/providers/app_providers_operations.dart';
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
    final personaId = persona?.personaId.trim() ?? '';
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
      final personaId = persona?.personaId.trim() ?? '';
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
        currentUserIdResolver: (ref) => ref.read(currentUserIdProvider).trim(),
        operationGatewayResolver: (ref) =>
            RemoteRealtimeConnectionOperationGateway(
              client: ref.read(generatedCloudOperationClientProvider),
              invocationContext: (clientPageId) => locationInvocationContext(
                ref,
                surface: AppUiSurfaces.appShell,
                clientPageId: clientPageId,
              ),
            ),
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

  Future<void> clearAccountScopedPersistence() {
    return Future.wait<void>(<Future<void>>[
      SearchRecentHistoryStore.clearAllNamespaces(),
      ref.read(localChatSearchStoreProvider).clearAllNamespaces(),
      ref.read(localCircleGroupSnapshotStoreProvider).clearAllNamespaces(),
    ]);
  }

  return CacheManagementService(
    postCache: ref.watch(postObjectCacheProvider),
    querySnapshotStore: ref.watch(contentQuerySnapshotStoreProvider),
    userProfileCache: ref.watch(userProfileCacheProvider),
    conversationCache: ref.watch(conversationCacheProvider),
    clearTemporaryImages: clearEphemeralResources,
    clearAllRebuildableImages: clearAllRebuildableResources,
    clearAccountScopedPersistence: clearAccountScopedPersistence,
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

final localCircleGroupSearchIndexProvider =
    Provider<LocalCircleGroupSearchIndex>((ref) {
      return SqfliteLocalCircleGroupSearchIndex(
        ref.watch(localCircleGroupSnapshotStoreProvider),
        ref.watch(activePersonaContextLoaderProvider),
        ref.watch(circlesListQueryProvider),
        ref.watch(globalSearchCircleGroupQueryProvider),
      );
    });

final userSyncRepositoryProvider = Provider<UserSyncRepository>((ref) {
  final ownerUserId = ref.watch(resolvedOwnerUserIdProvider);
  return UserProductionComposition.generatedAdapter<UserSyncRepository>(
    UserProductionAdapter.userSync,
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (String clientPageId) {
      final persona = ref.read(activePersonaContextProvider).asData?.value;
      final resolvedOwnerUserId = persona?.ownerUserId.trim() ?? '';
      final accountId = resolvedOwnerUserId.isNotEmpty
          ? resolvedOwnerUserId
          : ownerUserId.trim();
      final personaId = persona?.personaId.trim() ?? '';
      return CloudOperationInvocationContext(
        surfaceId: AppUiSurfaces.chatList.id,
        routeId: AppUiSurfaces.chatList.routeId,
        clientPageId: clientPageId,
        actor: CloudOperationActorContext(
          accountId: accountId.isEmpty ? null : accountId,
          personaId: personaId.isEmpty ? null : personaId,
        ),
      );
    },
  );
});

final _followingSubjectFacetsProvider =
    Provider<AppProductionFollowingSubjectFacets>((ref) {
      return UserProductionComposition.followingSubjectFacets(
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId, {String? idempotencyKey}) =>
            locationInvocationContext(
              ref,
              surface: AppUiSurfaces.homeFeed,
              clientPageId: clientPageId,
              idempotencyKey: idempotencyKey,
            ),
      );
    });

/// 关注频道读取端口；production 唯一经组合根装配 generated-client adapter。
final followingSubjectQueryProvider = Provider<FollowingSubjectQuery>(
  (ref) => ref.watch(_followingSubjectFacetsProvider).query,
);

/// 关注频道访问水位写入端口；alpha/test 覆盖同一对象级 typed port。
final followedSubjectVisitCommandWriterProvider =
    Provider<FollowedSubjectVisitCommandWriter>(
      (ref) => ref.watch(_followingSubjectFacetsProvider).visitWriter,
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
      invocationContext: (clientPageId) => locationInvocationContext(
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
    writer: ref.watch(contentBehaviorCommandWriterProvider),
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
    client: ref.watch(generatedCloudOperationClientProvider),
    myIntersectionsInvocationContext: (clientPageId) =>
        contentQueryInvocationContext(
          ref,
          surface: AppUiSurfaces.myIntersections,
          clientPageId: clientPageId,
        ),
    objectIntersectionsInvocationContext: (clientPageId) =>
        contentQueryInvocationContext(
          ref,
          surface: AppUiSurfaces.objectIntersections,
          clientPageId: clientPageId,
        ),
  ),
);

/// IntersectionVisitState typed 写面（content/content/intersection_visit_state 对象）：
/// production Remote-only；alpha/test 经 override 注入 Mock 同构替身。
final intersectionVisitWriterProvider = Provider<IntersectionVisitWriter>((
  ref,
) {
  return RemoteIntersectionVisitWriter(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId) => contentQueryInvocationContext(
      ref,
      surface: AppUiSurfaces.myIntersections,
      clientPageId: clientPageId,
    ),
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
    invocationContext: (clientPageId) => locationInvocationContext(
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
      sessionIdProvider: () => ref.read(feedSessionProvider.notifier).sessionId,
    ),
    ref.watch(localChatSearchStoreProvider),
    ref.watch(localChatSearchSyncProvider),
    ref.watch(localCircleGroupSearchIndexProvider),
    ref.watch(activePersonaContextLoaderProvider),
    ref.watch(cacheTelemetrySinkProvider),
  );
});

/// Direct `location.place` reads for deep links and process recovery.
///
/// Production delegates to the canonical remote Search operation; tests and
/// alpha inject a typed object-level substitute through this provider.
final locationPlaceReadQueryProvider = Provider<LocationPlaceReadQuery>((ref) {
  return SearchLocationPlaceReadQuery(
    search: ref.watch(searchRepositoryProvider),
  );
});

/// RelationshipCapability Repository（关系能力位投影，用户主页五态按钮矩阵 + RTC 门禁）
final relationshipCapabilityRepositoryProvider =
    Provider<RelationshipCapabilityRepository>((ref) {
      return RemoteRelationshipCapabilityRepository(
        query: ref.watch(
          personaRelationshipRemoteProvider(AppUiSurfaces.userProfile),
        ),
      );
    });

/// Greeting Repository（打招呼请求箱）
final greetingRepositoryProvider = Provider<GreetingRepository>((ref) {
  final facet = ref.watch(
    greetingRequestRemoteProvider(AppUiSurfaces.userProfile),
  );
  return RemoteGreetingRepository(commandWriter: facet, query: facet);
});

/// TagCatalogQuery（标签层级/解析/校验）：
/// production Remote-only（08 Mock 隔离），alpha 经 override 注入 TagCatalogTypedDouble。
final tagCatalogQueryProvider = Provider<TagCatalogQuery>((ref) {
  return RemoteGeneratedTagCatalogQuery(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId) => locationInvocationContext(
      ref,
      surface: AppUiSurfaces.profileCareerInterests,
      clientPageId: clientPageId,
    ),
  );
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
