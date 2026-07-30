part of 'app_providers.dart';

/// 仅供组合根装配 Remote / Mock / Cache 的强类型 facets holder。
/// 它不是业务 Repository；业务消费者只能读取各自的窄 Provider。
final class _ContentFacets {
  const _ContentFacets({
    required this.read,
    required this.write,
    required this.engagement,
    required this.config,
  });

  final ContentReadRepository read;
  final ContentWriteRepository write;
  final ContentEngagementRepository engagement;
  final ContentConfigRepository config;
}

final _contentFacetsProvider = Provider<_ContentFacets>((ref) {
  Future<List<String>> loadBlockedKeywords() async {
    if (!ref.read(authSessionControllerProvider).isAuthenticated) {
      return const <String>[];
    }
    return ref.read(blockedKeywordSnapshotCacheProvider).load(() async {
      final settings = await ref
          .read(userSettingsQueryReaderProvider)
          .getPrivacySettings();
      return settings.blockedKeywords;
    });
  }

  final facets = AppProductionComposition.contentFacets(
    httpClient: ref.watch(cloudHttpClientProvider),
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId) => _contentQueryInvocationContext(
      ref,
      surface: AppUiSurfaces.homeFeed,
      clientPageId: clientPageId,
    ),
    blockedKeywordsLoader: loadBlockedKeywords,
    postCache: ref.watch(postObjectCacheProvider),
    querySnapshotStore: ref.watch(contentQuerySnapshotStoreProvider),
    userProfileCache: ref.watch(userProfileCacheProvider),
    telemetrySink: ref.watch(cacheTelemetrySinkProvider),
  );
  return _ContentFacets(
    read: facets.read,
    write: facets.write,
    engagement: facets.engagement,
    config: facets.config,
  );
});

final profileMediaUploadGatewayProvider = Provider<ProfileMediaUploadGateway>((
  ref,
) {
  return ContentProfileMediaUploadGateway(
    ContentMediaUploadCoordinator(
      media: ref.watch(profileEditContentMediaFacetProvider),
      telemetry: ref.watch(appTelemetryReporterProvider),
    ),
    ref.watch(contentMediaSourceReaderProvider),
    ref.watch(contentMediaStreamObjectUploadProvider),
  );
});

final contentDiscoveryFeedQueryProvider = Provider<ContentDiscoveryFeedQuery>(
  (ref) => ref.watch(_contentFacetsProvider).read,
);
final contentWriteRepositoryProvider = Provider<ContentWriteRepository>(
  (ref) => ref.watch(_contentFacetsProvider).write,
);
final contentEngagementRepositoryProvider =
    Provider<ContentEngagementRepository>(
      (ref) => ref.watch(_contentFacetsProvider).engagement,
    );

ContentPostReactionFacet _productionPostReactionFacet(Ref ref) {
  return AppProductionComposition.generatedAdapter<ContentPostReactionFacet>(
    AppProductionAdapter.contentPostReaction,
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId, {required command}) {
      if (command) {
        return _contentCommandInvocationContext(
          ref,
          clientPageId: clientPageId,
        );
      }
      return _contentQueryInvocationContext(
        ref,
        surface: AppUiSurfaces.homeFeed,
        clientPageId: clientPageId,
      );
    },
  );
}

final contentPostReactionFacetProvider = Provider<ContentPostReactionFacet>(
  _productionPostReactionFacet,
);

final createContentPostPublicationWriterProvider =
    Provider<ContentPostPublicationWriter>((ref) {
      return AppProductionComposition.generatedAdapter<
        ContentPostPublicationWriter
      >(
        AppProductionAdapter.contentPostPublication,
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId, idempotencyKey) =>
            _contentCommandInvocationContext(
              ref,
              clientPageId: clientPageId,
              idempotencyKey: idempotencyKey,
            ),
      );
    });

ContentCommentFacet _remoteContentCommentFacet(Ref ref, AppUiSurface surface) {
  return AppProductionComposition.generatedAdapter<ContentCommentFacet>(
    AppProductionAdapter.contentComment,
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId, {required command}) {
      if (!command) {
        return _contentQueryInvocationContext(
          ref,
          surface: surface,
          clientPageId: clientPageId,
        );
      }
      final base = _contentQueryInvocationContext(
        ref,
        surface: surface,
        clientPageId: clientPageId,
      );
      return CloudOperationInvocationContext(
        surfaceId: base.surfaceId,
        clientPageId: base.clientPageId,
        routeId: base.routeId,
        actor: base.actor,
        idempotencyKey: AppTraceContextStore.instance.newRequestId(),
      );
    },
  );
}

ContentCommentFacet _productionCommentFacet(Ref ref, AppUiSurface surface) {
  return _remoteContentCommentFacet(ref, surface);
}

