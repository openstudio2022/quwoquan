import 'dart:async';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/di/cloud_http_client_provider.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/adapters/media_download_cache.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/adapters/media_upload_manager.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/media_upload_queue.dart';
import 'package:quwoquan_app/runtime/di/generated_operation_client_dependencies.dart';
import 'package:quwoquan_app/service/search_service/search/recent_search_state/adapters/search_recent_history_store.dart';
import 'package:quwoquan_app/service/tag_service/tag/tag_node_view/application/public/tag_catalog_query.dart';
import 'package:quwoquan_app/runtime/di/feed_session_provider.dart';
import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/application/chat_inbox_provider.dart';
import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/application/chat_inbox_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/application/greeting_inbox_provider.dart';
import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/application/public/chat_inbox_cache.dart';
import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/application/public/chat_inbox_list_commands.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/chat_conversation_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/conversation_avatar_members_provider.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/conversation_avatar_prefetch.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation_membership/application/public/chat_member_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/chat_message_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_timeline_cache.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/message_home_cache.dart';
import 'package:quwoquan_app/service/chat_service/chat/message_receipt_fact/application/public/message_receipt_fact_query.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/domain/realtime_connection_delegate.dart';
import 'package:quwoquan_app/service/realtime_gateway/realtime/connection/application/realtime_connection_notifier.dart';
import 'package:quwoquan_app/runtime/di/realtime_dependencies.dart';
import 'package:quwoquan_app/runtime/di/chat_dependencies.dart';
import 'package:quwoquan_app/runtime/di/chat_repository_facade.dart';
import 'package:quwoquan_app/runtime/di/content_dependencies.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/content_media_upload_coordinator.dart';
import 'package:quwoquan_app/service/content_service/content/intersection_visit_state/adapters/intersection_repository.dart';
import 'package:quwoquan_app/service/content_service/content/intersection_visit_state/adapters/intersection_visit_writer.dart';
import 'package:quwoquan_app/service/user_service/relationship/contact_discovery_record/application/public/contact_discovery_repository.dart';
import 'package:quwoquan_app/service/user_service/profile_projection/following_subject/application/public/following_subject_reader.dart';
import 'package:quwoquan_app/service/user_service/relationship/followed_subject_visit_state/application/public/followed_subject_visit_state_writer.dart';
import 'package:quwoquan_app/service/user_service/relationship/greeting_request/application/public/greeting_repository.dart';
import 'package:quwoquan_app/service/user_service/relationship/greeting_request/application/public/greeting_inbox_refresh.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/relationship_capability_repository.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/user_sync_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/adapters/conversation_cache_service.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/adapters/conversation_sync_service.dart';
import 'package:quwoquan_app/runtime/di/cache_management_service.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/content_cache_services.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/adapters/local_chat_search_store.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/adapters/local_search_namespace.dart';
import 'package:quwoquan_app/runtime/di/local_chat_search_sync_service.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/adapters/local_circle_group_search_index.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/adapters/local_circle_group_snapshot_store.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/application/public/circle_group_local_search.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/adapters/user_profile_cache_service.dart';
import 'package:quwoquan_app/runtime/di/ops_event_dependencies.dart';
import 'package:quwoquan_app/runtime/di/search_dependencies.dart';
import 'package:quwoquan_app/runtime/di/tag_dependencies.dart';
import 'package:quwoquan_app/runtime/di/user_dependencies.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/adapters/hybrid_search_repository.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/location_place_read_query.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/public/conversation_avatar_search_index.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/search_repository.dart';
import 'package:quwoquan_app/runtime/observability/trackers/chat_interaction_telemetry_tracker.dart';
import 'package:quwoquan_app/runtime/observability/trackers/journey_event_tracker.dart';
import 'package:quwoquan_app/runtime/platform/platform_providers.dart'
    show fileStorageGatewayProvider;
import 'package:quwoquan_app/runtime/platform/storage/local_database_path_resolver.dart';
import 'package:quwoquan_app/runtime/platform/storage/media_cache_file_storage_gateway.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    hide ContentDiscoveryFeedQuery;
import 'package:quwoquan_app/runtime/di/app_providers_app_state.dart';
import 'package:quwoquan_app/runtime/di/app_providers_circle_facets.dart';
import 'package:quwoquan_app/runtime/di/app_providers_client_sync.dart';
import 'package:quwoquan_app/runtime/di/app_providers_content_extras.dart';
import 'package:quwoquan_app/runtime/di/app_providers_content_facets.dart';
import 'package:quwoquan_app/runtime/di/app_providers_operations.dart';

/// Chat 域 production 组合根。内部只组合对象级 Remote Facet；测试可在
/// local_contract 边界覆盖该聚合入口，环境 App 始终使用同一 Remote composition。
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

  return ChatProductionComposition.repository(
    client: client,
    invocationContext: invocationContext,
  );
});

