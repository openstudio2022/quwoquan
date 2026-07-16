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
  final mode = ref.watch(appDataSourceModeProvider);
  final source = cloudRepositoryImplForMode<_ContentFacets>(
    mode,
    remote: () {
      final adapter = RemoteContentRepository(
        httpClient: ref.watch(cloudHttpClientProvider),
      );
      return _ContentFacets(
        read: adapter,
        write: adapter,
        engagement: adapter,
        config: adapter,
      );
    },
    mock: () {
      final adapter = MockContentRepository();
      return _ContentFacets(
        read: adapter,
        write: adapter,
        engagement: adapter,
        config: adapter,
      );
    },
  );
  final cached = CachedContentRepository(
    readDelegate: source.read,
    writeDelegate: source.write,
    postCache: ref.watch(postObjectCacheProvider),
    querySnapshotStore: ref.watch(contentQuerySnapshotStoreProvider),
    userProfileCache: ref.watch(userProfileCacheProvider),
    telemetrySink: ref.watch(cacheTelemetrySinkProvider),
  );
  return _ContentFacets(
    read: cached,
    write: cached,
    engagement: source.engagement,
    config: source.config,
  );
});

final profileMediaUploadGatewayProvider = Provider<ProfileMediaUploadGateway>((
  ref,
) {
  if (ref.watch(appDataSourceModeProvider) != AppDataSourceMode.remote) {
    throw StateError(
      'ProfileMediaUploadGateway is Remote-only in production composition; alpha must override it explicitly',
    );
  }
  final gateway = ContentProfileMediaUploadGateway(
    ref.watch(profileEditContentMediaFacetProvider),
  );
  ref.onDispose(gateway.dispose);
  return gateway;
});

final contentReadRepositoryProvider = Provider<ContentReadRepository>(
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
  if (ref.watch(appDataSourceModeProvider) != AppDataSourceMode.remote) {
    throw StateError(
      'ContentPostReactionFacet is Remote-only in production composition; alpha must override the typed Facet from quwoquan_cloud_mock',
    );
  }
  return RemoteContentPostReactionFacet(
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

final createContentPostLifecycleCommandWriterProvider =
    Provider<ContentPostLifecycleCommandWriter>((ref) {
      if (ref.watch(appDataSourceModeProvider) != AppDataSourceMode.remote) {
        throw StateError(
          'ContentPostLifecycleCommandWriter is Remote-only in production composition; alpha must override the typed writer from quwoquan_cloud_mock',
        );
      }
      return RemoteContentPostLifecycleCommandWriter(
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId) =>
            _contentCommandInvocationContext(ref, clientPageId: clientPageId),
      );
    });

RemoteContentCommentFacet _remoteContentCommentFacet(
  Ref ref,
  AppUiSurface surface,
) {
  return RemoteContentCommentFacet(
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
  if (ref.watch(appDataSourceModeProvider) != AppDataSourceMode.remote) {
    throw StateError(
      'ContentCommentFacet is Remote-only in production composition; alpha must override the typed Facet from quwoquan_cloud_mock',
    );
  }
  return _remoteContentCommentFacet(ref, surface);
}

final workBrowserContentCommentFacetProvider = Provider<ContentCommentFacet>(
  (ref) => _productionCommentFacet(ref, AppUiSurfaces.workBrowser),
);
final profileCommentsContentCommentFacetProvider =
    Provider<ContentCommentFacet>(
      (ref) => _productionCommentFacet(ref, AppUiSurfaces.profileComments),
    );
final contentConfigRepositoryProvider = Provider<ContentConfigRepository>(
  (ref) => ref.watch(_contentFacetsProvider).config,
);

RemoteContentMediaFacet _remoteContentMediaFacet(
  Ref ref,
  AppUiSurface surface,
) => RemoteContentMediaFacet(
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
  if (ref.watch(appDataSourceModeProvider) != AppDataSourceMode.remote) {
    throw StateError(
      'ContentMediaFacet is Remote-only in production composition; alpha must override it from quwoquan_cloud_mock',
    );
  }
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

final contentMediaObjectUploadProvider = Provider<ContentMediaObjectUpload>((
  ref,
) {
  if (ref.watch(appDataSourceModeProvider) != AppDataSourceMode.remote) {
    throw StateError(
      'ContentMediaObjectUpload is Remote-only in production composition; alpha must override the data-plane fixture',
    );
  }
  final uploader = RemoteContentMediaObjectUploader();
  ref.onDispose(uploader.dispose);
  return uploader.upload;
});

final contentMediaStreamObjectUploadProvider =
    Provider<ContentMediaStreamObjectUpload>((ref) {
      if (ref.watch(appDataSourceModeProvider) != AppDataSourceMode.remote) {
        throw StateError(
          'ContentMediaStreamObjectUpload is Remote-only in production composition; alpha must override the data-plane fixture',
        );
      }
      final uploader = RemoteContentMediaObjectUploader();
      ref.onDispose(uploader.dispose);
      return uploader.uploadStream;
    });

final contentMediaSourceReaderProvider = Provider<ContentMediaSourceReader>((
  ref,
) {
  if (ref.watch(appDataSourceModeProvider) != AppDataSourceMode.remote) {
    throw StateError(
      'ContentMediaSourceReader is Remote-only in production composition; alpha must override it explicitly',
    );
  }
  return const LocalContentMediaSourceReader();
});

ContentOutboundShareAppendWriter _productionOutboundShareWriter(
  Ref ref,
  AppUiSurface surface,
) {
  if (ref.watch(appDataSourceModeProvider) != AppDataSourceMode.remote) {
    throw StateError(
      'ContentOutboundShareAppendWriter is Remote-only in production composition; alpha must override it explicitly',
    );
  }
  return RemoteContentOutboundShareAppendWriter(
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
  if (ref.watch(appDataSourceModeProvider) != AppDataSourceMode.remote) {
    throw StateError(
      'CirclePostPlacementCommandWriter is Remote-only in production composition; alpha must override it explicitly',
    );
  }
  return RemoteCirclePostPlacementCommandWriter(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId) {
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
