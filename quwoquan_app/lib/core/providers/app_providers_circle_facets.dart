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

T _circlePort<T>(Ref ref, AppUiSurface surface, AppProductionAdapter adapter) {
  if (ref.watch(appDataSourceModeProvider) != AppDataSourceMode.remote) {
    throw StateError(
      'Circle ports are Remote-only in production composition; alpha must override them from quwoquan_cloud_mock',
    );
  }
  return AppProductionComposition.generatedAdapter<T>(
    adapter,
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
      (ref) => _circlePort(
        ref,
        AppUiSurfaces.circlesList,
        AppProductionAdapter.circleQuery,
      ),
    );

/// 圈子目录的 typed 查询能力；生产只装配 generated Remote reader。
final circlesListQueryProvider = Provider<CircleQueryReader>(
  (ref) => _circlePort(
    ref,
    AppUiSurfaces.circlesList,
    AppProductionAdapter.circleQuery,
  ),
);

/// 圈子详情的 typed 查询能力；生产只装配 generated Remote reader。
final circleDetailQueryProvider = Provider<CircleQueryReader>(
  (ref) => _circlePort(
    ref,
    AppUiSurfaces.circleDetail,
    AppProductionAdapter.circleQuery,
  ),
);

final circleDetailFeedQueryProvider = Provider<CircleFeedQueryReader>(
  (ref) => _circlePort(
    ref,
    AppUiSurfaces.circleDetail,
    AppProductionAdapter.circleQuery,
  ),
);

final circleDetailPostPlacementCommandWriterProvider =
    Provider<CirclePostPlacementCommandWriter>((ref) {
      if (ref.watch(appDataSourceModeProvider) != AppDataSourceMode.remote) {
        throw StateError(
          'CirclePostPlacementCommandWriter is Remote-only in production composition; alpha must override it from quwoquan_cloud_mock',
        );
      }
      return AppProductionComposition.generatedAdapter<
        CirclePostPlacementCommandWriter
      >(
        AppProductionAdapter.circlePostPlacement,
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
      (ref) => _circlePort(
        ref,
        AppUiSurfaces.circlesList,
        AppProductionAdapter.circleLifecycle,
      ),
    );

/// 圈主管理动作（更新/归档/板块配置）归属详情 surface（circleDetail）。
final circleDetailCircleLifecycleCommandWriterProvider =
    Provider<CircleLifecycleCommandWriter>(
      (ref) => _circlePort(
        ref,
        AppUiSurfaces.circleDetail,
        AppProductionAdapter.circleLifecycle,
      ),
    );

final circleDetailCircleConfigurationCommandWriterProvider =
    Provider<CircleConfigurationCommandWriter>(
      (ref) => _circlePort(
        ref,
        AppUiSurfaces.circleDetail,
        AppProductionAdapter.circleLifecycle,
      ),
    );

final circleDetailGroupQueryProvider = Provider<CircleGroupQueryReader>(
  (ref) => _circlePort(
    ref,
    AppUiSurfaces.circleDetail,
    AppProductionAdapter.circleGroup,
  ),
);

final circleDetailFileCommandWriterProvider = Provider<CircleFileCommandWriter>(
  (ref) => _circlePort(
    ref,
    AppUiSurfaces.circleDetail,
    AppProductionAdapter.circleFile,
  ),
);

final circleDetailFileQueryProvider = Provider<CircleFileQueryReader>(
  (ref) => _circlePort(
    ref,
    AppUiSurfaces.circleDetail,
    AppProductionAdapter.circleFile,
  ),
);

final circleStatsGroupQueryProvider = Provider<CircleGroupQueryReader>(
  (ref) => _circlePort(
    ref,
    AppUiSurfaces.circleDetail,
    AppProductionAdapter.circleGroup,
  ),
);

final globalSearchCircleGroupQueryProvider = Provider<CircleGroupQueryReader>(
  (ref) => _circlePort(
    ref,
    AppUiSurfaces.globalSearchSuggestions,
    AppProductionAdapter.circleGroup,
  ),
);

final circleDetailMembershipCommandWriterProvider =
    Provider<CircleMembershipCommandWriter>(
      (ref) => _circlePort(
        ref,
        AppUiSurfaces.circleDetail,
        AppProductionAdapter.circleMembership,
      ),
    );

final circleDetailMembershipQueryProvider = Provider<CircleMembershipQuery>(
  (ref) => _circlePort(
    ref,
    AppUiSurfaces.circleDetail,
    AppProductionAdapter.circleMembership,
  ),
);

/// 圈子级审批（owner/admin）：命令与待审批队列按 circleDetail surface 装配。
final circleDetailMembershipModerationWriterProvider =
    Provider<CircleMembershipModerationWriter>(
      (ref) => _circlePort(
        ref,
        AppUiSurfaces.circleDetail,
        AppProductionAdapter.circleMembership,
      ),
    );

final circleDetailPendingMembershipQueryProvider =
    Provider<PendingCircleMembershipQuery>(
      (ref) => _circlePort(
        ref,
        AppUiSurfaces.circleDetail,
        AppProductionAdapter.circleMembership,
      ),
    );

final circleStatsMembershipQueryProvider = Provider<CircleMembershipQuery>(
  (ref) => _circlePort(
    ref,
    AppUiSurfaces.circleStats,
    AppProductionAdapter.circleMembership,
  ),
);

final homeFeedCircleMembershipQueryProvider = Provider<CircleMembershipQuery>(
  (ref) => _circlePort(
    ref,
    AppUiSurfaces.homeFeed,
    AppProductionAdapter.circleMembership,
  ),
);

final workBrowserCircleMembershipQueryProvider =
    Provider<CircleMembershipQuery>(
      (ref) => _circlePort(
        ref,
        AppUiSurfaces.workBrowser,
        AppProductionAdapter.circleMembership,
      ),
    );

final userProfileCircleMembershipQueryProvider =
    Provider<CircleMembershipQuery>(
      (ref) => _circlePort(
        ref,
        AppUiSurfaces.userProfile,
        AppProductionAdapter.circleMembership,
      ),
    );

final circleDetailBehaviorFactWriterProvider = Provider<CircleBehaviorFactWriter>((
  ref,
) {
  if (ref.watch(appDataSourceModeProvider) != AppDataSourceMode.remote) {
    throw StateError(
      'CircleBehaviorFactWriter is Remote-only in production composition; alpha must override it from quwoquan_cloud_mock',
    );
  }
  return AppProductionComposition.generatedAdapter<CircleBehaviorFactWriter>(
    AppProductionAdapter.circleBehaviorFact,
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId) => _circleOperationInvocationContext(
      ref,
      surface: AppUiSurfaces.circleDetail,
      clientPageId: clientPageId,
      command: true,
    ),
  );
});
