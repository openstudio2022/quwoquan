part of 'app_providers.dart';

CloudOperationInvocationContext _circleOperationInvocationContext(
  Ref ref, {
  required AppUiSurface surface,
  required String clientPageId,
  required bool command,
  String? idempotencyKey,
}) {
  final accountId = ref.read(resolvedOwnerUserIdProvider).trim();
  final persona = ref.read(activePersonaContextProvider).asData?.value;
  final personaId = persona?.subAccountId.trim() ?? '';
  return CloudOperationInvocationContext(
    surfaceId: surface.id,
    clientPageId: clientPageId,
    routeId: surface.routeId,
    actor: CloudOperationActorContext(
      accountId: accountId.isEmpty ? null : accountId,
      personaId: personaId.isEmpty ? null : personaId,
    ),
    idempotencyKey: command
        ? (idempotencyKey ?? AppTraceContextStore.instance.newRequestId())
        : null,
  );
}

RemoteCircleMembershipFacet _remoteCircleMembershipFacet(
  Ref ref,
  AppUiSurface surface,
) {
  if (ref.watch(appDataSourceModeProvider) != AppDataSourceMode.remote) {
    throw StateError(
      'CircleMembership Facets are Remote-only in production composition; alpha must override them from quwoquan_cloud_mock',
    );
  }
  return RemoteCircleMembershipFacet(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId, {required command}) =>
        _circleOperationInvocationContext(
          ref,
          surface: surface,
          clientPageId: clientPageId,
          command: command,
        ),
  );
}

RemoteCircleGroupFacet _remoteCircleGroupFacet(Ref ref, AppUiSurface surface) {
  if (ref.watch(appDataSourceModeProvider) != AppDataSourceMode.remote) {
    throw StateError(
      'CircleGroup Facets are Remote-only in production composition; alpha must override them from quwoquan_cloud_mock',
    );
  }
  return RemoteCircleGroupFacet(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId, {required command}) =>
        _circleOperationInvocationContext(
          ref,
          surface: surface,
          clientPageId: clientPageId,
          command: command,
        ),
  );
}

RemoteCircleFileFacet _remoteCircleFileFacet(Ref ref, AppUiSurface surface) {
  if (ref.watch(appDataSourceModeProvider) != AppDataSourceMode.remote) {
    throw StateError(
      'CircleFile Facets are Remote-only in production composition; alpha must override them from quwoquan_cloud_mock',
    );
  }
  return RemoteCircleFileFacet(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId, {required command}) =>
        _circleOperationInvocationContext(
          ref,
          surface: surface,
          clientPageId: clientPageId,
          command: command,
        ),
  );
}

RemoteCircleLifecycleFacet _remoteCircleLifecycleFacet(
  Ref ref,
  AppUiSurface surface,
) {
  if (ref.watch(appDataSourceModeProvider) != AppDataSourceMode.remote) {
    throw StateError(
      'Circle lifecycle Facets are Remote-only in production composition; alpha must override them from quwoquan_cloud_mock',
    );
  }
  return RemoteCircleLifecycleFacet(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId, {required command}) =>
        _circleOperationInvocationContext(
          ref,
          surface: surface,
          clientPageId: clientPageId,
          command: command,
        ),
  );
}

RemoteCircleQueryReader _remoteCircleQueryReader(
  Ref ref,
  AppUiSurface surface,
) {
  if (ref.watch(appDataSourceModeProvider) != AppDataSourceMode.remote) {
    throw StateError(
      'Circle query facets are Remote-only in production composition; alpha must override them from quwoquan_cloud_mock',
    );
  }
  return RemoteCircleQueryReader(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId, {required command}) =>
        _circleOperationInvocationContext(
          ref,
          surface: surface,
          clientPageId: clientPageId,
          command: command,
        ),
  );
}

final circlesListDiscoveryFeedQueryProvider =
    Provider<CircleDiscoveryFeedQueryReader>(
      (ref) => _remoteCircleQueryReader(ref, AppUiSurfaces.circlesList),
    );

/// 圈子目录的 typed 查询能力；生产只装配 generated Remote reader。
final circlesListQueryProvider = Provider<CircleQueryReader>(
  (ref) => _remoteCircleQueryReader(ref, AppUiSurfaces.circlesList),
);

/// 圈子详情的 typed 查询能力；生产只装配 generated Remote reader。
final circleDetailQueryProvider = Provider<CircleQueryReader>(
  (ref) => _remoteCircleQueryReader(ref, AppUiSurfaces.circleDetail),
);

final circleDetailFeedQueryProvider = Provider<CircleFeedQueryReader>(
  (ref) => _remoteCircleQueryReader(ref, AppUiSurfaces.circleDetail),
);