/// ChatInboxView 对象读 Facet。
final chatInboxRepositoryProvider = Provider<ChatInboxRepository>(
  (ref) => ref.watch(chatRepositoryCompositionProvider),
);

/// Conversation 对外会话头像预取能力；跨对象只消费 public seam，不直连 Notifier。
final conversationAvatarPrefetchProvider =
    Provider<ConversationAvatarPrefetchCapability>((ref) {
      return ref.read(conversationAvatarMembersProvider.notifier);
    });

/// ChatInboxView 对外列表命令；跨对象只消费 public seam，不直连 inbox Notifier。
final chatInboxListCommandsProvider = Provider<ChatInboxListCommands>((ref) {
  return ref.read(chatInboxListProvider.notifier);
});

/// Chat Conversation 对象查询/命令 Facet。
final chatConversationRepositoryProvider = Provider<ChatConversationRepository>(
  (ref) => ref.watch(chatRepositoryCompositionProvider),
);

/// Chat 消息对象 Facet（历史、同步、撤回、已读、回执）。
final chatMessageRepositoryProvider = Provider<ChatMessageRepository>(
  (ref) => ref.watch(chatRepositoryCompositionProvider),
);

/// MessageReceiptFact 对象查询 Facet。页面只消费该窄端口，不穿透 Message adapter。
final messageReceiptFactQueryProvider = Provider<MessageReceiptFactQuery>((
  ref,
) {
  return ChatProductionComposition.messageReceiptFactQuery(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (surface, clientPageId, {idempotencyKey}) {
      final ownerUserId = ref.read(resolvedOwnerUserIdProvider).trim();
      final persona = ref.read(activePersonaContextProvider).asData?.value;
      final personaId = persona?.personaId.trim() ?? '';
      return CloudOperationInvocationContext(
        surfaceId: surface.id,
        routeId: surface.routeId,
        clientPageId: clientPageId,
        actor: CloudOperationActorContext(
          accountId: ownerUserId.isEmpty ? null : ownerUserId,
          personaId: personaId.isEmpty ? null : personaId,
        ),
        idempotencyKey: idempotencyKey,
      );
    },
  );
});

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
  return ChatProductionComposition.messageCommandWriter(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (surface, clientPageId, {idempotencyKey}) {
      final accountId = ref.read(resolvedOwnerUserIdProvider).trim();
      final persona = ref.read(activePersonaContextProvider).asData?.value;
      final personaId = persona?.personaId.trim() ?? '';
      return CloudOperationInvocationContext(
        surfaceId: surface.id,
        clientPageId: clientPageId,
        routeId: surface.routeId,
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
            RealtimeProductionComposition.connectionOperations(
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

final chatInboxCacheProvider = Provider<ChatInboxCache>(
  (ref) => ref.watch(conversationCacheProvider),
);

final messageHomeCacheProvider = Provider<MessageHomeCache>(
  (ref) => ref.watch(conversationCacheProvider),
);

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
    personaContextLoader: ref.read(searchActorScopeLoaderProvider),
  );
});

final _localDatabasePathResolverProvider = Provider<LocalDatabasePathResolver>((
  ref,
) {
  return createLocalDatabasePathResolver(ref.watch(fileStorageGatewayProvider));
});

final localChatSearchStoreProvider = Provider<LocalChatSearchStore>((ref) {
  final store = LocalChatSearchStore(
    databasePathResolver: ref.watch(_localDatabasePathResolverProvider),
  );
  ref.onDispose(() => unawaited(store.close()));
  return store;
});

/// Chat Message application only sees its public timeline seam; SQLite remains
/// a Search adapter detail composed here.
final chatMessageTimelineCacheProvider = Provider<ChatMessageTimelineCache>(
  (ref) => ref.watch(localChatSearchStoreProvider),
);

final localCircleGroupSnapshotStoreProvider =
    Provider<LocalCircleGroupSnapshotStore>((ref) {
      final store = LocalCircleGroupSnapshotStore(
        databasePathResolver: ref.watch(_localDatabasePathResolverProvider),
      );
      ref.onDispose(() => unawaited(store.close()));
      return store;
    });

final localCircleGroupSearchIndexProvider =
    Provider<CircleGroupLocalSearchIndex>((ref) {
      return SqfliteLocalCircleGroupSearchIndex(
        ref.watch(localCircleGroupSnapshotStoreProvider),
        ref.watch(searchActorScopeLoaderProvider),
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

/// 关注频道读取端口；production 唯一经组合根装配 generated-client adapter。
final followingSubjectQueryProvider = Provider<FollowingSubjectReader>((ref) {
  return UserProductionComposition.followingSubjectReader(
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

/// 关注频道访问水位写入端口；alpha/test 覆盖同一对象级 typed port。
final followedSubjectVisitCommandWriterProvider =
    Provider<FollowedSubjectVisitStateWriter>((ref) {
      return UserProductionComposition.followedSubjectVisitStateWriter(
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
    return UserProductionComposition.contactDiscoveryRepository(
      client: ref.watch(generatedCloudOperationClientProvider),
      invocationContext: (clientPageId) => locationInvocationContext(
        ref,
        surface: AppUiSurfaces.addContactPhone,
        clientPageId: clientPageId,
      ),
    );
  },
);

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
  (ref) => ContentProductionComposition.intersectionRepository(
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
  return ContentProductionComposition.intersectionVisitWriter(
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

final searchActorScopeLoaderProvider = Provider<SearchActorScopeLoader>((ref) {
  final loadPersona = ref.watch(activePersonaContextLoaderProvider);
  return () async {
    final context = await loadPersona();
    final ownerUserId = context.ownerUserId.trim();
    final personaId = context.personaId.trim().isEmpty
        ? ownerUserId
        : context.personaId.trim();
    return SearchActorScope(
      ownerUserId: ownerUserId,
      personaId: personaId,
      subjectType: context.subjectType.trim(),
      personaContextVersion: context.contextVersion.toString(),
    );
  };
});

final localChatSearchSyncProvider = Provider<LocalChatSearchSyncService>((ref) {
  return LocalChatSearchSyncService(
    contactRepository: ref.watch(chatContactRepositoryProvider),
    conversationRepository: ref.watch(chatConversationRepositoryProvider),
    messageRepository: ref.watch(chatMessageRepositoryProvider),
    conversationCache: ref.watch(conversationCacheProvider),
    store: ref.watch(localChatSearchStoreProvider),
    personaContextLoader: ref.watch(activePersonaContextLoaderProvider),
    telemetrySink: ref.watch(cacheTelemetrySinkProvider),
  );
});

/// 两阶段搜索：result 只走 search-service canonical Remote；suggest 在 Remote
/// 结果上合并账号隔离的本地联系人/会话/消息索引。本地对象绝不进入结果页。
/// alpha/test 通过 ProviderScope override 该对象级 Repository。
final searchRepositoryProvider = Provider<SearchRepository>((ref) {
  return HybridSearchRepository(
    SearchProductionComposition.searchRepository(
      client: ref.watch(generatedCloudOperationClientProvider),
      invocationContext: (clientPageId) => locationInvocationContext(
        ref,
        surface: AppUiSurfaces.globalSearchNetworkResults,
        clientPageId: clientPageId,
      ),
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
      return UserProductionComposition.relationshipCapabilityRepository(
        query: ref
            .watch(personaRelationshipRemoteProvider(AppUiSurfaces.userProfile))
            .capabilityQuery,
      );
    });

/// Greeting Repository（打招呼请求箱）
final greetingRepositoryProvider = Provider<GreetingRepository>((ref) {
  final facet = ref.watch(
    greetingRequestRemoteProvider(AppUiSurfaces.userProfile),
  );
  return UserProductionComposition.greetingRepository(facets: facet);
});

final greetingInboxRefreshProvider = Provider<GreetingInboxRefresh>(
  _RiverpodGreetingInboxRefresh.new,
);

final class _RiverpodGreetingInboxRefresh implements GreetingInboxRefresh {
  const _RiverpodGreetingInboxRefresh(this._ref);

  final Ref _ref;

  @override
  void refreshPendingInbox() => _ref.invalidate(chatGreetingInboxProvider);
}

/// TagCatalogQuery（标签层级/解析/校验）：
/// production Remote-only（08 Mock 隔离），alpha 经 override 注入 TagCatalogTypedDouble。
final tagCatalogQueryProvider = Provider<TagCatalogQuery>((ref) {
  return TagProductionComposition.catalogQuery(
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

final mediaUploadQueueProvider = Provider<MediaUploadQueue>(
  (ref) => ref.watch(mediaUploadManagerProvider),
);

/// Media Download Cache（LRU 媒体下载缓存，默认 200MB）
final mediaDownloadCacheProvider = Provider<MediaDownloadCache>((ref) {
  final profile = ref.watch(appResourceCacheProfileProvider);
  final fileStorageGateway = requireMediaCacheFileStorageGateway(
    ref.watch(fileStorageGatewayProvider),
  );
  return MediaDownloadCache(
    client: ref.watch(mediaDataPlaneHttpClientProvider),
    maxCacheSizeMb: profile.maxMediaDownloadCacheSizeMb,
    maxConcurrentDownloads: profile.maxConcurrentMediaDownloads,
    fileStorageGateway: fileStorageGateway,
    telemetrySink: ref.watch(cacheTelemetrySinkProvider),
  );
});
