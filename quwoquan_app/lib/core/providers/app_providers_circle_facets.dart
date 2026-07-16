part of 'app_providers.dart';

CloudOperationInvocationContext _circleOperationInvocationContext(
  Ref ref, {
  required AppUiSurface surface,
  required String clientPageId,
  required bool command,
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
        ? AppTraceContextStore.instance.newRequestId()
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

RemoteCircleGroupMembershipFacet _remoteCircleGroupMembershipFacet(
  Ref ref,
  AppUiSurface surface,
) {
  if (ref.watch(appDataSourceModeProvider) != AppDataSourceMode.remote) {
    throw StateError(
      'CircleGroupMembership Facets are Remote-only in production composition; alpha must override them from quwoquan_cloud_mock',
    );
  }
  return RemoteCircleGroupMembershipFacet(
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

final circleDetailGroupCommandWriterProvider =
    Provider<CircleGroupCommandWriter>(
      (ref) => _remoteCircleGroupFacet(ref, AppUiSurfaces.circleDetail),
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

final circleDetailGroupMembershipCommandWriterProvider =
    Provider<CircleGroupMembershipCommandWriter>(
      (ref) =>
          _remoteCircleGroupMembershipFacet(ref, AppUiSurfaces.circleDetail),
    );

final circleDetailGroupMembershipQueryProvider =
    Provider<CircleGroupMembershipQueryReader>(
      (ref) =>
          _remoteCircleGroupMembershipFacet(ref, AppUiSurfaces.circleDetail),
    );

final circleStatsGroupMembershipCommandWriterProvider =
    Provider<CircleGroupMembershipCommandWriter>(
      (ref) =>
          _remoteCircleGroupMembershipFacet(ref, AppUiSurfaces.circleStats),
    );

final circleStatsGroupMembershipQueryProvider =
    Provider<CircleGroupMembershipQueryReader>(
      (ref) =>
          _remoteCircleGroupMembershipFacet(ref, AppUiSurfaces.circleStats),
    );

final circleDetailMembershipCommandWriterProvider =
    Provider<CircleMembershipCommandWriter>(
      (ref) => _remoteCircleMembershipFacet(ref, AppUiSurfaces.circleDetail),
    );

final circleDetailMembershipQueryProvider = Provider<CircleMembershipQuery>(
  (ref) => _remoteCircleMembershipFacet(ref, AppUiSurfaces.circleDetail),
);

final circleStatsMembershipCommandWriterProvider =
    Provider<CircleMembershipCommandWriter>(
      (ref) => _remoteCircleMembershipFacet(ref, AppUiSurfaces.circleStats),
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