final workBrowserContentCommentFacetProvider = Provider<ContentCommentFacet>(
  (ref) => _productionCommentFacet(ref, AppUiSurfaces.workBrowser),
);
final profileCommentsContentCommentFacetProvider =
    Provider<ContentCommentFacet>(
      (ref) => _productionCommentFacet(ref, AppUiSurfaces.profileHome),
    );
final contentConfigRepositoryProvider = Provider<ContentConfigRepository>(
  (ref) => ref.watch(_contentFacetsProvider).config,
);

final _imageEditorFilterCatalogQueryProvider =
    Provider<ContentFilterCatalogQuery>((ref) {
      return AppProductionComposition.generatedAdapter<
        ContentFilterCatalogQuery
      >(
        AppProductionAdapter.filterCatalog,
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId) => _contentQueryInvocationContext(
          ref,
          surface: AppUiSurfaces.imageEditor,
          clientPageId: clientPageId,
        ),
      );
    });

final filterCatalogCoordinatorProvider = Provider<FilterCatalogCoordinator>((
  ref,
) {
  return FilterCatalogCoordinator(
    remote: ref.watch(_imageEditorFilterCatalogQueryProvider),
    verifiedStore: const SharedPreferencesVerifiedFilterCatalogStore(),
    bootstrapReader: const AssetFilterCatalogBootstrapReader(),
    integrityVerifier: const CanonicalFilterCatalogIntegrityVerifier(),
    observer: _AppTelemetryFilterCatalogResolutionObserver(
      ref.watch(appTelemetryReporterProvider),
    ),
  );
});

final imageEditorFilterRepositoryProvider =
    Provider<ImageEditorFilterRepository>((ref) {
      final coordinator = ref.watch(filterCatalogCoordinatorProvider);
      return ImageEditorFilterRepository(
        catalogLoader: () async => imageEditorFilterConfigFromSnapshot(
          (await coordinator.load()).snapshot,
        ),
      );
    });

final class _AppTelemetryFilterCatalogResolutionObserver
    implements FilterCatalogResolutionObserver {
  const _AppTelemetryFilterCatalogResolutionObserver(this._telemetry);

  final AppTelemetryRecorder _telemetry;

  @override
  void sourceSelected(ResolvedFilterCatalog resolved) {
    final source = resolved.source;
    final releaseIdHash = sha256
        .convert(utf8.encode(resolved.snapshot.releaseId))
        .toString();
    unawaited(
      _telemetry.record(
        AppTelemetryPayload.filterCatalogLoad(
          catalogSource: _catalogSource(source),
          releaseIdHash: releaseIdHash,
          digestMatch: true,
          cacheAgeBucket: _cacheAgeBucket(resolved),
          result: 'resolved',
        ),
        pageName: PageNames.createEditImage,
      ),
    );
  }

  @override
  void candidateRejected(FilterCatalogSource source, Object error) {
    _recordOperationResult('rejected_${source.name}');
  }

  void _recordOperationResult(String result) {
    unawaited(
      _telemetry.record(
        AppTelemetryPayload.operationResult(
          operationId: AppCloudOperationIds
              .contentFilterCatalogReleaseGetActiveFilterCatalog,
          result: result,
        ),
        pageName: PageNames.createEditImage,
      ),
    );
  }

  static String _catalogSource(FilterCatalogSource source) => switch (source) {
    FilterCatalogSource.remote => 'remote',
    FilterCatalogSource.verifiedCache => 'verified_cache',
    FilterCatalogSource.bootstrapReplica => 'bootstrap_replica',
  };

  static String _cacheAgeBucket(ResolvedFilterCatalog resolved) {
    final verifiedAt = resolved.cacheVerifiedAt;
    if (resolved.source != FilterCatalogSource.verifiedCache ||
        verifiedAt == null) {
      return 'not_applicable';
    }
    final age = DateTime.now().toUtc().difference(verifiedAt);
    if (age <= const Duration(hours: 1)) return 'under_1h';
    if (age <= const Duration(hours: 24)) return 'one_to_24h';
    return 'over_24h';
  }
}

ContentMediaFacet _remoteContentMediaFacet(Ref ref, AppUiSurface surface) =>
    AppProductionComposition.generatedAdapter<ContentMediaFacet>(
      AppProductionAdapter.contentMedia,
      client: ref.watch(generatedCloudOperationClientProvider),
      invocationContext: (clientPageId, {required command}) {
        final base = _contentQueryInvocationContext(
          ref,
          surface: surface,
          clientPageId: clientPageId,
        );
        if (!command) return base;
        return CloudOperationInvocationContext(
          surfaceId: base.surfaceId,
          clientPageId: base.clientPageId,
          routeId: base.routeId,
          actor: base.actor,
          idempotencyKey: AppTraceContextStore.instance.newRequestId(),
        );
      },
    );

