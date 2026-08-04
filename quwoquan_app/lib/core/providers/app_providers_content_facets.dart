import 'dart:async';
import 'dart:convert';
import 'package:crypto/crypto.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/application/assistant/presentation/assistant_presentation_media_resolver.dart';
import 'package:quwoquan_app/application/content/filter_catalog/filter_catalog_coordinator.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_trace_context_store.dart';
import 'package:quwoquan_app/core/di/generated_operation_client_dependencies.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/cloud/remote/content/media/local_media_upload_source.dart';
import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_repository.dart';
import 'package:quwoquan_app/application/content/media/content_media_upload_coordinator.dart';
import 'package:quwoquan_app/cloud/services/user/profile_media_upload_gateway.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/media/media_delivery_reference.dart';
import 'package:quwoquan_app/core/di/ops_event_dependencies.dart';
import 'package:quwoquan_app/runtime/di/circle_dependencies.dart';
import 'package:quwoquan_app/runtime/di/content_dependencies.dart';
import 'package:quwoquan_app/app/navigation/generated/app_pages.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/core/telemetry/app_telemetry_reporter.dart';
import 'package:quwoquan_app/infrastructure/local/content/filter_catalog/verified_filter_catalog_store.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    hide ContentDiscoveryFeedQuery;
import 'package:quwoquan_app/core/providers/app_providers_chat_search.dart';
import 'package:quwoquan_app/core/providers/app_providers_client_sync.dart';
import 'package:quwoquan_app/core/providers/app_providers_content_extras.dart';
import 'package:quwoquan_app/core/providers/app_providers_operations.dart';
/// 仅供组合根装配 Remote / Mock / Cache 的强类型 facets holder。
/// 它不是业务 Repository；业务消费者只能读取各自的窄 Provider。
final class _ContentFacets {
  const _ContentFacets({
    required this.read,
    required this.postDeleteWriter,
    required this.behaviorWriter,
  });

  final ContentReadRepository read;
  final ContentPostDeleteCommandWriter postDeleteWriter;
  final ContentBehaviorCommandWriter behaviorWriter;
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

  final facets = ContentProductionComposition.contentFacets(
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId) => contentQueryInvocationContext(
      ref,
      surface: AppUiSurfaces.homeFeed,
      clientPageId: clientPageId,
    ),
    deleteInvocationContext: (clientPageId, idempotencyKey) =>
        contentCommandInvocationContext(
          ref,
          surface: AppUiSurfaces.workBrowser,
          clientPageId: clientPageId,
          idempotencyKey: idempotencyKey,
        ),
    blockedKeywordsLoader: loadBlockedKeywords,
    postCache: ref.watch(postObjectCacheProvider),
    querySnapshotStore: ref.watch(contentQuerySnapshotStoreProvider),
    userProfileCache: ref.watch(userProfileCacheProvider),
    telemetrySink: ref.watch(cacheTelemetrySinkProvider),
  );
  return _ContentFacets(
    read: facets.read,
    postDeleteWriter: facets.postDeleteWriter,
    behaviorWriter: facets.behaviorWriter,
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
final contentPostDeleteCommandWriterProvider =
    Provider<ContentPostDeleteCommandWriter>(
      (ref) => ref.watch(_contentFacetsProvider).postDeleteWriter,
    );
final contentBehaviorCommandWriterProvider =
    Provider<ContentBehaviorCommandWriter>(
      (ref) => ref.watch(_contentFacetsProvider).behaviorWriter,
    );

ContentPostReactionFacet _productionPostReactionFacet(Ref ref) {
  return ContentProductionComposition.generatedAdapter<ContentPostReactionFacet>(
    ContentProductionAdapter.postReaction,
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId, {required command}) {
      if (command) {
        return contentCommandInvocationContext(
          ref,
          clientPageId: clientPageId,
        );
      }
      return contentQueryInvocationContext(
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
      return ContentProductionComposition.generatedAdapter<
        ContentPostPublicationWriter
      >(
        ContentProductionAdapter.postPublication,
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId, idempotencyKey) =>
            contentCommandInvocationContext(
              ref,
              clientPageId: clientPageId,
              idempotencyKey: idempotencyKey,
            ),
      );
    });

ContentCommentFacet _remoteContentCommentFacet(Ref ref, AppUiSurface surface) {
  return ContentProductionComposition.generatedAdapter<ContentCommentFacet>(
    ContentProductionAdapter.comment,
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId, {required command}) {
      if (!command) {
        return contentQueryInvocationContext(
          ref,
          surface: surface,
          clientPageId: clientPageId,
        );
      }
      final base = contentQueryInvocationContext(
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
final contentConfigRepositoryProvider = Provider<ContentConfigRepository>((
  ref,
) {
  return ContentProductionComposition.generatedAdapter<ContentConfigRepository>(
    ContentProductionAdapter.appConfigQuery,
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId) => contentQueryInvocationContext(
      ref,
      surface: AppUiSurfaces.homeFeed,
      clientPageId: clientPageId,
    ),
  );
});

final _imageEditorFilterCatalogQueryProvider =
    Provider<ContentFilterCatalogQuery>((ref) {
      return ContentProductionComposition.generatedAdapter<
        ContentFilterCatalogQuery
      >(
        ContentProductionAdapter.filterCatalog,
        client: ref.watch(generatedCloudOperationClientProvider),
        invocationContext: (clientPageId) => contentQueryInvocationContext(
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
    ContentProductionComposition.generatedAdapter<ContentMediaFacet>(
      ContentProductionAdapter.media,
      client: ref.watch(generatedCloudOperationClientProvider),
      invocationContext: (clientPageId, {required command}) {
        final base = contentQueryInvocationContext(
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
final personalAssistantContentMediaFacetProvider = Provider<ContentMediaFacet>(
  (ref) =>
      _productionContentMediaFacet(ref, AppUiSurfaces.personalAssistantDialog),
);
final assistantPresentationMediaResolverProvider =
    Provider<AssistantPresentationMediaResolver>((ref) {
      return AssistantPresentationMediaResolver(
        media: ref.watch(personalAssistantContentMediaFacetProvider),
        delivery: MediaDeliveryResolver.fromRuntimeConfig(),
      );
    });

final contentMediaStreamObjectUploadProvider =
    Provider<ContentMediaStreamObjectUpload>((ref) {
      return ContentProductionComposition.contentMediaObjectUpload(
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
  return ContentProductionComposition.generatedAdapter<
    ContentOutboundShareAppendWriter
  >(
    ContentProductionAdapter.outboundShare,
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId, command) {
      final base = contentQueryInvocationContext(
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
  return CircleProductionComposition.generatedAdapter<
    CirclePostPlacementCommandWriter
  >(
    CircleProductionAdapter.postPlacement,
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (clientPageId, idempotencyKey) {
      final base = contentQueryInvocationContext(
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