final circleDetailPostPlacementCommandWriterProvider =
    Provider<CirclePostPlacementCommandWriter>((ref) {
      if (ref.watch(appDataSourceModeProvider) != AppDataSourceMode.remote) {
        throw StateError(
          'CirclePostPlacementCommandWriter is Remote-only in production composition; alpha must override it from quwoquan_cloud_mock',
        );
      }
      return RemoteCirclePostPlacementCommandWriter(
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId, idempotencyKey) =>
            _circleOperationInvocationContext(
              ref,
              surface: AppUiSurfaces.circleDetail,
              clientPageId: clientPageId,
              command: true,
              idempotencyKey: idempotencyKey,
            ),
      );
    });

final circleProjectionMapperProvider = Provider<CircleProjectionMapper>(
  (ref) => const CircleProjectionMapper(),
);

/// 建圈动作归属圈子列表 surface（circlesList）。
final circlesListCircleLifecycleCommandWriterProvider =
    Provider<CircleLifecycleCommandWriter>(
      (ref) => _remoteCircleLifecycleFacet(ref, AppUiSurfaces.circlesList),
    );

/// 圈主管理动作（更新/归档/板块配置）归属详情 surface（circleDetail）。
final circleDetailCircleLifecycleCommandWriterProvider =
    Provider<CircleLifecycleCommandWriter>(
      (ref) => _remoteCircleLifecycleFacet(ref, AppUiSurfaces.circleDetail),
    );

final circleDetailCircleConfigurationCommandWriterProvider =
    Provider<CircleConfigurationCommandWriter>(
      (ref) => _remoteCircleLifecycleFacet(ref, AppUiSurfaces.circleDetail),
    );

final circleDetailGroupQueryProvider = Provider<CircleGroupQueryReader>(
  (ref) => _remoteCircleGroupFacet(ref, AppUiSurfaces.circleDetail),
);

final circleDetailFileCommandWriterProvider = Provider<CircleFileCommandWriter>(
  (ref) => _remoteCircleFileFacet(ref, AppUiSurfaces.circleDetail),
);

final circleDetailFileQueryProvider = Provider<CircleFileQueryReader>(
  (ref) => _remoteCircleFileFacet(ref, AppUiSurfaces.circleDetail),
);

final circleStatsGroupQueryProvider = Provider<CircleGroupQueryReader>(
  (ref) => _remoteCircleGroupFacet(ref, AppUiSurfaces.circleDetail),
);

final globalSearchCircleGroupQueryProvider = Provider<CircleGroupQueryReader>(
  (ref) => _remoteCircleGroupFacet(ref, AppUiSurfaces.globalSearchSuggestions),
);

final circleDetailMembershipCommandWriterProvider =
    Provider<CircleMembershipCommandWriter>(
      (ref) => _remoteCircleMembershipFacet(ref, AppUiSurfaces.circleDetail),
    );

final circleDetailMembershipQueryProvider = Provider<CircleMembershipQuery>(
  (ref) => _remoteCircleMembershipFacet(ref, AppUiSurfaces.circleDetail),
);

/// 圈子级审批（owner/admin）：命令与待审批队列按 circleDetail surface 装配。
final circleDetailMembershipModerationWriterProvider =
    Provider<CircleMembershipModerationWriter>(
      (ref) => _remoteCircleMembershipFacet(ref, AppUiSurfaces.circleDetail),
    );

final circleDetailPendingMembershipQueryProvider =
    Provider<PendingCircleMembershipQuery>(
      (ref) => _remoteCircleMembershipFacet(ref, AppUiSurfaces.circleDetail),
    );

final circleStatsMembershipQueryProvider = Provider<CircleMembershipQuery>(
  (ref) => _remoteCircleMembershipFacet(ref, AppUiSurfaces.circleStats),
);

final homeFeedCircleMembershipQueryProvider = Provider<CircleMembershipQuery>(
  (ref) => _remoteCircleMembershipFacet(ref, AppUiSurfaces.homeFeed),
);

final workBrowserCircleMembershipQueryProvider =
    Provider<CircleMembershipQuery>(
      (ref) => _remoteCircleMembershipFacet(ref, AppUiSurfaces.workBrowser),
    );

final userProfileCircleMembershipQueryProvider =
    Provider<CircleMembershipQuery>(
      (ref) => _remoteCircleMembershipFacet(ref, AppUiSurfaces.userProfile),
    );

final circleDetailBehaviorFactWriterProvider = Provider<CircleBehaviorFactWriter>((
  ref,
) {
  if (ref.watch(appDataSourceModeProvider) != AppDataSourceMode.remote) {
    throw StateError(
      'CircleBehaviorFactWriter is Remote-only in production composition; alpha must override it from quwoquan_cloud_mock',
    );
  }
  return RemoteCircleBehaviorFactWriter(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId) => _circleOperationInvocationContext(
      ref,
      surface: AppUiSurfaces.circleDetail,
      clientPageId: clientPageId,
      command: true,
    ),
  );
});