ContentMediaFacet _productionContentMediaFacet(Ref ref, AppUiSurface surface) {
  return _remoteContentMediaFacet(ref, surface);
}

final createContentMediaFacetProvider = Provider<ContentMediaFacet>(
  (ref) => _productionContentMediaFacet(ref, AppUiSurfaces.createWorkspace),
);
final homeFeedContentMediaFacetProvider = Provider<ContentMediaFacet>(
  (ref) => _productionContentMediaFacet(ref, AppUiSurfaces.homeFeed),
);
final workBrowserContentMediaFacetProvider = Provider<ContentMediaFacet>(
  (ref) => _productionContentMediaFacet(ref, AppUiSurfaces.workBrowser),
);
final chatDetailContentMediaFacetProvider = Provider<ContentMediaFacet>(
  (ref) => _productionContentMediaFacet(ref, AppUiSurfaces.chatDetail),
);
final profileEditContentMediaFacetProvider = Provider<ContentMediaFacet>(
  (ref) => _productionContentMediaFacet(ref, AppUiSurfaces.profileEdit),
);
final circleDetailContentMediaFacetProvider = Provider<ContentMediaFacet>(
  (ref) => _productionContentMediaFacet(ref, AppUiSurfaces.circleDetail),
);

final contentMediaStreamObjectUploadProvider =
    Provider<ContentMediaStreamObjectUpload>((ref) {
      return AppProductionComposition.contentMediaObjectUpload(
        onDispose: ref.onDispose,
      );
    });

final contentMediaSourceReaderProvider = Provider<ContentMediaSourceReader>((
  ref,
) {
  return const LocalContentMediaSourceReader();
});

/// 已接受发布的进程内一致性信号。写侧只广播事实，发现流等读模型按需刷新；
/// 不允许发布页面反向 import 其他 UI 领域的 Provider。
final contentPublicationEpochProvider =
    NotifierProvider<ContentPublicationEpochNotifier, int>(
      ContentPublicationEpochNotifier.new,
    );

final class ContentPublicationEpochNotifier extends Notifier<int> {
  @override
  int build() => 0;

  void notifyCommitted() {
    state += 1;
  }
}

ContentOutboundShareAppendWriter _productionOutboundShareWriter(
  Ref ref,
  AppUiSurface surface,
) {
  return AppProductionComposition.generatedAdapter<
    ContentOutboundShareAppendWriter
  >(
    AppProductionAdapter.contentOutboundShare,
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId, command) {
      final base = _contentQueryInvocationContext(
        ref,
        surface: surface,
        clientPageId: clientPageId,
      );
      return CloudOperationInvocationContext(
        surfaceId: base.surfaceId,
        clientPageId: base.clientPageId,
        routeId: base.routeId,
        actor: base.actor,
        idempotencyKey: 'outbound-share:${command.referralId}',
      );
    },
  );
}

final homeFeedContentOutboundShareWriterProvider =
    Provider<ContentOutboundShareAppendWriter>(
      (ref) => _productionOutboundShareWriter(ref, AppUiSurfaces.homeFeed),
    );
final workBrowserContentOutboundShareWriterProvider =
    Provider<ContentOutboundShareAppendWriter>(
      (ref) => _productionOutboundShareWriter(ref, AppUiSurfaces.workBrowser),
    );

CirclePostPlacementCommandWriter _productionCirclePostPlacementWriter(
  Ref ref,
  AppUiSurface surface,
) {
  return AppProductionComposition.generatedAdapter<
    CirclePostPlacementCommandWriter
  >(
    AppProductionAdapter.circlePostPlacement,
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId, idempotencyKey) {
      final base = _contentQueryInvocationContext(
        ref,
        surface: surface,
        clientPageId: clientPageId,
      );
      return CloudOperationInvocationContext(
        surfaceId: base.surfaceId,
        clientPageId: base.clientPageId,
        routeId: base.routeId,
        actor: base.actor,
        idempotencyKey: idempotencyKey,
      );
    },
  );
}

final homeFeedCirclePostPlacementWriterProvider =
    Provider<CirclePostPlacementCommandWriter>(
      (ref) =>
          _productionCirclePostPlacementWriter(ref, AppUiSurfaces.homeFeed),
    );
final workBrowserCirclePostPlacementWriterProvider =
    Provider<CirclePostPlacementCommandWriter>(
      (ref) =>
          _productionCirclePostPlacementWriter(ref, AppUiSurfaces.workBrowser),
    );

final createWorkspaceCirclePostPlacementWriterProvider =
    Provider<CirclePostPlacementCommandWriter>(
      (ref) => _productionCirclePostPlacementWriter(
        ref,
        AppUiSurfaces.createWorkspace,
      ),
    );
