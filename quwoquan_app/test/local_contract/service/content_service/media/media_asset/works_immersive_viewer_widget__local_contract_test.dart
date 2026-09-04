// spec_ref: specs/feature-tree/runtime/native-edge-gesture-navigation/spec.md#sit-001
// spec_ref: specs/feature-tree/runtime/native-edge-gesture-navigation/immersive-media-edge-swipe-back/spec.md#gwt-001
// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-012
// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-012.t3
// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-012.t4
// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-017
// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-017.t1
// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-017.t3
// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-017.t5
// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-018
// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-018.t1
// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-020

import 'dart:async';
import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart' show RenderObject, RenderParagraph;
import 'package:flutter/services.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    hide ContentDiscoveryFeedQuery;
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/observability/analytics.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_pages.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/adapters/media_download_cache.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/video_preview_track_query.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/application/public/discovery_feed_page.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/content_repository_contract.dart'
    show ContentConfigRepository, ContentPostDetailReader;
import 'package:quwoquan_app/service/content_service/trust_safety/report/application/public/content_report_ports.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_detail_payload.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/post_article_detail_projector.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/post_view_projection.dart';
import 'package:quwoquan_app/service/content_service/content/feed_delivery_page/application/public/discovery_feed_query.dart'
    show ContentDiscoveryFeedQuery, kFeedSortRecommend;
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_projection_codec.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart'
    show ActivePersonaContextViewData;

import '../../../../../support/service/content_service/content/content_behavior_fact/recording_content_behavior_repository.dart';
import '../../../../../support/service/content_service/content/post/content_post_test_builder.dart';
import '../../../../../support/service/content_service/content/post/test_content_app_config.dart';
import '../../../../../support/service/content_service/content/comment/in_memory_content_comment_facet.dart';
import '../../../../../support/service/recommendation_service/recommendation/recommendation_feature_profile_view/intersection_fixtures.dart';

import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/image_book_canvas.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/media_page_flip_book.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/media_caption_widgets.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/public/media_viewer_extra.dart';
import 'package:quwoquan_app/runtime/transport/media/content_media_url.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_app/runtime/transport/media/media_load_failure_cache.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/di/works_viewer_article_dependencies.dart';
import 'package:quwoquan_app/runtime/di/runtime_observability_dependencies.dart';
import 'package:quwoquan_app/runtime/di/video_preview_track_dependencies.dart';
import 'package:quwoquan_app/runtime/auth/auth_continuation.dart';
import 'package:quwoquan_app/runtime/auth/auth_gate.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/l10n/copy/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/design_system/semantics/settings_semantic_constants.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/content_behavior_tracker.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_engagement_tracker.dart';
import 'package:quwoquan_app/runtime/observability/runtime_log_ports.dart';
import 'package:quwoquan_app/runtime/observability/runtime_log_record.dart';
import 'package:quwoquan_app/runtime/observability/runtime_logger.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/icons/app_custom_icons.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/spacing/immersive_media_wait_motion.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/immersive_engagement_bar.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/immersive_viewer_layout.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/video_player_widget.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_content_block_renderer.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_reader/pageflip/host/article_read_only_book_deck.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_reader/pageflip/host/article_reader_flip_host.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/unified_media_viewer_page.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_surface_view.dart';
import 'package:quwoquan_app/runtime/di/content_surface_view_mapper.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_paged_canvas.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/discovery_feed_provider.dart';
import 'package:quwoquan_app/runtime/di/works_viewer_feed_bridge.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/works_immersive_viewer.dart';
import 'package:video_player_platform_interface/video_player_platform_interface.dart';

import '../../../../../support/service/content_service/content/post/content_facet_overrides.dart';
import '../../../../../support/runtime/platform/media/fake_video_player_platform.dart';
import '../../../../../support/service/content_service/content/post/content_post_typed_doubles.dart';
import '../../../../../support/runtime/platform/storage/sqflite_ffi_test_support.dart';
import '../../../../../support/runtime/observability/recording_app_telemetry_recorder.dart';
import '../../../../../support/runtime/cloud_boundary_test_scope.dart';

import 'package:http/testing.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';

Map<String, MediaViewerPostWireRow> _viewerRawByPostId(
  Map<String, Map<String, dynamic>> raw,
) => raw.map(
  (id, row) => MapEntry(id, MediaViewerPostWireRow.fromDynamicMap(row)),
);

Map<String, dynamic> _canonicalPostWire(ContentPostViewData post) =>
    Map<String, dynamic>.from(contentPostProjectionFromViewData(post).toWire());

const String _canonicalTestSha256 =
    'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';

ContentPostDetailSlice _contentPostDetailSliceFromTestMap(
  Map<String, dynamic> raw, {
  String? postId,
}) {
  final wire = Map<String, Object?>.from(raw);
  wire['postId'] = postId ?? wire['postId'];
  wire.putIfAbsent('contentType', () => 'article');
  wire.putIfAbsent('contentIdentity', () => 'work');
  final now = DateTime.utc(2026).toIso8601String();
  wire.putIfAbsent('status', () => 'published');
  wire.putIfAbsent('visibility', () => 'public');
  wire.putIfAbsent('likeCount', () => 0);
  wire.putIfAbsent('commentCount', () => 0);
  wire.putIfAbsent('shareCount', () => 0);
  wire.putIfAbsent('viewCount', () => 0);
  wire.putIfAbsent('createdAt', () => now);
  wire.putIfAbsent('updatedAt', () => now);

  final manifest = wire['articleAssetManifest'];
  if (manifest is Map) {
    final normalized = Map<String, Object?>.from(manifest);
    normalized.putIfAbsent('documentSha256', () => _canonicalTestSha256);
    normalized.putIfAbsent('assetManifestSha256', () => _canonicalTestSha256);
    normalized.putIfAbsent('documentVersionSha256', () => _canonicalTestSha256);
    wire['articleAssetManifest'] = normalized;
  }
  return ContentPostDetailSlice.fromWire(wire);
}

final MediaEndpointConfig _testMediaEndpointConfig = MediaEndpointConfig(
  avatarBaseUrl: 'https://example.com/media/avatar',
  imageBaseUrl: 'https://example.com/media/image',
  videoBaseUrl: 'https://example.com/media/video',
  attachmentBaseUrl: 'https://example.com',
);

final class _EndpointBoundPostArticleDetailProjector
    implements PostArticleDetailProjector {
  const _EndpointBoundPostArticleDetailProjector(this.endpointConfig);

  final MediaEndpointConfig endpointConfig;

  @override
  ContentArticleRender project(
    Map<String, dynamic> raw, {
    required String fallbackArticleId,
  }) {
    return projectArticleDetailView(
      raw,
      fallbackArticleId: fallbackArticleId,
      mediaResolver: MediaDeliveryResolver(endpointConfig),
    );
  }
}

List<Override> _sealedViewerBoundaryOverrides() => <Override>[
  ...sealedCloudBoundaryOverrides(),
  activePersonaContextProvider.overrideWith(
    (_) async => ActivePersonaContextViewData.fallback(
      personaId: 'immersive-viewer-test-persona',
      ownerUserId: 'immersive-viewer-test-account',
      displayName: '测试用户',
      avatarUrl: '',
    ),
  ),
  videoPreviewTrackQueryProvider.overrideWithValue(
    const _UnusedVideoPreviewTrackQuery(),
  ),
  runtimeLoggerProvider.overrideWith((ref) {
    final logger = RuntimeLogger(
      resource: const RuntimeLogResource(
        sourceType: 'app',
        environment: 'alpha',
        service: 'quwoquan_app',
        appVersion: 'test',
      ),
      buffer: InMemoryRuntimeLogBuffer(),
    );
    ref.onDispose(logger.dispose);
    return logger;
  }),
];

final class _UnusedVideoPreviewTrackQuery implements VideoPreviewTrackQuery {
  const _UnusedVideoPreviewTrackQuery();

  @override
  Future<VideoPreviewTrackManifest> loadManifest(
    VideoPreviewTrackDescriptor descriptor,
  ) {
    throw StateError('该 Widget contract 不应请求视频预览轨');
  }
}

ProviderContainer _testProviderContainer({
  List<Override> overrides = const <Override>[],
}) {
  return ProviderContainer(
    overrides: <Override>[
      ..._sealedViewerBoundaryOverrides(),
      mediaEndpointConfigProvider.overrideWithValue(_testMediaEndpointConfig),
      ...overrides,
    ],
  );
}

IntersectionReason _displayableIntersectionReason({
  required String primaryText,
  required String dimension,
  required String source,
  String intersectionId = '',
  String intersectionClass = 'fact',
  String pointSummarySnapshotId = '',
  int totalPointCount = 1,
  List<String> tagRefs = const <String>[],
  List<IntersectionTextSpan>? primarySpans,
  List<IntersectionVisual> sampleVisuals = const <IntersectionVisual>[],
  String objectKind = '',
  String actionTargetId = '',
  String displayBinding = 'host_implicit',
}) {
  final text = primaryText.trim();
  final resolvedObjectKind = objectKind.trim().isEmpty
      ? 'content'
      : objectKind.trim();
  final targetId = actionTargetId.trim().isNotEmpty
      ? actionTargetId.trim()
      : 'moment-1';
  final target = _intersectionTargetFor(
    objectKind: resolvedObjectKind,
    objectId: targetId,
  );
  return intersectionReasonFixture(
    kind: resolvedObjectKind,
    vertical: 'content',
    intersectionId: intersectionId,
    dimension: dimension,
    relationKind: source,
    relationObjectId: targetId,
    strength: 1,
    primaryText: text,
    primaryTextL10nKey: '',
    displayBinding: displayBinding,
    actionType: 'open',
    primarySpans: primarySpans ?? _defaultDisplaySpans(text),
    totalPointCount: totalPointCount,
    source: source,
    tagRefs: tagRefs,
    intersectionClass: intersectionClass,
    pointSummarySnapshotId: pointSummarySnapshotId,
    sampleVisuals: sampleVisuals,
    objectKind: resolvedObjectKind,
    actionTargetId: target.objectId,
    actorEvidenceTotalCount: 1,
    actorEvidenceCompleteness: 'complete',
    representativeActor: IntersectionRepresentativeActor(
      actorId: 'u_lin',
      displayName: '林清越',
      avatarUrl: '',
      relationLabel: '联系人',
      privacyState: 'visible',
      target: _intersectionTargetFor(objectKind: 'person', objectId: 'u_lin'),
      evidenceRank: 1,
      snapshotVersion: pointSummarySnapshotId,
    ),
  );
}

IntersectionTextSpan _plain(String text) =>
    IntersectionTextSpan(text: text, role: 'plain');

List<IntersectionTextSpan> _defaultDisplaySpans(String text) {
  final nameIndex = text.indexOf('林清越');
  if (nameIndex < 0) {
    return <IntersectionTextSpan>[_plain(text)];
  }
  final before = text.substring(0, nameIndex);
  final after = text.substring(nameIndex + '林清越'.length);
  return <IntersectionTextSpan>[
    if (before.isNotEmpty) _plain(before),
    IntersectionTextSpan(
      text: '林清越',
      role: 'object',
      target: _intersectionTargetFor(objectKind: 'person', objectId: 'u_lin'),
    ),
    if (after.isNotEmpty) _plain(after),
  ];
}

IntersectionTarget _intersectionTargetFor({
  required String objectKind,
  required String objectId,
}) {
  switch (objectKind.trim()) {
    case 'person':
      return IntersectionTarget(
        objectType: 'user',
        objectId: objectId,
        objectKind: 'person',
        routeId: 'userProfile',
      );
    case 'circle':
      return IntersectionTarget(
        objectType: 'circle',
        objectId: objectId,
        objectKind: 'circle',
        routeId: 'circleDetail',
      );
    case 'content':
      return IntersectionTarget(
        objectType: 'post',
        objectId: objectId,
        objectKind: 'content',
        routeId: 'workBrowser',
      );
    case 'route':
    case 'place':
    case 'homepage':
    default:
      return IntersectionTarget(
        objectType: 'homepage',
        objectId: objectId,
        objectKind: objectKind.trim().isEmpty ? 'homepage' : objectKind.trim(),
        routeId: 'homepageDetail',
      );
  }
}

final class _HttpStatusTestException implements Exception {
  const _HttpStatusTestException(this.statusCode, this.message);

  final int statusCode;
  final String message;

  @override
  String toString() => '_HttpStatusTestException($statusCode, $message)';
}

class _FakeHttpOverrides extends HttpOverrides {
  @override
  HttpClient createHttpClient(SecurityContext? context) => _FakeHttpClient();
}

class _FakeHttpClient implements HttpClient {
  @override
  bool autoUncompress = true;
  @override
  Duration? connectionTimeout;
  @override
  Duration idleTimeout = const Duration(seconds: 15);
  @override
  int? maxConnectionsPerHost;
  @override
  String? userAgent;
  @override
  void addCredentials(
    Uri url,
    String realm,
    HttpClientCredentials credentials,
  ) {}
  @override
  void addProxyCredentials(
    String host,
    int port,
    String realm,
    HttpClientCredentials credentials,
  ) {}
  @override
  set authenticate(Future<bool> Function(Uri, String, String?)? f) {}
  @override
  set authenticateProxy(
    Future<bool> Function(String, int, String, String?)? f,
  ) {}
  @override
  set badCertificateCallback(
    bool Function(X509Certificate, String, int)? callback,
  ) {}
  @override
  set connectionFactory(
    Future<ConnectionTask<Socket>> Function(Uri, String?, int?)? f,
  ) {}
  @override
  set findProxy(String Function(Uri)? f) {}
  @override
  set keyLog(Function(String)? callback) {}
  @override
  void close({bool force = false}) {}
  @override
  Future<HttpClientRequest> open(
    String method,
    String host,
    int port,
    String path,
  ) => _fakeRequest();
  @override
  Future<HttpClientRequest> openUrl(String method, Uri url) => _fakeRequest();
  @override
  Future<HttpClientRequest> get(String host, int port, String path) =>
      _fakeRequest();
  @override
  Future<HttpClientRequest> getUrl(Uri url) => _fakeRequest();
  @override
  Future<HttpClientRequest> post(String host, int port, String path) =>
      _fakeRequest();
  @override
  Future<HttpClientRequest> postUrl(Uri url) => _fakeRequest();
  @override
  Future<HttpClientRequest> put(String host, int port, String path) =>
      _fakeRequest();
  @override
  Future<HttpClientRequest> putUrl(Uri url) => _fakeRequest();
  @override
  Future<HttpClientRequest> delete(String host, int port, String path) =>
      _fakeRequest();
  @override
  Future<HttpClientRequest> deleteUrl(Uri url) => _fakeRequest();
  @override
  Future<HttpClientRequest> head(String host, int port, String path) =>
      _fakeRequest();
  @override
  Future<HttpClientRequest> headUrl(Uri url) => _fakeRequest();
  @override
  Future<HttpClientRequest> patch(String host, int port, String path) =>
      _fakeRequest();
  @override
  Future<HttpClientRequest> patchUrl(Uri url) => _fakeRequest();

  Future<HttpClientRequest> _fakeRequest() =>
      Future<HttpClientRequest>.value(_FakeHttpClientRequest());
}

class _FakeHttpClientRequest extends Fake implements HttpClientRequest {
  @override
  HttpHeaders get headers => _FakeHttpHeaders();

  @override
  Future<HttpClientResponse> close() =>
      Future<HttpClientResponse>.value(_FakeHttpClientResponse());
}

class _FakeHttpHeaders extends Fake implements HttpHeaders {}

class _FakeHttpClientResponse extends Fake implements HttpClientResponse {
  static const _kTransparentPng = [
    0x89,
    0x50,
    0x4E,
    0x47,
    0x0D,
    0x0A,
    0x1A,
    0x0A,
    0x00,
    0x00,
    0x00,
    0x0D,
    0x49,
    0x48,
    0x44,
    0x52,
    0x00,
    0x00,
    0x00,
    0x01,
    0x00,
    0x00,
    0x00,
    0x01,
    0x08,
    0x06,
    0x00,
    0x00,
    0x00,
    0x1F,
    0x15,
    0xC4,
    0x89,
    0x00,
    0x00,
    0x00,
    0x0A,
    0x49,
    0x44,
    0x41,
    0x54,
    0x78,
    0x9C,
    0x62,
    0x00,
    0x00,
    0x00,
    0x02,
    0x00,
    0x01,
    0xE5,
    0x27,
    0xDE,
    0xFC,
    0x00,
    0x00,
    0x00,
    0x00,
    0x49,
    0x45,
    0x4E,
    0x44,
    0xAE,
    0x42,
    0x60,
    0x82,
  ];

  @override
  int get statusCode => 200;

  @override
  int get contentLength => _kTransparentPng.length;

  @override
  HttpClientResponseCompressionState get compressionState =>
      HttpClientResponseCompressionState.notCompressed;

  @override
  StreamSubscription<List<int>> listen(
    void Function(List<int>)? onData, {
    Function? onError,
    void Function()? onDone,
    bool? cancelOnError,
  }) {
    return Stream<List<int>>.fromIterable([_kTransparentPng]).listen(
      onData,
      onError: onError,
      onDone: onDone,
      cancelOnError: cancelOnError,
    );
  }
}

class _FakeAnalyticsService extends AnalyticsService {
  _FakeAnalyticsService() : super.forTesting();

  final List<AnalyticsEvent> events = <AnalyticsEvent>[];

  @override
  Future<void> trackEvent(AnalyticsEvent event) async {
    events.add(event);
  }
}

class _ConfigurableContentDetailReader implements ContentPostDetailReader {
  _ConfigurableContentDetailReader({
    this.detailById = const <String, Map<String, dynamic>>{},
  });

  final Map<String, Map<String, dynamic>> detailById;
  int getPostCallCount = 0;

  @override
  Future<ContentPostDetailPayload> getPost({
    required String postId,
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    getPostCallCount += 1;
    final detail = detailById[postId];
    if (detail != null) {
      return ContentPostDetailPayload.fromWire(
        _contentPostDetailSliceFromTestMap(detail, postId: postId),
      );
    }
    return InMemoryContentPostDetailReader(InMemoryContentPostStore()).getPost(
      postId: postId,
      cancellation: cancellation,
      deadlineAt: deadlineAt,
    );
  }
}

class _ConfigurableContentConfigRepository implements ContentConfigRepository {
  _ConfigurableContentConfigRepository({required this.appConfig});

  final Map<String, dynamic> appConfig;

  @override
  Future<AppConfigSlice> getAppConfig() async {
    return testAppConfigSlice(
      content: Map<String, Object?>.from(appConfig['content']! as Map),
      defaultActivation: 'immediate',
      fetchedAt: DateTime.now().toUtc(),
      maxAgeSec: 3600,
    );
  }

  @override
  bool get requiresResolvedPersonaForMutations => false;
}

class _BlockingArticleHydrationRepository implements ContentPostDetailReader {
  _BlockingArticleHydrationRepository({this.lateSuccessDetail});

  final Map<String, dynamic>? lateSuccessDetail;
  final List<String> startedPostIds = <String>[];
  final List<String> cancelledPostIds = <String>[];
  int activeRequests = 0;
  int maxActiveRequests = 0;

  @override
  Future<ContentPostDetailPayload> getPost({
    required String postId,
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    if (cancellation == null) {
      throw StateError('viewer hydration must provide cancellation');
    }
    startedPostIds.add(postId);
    activeRequests += 1;
    maxActiveRequests = maxActiveRequests < activeRequests
        ? activeRequests
        : maxActiveRequests;
    final result = Completer<ContentPostDetailPayload>();
    unawaited(
      cancellation.whenCancelled.then((_) {
        cancelledPostIds.add(postId);
        if (!result.isCompleted) {
          final detail = lateSuccessDetail;
          if (detail == null) {
            result.completeError(const CloudOperationCancelledException());
          } else {
            result.complete(
              ContentPostDetailPayload.fromWire(
                _contentPostDetailSliceFromTestMap(detail, postId: postId),
              ),
            );
          }
        }
      }),
    );
    try {
      return await result.future;
    } finally {
      activeRequests -= 1;
    }
  }
}

class _PagedFeaturedContentRepository
    extends InMemoryContentDiscoveryFeedQuery {
  _PagedFeaturedContentRepository() : super(InMemoryContentPostStore());

  final int pageSize = 2;
  final Duration appendDelay = const Duration(seconds: 4);
  int appendCallCount = 0;

  List<ContentPostViewData> _postsForCategory(String category) {
    List<ContentPostViewData> source;
    switch (category) {
      case 'photo':
        source = contentPostListBuilder(
          contentType: 'image',
          count: 4,
          idPrefix: 'immersive-photo',
        );
        break;
      case 'video':
        source = contentPostListBuilder(
          contentType: 'video',
          count: 4,
          idPrefix: 'immersive-video',
        );
        break;
      case 'article':
        source = contentPostListBuilder(
          contentType: 'article',
          count: 4,
          idPrefix: 'immersive-article',
        );
        break;
      default:
        return const <ContentPostViewData>[];
    }
    return source;
  }

  @override
  Future<DiscoveryFeedPage> listDiscoveryFeedPage({
    required String category,
    String? channelId,
    String? identity,
    String? type,
    String? subCategory,
    int limit = 20,
    String? cursor,
    String sort = kFeedSortRecommend,
    String? sessionId,
    String? feedRequestId,
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    final posts = _postsForCategory(category);
    if (posts.isEmpty) {
      return super.listDiscoveryFeedPage(
        category: category,
        channelId: channelId,
        identity: identity,
        type: type,
        subCategory: subCategory,
        limit: limit,
        cursor: cursor,
        sort: sort,
        sessionId: sessionId,
        feedRequestId: feedRequestId,
        cancellation: cancellation,
        deadlineAt: deadlineAt,
      );
    }
    final offset = int.tryParse((cursor ?? '').trim()) ?? 0;
    if (offset > 0 && appendDelay > Duration.zero) {
      appendCallCount += 1;
      await Future<void>.delayed(appendDelay);
    }
    final end = (offset + pageSize).clamp(0, posts.length);
    return DiscoveryFeedPage(
      items: posts.sublist(offset, end),
      nextCursor: end < posts.length ? '$end' : null,
      feedRequestId: feedRequestId?.trim().isNotEmpty == true
          ? feedRequestId!.trim()
          : 'frq_mock_${DateTime.now().microsecondsSinceEpoch}',
    );
  }
}

class _AuthenticatedViewerSession extends AuthSessionController {
  @override
  AuthSessionState build() {
    return const AuthSessionState(
      status: AuthSessionStatus.authenticated,
      accessToken: 'viewer-test-token',
      refreshToken: 'viewer-test-refresh-token',
      ownerId: 'viewer-test-owner',
      activePersonaId: 'viewer-test-persona',
    );
  }
}

class _FlippableViewerSession extends AuthSessionController {
  @override
  AuthSessionState build() =>
      const AuthSessionState(status: AuthSessionStatus.guest);

  void loginNow() {
    state = const AuthSessionState(
      status: AuthSessionStatus.authenticated,
      accessToken: 'viewer-resume-token',
      refreshToken: 'viewer-resume-refresh-token',
      ownerId: 'viewer-resume-owner',
      activePersonaId: 'viewer-resume-persona',
    );
  }
}

class _RecordingContentReportWriter implements ContentReportWriter {
  final List<CreateContentReportCommand> commands =
      <CreateContentReportCommand>[];

  @override
  Future<void> createReport(CreateContentReportCommand command) async {
    commands.add(command);
  }
}

class _RecordingContentMediaFacet implements ContentMediaFacet {
  _RecordingContentMediaFacet(this.originalUrl);

  final Uri originalUrl;
  final List<String> requestedMediaIds = <String>[];

  @override
  Future<MediaOriginalAccessGrant> requestOriginalAccess(
    RequestContentMediaOriginalAccessCommand command,
  ) async {
    requestedMediaIds.add(command.mediaId);
    return MediaOriginalAccessGrant(
      mediaId: command.mediaId,
      status: 'granted',
      originalUrl: originalUrl,
      format: 'jpeg',
      sizeBytes: 2048,
      expiresAt: DateTime.now().toUtc().add(const Duration(minutes: 5)),
      ttlSeconds: 300,
      auditId: 'audit-original-viewer',
    );
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

ContentPostViewData _photoPost({
  String id = 'photo-1',
  List<String> imageUrls = const ['media/image/s/fixture/photo.jpg'],
  String body = 'dto body',
  String coverUrl = 'media/image/s/fixture/photo.jpg',
  String avatarUrl = 'https://example.com/avatar.jpg',
  int? width,
  int? height,
  List<IntersectionReason>? intersectionReasons,
}) {
  return ContentPostViewData.fromWire(
    ContentPostProjection(
      postId: id,
      contentType: 'image',
      contentIdentity: 'work',
      assistantUsePolicy: AssistantUsePolicy.inherit,
      authorId: 'author-1',
      authorDisplayName: '摄影师',
      authorAvatarUrl: avatarUrl,
      authorRoleLabel: '',
      authorIdentityTags: const <String>[],
      authorVerified: false,
      body: body,
      coverUrl: coverUrl,
      mediaUrls: imageUrls,
      mediaItems: <PostMediaItem>[
        for (final url in imageUrls)
          PostMediaItem(
            kind: 'image',
            url: url,
            accessMode: MediaDeliveryAccessMode.public,
          ),
      ],
      width: width,
      height: height,
      likeCount: 0,
      commentCount: 0,
      shareCount: 0,
      createdAt: DateTime.now(),
      intersectionReasons: intersectionReasons,
    ),
  );
}

ContentPostViewData _videoPost({
  int? width,
  int? height,
  String body = 'video body',
  String videoUrl =
      'media/video/s/video-primary-0001/post/video-content-0001/v1/source.mp4',
  String coverUrl =
      'media/image/s/archived-image/post/fixture_video_001/v1/cover.png',
  SourceAttribution? sourceAttribution,
  List<IntersectionReason>? intersectionReasons,
}) {
  return ContentPostViewData.fromWire(
    ContentPostProjection(
      postId: 'video-1',
      contentType: 'video',
      contentIdentity: 'work',
      assistantUsePolicy: AssistantUsePolicy.inherit,
      authorId: 'author-video',
      authorDisplayName: '视频作者',
      authorAvatarUrl: '',
      authorRoleLabel: '',
      authorIdentityTags: const <String>[],
      authorVerified: false,
      body: body,
      videoUrl: videoUrl,
      thumbnailUrl: coverUrl,
      coverUrl: coverUrl,
      width: width,
      height: height,
      durationMs: 125000,
      mediaItems: <PostMediaItem>[
        PostMediaItem(
          kind: 'video',
          url: videoUrl,
          accessMode: MediaDeliveryAccessMode.public,
          coverUrl: coverUrl.isEmpty ? null : coverUrl,
          durationMs: 125000,
        ),
      ],
      likeCount: 0,
      commentCount: 0,
      shareCount: 0,
      createdAt: DateTime.now(),
      intersectionReasons: intersectionReasons,
    ),
    sourceAttribution: sourceAttribution,
  );
}

ContentPostViewData _articlePost({
  List<IntersectionReason>? intersectionReasons,
  DateTime? createdAt,
  DateTime? updatedAt,
}) {
  return ContentPostViewData.fromWire(
    ContentPostProjection(
      postId: 'article-1',
      contentType: 'article',
      contentIdentity: 'work',
      assistantUsePolicy: AssistantUsePolicy.inherit,
      authorId: 'author-3',
      authorDisplayName: '写作者',
      authorAvatarUrl: 'https://example.com/avatar-3.jpg',
      authorRoleLabel: '',
      authorIdentityTags: const <String>[],
      authorVerified: false,
      title: '图文翻页',
      body: '文章摘要',
      summary: '文章摘要',
      coverUrl: 'https://example.com/article-cover.jpg',
      articleTemplate: 'gentle',
      articleFontPreset: 'clean',
      likeCount: 0,
      commentCount: 0,
      shareCount: 0,
      createdAt: createdAt ?? DateTime.now(),
      updatedAt: updatedAt,
      intersectionReasons: intersectionReasons,
    ),
  );
}

/// 生成确定性多页文章 markdown（唯一内容真相源）。
/// 替代旧 `cards` 借壳分页：markdown-only 契约下，多页由排版流引擎按视口高度切分。
String _multiPageArticleMarkdown(
  ContentPostViewData post, {
  int sections = 14,
  int paragraphsPerSection = 1,
}) {
  final blocks = List<String>.generate(sections, (index) {
    final paragraphs = List<String>.generate(
      paragraphsPerSection,
      (p) =>
          '这是第 ${index + 1} 小节第 ${p + 1} 段用于沉浸式文章自动分页的长正文，'
          '需要被继续拆到后续页面中，不能仍然停留在 1/1。',
    ).join('\n\n');
    return '## 小节${index + 1}\n\n$paragraphs';
  }).join('\n\n');
  return '---\n'
      'title: ${post.title}\n'
      'template: ${post.articleTemplate}\n'
      'fontPreset: ${post.articleFontPreset}\n'
      '---\n\n'
      '$blocks\n';
}

/// 以 markdown 为唯一内容源构造沉浸 viewer 的文章原始行。
Map<String, dynamic> _articleMarkdownRaw(
  ContentPostViewData post,
  String markdown, {
  Map<String, dynamic> extra = const <String, dynamic>{},
}) {
  return <String, dynamic>{
    'postId': post.id,
    'contentType': 'article',
    'authorId': post.authorId,
    'authorDisplayName': post.displayName,
    'authorAvatarUrl': post.avatarUrl,
    'title': post.title,
    'body': post.body,
    'summary': post.summary,
    'coverUrl': post.coverUrl,
    'articleTemplate': post.articleTemplate,
    'articleFontPreset': post.articleFontPreset,
    'articleMarkdown': markdown,
    'markdownDialect': 'qwq-rich-md',
    'articleAssetManifest': const <String, dynamic>{
      'schema': 'article-asset-manifest',
      'markdownDialect': 'qwq-rich-md',
      'articleMarkdownDigest': 'fixture:multipage',
      'assets': <Map<String, dynamic>>[],
    },
    'articleRenderProfile': <String, dynamic>{
      'template': post.articleTemplate,
      'fontPreset': post.articleFontPreset,
    },
    ...extra,
  };
}

String _articleProgressLabel(WidgetTester tester) {
  final label = tester.widget<Text>(
    find.byKey(const ValueKey<String>('works-article-page-progress')),
  );
  return label.data ?? '';
}

/// 断言已离开第 1 页（翻页生效）。markdown-only 后不再断言具体卡片文案。
void _expectArticleAdvancedPastFirstPage(WidgetTester tester) {
  expect(_articleProgressLabel(tester), isNot(startsWith('1 / ')));
}

/// 用页码 chevron 把文章翻到末页（确定性导航，替代旧 2 页 fixture 的单次拖拽到末页）。
Future<void> _flipArticleToLastPage(WidgetTester tester) async {
  final next = find.byKey(const ValueKey<String>('works-article-page-next'));
  for (var guard = 0; guard < 200; guard += 1) {
    final parts = _articleProgressLabel(tester).split(' / ');
    if (parts.length == 2 && parts[0].trim() == parts[1].trim()) {
      final total = int.tryParse(parts[1].trim()) ?? 1;
      final lastSurfaceKey = ValueKey<String>(
        'article-reader-page-surface-${total - 1}',
      );
      for (var settleGuard = 0; settleGuard < 12; settleGuard += 1) {
        if (find.byKey(lastSurfaceKey).evaluate().isNotEmpty) {
          return;
        }
        await tester.pump(const Duration(milliseconds: 16));
      }
      return;
    }
    if (next.evaluate().isEmpty) {
      return;
    }
    await tester.tap(next);
    await _pumpSettledFrames(tester);
  }
}

Future<void> _flipArticleToSecondPage(WidgetTester tester) async {
  final next = find.byKey(const ValueKey<String>('works-article-page-next'));
  if (next.evaluate().isEmpty ||
      _articleProgressLabel(tester).startsWith('2 / ')) {
    return;
  }
  await tester.tap(next);
  await _pumpSettledFrames(tester);
}

ContentPostViewData _textMoment({
  List<IntersectionReason>? intersectionReasons,
}) {
  return ContentPostViewData.fromWire(
    ContentPostProjection(
      postId: 'moment-1',
      contentType: 'micro',
      contentIdentity: 'moment',
      assistantUsePolicy: AssistantUsePolicy.inherit,
      authorId: 'author-2',
      authorDisplayName: '圈友',
      authorAvatarUrl: 'https://example.com/avatar-2.jpg',
      authorRoleLabel: '',
      authorIdentityTags: const <String>[],
      authorVerified: false,
      body: '今天风有点大，大家从南门集合。',
      mediaUrls: const <String>[],
      likeCount: 0,
      commentCount: 0,
      shareCount: 0,
      createdAt: DateTime.now(),
      intersectionReasons: intersectionReasons,
    ),
  );
}

Widget _wrap(
  Widget child, {
  List overrides = const [],
  bool useProductionRuntimeConfig = false,
  double? textScaleFactor,
  EdgeInsets? viewPadding,
  ContentPostDetailReader? detailReader,
  ContentConfigRepository? configRepository,
  ContentDiscoveryFeedQuery? feedQuery,
}) {
  final allOverrides = [
    ..._sealedViewerBoundaryOverrides(),
    ...mockContentFacetOverrides(
      store: InMemoryContentPostStore(),
      detailReader: detailReader,
      configRepository: configRepository,
      feedQuery: feedQuery,
    ),
    mediaEndpointConfigProvider.overrideWithValue(_testMediaEndpointConfig),
    if (!useProductionRuntimeConfig)
      contentRuntimeConfigProvider.overrideWithValue(
        buildAlphaContentRuntimeConfigDefaults(),
      ),
    ...overrides,
  ];
  return ProviderScope(
    overrides: allOverrides.cast(),
    child: ScreenUtilInit(
      designSize: const Size(375, 812),
      builder: (context, _) => MaterialApp(
        theme: ThemeData.dark(),
        builder: textScaleFactor == null && viewPadding == null
            ? null
            : (context, child) {
                final mediaQuery = MediaQuery.of(context);
                return MediaQuery(
                  data: mediaQuery.copyWith(
                    textScaler: textScaleFactor == null
                        ? mediaQuery.textScaler
                        : TextScaler.linear(textScaleFactor),
                    padding: viewPadding ?? mediaQuery.padding,
                    viewPadding: viewPadding ?? mediaQuery.viewPadding,
                  ),
                  child: child!,
                );
              },
        home: Scaffold(body: child),
      ),
    ),
  );
}

/// 该 double 覆写了全部网络入口，因此数据面 client 永不应被触达；
/// 内层传输故意直接抛错，把「意外发起真实下载」变成显式测试失败。
CloudHttpClient _unreachableDataPlaneClient() => CloudHttpClient(
  client: MockClient(
    (request) async => throw StateError(
      'MediaDownloadCache double must not perform network IO',
    ),
  ),
);

final class _NoopMediaDownloadCache extends MediaDownloadCache {
  _NoopMediaDownloadCache() : super(client: _unreachableDataPlaneClient());

  @override
  Future<String?> getCachedFilePath(String url) async => null;
}

FakeVideoPlayerPlatform _installImmersiveVideoTestPlatform() {
  final originalPlatform = VideoPlayerPlatform.instance;
  final fakePlatform = FakeVideoPlayerPlatform();
  VideoPlayerPlatform.instance = fakePlatform;
  VideoPlayerWidget.debugResetControllerSlots();
  FlutterSecureStorage.setMockInitialValues(<String, String>{});
  _mockPathProviderForImmersiveViewerTest();
  addTearDown(() {
    VideoPlayerPlatform.instance = originalPlatform;
    VideoPlayerWidget.debugResetControllerSlots();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
          const MethodChannel('plugins.flutter.io/path_provider'),
          null,
        );
  });
  return fakePlatform;
}

void _mockPathProviderForImmersiveViewerTest() {
  const channel = MethodChannel('plugins.flutter.io/path_provider');
  TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
      .setMockMethodCallHandler(channel, (call) async {
        final directory = Directory.systemTemp.createTempSync(
          'quwoquan-works-immersive-test-',
        );
        addTearDown(() {
          if (directory.existsSync()) {
            directory.deleteSync(recursive: true);
          }
        });
        switch (call.method) {
          case 'getApplicationDocumentsDirectory':
          case 'getApplicationSupportDirectory':
          case 'getTemporaryDirectory':
            return directory.path;
          default:
            return null;
        }
      });
}

Widget _wrapWithRouter(
  Widget child, {
  List overrides = const [],
  ContentPostDetailReader? detailReader,
}) {
  final router = GoRouter(
    routes: [
      GoRoute(
        path: '/',
        builder: (context, state) => Scaffold(body: child),
      ),
      GoRoute(
        path: '/user/:userHandle',
        builder: (context, state) => Text(
          'user:${state.pathParameters['userHandle']}',
          key: const ValueKey<String>('user-profile-probe'),
        ),
      ),
      GoRoute(
        path: '/homepages/:id',
        builder: (context, state) => Text(
          'homepage:${state.pathParameters['id']}',
          key: const ValueKey<String>('homepage-detail-probe'),
        ),
      ),
      GoRoute(
        path: AppRoutePaths.globalSearchNetworkResultsPathTemplate,
        builder: (context, state) => Text(
          'search:${state.uri.queryParameters['query'] ?? ''}',
          key: const ValueKey<String>('search-network-probe'),
        ),
      ),
    ],
  );
  return ProviderScope(
    overrides: [
      ..._sealedViewerBoundaryOverrides(),
      ...mockContentFacetOverrides(
        store: InMemoryContentPostStore(),
        detailReader: detailReader,
      ),
      mediaEndpointConfigProvider.overrideWithValue(_testMediaEndpointConfig),
      ...overrides,
    ].cast(),
    child: ScreenUtilInit(
      designSize: const Size(375, 812),
      builder: (context, _) =>
          MaterialApp.router(theme: ThemeData.dark(), routerConfig: router),
    ),
  );
}

void _consumeImageLoadExceptions(WidgetTester tester) {
  Object? exception;
  while ((exception = tester.takeException()) != null) {
    final message = exception.toString();
    final isExpectedImageFailure =
        exception is NetworkImageLoadException ||
        exception is HttpException ||
        exception is SocketException ||
        message.contains('ImageCodecException') ||
        message.contains('Invalid image data');
    if (!isExpectedImageFailure) {
      throw exception!;
    }
  }
}

Future<void> _pumpImmersiveViewerFirstFrames(WidgetTester tester) async {
  await tester.pump();
  _consumeImageLoadExceptions(tester);
  // 沉浸 viewer 首帧可能同时构建视频占位；测试环境视频初始化不完成时
  // CupertinoActivityIndicator 会持续调度帧，因此不能用 pumpAndSettle。
  await tester.pump(const Duration(milliseconds: 16));
  await tester.pump(const Duration(milliseconds: 16));
  _consumeImageLoadExceptions(tester);
}

Future<Finder> _waitForVideoTimelineMeasurementFrame(
  WidgetTester tester,
) async {
  final timeline = find.byKey(
    const ValueKey<String>('video-playback-timeline-workBrowser'),
  );
  for (var attempt = 0; attempt < 40; attempt += 1) {
    await tester.runAsync(() async {
      await Future<void>.delayed(Duration.zero);
    });
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    if (timeline.evaluate().isNotEmpty) {
      return timeline;
    }
    await tester.pump(const Duration(milliseconds: 16));
    _consumeImageLoadExceptions(tester);
    if (timeline.evaluate().isNotEmpty) {
      return timeline;
    }
  }
  expect(timeline, findsOneWidget, reason: '受控视频会话应在有界帧内装配共享时间轴。');
  return timeline;
}

Future<void> _pumpSettledFrames(WidgetTester tester) async {
  _consumeImageLoadExceptions(tester);
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 450));
  await tester.pump(const Duration(milliseconds: 16));
  _consumeImageLoadExceptions(tester);
}

List<Rect> _globalTextPaintRects(WidgetTester tester, Finder finder) {
  final root = tester.renderObject<RenderObject>(finder);
  final result = <Rect>[];
  void collect(RenderObject object) {
    if (object is RenderParagraph && object.attached && object.hasSize) {
      final textLength = object.text.toPlainText().length;
      if (textLength > 0) {
        for (final box in object.getBoxesForSelection(
          TextSelection(baseOffset: 0, extentOffset: textLength),
        )) {
          final localRect = box.toRect();
          result.add(
            Rect.fromPoints(
              object.localToGlobal(localRect.topLeft),
              object.localToGlobal(localRect.bottomRight),
            ),
          );
        }
      }
    }
    object.visitChildren(collect);
  }

  collect(root);
  return result;
}

Future<void> _tapRichTextSubstring(
  WidgetTester tester,
  Finder finder,
  String substring,
) async {
  final render = tester.renderObject<RenderParagraph>(finder);
  final plainText = render.text.toPlainText();
  final start = plainText.indexOf(substring);
  expect(start, greaterThanOrEqualTo(0), reason: '未找到文本片段: $substring');
  final end = start + substring.length;
  final boxes = render.getBoxesForSelection(
    TextSelection(baseOffset: start, extentOffset: end),
  );
  expect(boxes, isNotEmpty, reason: '文本片段未生成可点击字形框: $substring');
  final TextBox box = boxes.first;
  await tester.tapAt(render.localToGlobal(box.toRect().center));
}

class _DeferredPostWorksViewer extends StatefulWidget {
  const _DeferredPostWorksViewer({
    required this.post,
    required this.rawRow,
    required this.revealDelay,
  });

  final ContentPostViewData post;
  final Map<String, dynamic> rawRow;
  final Duration revealDelay;

  @override
  State<_DeferredPostWorksViewer> createState() =>
      _DeferredPostWorksViewerState();
}

class _DeferredPostWorksViewerState extends State<_DeferredPostWorksViewer> {
  List<ContentPostViewData> _posts = const <ContentPostViewData>[];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      await Future<void>.delayed(widget.revealDelay);
      if (!mounted) {
        return;
      }
      setState(() {
        _posts = <ContentPostViewData>[widget.post];
      });
    });
  }

  @override
  Widget build(BuildContext context) {
    return WorksImmersiveViewer(
      showWorksToolbar: true,
      showTopNavigation: false,
      externalPosts: _posts,
      externalPostViews: _posts
          .map(ContentSurfaceViewMapper.fromDto)
          .toList(growable: false),
      rawPostsById: _posts.isEmpty
          ? const <String, MediaViewerPostWireRow>{}
          : _viewerRawByPostId({widget.post.id: widget.rawRow}),
      onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
      onAssistantTap: () {},
    );
  }
}

WorksViewerFeedSnapshot _worksFeedSnapshot({
  List<ContentPostViewData> items = const <ContentPostViewData>[],
  bool isLoading = false,
  bool hasMore = false,
  Object? blockingError,
  ContentFeedEmptyReason? emptyReason,
  Object? appendError,
}) {
  return WorksViewerFeedSnapshot(
    items: items,
    hasMore: hasMore,
    isLoading: isLoading,
    blockingError: blockingError,
    emptyReason: emptyReason,
    appendError: appendError,
  );
}

final class _RecordingWorksViewerFeedCommands extends WorksViewerFeedCommands {
  _RecordingWorksViewerFeedCommands(
    super.ref,
    this.loadedChannels,
    this.loadTerminals,
    this.loadGate,
  );

  final List<String> loadedChannels;
  final Map<String, DiscoveryFeedLoadTerminal> loadTerminals;
  final Future<void>? loadGate;
  int _generation = 0;

  @override
  bool contains(String channelId) => false;

  @override
  Future<DiscoveryFeedLoadResult> load(
    String channelId, {
    bool force = false,
  }) async {
    loadedChannels.add(channelId);
    await loadGate;
    return DiscoveryFeedLoadResult(
      terminal:
          loadTerminals[channelId] ?? DiscoveryFeedLoadTerminal.canonicalEmpty,
      generation: ++_generation,
    );
  }
}

List<Override> _worksInternalFeedOverrides({
  required AsyncValue<WorksViewerFeedSnapshot> photo,
  required AsyncValue<WorksViewerFeedSnapshot> video,
  required AsyncValue<WorksViewerFeedSnapshot> article,
  List<String>? loadedChannels,
  Map<String, DiscoveryFeedLoadTerminal> loadTerminals = const {},
  Future<void>? loadGate,
}) {
  return <Override>[
    worksViewerFeedProvider('photo').overrideWithValue(photo),
    worksViewerFeedProvider('video').overrideWithValue(video),
    worksViewerFeedProvider('article').overrideWithValue(article),
    worksViewerFeedCommandsProvider.overrideWith(
      (ref) => _RecordingWorksViewerFeedCommands(
        ref,
        loadedChannels ?? <String>[],
        loadTerminals,
        loadGate,
      ),
    ),
  ];
}

Widget _internalWorksViewer() {
  return WorksImmersiveViewer(
    showWorksToolbar: true,
    showTopNavigation: false,
    source: 'browse',
    onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
    onAssistantTap: () {},
  );
}

void main() {
  setUpAll(ensureSqfliteFfiInitialized);

  setUp(() {
    HttpOverrides.global = _FakeHttpOverrides();
    _mockPathProviderForImmersiveViewerTest();
  });

  test('沉浸媒体滑动顺滑性静态契约', () {
    // 视频书重构后，图片横滑翻书迁移到 components/media 公共层；
    // viewer/canvas 只保留 discovery adapter，视频只保活当前页以控制解码器压力。
    final viewerSource =
        File(
          'lib/service/content_service/media/media_asset/presentation/works_immersive_viewer.dart',
        ).readAsStringSync() +
        File(
          'lib/service/content_service/media/media_asset/presentation/works_immersive_viewer_build.dart',
        ).readAsStringSync() +
        File(
          'lib/service/content_service/media/media_asset/presentation/works_immersive_viewer_canvas.dart',
        ).readAsStringSync() +
        File(
          'lib/service/content_service/media/media_asset/presentation/works_immersive_viewer_lifecycle.dart',
        ).readAsStringSync();
    final imageBookSource = File(
      'lib/service/content_service/media/media_asset/presentation/image_book_canvas.dart',
    ).readAsStringSync();
    final mediaPageflipSource =
        File(
          'lib/service/content_service/media/media_asset/presentation/media_page_flip_book.dart',
        ).readAsStringSync() +
        File(
          'lib/service/content_service/media/media_asset/presentation/media_page_flip_book_soft_surface.dart',
        ).readAsStringSync() +
        File(
          'lib/service/content_service/media/media_asset/presentation/media_page_flip_book_gestures.dart',
        ).readAsStringSync() +
        File(
          'lib/service/content_service/media/media_asset/presentation/media_page_flip_book_texture_cache.dart',
        ).readAsStringSync();
    final videoPlayerSource = File(
      'lib/service/content_service/media/media_asset/presentation/video_player_widget.dart',
    ).readAsStringSync();

    expect(viewerSource, contains('return ImageBookCanvas('));
    expect(imageBookSource, contains('class ImageBookCanvas'));
    expect(
      imageBookSource,
      contains('ImageBookPageSurfaceFactory'),
      reason: '图片书 ready 图片必须统一成同尺寸 page surface。',
    );
    expect(imageBookSource, contains('MediaPageFlipBook('));
    expect(imageBookSource, contains('textureSnapshotBuilder:'));
    expect(imageBookSource, contains('_buildTexturePair('));
    expect(imageBookSource, contains('class _ImageBookPageResource'));
    expect(
      imageBookSource,
      isNot(contains('buildLoadingTexture(')),
      reason: '图片书 active curl 不得把 loading 模糊面提升为翻页材质。',
    );
    expect(imageBookSource, isNot(contains('buildFailureTexture(')));
    expect(imageBookSource, contains('buildNeutralTexture('));
    expect(mediaPageflipSource, contains('class MediaPageFlipBook'));
    expect(mediaPageflipSource, contains('computeStPageFlipLayout('));
    expect(mediaPageflipSource, contains('_buildDynamicLayers('));
    expect(mediaPageflipSource, contains('media-pageflip-flipping-layer'));
    expect(
      imageBookSource,
      contains('cacheManagerForPreset'),
      reason: '每页唯一解码链必须使用 cover cache manager。',
    );
    expect(
      viewerSource,
      contains('allowImplicitScrolling: true'),
      reason: '视频书只通过真实相邻页承载唯一 N+1 预热，不额外创建隐藏播放器。',
    );
    expect(
      viewerSource,
      contains('final keepAlive = shouldInitialize'),
      reason: '视频书只保活当前项与唯一 N+1，取消预热后立即释放非活跃页。',
    );
    expect(
      viewerSource,
      contains('isVisible: index == _currentPage'),
      reason: '外层 PageView 预建相邻帖子时，非可见视频帖子不得初始化 decoder。',
    );
    expect(
      viewerSource,
      contains('initialize: shouldInitialize'),
      reason: '只有当前可见帖子内的当前分集与唯一 N+1 可以占用全局 controller 槽位。',
    );
    expect(
      viewerSource,
      contains('index == _currentEpisodeIndex + 1'),
      reason: '预热边界必须严格收口为当前项后的唯一 N+1。',
    );
    expect(
      viewerSource,
      contains('didHaveMemoryPressure()'),
      reason: '内存压力必须取消并释放 N+1 预热槽位。',
    );
    expect(
      viewerSource,
      contains('viewportEpoch != _videoViewportEpoch'),
      reason: '外层翻页后的迟到播放会话回调不得覆盖当前可见视频。',
    );
    expect(
      videoPlayerSource,
      contains('void didUpdateWidget(covariant VideoPlayerWidget oldWidget)'),
      reason: '视频播放器必须响应 autoPlay 变化，同步切页后的播放/暂停状态。',
    );
    expect(
      videoPlayerSource,
      contains(
        '_playbackSession.setAutomaticPlaybackEligible(widget.autoPlay);',
      ),
      reason:
          'autoPlay 变更必须经 VideoPlaybackSession 的强类型状态机同步，'
          '不能回退到播放器私有播放控制。',
    );
  });

  test('沉浸浏览器主文件与职责 companion 均低于千行', () {
    final files =
        Directory(
          'lib/service/content_service/media/media_asset/presentation',
        ).listSync().whereType<File>().where(
          (file) =>
              file.uri.pathSegments.last.startsWith('works_immersive_viewer') &&
              file.path.endsWith('.dart'),
        );
    for (final file in files) {
      final lineCount = file.readAsStringSync().split('\n').length;
      expect(
        lineCount,
        lessThan(1000),
        reason: '${file.uri.pathSegments.last} 不得重新膨胀为千行级职责集合。',
      );
    }
  });

  testWidgets('视频书沉浸流尾部显示加载哨兵并预取下一批内容', (tester) async {
    final repo = _PagedFeaturedContentRepository();
    final analytics = _FakeAnalyticsService();
    final container = _testProviderContainer(
      overrides: [
        ...mockContentFacetOverrides(
          store: InMemoryContentPostStore(),
          feedQuery: repo,
        ),
        analyticsProvider.overrideWithValue(analytics),
      ],
    );
    addTearDown(container.dispose);

    var switchedToHome = false;

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: ScreenUtilInit(
          designSize: const Size(375, 812),
          builder: (context, _) => MaterialApp(
            theme: ThemeData.dark(),
            home: Scaffold(
              body: WorksImmersiveViewer(
                showWorksToolbar: true,
                showTopNavigation: true,
                source: 'browse',
                onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
                onAssistantTap: () {},
                onSwitchToCircles: () => switchedToHome = true,
                onSwitchToFollowing: () => switchedToHome = true,
              ),
            ),
          ),
        ),
      ),
    );
    await _pumpImmersiveViewerFirstFrames(tester);
    for (var attempt = 0; attempt < 40; attempt += 1) {
      final allFeedsReady = const <String>['photo', 'video', 'article'].every(
        (channelId) =>
            container.read(discoveryFeedProvider(channelId)).value != null,
      );
      if (allFeedsReady) {
        break;
      }
      await tester.runAsync(() => Future<void>.delayed(Duration.zero));
      await tester.pump(const Duration(milliseconds: 16));
      _consumeImageLoadExceptions(tester);
    }

    expect(
      container.read(discoveryFeedProvider('photo')).value?.items.length,
      equals(2),
    );
    expect(
      container.read(discoveryFeedProvider('video')).value?.items.length,
      equals(2),
    );
    expect(
      container.read(discoveryFeedProvider('article')).value?.items.length,
      equals(2),
    );

    final verticalPager = find.byKey(TestKeys.worksImmersivePager);
    var reachedSentinel = false;
    for (var i = 0; i < 8; i += 1) {
      await tester.fling(verticalPager, const Offset(0, -700), 1200);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 450));
      reachedSentinel = find
          .byKey(TestKeys.worksLoadMoreSentinel)
          .evaluate()
          .isNotEmpty;
      if (reachedSentinel) {
        break;
      }
    }

    expect(reachedSentinel, isTrue);
    expect(repo.appendCallCount, greaterThan(0));
    expect(switchedToHome, isFalse);

    // 预取耗时 4s（append delay）；推进 5s 让追加完成并回灌 provider。预取揭示后
    // 当前竖向页可能聚焦到视频卡，其 autoPlay 加载占位的 CupertinoActivityIndicator
    // 是 by-design 永续动画，pumpAndSettle 会永不收敛。改用有界 pump 让回灌后的重建
    // 帧落地，再断言 provider 真实条数与哨兵消失。
    await tester.pump(const Duration(seconds: 5));
    _consumeImageLoadExceptions(tester);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 16));
    _consumeImageLoadExceptions(tester);

    expect(
      container.read(discoveryFeedProvider('photo')).value?.items.length,
      equals(4),
    );
    expect(
      container.read(discoveryFeedProvider('video')).value?.items.length,
      equals(4),
    );
    expect(
      container.read(discoveryFeedProvider('article')).value?.items.length,
      equals(4),
    );
    expect(find.byKey(TestKeys.worksLoadMoreSentinel), findsNothing);
    expect(switchedToHome, isFalse);

    // 滚动翻页会经 trackSkip 懒创建 ContentBehaviorTracker（周期性 flush 定时器，
    // 生命周期绑定 container.onDispose）。在测试体结束前显式 dispose container，
    // 使定时器在 pending-timer 不变量校验前被取消，避免 "Timer still pending"。
    container.dispose();
  });

  testWidgets('视频书顶部仅保留返回与更多入口并取消形态分段与一级 tab', (tester) async {
    final repo = _PagedFeaturedContentRepository();
    final container = _testProviderContainer(
      overrides: [
        ...mockContentFacetOverrides(
          store: InMemoryContentPostStore(),
          feedQuery: repo,
        ),
      ],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: ScreenUtilInit(
          designSize: const Size(375, 812),
          builder: (context, _) => MaterialApp(
            theme: ThemeData.dark(),
            home: Scaffold(
              body: WorksImmersiveViewer(
                showWorksToolbar: true,
                showTopNavigation: true,
                onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
                onAssistantTap: () {},
                onSwitchToFollowing: () {},
                onSwitchToCircles: () {},
              ),
            ),
          ),
        ),
      ),
    );
    await _pumpImmersiveViewerFirstFrames(tester);

    // 顶部仅保留「返回 + 更多」，禁止形态分段 / 一级 tab。
    expect(
      find.byKey(const ValueKey<String>('works-top-back')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('works-top-more')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('works-format-tab-strip')),
      findsNothing,
    );

    container.dispose();
  });

  testWidgets('UnifiedMediaViewerPage 首帧后灌入互动快照且不抛 provider 生命周期异常', (
    tester,
  ) async {
    final post = _photoPost(
      imageUrls: const ['media/image/s/fixture/photo-regression.jpg'],
    );
    final container = _testProviderContainer(
      overrides: <Override>[
        ...mockContentFacetOverrides(store: InMemoryContentPostStore()),
      ],
    );

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: ScreenUtilInit(
          designSize: const Size(375, 812),
          builder: (context, _) => MaterialApp(
            theme: ThemeData.dark(),
            home: UnifiedMediaViewerPage(
              extra: MediaViewerExtra(
                posts: <ContentSurfaceView>[
                  ContentSurfaceViewMapper.fromDto(post),
                ],
                dtoPosts: <ContentPostViewData>[post],
                initialIndex: 0,
                rawPostsById: _viewerRawByPostId({
                  post.id: <String, dynamic>{
                    'postId': post.id,
                    'type': 'image',
                    'contentType': 'image',
                    'authorId': post.authorId,
                    'authorDisplayName': post.displayName,
                    'authorAvatarUrl': post.avatarUrl,
                    'title': '回归标题',
                    'body': '回归正文',
                    'coverUrl': post.coverUrl,
                    'imageUrls': post.imageUrls,
                  },
                }),
                interactionSnapshot: MediaViewerInteractionSnapshot(
                  scopePostIds: <String>{post.id},
                  scopeProfileIds: <String>{post.personaId},
                  followingUsers: <String>{post.personaId},
                  likedPosts: <String>{post.id},
                  postLikesCount: <String, int>{post.id: 7},
                  postCommentCount: <String, int>{post.id: 4},
                  postSharesCount: <String, int>{post.id: 3},
                ),
              ),
            ),
          ),
        ),
      ),
    );

    expect(tester.takeException(), isNull);
    await _pumpImmersiveViewerFirstFrames(tester);
    expect(tester.takeException(), isNull);
    await tester.pump(const Duration(milliseconds: 16));
    _consumeImageLoadExceptions(tester);
    expect(tester.takeException(), isNull);

    expect(find.byType(WorksImmersiveViewer), findsOneWidget);
    final relationshipState = container.read(userRelationshipStateProvider);
    final postInteractionState = container.read(postInteractionStateProvider);
    expect(relationshipState.isFollowing(post.personaId), isTrue);
    expect(postInteractionState.isLiked(post.id), isTrue);
    expect(postInteractionState.commentCountFor(post.id), 4);
    expect(postInteractionState.shareCountFor(post.id), 3);

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    container.dispose();
  });

  testWidgets('UnifiedMediaViewerPage 文章底部工具栏沿统一安全轨道收口', (tester) async {
    final post = _articlePost();
    final container = _testProviderContainer(
      overrides: <Override>[
        ...mockContentFacetOverrides(store: InMemoryContentPostStore()),
      ],
    );

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MediaQuery(
          data: const MediaQueryData(
            size: Size(390, 844),
            padding: EdgeInsets.only(top: 47, bottom: 34),
            viewPadding: EdgeInsets.only(top: 47, bottom: 34),
          ),
          child: MaterialApp(
            theme: ThemeData.dark(),
            home: UnifiedMediaViewerPage(
              extra: MediaViewerExtra(
                posts: <ContentSurfaceView>[
                  ContentSurfaceViewMapper.fromDto(post),
                ],
                dtoPosts: <ContentPostViewData>[post],
                initialIndex: 0,
                rawPostsById: _viewerRawByPostId({
                  post.id: <String, dynamic>{
                    'postId': post.id,
                    'type': 'article',
                    'contentType': 'article',
                    'authorId': post.authorId,
                    'authorDisplayName': post.displayName,
                    'authorAvatarUrl': post.avatarUrl,
                    'title': post.title,
                    'body': post.body,
                    'summary': post.summary,
                    'coverUrl': post.coverUrl,
                    'articleTemplate': post.articleTemplate,
                    'articleFontPreset': post.articleFontPreset,
                    'cards': const [
                      {'title': '第二页标题', 'body': '第二页正文'},
                    ],
                  },
                }),
              ),
            ),
          ),
        ),
      ),
    );
    await _pumpImmersiveViewerFirstFrames(tester);

    final barFinder = find.byType(ImmersiveEngagementBar);
    final railFinder = find.byKey(const ValueKey('immersive-engagement-rail'));
    final barRect = tester.getRect(barFinder);
    final railRect = tester.getRect(railFinder);
    // 对齐轨道单源（REQ-019）：文章阶段底栏与正文 contentPadding 同源，
    // 不再叠加底部安全区侧向保护。
    const expectedSideInset = AppSpacing.containerLg;

    expect(
      (railRect.left - barRect.left - expectedSideInset).abs(),
      lessThan(1),
    );
    expect(
      (barRect.right - railRect.right - expectedSideInset).abs(),
      lessThan(1),
    );

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    container.dispose();
  });

  testWidgets('photo post 在 unified viewer 中展示 raw title/body', (tester) async {
    final post = _photoPost(
      imageUrls: const [
        'media/image/s/fixture/photo.jpg',
        'media/image/s/fixture/photo-2.jpg',
        'media/image/s/fixture/photo-3.jpg',
        'media/image/s/fixture/photo-4.jpg',
        'media/image/s/fixture/photo-5.jpg',
        'media/image/s/fixture/photo-6.jpg',
        'media/image/s/fixture/photo-7.jpg',
        'media/image/s/fixture/photo-8.jpg',
      ],
    );
    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: <String, dynamic>{
              'postId': post.id,
              'type': 'photo',
              'contentType': 'image',
              'authorId': post.authorId,
              'authorDisplayName': post.displayName,
              'authorAvatarUrl': post.avatarUrl,
              'title': '封面标题',
              'body': '封面正文，需要在浏览器底部展示出来。',
              'coverUrl': post.coverUrl,
              'imageUrls': post.imageUrls,
            },
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await _pumpImmersiveViewerFirstFrames(tester);

    expect(find.text('封面标题'), findsOneWidget);
    expect(find.textContaining('封面正文'), findsOneWidget);
    // 禁止顶部页码；多图导航使用点指示器（内容下方、标题上方）。
    expect(
      find.byKey(const ValueKey<String>('works-top-progress-label')),
      findsNothing,
    );
    expect(find.text('1/8'), findsNothing);
    expect(
      find.byKey(const ValueKey<String>('works-page-indicator')),
      findsOneWidget,
    );
    final indicatorRect = tester.getRect(
      find.byKey(const ValueKey<String>('works-page-indicator')),
    );
    final backRect = tester.getRect(
      find.byKey(const ValueKey<String>('works-top-back')),
    );
    final titleRect = tester.getRect(find.text('封面标题'));
    expect(indicatorRect.top, greaterThan(backRect.bottom));
    expect(indicatorRect.bottom, lessThanOrEqualTo(titleRect.top));
    // 圈子信息不再出现在工具栏（被交集理由位替代）。
    expect(find.text('测试圈子A'), findsNothing);
    expect(find.text('测试圈子B'), findsNothing);
    expect(find.byType(MediaBlurCaptionOverlay), findsNothing);
  });

  testWidgets('首页进入视频书沉浸浏览器后上下滑动切换推荐流且不弹旧禁用提示', (tester) async {
    final first = _photoPost(
      imageUrls: const ['media/image/s/fixture/home-first.jpg'],
    );
    final second = _photoPost(
      id: 'photo-2',
      imageUrls: const ['media/image/s/fixture/home-second.jpg'],
      body: 'second body',
    );

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [first, second],
          externalPostViews: [
            ContentSurfaceViewMapper.fromDto(first),
            ContentSurfaceViewMapper.fromDto(second),
          ],
          source: 'home_feed',
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await _pumpImmersiveViewerFirstFrames(tester);

    final gestureLayer = find.byKey(
      const ValueKey<String>('media-pageflip-gesture-layer'),
    );
    expect(gestureLayer, findsOneWidget);
    await tester.timedDrag(
      gestureLayer,
      const Offset(0, -360),
      const Duration(milliseconds: 420),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    _consumeImageLoadExceptions(tester);
    expect(find.text('second body'), findsOneWidget);
    expect(find.text('dto body'), findsNothing);
    expect(find.textContaining('不支持上下切换'), findsNothing);
  });

  testWidgets('视频书竖向作品流慢速拖过阈值后吸附到下一作品不弹回', (tester) async {
    final first = _photoPost(
      imageUrls: const ['media/image/s/fixture/photo-first.jpg'],
    );
    final second = _photoPost(
      id: 'photo-2',
      imageUrls: const ['media/image/s/fixture/photo-second.jpg'],
      body: 'second body',
    );
    final changed = <int>[];

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [first, second],
          externalPostViews: [
            ContentSurfaceViewMapper.fromDto(first),
            ContentSurfaceViewMapper.fromDto(second),
          ],
          onPostIndexChanged: changed.add,
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await _pumpImmersiveViewerFirstFrames(tester);

    expect(
      find.byKey(const ValueKey<String>('works-status-content-canvas-photo-1')),
      findsOneWidget,
    );

    final verticalPager = find.byWidgetPredicate(
      (widget) => widget is PageView && widget.scrollDirection == Axis.vertical,
    );
    await tester.timedDrag(
      verticalPager,
      const Offset(0, -272),
      const Duration(milliseconds: 480),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 1500));
    _consumeImageLoadExceptions(tester);

    expect(changed, contains(1));
    expect(
      find.byKey(const ValueKey<String>('works-status-content-canvas-photo-2')),
      findsOneWidget,
      reason: '慢速上滑超过阈值后应稳定吸附到下一作品，不能弹回当前作品。',
    );
  });

  testWidgets('视频书竖向图片按宽高比铺入状态栏', (tester) async {
    final post = _photoPost(width: 900, height: 1200);
    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          topChromeSafeInset: AppSpacing.twenty,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await _pumpImmersiveViewerFirstFrames(tester);

    final viewerRect = tester.getRect(find.byType(WorksImmersiveViewer));
    final canvasRect = tester.getRect(
      find.byKey(ValueKey<String>('works-status-content-canvas-${post.id}')),
    );
    expect((canvasRect.top - viewerRect.top).abs(), lessThan(1));
  });

  testWidgets('视频书宽横图保留状态栏安全区', (tester) async {
    final post = _photoPost(width: 1600, height: 900);
    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          topChromeSafeInset: AppSpacing.twenty,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await _pumpImmersiveViewerFirstFrames(tester);

    final viewerRect = tester.getRect(find.byType(WorksImmersiveViewer));
    final canvasRect = tester.getRect(
      find.byKey(ValueKey<String>('works-status-content-canvas-${post.id}')),
    );
    expect(
      canvasRect.top - viewerRect.top,
      moreOrLessEquals(AppSpacing.twenty),
    );
  });

  testWidgets('视频书视频可铺入状态栏', (tester) async {
    final post = _videoPost(width: 1920, height: 1080);
    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          topChromeSafeInset: AppSpacing.twenty,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    // 聚焦视频默认 autoPlay（canvas `_episodePlaybackSettled` 初值为 true），其加载占位
    // 是 CupertinoActivityIndicator —— 一个 by-design 永续动画。widget 测试环境没有
    // video_player 平台实现，VideoPlayerController.initialize() 永不回报 initialized，
    // 占位转圈会一直调度新帧，pumpAndSettle 因此永不收敛。布局（canvas 矩形）不依赖该
    // 转圈，用有界 pump 让布局稳定后断言真实的状态栏铺入几何即可。
    await tester.pump(const Duration(milliseconds: 16));
    await tester.pump(const Duration(milliseconds: 16));
    _consumeImageLoadExceptions(tester);

    final viewerRect = tester.getRect(find.byType(WorksImmersiveViewer));
    final canvasRect = tester.getRect(
      find.byKey(ValueKey<String>('works-status-content-canvas-${post.id}')),
    );
    expect((canvasRect.top - viewerRect.top).abs(), lessThan(1));
  });

  testWidgets('外部来源视频在沉浸播放器展示冻结的原创者归属', (tester) async {
    const attributionText = '原创：山海旅行者 · 来源：头条';
    final post = _videoPost(
      width: 1920,
      height: 1080,
      sourceAttribution: SourceAttribution(
        isOriginal: false,
        originalCreatorName: '山海旅行者',
        platform: '头条',
        sourcePostUrl: 'https://example.com/source-post',
        originalAssetUrl: 'https://example.com/source.mp4',
        attributionText: attributionText,
        rightsBasis: 'risk_accepted_attribution_only',
        commercialAuthorizationStatus: 'not_verified',
        publicationAdmission: 'risk_accepted_attribution_only',
        watermarkStatus: 'absent',
        audioRightsStatus: 'replaced_with_licensed_track',
        modelReleaseStatus: 'not_required',
        propertyReleaseStatus: 'not_required',
        collectedAt: DateTime(2026, 7, 20),
        takedownPolicy: 'notice_and_takedown',
      ),
    );

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump(const Duration(milliseconds: 16));
    _consumeImageLoadExceptions(tester);

    expect(
      find.byKey(const ValueKey<String>('works-video-source-attribution')),
      findsOneWidget,
    );
    expect(find.text(attributionText), findsOneWidget);
  });

  testWidgets('视频底部栈将文本置于时长和时间轴之上且时长只展示首次五秒', (tester) async {
    _installImmersiveVideoTestPlatform();

    final post = _videoPost(
      width: 1920,
      height: 1080,
      body: '标题正文与交集说明共同组成沉浸视频文本区。',
      intersectionReasons: <IntersectionReason>[
        _displayableIntersectionReason(
          dimension: 'relationship',
          primaryText: '联系人林清越收藏过',
          source: 'identity',
          actionTargetId: 'video-1',
        ),
      ],
      coverUrl: '',
    );
    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
        overrides: [
          mediaDownloadCacheProvider.overrideWithValue(
            _NoopMediaDownloadCache(),
          ),
        ],
        viewPadding: const EdgeInsets.only(bottom: 34),
      ),
    );
    await tester.pump();
    expect(find.byType(VideoPlayerWidget), findsOneWidget);
    expect(
      VideoPlayerWidget.debugActiveControllerCount,
      greaterThanOrEqualTo(1),
    );
    // 首次出现的测量帧必须先保持透明；实际 RenderBox 无碰撞后下一帧才显示。
    final timeline = await _waitForVideoTimelineMeasurementFrame(tester);

    final toolbarRect = tester.getRect(find.byType(ImmersiveEngagementBar));
    final track = find.byKey(
      const ValueKey<String>('video-playback-timeline-track'),
    );
    final duration = find.byKey(
      const ValueKey<String>('works-video-transient-duration'),
    );
    final caption = find.byKey(const ValueKey<String>('works-caption-rail'));
    final engagementRail = find.byKey(
      const ValueKey<String>('immersive-engagement-rail'),
    );
    final intersection = find.byKey(
      const ValueKey<String>('works-caption-intersection-reason'),
    );

    expect(timeline, findsOneWidget);
    expect(track, findsOneWidget);
    expect(duration, findsOneWidget);
    expect(caption, findsOneWidget);
    expect(intersection, findsOneWidget);
    expect(
      tester.widget<Opacity>(duration).opacity,
      0,
      reason: '首个布局帧尚未完成碰撞测量，总时长不得先闪现。',
    );
    await tester.pump();

    final timelineRect = tester.getRect(timeline);
    final trackRect = tester.getRect(track);
    final durationRect = tester.getRect(duration);
    final captionRect = tester.getRect(caption);
    final engagementRailRect = tester.getRect(engagementRail);
    final intersectionRect = tester.getRect(intersection);
    expect(timelineRect.bottom, closeTo(toolbarRect.top, 1));
    expect(trackRect.bottom, closeTo(toolbarRect.top, 1));
    expect(trackRect.width, closeTo(timelineRect.width, 1));
    expect(timelineRect.left, closeTo(engagementRailRect.left, 1));
    expect(timelineRect.right, closeTo(engagementRailRect.right, 1));
    expect(durationRect.right, closeTo(trackRect.right, 1));
    expect(durationRect.bottom, lessThan(trackRect.top));
    expect(captionRect.bottom, lessThan(durationRect.top));
    expect(intersectionRect.top, greaterThanOrEqualTo(captionRect.top));
    expect(intersectionRect.bottom, lessThanOrEqualTo(captionRect.bottom));
    expect(
      tester.widget<Opacity>(duration).opacity,
      1,
      reason: '首次进入且无文本碰撞时应显示总时长。',
    );

    final timelineRectBeforeExpiry = tester.getRect(timeline);
    final trackRectBeforeExpiry = tester.getRect(track);
    final captionRectBeforeExpiry = tester.getRect(caption);
    await tester.pump(const Duration(seconds: 3));
    await tester.tap(
      find.byKey(const ValueKey<String>('video-playback-timeline-hit-area')),
    );
    for (
      var attempt = 0;
      attempt < 10 && tester.widget<Opacity>(duration).opacity != 1;
      attempt += 1
    ) {
      await tester.pump(const Duration(milliseconds: 16));
    }
    expect(
      tester.widget<Opacity>(duration).opacity,
      1,
      reason: '普通点击不得提前结束或重启仍在进行的 entry-only 窗口。',
    );
    await tester.pump(const Duration(milliseconds: 2100));
    expect(
      tester.widget<Opacity>(duration).opacity,
      0,
      reason: '点击/拖动不得重新开启 entry_only 的五秒窗口。',
    );
    expect(tester.getRect(timeline), timelineRectBeforeExpiry);
    expect(tester.getRect(track), trackRectBeforeExpiry);
    expect(tester.getRect(caption), captionRectBeforeExpiry);
  });

  testWidgets('视频底部层级在双手机与 iPad 视口保持贴栏和安全轨对齐', (tester) async {
    _installImmersiveVideoTestPlatform();
    tester.view.devicePixelRatio = 1;
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });
    final post = _videoPost(
      width: 1920,
      height: 1080,
      body: '短标题正文',
      coverUrl: '',
    );
    final viewports = <({Size size, double bottomInset})>[
      (size: const Size(390, 844), bottomInset: 34),
      (size: const Size(430, 932), bottomInset: 34),
      (size: const Size(1024, 1366), bottomInset: 24),
    ];

    for (final viewport in viewports) {
      tester.view.physicalSize = viewport.size;
      await tester.pumpWidget(
        _wrap(
          WorksImmersiveViewer(
            showWorksToolbar: true,
            showTopNavigation: false,
            externalPosts: [post],
            externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
            onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
            onAssistantTap: () {},
          ),
          viewPadding: EdgeInsets.only(bottom: viewport.bottomInset),
          overrides: [
            mediaDownloadCacheProvider.overrideWithValue(
              _NoopMediaDownloadCache(),
            ),
          ],
        ),
      );
      final timeline = await _waitForVideoTimelineMeasurementFrame(tester);
      await tester.pump();
      final track = find.byKey(
        const ValueKey<String>('video-playback-timeline-track'),
      );
      final duration = find.byKey(
        const ValueKey<String>('works-video-transient-duration'),
      );
      final caption = find.byKey(const ValueKey<String>('works-caption-rail'));
      final toolbar = find.byType(ImmersiveEngagementBar);
      final engagementRail = find.byKey(
        const ValueKey<String>('immersive-engagement-rail'),
      );
      final timelineRect = tester.getRect(timeline);
      final trackRect = tester.getRect(track);
      final toolbarRect = tester.getRect(toolbar);
      final railRect = tester.getRect(engagementRail);

      expect(
        timelineRect.bottom,
        closeTo(toolbarRect.top, 1),
        reason: '${viewport.size} 时间轴热区未贴互动栏。',
      );
      expect(
        trackRect.bottom,
        closeTo(toolbarRect.top, 1),
        reason: '${viewport.size} 轨道本体未贴互动栏。',
      );
      expect(timelineRect.left, closeTo(railRect.left, 1));
      expect(timelineRect.right, closeTo(railRect.right, 1));
      expect(
        tester.getRect(caption).bottom,
        lessThan(tester.getRect(duration).top),
      );

      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump();
      for (
        var attempt = 0;
        attempt < 20 && VideoPlayerWidget.debugActiveControllerCount > 0;
        attempt += 1
      ) {
        await tester.runAsync(() async {
          await Future<void>.delayed(Duration.zero);
        });
        await tester.pump();
      }
      expect(VideoPlayerWidget.debugActiveControllerCount, 0);
    }
  });

  testWidgets('文本与总时长真实碰撞时首帧不闪现且仅隐藏视觉时长', (tester) async {
    _installImmersiveVideoTestPlatform();
    final post = _videoPost(
      width: 1920,
      height: 1080,
      body:
          '高文字缩放下仍需完整保留的标题正文，这段内容会连续铺满文本轨道，'
          '用于证明真正绘制出来的字形与右侧总时长发生碰撞，而不是只比较外层容器。',
      intersectionReasons: <IntersectionReason>[
        _displayableIntersectionReason(
          dimension: 'relationship',
          primaryText: '联系人林清越收藏过',
          source: 'identity',
          actionTargetId: 'video-1',
        ),
      ],
      coverUrl: '',
    );

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          // 碰撞测试只隔离 caption/timeline chrome，避免全局大字缩放把
          // 独立的互动工具栏可访问性约束混入本断言。
          showWorksToolbar: false,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
        textScaleFactor: 5,
        overrides: [
          mediaDownloadCacheProvider.overrideWithValue(
            _NoopMediaDownloadCache(),
          ),
        ],
      ),
    );

    final timeline = await _waitForVideoTimelineMeasurementFrame(tester);
    final duration = find.byKey(
      const ValueKey<String>('works-video-transient-duration'),
    );
    final caption = find.byKey(const ValueKey<String>('works-caption-rail'));
    final track = find.byKey(
      const ValueKey<String>('video-playback-timeline-track'),
    );
    expect(tester.widget<Opacity>(duration).opacity, 0);

    await tester.pump();
    final timelineRect = tester.getRect(timeline);
    final trackRect = tester.getRect(track);
    final durationRect = tester.getRect(duration);
    final textPaintRects = _globalTextPaintRects(tester, caption);
    expect(
      textPaintRects.any(
        (rect) => rect.inflate(AppSpacing.intraGroupXs).overlaps(durationRect),
      ),
      isTrue,
      reason: '测试必须制造真实 RenderParagraph 字形碰撞，而不是比较整条 rail 包围盒。',
    );
    expect(
      tester.widget<Opacity>(duration).opacity,
      0,
      reason: '碰撞时总时长必须立即保持透明。',
    );
    await tester.pump(const Duration(seconds: 1));
    expect(tester.getRect(timeline), timelineRect);
    expect(tester.getRect(track), trackRect);
    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget is Semantics &&
            widget.properties.label == MediaText.videoPlaybackProgressLabel &&
            widget.properties.value == '0:00 / 2:05',
      ),
      findsOneWidget,
      reason: '隐藏视觉时长不得删除 current/total 无障碍语义。',
    );
  });

  testWidgets('大字短文本未占满右侧时不按整条 rail 误隐藏时长', (tester) async {
    _installImmersiveVideoTestPlatform();
    final post = _videoPost(
      width: 1920,
      height: 1080,
      body: '短文',
      coverUrl: '',
    );
    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: false,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
        textScaleFactor: 5,
        overrides: [
          mediaDownloadCacheProvider.overrideWithValue(
            _NoopMediaDownloadCache(),
          ),
        ],
      ),
    );

    await _waitForVideoTimelineMeasurementFrame(tester);
    await tester.pump();
    final duration = find.byKey(
      const ValueKey<String>('works-video-transient-duration'),
    );
    final caption = find.byKey(const ValueKey<String>('works-caption-rail'));
    final durationRect = tester.getRect(duration);
    expect(
      tester
          .getRect(caption)
          .inflate(AppSpacing.intraGroupXs)
          .overlaps(durationRect),
      isTrue,
      reason: '测试需证明整条 rail 包围盒会产生旧实现的误判条件。',
    );
    expect(
      _globalTextPaintRects(tester, caption).any(
        (rect) => rect.inflate(AppSpacing.intraGroupXs).overlaps(durationRect),
      ),
      isFalse,
    );
    expect(
      tester.widget<Opacity>(duration).opacity,
      1,
      reason: '实际字形未填满右侧时，总时长可共享该纵向区域且不另占一行。',
    );
  });

  testWidgets('文字缩放动态变化会先隐藏并重新测量总时长', (tester) async {
    _installImmersiveVideoTestPlatform();
    final textScale = ValueNotifier<double>(1);
    addTearDown(textScale.dispose);
    final post = _videoPost(
      width: 1920,
      height: 1080,
      body:
          '动态文字缩放后必须重新测量的标题正文，这段内容会铺满文本轨道，'
          '让放大后的实际字形进入总时长区域。',
      intersectionReasons: <IntersectionReason>[
        _displayableIntersectionReason(
          dimension: 'relationship',
          primaryText: '联系人林清越收藏过',
          source: 'identity',
          actionTargetId: 'video-1',
        ),
      ],
      coverUrl: '',
    );

    await tester.pumpWidget(
      ValueListenableBuilder<double>(
        valueListenable: textScale,
        builder: (context, scale, _) => _wrap(
          WorksImmersiveViewer(
            showWorksToolbar: false,
            showTopNavigation: false,
            externalPosts: [post],
            externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
            onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
            onAssistantTap: () {},
          ),
          textScaleFactor: scale,
          overrides: [
            mediaDownloadCacheProvider.overrideWithValue(
              _NoopMediaDownloadCache(),
            ),
          ],
        ),
      ),
    );

    await _waitForVideoTimelineMeasurementFrame(tester);
    await tester.pump();
    final duration = find.byKey(
      const ValueKey<String>('works-video-transient-duration'),
    );
    final caption = find.byKey(const ValueKey<String>('works-caption-rail'));
    expect(tester.widget<Opacity>(duration).opacity, 1);

    textScale.value = 6;
    await tester.pump();
    expect(
      tester.widget<Opacity>(duration).opacity,
      0,
      reason: 'MediaQuery 几何改变后的首帧必须先透明，不能沿用旧碰撞结论。',
    );
    await tester.pump();
    final durationRect = tester.getRect(duration);
    expect(
      _globalTextPaintRects(tester, caption).any(
        (rect) => rect.inflate(AppSpacing.intraGroupXs).overlaps(durationRect),
      ),
      isTrue,
    );
    expect(tester.widget<Opacity>(duration).opacity, 0);
  });

  testWidgets('共享时间轴视觉关闭时仍保留视频进度语义', (tester) async {
    _installImmersiveVideoTestPlatform();
    final post = _videoPost(width: 1920, height: 1080, coverUrl: '');
    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
        overrides: [
          mediaDownloadCacheProvider.overrideWithValue(
            _NoopMediaDownloadCache(),
          ),
          contentFeatureFlagProvider('enable_shared_video_timeline')
              .overrideWith((ref) => false),
        ],
      ),
    );

    await _waitForVideoTimelineMeasurementFrame(tester);
    expect(
      find.byKey(const ValueKey<String>('video-playback-timeline-track')),
      findsNothing,
    );
    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget is Semantics &&
            widget.properties.label == MediaText.videoPlaybackProgressLabel &&
            widget.properties.value == '0:00 / 2:05',
      ),
      findsOneWidget,
    );
  });

  testWidgets('视频书只预热唯一 N+1 且方向变化与内存压力会释放', (tester) async {
    final fakePlatform = _installImmersiveVideoTestPlatform();
    final post = _videoPost(width: 1920, height: 1080, coverUrl: '');
    final raw = _viewerRawByPostId({
      post.id: <String, dynamic>{
        ..._canonicalPostWire(post),
        'workId': post.id,
        'workType': 'video',
        'workIdentity': 'work',
        'caption': post.body,
        'mediaItems': <Map<String, dynamic>>[
          for (var episode = 1; episode <= 3; episode += 1)
            <String, dynamic>{
              'kind': 'video',
              'url':
                  'media/video/s/video-series-001/post/video-1/'
                  'v1/episode-$episode.mp4',
              'accessMode': 'public',
              'durationMs': 125000,
            },
        ],
      },
    });

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: raw,
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
        overrides: [
          mediaDownloadCacheProvider.overrideWithValue(
            _NoopMediaDownloadCache(),
          ),
        ],
      ),
    );

    await _waitForVideoTimelineMeasurementFrame(tester);
    for (
      var attempt = 0;
      attempt < 30 && VideoPlayerWidget.debugActiveControllerCount != 2;
      attempt += 1
    ) {
      await tester.runAsync(() async {
        await Future<void>.delayed(Duration.zero);
      });
      await tester.pump(const Duration(milliseconds: 16));
    }

    var players = tester
        .widgetList<VideoPlayerWidget>(
          find.byType(VideoPlayerWidget, skipOffstage: false),
        )
        .toList(growable: false);
    expect(VideoPlayerWidget.debugActiveControllerCount, 2);
    expect(players.where((player) => player.initialize), hasLength(2));
    expect(players.where((player) => player.autoPlay), hasLength(1));
    expect(
      players.where((player) => player.initialize && !player.autoPlay),
      hasLength(1),
      reason: 'N+1 只完成 controller/decoder 预热，不得自动播放。',
    );
    final initialCurrentPlayCount = fakePlatform.playCount;
    expect(
      initialCurrentPlayCount,
      greaterThanOrEqualTo(1),
      reason: '当前项应保持自动播放语义。',
    );

    final episodePageView = find.byWidgetPredicate(
      (widget) =>
          widget is PageView &&
          widget.scrollDirection == Axis.horizontal &&
          widget.allowImplicitScrolling,
    );
    expect(episodePageView, findsOneWidget);
    final pageViewContext = tester.element(episodePageView);
    final metrics = FixedScrollMetrics(
      minScrollExtent: 0,
      maxScrollExtent: 750,
      pixels: 48,
      viewportDimension: 375,
      axisDirection: AxisDirection.right,
      devicePixelRatio: 1,
    );
    ScrollStartNotification(
      metrics: metrics,
      context: pageViewContext,
    ).dispatch(pageViewContext);
    ScrollUpdateNotification(
      metrics: metrics,
      context: pageViewContext,
      scrollDelta: 24,
    ).dispatch(pageViewContext);
    ScrollUpdateNotification(
      metrics: metrics,
      context: pageViewContext,
      scrollDelta: -12,
    ).dispatch(pageViewContext);
    await tester.pump();
    for (
      var attempt = 0;
      attempt < 20 && VideoPlayerWidget.debugActiveControllerCount > 1;
      attempt += 1
    ) {
      await tester.runAsync(() async {
        await Future<void>.delayed(Duration.zero);
      });
      await tester.pump();
    }
    expect(
      VideoPlayerWidget.debugActiveControllerCount,
      1,
      reason: '前向手势反向后必须立即取消旧 N+1 预热。',
    );
    expect(fakePlatform.playCount, initialCurrentPlayCount);

    ScrollEndNotification(
      metrics: metrics,
      context: pageViewContext,
    ).dispatch(pageViewContext);
    await tester.pump(const Duration(milliseconds: 120));
    for (
      var attempt = 0;
      attempt < 20 && VideoPlayerWidget.debugActiveControllerCount != 2;
      attempt += 1
    ) {
      await tester.runAsync(() async {
        await Future<void>.delayed(Duration.zero);
      });
      await tester.pump();
    }
    expect(VideoPlayerWidget.debugActiveControllerCount, 2);
    final resumedCurrentPlayCount = fakePlatform.playCount;
    expect(resumedCurrentPlayCount, greaterThan(initialCurrentPlayCount));

    WidgetsBinding.instance.handleMemoryPressure();
    await tester.pump();
    for (
      var attempt = 0;
      attempt < 20 && VideoPlayerWidget.debugActiveControllerCount > 1;
      attempt += 1
    ) {
      await tester.runAsync(() async {
        await Future<void>.delayed(Duration.zero);
      });
      await tester.pump();
    }
    players = tester
        .widgetList<VideoPlayerWidget>(
          find.byType(VideoPlayerWidget, skipOffstage: false),
        )
        .toList(growable: false);
    expect(VideoPlayerWidget.debugActiveControllerCount, 1);
    expect(players.where((player) => player.initialize), hasLength(1));
    expect(players.where((player) => player.autoPlay), hasLength(1));
    expect(fakePlatform.playCount, resumedCurrentPlayCount);

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    for (
      var attempt = 0;
      attempt < 20 && VideoPlayerWidget.debugActiveControllerCount > 0;
      attempt += 1
    ) {
      await tester.runAsync(() async {
        await Future<void>.delayed(Duration.zero);
      });
      await tester.pump();
    }
    expect(VideoPlayerWidget.debugActiveControllerCount, 0);
  });

  testWidgets('重复公开交付引用仍为每个分集分配唯一 stage 与 session', (tester) async {
    _installImmersiveVideoTestPlatform();
    final post = _videoPost(width: 1920, height: 1080, coverUrl: '');
    final duplicateUrl =
        'media/video/s/video-series-duplicate/post/video-1/v1/shared.mp4';
    final raw = _viewerRawByPostId({
      post.id: <String, dynamic>{
        ..._canonicalPostWire(post),
        'workId': post.id,
        'workType': 'video',
        'workIdentity': 'work',
        'caption': post.body,
        'mediaItems': <Map<String, dynamic>>[
          <String, dynamic>{
            'kind': 'video',
            'url': duplicateUrl,
            'accessMode': 'public',
            'durationMs': 125000,
          },
          <String, dynamic>{
            'kind': 'video',
            'url': duplicateUrl,
            'accessMode': 'public',
            'durationMs': 125000,
          },
        ],
      },
    });

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: raw,
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
        overrides: [
          mediaDownloadCacheProvider.overrideWithValue(
            _NoopMediaDownloadCache(),
          ),
        ],
      ),
    );

    await _waitForVideoTimelineMeasurementFrame(tester);
    for (
      var attempt = 0;
      attempt < 30 &&
          find
                  .byType(VideoPlayerWidget, skipOffstage: false)
                  .evaluate()
                  .length <
              2;
      attempt += 1
    ) {
      await tester.runAsync(() async {
        await Future<void>.delayed(Duration.zero);
      });
      await tester.pump(const Duration(milliseconds: 16));
    }

    final players = tester
        .widgetList<VideoPlayerWidget>(
          find.byType(VideoPlayerWidget, skipOffstage: false),
        )
        .toList(growable: false);
    expect(players, hasLength(2));
    expect(players.map((player) => player.key).toSet(), hasLength(2));
    expect(
      players.map((player) => player.playbackSession).toSet(),
      hasLength(2),
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('切集为每个分集重新开启一次五秒窗口', (tester) async {
    _installImmersiveVideoTestPlatform();
    final post = _videoPost(width: 1920, height: 1080, coverUrl: '');
    final raw = _viewerRawByPostId({
      post.id: <String, dynamic>{
        ..._canonicalPostWire(post),
        'workId': post.id,
        'workType': 'video',
        'workIdentity': 'work',
        'caption': post.body,
        'mediaItems': <Map<String, dynamic>>[
          <String, dynamic>{
            'kind': 'video',
            'url':
                'media/video/s/video-series-001/post/video-1/v1/episode-1.mp4',
            'accessMode': 'public',
            'durationMs': 125000,
          },
          <String, dynamic>{
            'kind': 'video',
            'url':
                'media/video/s/video-series-001/post/video-1/v1/episode-2.mp4',
            'accessMode': 'public',
            'durationMs': 125000,
          },
        ],
      },
    });

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: raw,
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
        overrides: [
          mediaDownloadCacheProvider.overrideWithValue(
            _NoopMediaDownloadCache(),
          ),
          workBrowserContentCommentFacetProvider.overrideWithValue(
            InMemoryContentCommentFacet(),
          ),
        ],
      ),
    );

    await _waitForVideoTimelineMeasurementFrame(tester);
    await tester.pump();
    final duration = find.byKey(
      const ValueKey<String>('works-video-transient-duration'),
    );
    expect(find.text('视频集 · 1/2'), findsOneWidget);
    expect(tester.widget<Opacity>(duration).opacity, 1);
    await tester.pump(const Duration(milliseconds: 5100));
    expect(tester.widget<Opacity>(duration).opacity, 0);

    final episodeStage = find.byKey(
      const ValueKey<String>('works-video-stage-video-1-0'),
    );
    expect(episodeStage, findsOneWidget);
    await tester.fling(episodeStage, const Offset(-700, 0), 1200);
    await tester.pump(const Duration(seconds: 1));
    for (
      var attempt = 0;
      attempt < 40 &&
          (find.text('视频集 · 2/2').evaluate().isEmpty ||
              duration.evaluate().isEmpty);
      attempt += 1
    ) {
      await tester.runAsync(() async {
        await Future<void>.delayed(Duration.zero);
      });
      await tester.pump(const Duration(milliseconds: 16));
      _consumeImageLoadExceptions(tester);
    }
    expect(find.text('视频集 · 2/2'), findsOneWidget);
    expect(duration, findsOneWidget);
    await tester.pump();
    expect(
      tester.widget<Opacity>(duration).opacity,
      1,
      reason: '切集后的新 chrome/session 必须重新开启一次窗口。',
    );
    await tester.pump(const Duration(milliseconds: 5100));
    expect(tester.widget<Opacity>(duration).opacity, 0);

    await tester.tap(find.byType(AppMediaCommentIcon));
    await _pumpSettledFrames(tester);
    expect(find.byKey(TestKeys.immersiveCommentSplitSheet), findsOneWidget);
    await tester.tap(find.byIcon(CupertinoIcons.xmark_circle_fill));
    await _pumpSettledFrames(tester);
    await _waitForVideoTimelineMeasurementFrame(tester);
    await tester.pump();
    expect(find.text('视频集 · 2/2'), findsOneWidget);
    expect(
      tester.widget<Opacity>(duration).opacity,
      0,
      reason: '评论分屏只是临时重建，必须恢复同一媒体身份且不能重启已结束的窗口。',
    );

    final secondEpisodeStage = find.byKey(
      const ValueKey<String>('works-video-stage-video-1-1'),
    );
    await tester.fling(secondEpisodeStage, const Offset(700, 0), 1200);
    await tester.pump(const Duration(seconds: 1));
    for (
      var attempt = 0;
      attempt < 40 &&
          (find.text('视频集 · 1/2').evaluate().isEmpty ||
              duration.evaluate().isEmpty);
      attempt += 1
    ) {
      await tester.runAsync(() async {
        await Future<void>.delayed(Duration.zero);
      });
      await tester.pump(const Duration(milliseconds: 16));
      _consumeImageLoadExceptions(tester);
    }
    expect(find.text('视频集 · 1/2'), findsOneWidget);
    await tester.pump();
    expect(
      tester.widget<Opacity>(duration).opacity,
      1,
      reason: '2→1 是真实切集，即使回到既有媒体身份也必须开启新的 entry-only 窗口。',
    );
  });

  testWidgets('分集列表重排按媒体身份保留当前集且不重启时长窗口', (tester) async {
    _installImmersiveVideoTestPlatform();
    final reordered = ValueNotifier<bool>(false);
    addTearDown(reordered.dispose);
    final post = _videoPost(width: 1920, height: 1080, coverUrl: '');

    Map<String, MediaViewerPostWireRow> rawFor(bool reverse) {
      final episodes = <Map<String, dynamic>>[
        <String, dynamic>{
          'kind': 'video',
          'url': 'media/video/s/video-series-001/post/video-1/v1/episode-1.mp4',
          'accessMode': 'public',
          'durationMs': 125000,
        },
        <String, dynamic>{
          'kind': 'video',
          'url': 'media/video/s/video-series-001/post/video-1/v1/episode-2.mp4',
          'accessMode': 'public',
          'durationMs': 125000,
        },
      ];
      return _viewerRawByPostId({
        post.id: <String, dynamic>{
          ..._canonicalPostWire(post),
          'workId': post.id,
          'workType': 'video',
          'workIdentity': 'work',
          'caption': post.body,
          'mediaItems': reverse ? episodes.reversed.toList() : episodes,
        },
      });
    }

    await tester.pumpWidget(
      ValueListenableBuilder<bool>(
        valueListenable: reordered,
        builder: (context, reverse, _) => _wrap(
          WorksImmersiveViewer(
            showWorksToolbar: true,
            showTopNavigation: false,
            externalPosts: [post],
            externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
            rawPostsById: rawFor(reverse),
            onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
            onAssistantTap: () {},
          ),
          overrides: [
            mediaDownloadCacheProvider.overrideWithValue(
              _NoopMediaDownloadCache(),
            ),
          ],
        ),
      ),
    );

    await _waitForVideoTimelineMeasurementFrame(tester);
    final firstEpisodeStage = find.byKey(
      const ValueKey<String>('works-video-stage-video-1-0'),
    );
    await tester.fling(firstEpisodeStage, const Offset(-700, 0), 1200);
    await tester.pump(const Duration(seconds: 1));
    expect(find.text('视频集 · 2/2'), findsOneWidget);
    final duration = find.byKey(
      const ValueKey<String>('works-video-transient-duration'),
    );
    await tester.pump(const Duration(milliseconds: 5100));
    expect(tester.widget<Opacity>(duration).opacity, 0);

    reordered.value = true;
    await tester.pump();
    for (
      var attempt = 0;
      attempt < 40 && find.text('视频集 · 1/2').evaluate().isEmpty;
      attempt += 1
    ) {
      await tester.runAsync(() async {
        await Future<void>.delayed(Duration.zero);
      });
      await tester.pump(const Duration(milliseconds: 16));
      _consumeImageLoadExceptions(tester);
    }
    expect(
      find.text('视频集 · 1/2'),
      findsOneWidget,
      reason: '原第 2 集重排到索引 0 后应按 delivery identity 保持为当前媒体。',
    );
    await _waitForVideoTimelineMeasurementFrame(tester);
    await tester.pump();
    expect(
      tester.widget<Opacity>(duration).opacity,
      0,
      reason: '同一媒体仅发生列表重排，不属于切集，不能重启已结束的五秒窗口。',
    );
    expect(tester.takeException(), isNull);
  });

  test('视频 bottom chrome 单轨装配且不恢复左侧播放按钮', () {
    final controlsSource = File(
      'lib/service/content_service/media/media_asset/presentation/works_immersive_viewer_controls.dart',
    ).readAsStringSync();
    final chromeSource = File(
      'lib/service/content_service/media/media_asset/presentation/works_immersive_viewer_video_chrome.dart',
    ).readAsStringSync();
    final canvasSource = File(
      'lib/service/content_service/media/media_asset/presentation/works_immersive_viewer_canvas.dart',
    ).readAsStringSync();

    expect(controlsSource, isNot(contains('works-video-play-toggle')));
    expect(controlsSource, contains('VideoPlaybackTimeline('));
    expect(
      chromeSource,
      contains('ImmersiveEngagementBar.reservedHeight(context)'),
    );
    expect(chromeSource, contains('footer: widget.intersection'));
    expect(chromeSource, contains('_collidesWithCaption'));
    expect(
      chromeSource,
      contains('widget.durationWindowActive && _durationVisible'),
    );
    expect(
      File(
        'lib/service/content_service/media/media_asset/presentation/works_immersive_viewer_lifecycle.dart',
      ).readAsStringSync(),
      contains('_videoDurationWindowTimer = Timer(const Duration(seconds: 5)'),
    );
    expect(chromeSource, contains('required this.intersection'));
    expect(chromeSource, contains('scrubTimeVisible: _scrubTimeVisible'));
    expect(canvasSource, contains('VideoPlaybackCenterPlayGlyph()'));
  });

  testWidgets('photo post 在 iPad 宽屏下顶部说明底部对齐到同一 media rail', (tester) async {
    tester.view.devicePixelRatio = 1.0;
    tester.view.physicalSize = const Size(1024, 1366);
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    final post = _photoPost(
      imageUrls: const ['media/image/s/fixture/photo-wide.jpg'],
    );
    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: <String, dynamic>{
              'postId': post.id,
              'type': 'photo',
              'contentType': 'image',
              'authorId': post.authorId,
              'authorDisplayName': post.displayName,
              'authorAvatarUrl': post.avatarUrl,
              'title': '宽屏标题',
              'body': '宽屏说明正文',
              'coverUrl': post.coverUrl,
              'imageUrls': post.imageUrls,
            },
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await _pumpImmersiveViewerFirstFrames(tester);

    final viewerRect = tester.getRect(find.byType(WorksImmersiveViewer));
    final topRailRect = tester.getRect(
      find.byKey(const ValueKey<String>('works-top-rail')),
    );
    final captionRailRect = tester.getRect(
      find.byKey(const ValueKey<String>('works-caption-rail')),
    );
    final bottomRailRect = tester.getRect(
      find.byKey(const ValueKey('immersive-engagement-rail')),
    );

    expect((captionRailRect.left - topRailRect.left).abs(), lessThan(1));
    expect((captionRailRect.right - topRailRect.right).abs(), lessThan(1));
    expect((bottomRailRect.left - topRailRect.left).abs(), lessThan(1));
    expect((bottomRailRect.right - topRailRect.right).abs(), lessThan(1));

    final barContext = tester.element(find.byType(ImmersiveEngagementBar));
    final expectedBottomInset = ImmersiveViewerLayout.horizontalPadding(
      barContext,
      layoutSpec: ImmersiveViewerStageLayoutSpec.mediaStage,
    );
    expect((bottomRailRect.left - expectedBottomInset).abs(), lessThan(1));
    expect(
      (viewerRect.right - bottomRailRect.right - expectedBottomInset).abs(),
      lessThan(1),
    );
  });

  testWidgets('首帧帖子延后就绪时 follow 按钮随工具栏常驻可见且无定时', (tester) async {
    tester.view.devicePixelRatio = 1.0;
    tester.view.physicalSize = const Size(390, 844);
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    final post = _photoPost();
    await tester.pumpWidget(
      _wrap(
        _DeferredPostWorksViewer(
          post: post,
          revealDelay: const Duration(milliseconds: 50),
          rawRow: <String, dynamic>{
            'postId': post.id,
            'type': 'photo',
            'contentType': 'image',
            'authorId': post.authorId,
            'authorDisplayName': post.displayName,
            'authorAvatarUrl': post.avatarUrl,
            'title': '延后加载标题',
            'body': '延后加载正文',
            'coverUrl': post.coverUrl,
            'imageUrls': post.imageUrls,
          },
        ),
      ),
    );

    await tester.pump();
    await tester.pump(const Duration(milliseconds: 60));
    _consumeImageLoadExceptions(tester);
    await tester.pump();

    final followLane = find.byKey(const ValueKey('immersive-follow-lane'));
    expect(find.byType(ImmersiveEngagementBar), findsOneWidget);
    // 关注按钮随工具栏常驻，不再有出现定时。
    expect(tester.getSize(followLane).width, greaterThan(0));
    expect(
      find.byKey(const ValueKey('immersive-follow-button')),
      findsOneWidget,
    );
  });

  testWidgets('photo caption 与底部工具栏顶部保持固定间距', (tester) async {
    tester.view.devicePixelRatio = 1.0;
    tester.view.physicalSize = const Size(390, 844);
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    final post = _photoPost(
      imageUrls: const ['media/image/s/fixture/photo-gap.jpg'],
    );
    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: <String, dynamic>{
              'postId': post.id,
              'type': 'photo',
              'contentType': 'image',
              'authorId': post.authorId,
              'authorDisplayName': post.displayName,
              'authorAvatarUrl': post.avatarUrl,
              'title': '贴底标题',
              'body': '贴底说明正文',
              'coverUrl': post.coverUrl,
              'imageUrls': post.imageUrls,
            },
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await _pumpImmersiveViewerFirstFrames(tester);

    final captionRect = tester.getRect(
      find.byKey(const ValueKey<String>('works-caption-rail')),
    );
    final toolbarRect = tester.getRect(find.byType(ImmersiveEngagementBar));

    expect(
      toolbarRect.top - captionRect.bottom,
      moreOrLessEquals(AppSpacing.containerSm, epsilon: 1),
    );
  });

  testWidgets('分页书内容区与底部工具栏保持统一净空', (tester) async {
    tester.view.devicePixelRatio = 1.0;
    tester.view.physicalSize = const Size(390, 844);
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    final post = _articlePost();
    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: _articleMarkdownRaw(post, _multiPageArticleMarkdown(post)),
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await _pumpImmersiveViewerFirstFrames(tester);

    final bookRect = tester.getRect(find.byType(ArticleReadOnlyBookDeck));
    final toolbarRect = tester.getRect(find.byType(ImmersiveEngagementBar));
    final screenWidth =
        tester.view.physicalSize.width / tester.view.devicePixelRatio;

    expect(
      toolbarRect.top - bookRect.bottom,
      moreOrLessEquals(AppSpacing.containerMd, epsilon: 1),
    );
    expect(bookRect.left, closeTo(0, 1));
    expect(bookRect.top, closeTo(0, 1));
    expect(bookRect.right, closeTo(screenWidth, 1));
  });

  testWidgets('text-only moment 使用文本画布展示 title/body', (tester) async {
    final post = _textMoment();
    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: <String, dynamic>{
              'postId': post.id,
              'type': 'micro',
              'contentType': 'micro',
              'authorId': post.authorId,
              'authorDisplayName': post.displayName,
              'authorAvatarUrl': post.avatarUrl,
              'title': '临时改地点提醒',
              'body': post.body,
            },
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await _pumpImmersiveViewerFirstFrames(tester);

    expect(find.text('临时改地点提醒'), findsOneWidget);
    expect(find.textContaining('今天风有点大'), findsOneWidget);
  });

  testWidgets('交集以具象化句子呈现在底部并可点击弹出推荐解释详情', (tester) async {
    final post = _textMoment(
      intersectionReasons: <IntersectionReason>[
        _displayableIntersectionReason(
          dimension: 'identity',
          primaryText: '联系人林清越赞过和评论过',
          totalPointCount: 2,
          source: 'identity',
        ),
      ],
    );
    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: <String, dynamic>{
              'postId': post.id,
              'type': 'micro',
              'contentType': 'micro',
              'authorId': post.authorId,
              'authorDisplayName': post.displayName,
              'authorAvatarUrl': post.avatarUrl,
              'title': '临时改地点提醒',
              'body': post.body,
            },
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await _pumpSettledFrames(tester);

    // 视频书：交集作为内容区底部统一具象化句子，不回退到「N 个交集」摘要。
    expect(
      find.byKey(const ValueKey<String>('works-caption-intersection-reason')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('immersive-intersection-statement')),
      findsOneWidget,
    );
    expect(
      find.text(DiscoveryFeedText.intersectionEntrySummary(1)),
      findsNothing,
    );
    expect(find.text('联系人林清越赞过和评论过'), findsOneWidget);

    final intersectionRect = tester.getRect(
      find.byKey(const ValueKey<String>('works-caption-intersection-reason')),
    );
    final textRailRect = tester.getRect(
      find.byKey(const ValueKey<String>('works-text-stage-rail')),
    );
    final toolbarRect = tester.getRect(find.byType(ImmersiveEngagementBar));
    expect(
      intersectionRect.top,
      greaterThan(textRailRect.bottom),
      reason: '交集句应独立位于内容文字下方，而不是塞回正文卡片或工具栏。',
    );
    expect(
      toolbarRect.top - intersectionRect.bottom,
      moreOrLessEquals(AppSpacing.intraGroupXs, epsilon: 1),
      reason: '交集句应作为内容区最底部一行，贴近但不进入底部工具栏。',
    );

    // 点击降级整句弹出交集详情面板，展示完整 displayText。
    await tester.tap(find.text('联系人林清越赞过和评论过'));
    await _pumpSettledFrames(tester);
    expect(
      find.byKey(const ValueKey<String>('works-intersection-detail-sheet')),
      findsOneWidget,
    );
    expect(find.text('联系人林清越赞过和评论过'), findsNWidgets(2));
    // 详情 sheet 为「为什么推荐给你」+ ✓ 证据列表。
    expect(
      find.text(DiscoveryFeedText.intersectionDetailTitle),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('works-intersection-check')),
      findsOneWidget,
    );
  });

  testWidgets('视频书交集代表人 span 点击进入用户并透传 feedRequestId 归因', (tester) async {
    final behaviorRepo = RecordingContentBehaviorRepository();
    final tracker = ContentBehaviorTracker(
      reporter: behaviorRepo,
      maxBatchSize: 1,
      enablePeriodicFlush: false,
    );
    addTearDown(tracker.dispose);

    final post = _textMoment(
      intersectionReasons: <IntersectionReason>[
        _displayableIntersectionReason(
          intersectionId: 'ix_works_span',
          dimension: 'relationship',
          primaryText: '联系人林清越收藏过',
          primarySpans: <IntersectionTextSpan>[
            _plain('联系人'),
            IntersectionTextSpan(
              text: '林清越',
              role: 'object',
              target: IntersectionTarget(
                objectType: 'user',
                objectId: 'u_lin',
                objectKind: 'person',
                routeId: 'userProfile',
              ),
            ),
            _plain('收藏过'),
          ],
          totalPointCount: 1,
          source: 'sharedFollowees',
          tagRefs: const <String>['relationship/sharedFollowees'],
          intersectionClass: 'fact',
          pointSummarySnapshotId: 'ev_works_span',
        ),
      ],
    );

    await tester.pumpWidget(
      _wrapWithRouter(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          feedRequestId: 'feed-request-works-span',
          rawPostsById: _viewerRawByPostId({
            post.id: <String, dynamic>{
              'postId': post.id,
              'type': 'micro',
              'contentType': 'micro',
              'authorId': post.authorId,
              'authorDisplayName': post.displayName,
              'authorAvatarUrl': post.avatarUrl,
              'title': '临时改地点提醒',
              'body': post.body,
            },
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
        overrides: [contentBehaviorTrackerProvider.overrideWithValue(tracker)],
      ),
    );
    await _pumpSettledFrames(tester);

    final richTextFinder = find.descendant(
      of: find.byKey(
        const ValueKey<String>('works-caption-intersection-reason'),
      ),
      matching: find.byType(RichText),
    );
    await _tapRichTextSubstring(tester, richTextFinder, '林清越');
    await _pumpSettledFrames(tester);
    await tracker.flush();

    final clicks = behaviorRepo.recorded
        .where((event) => event.action == BehaviorEventType.tagClick)
        .toList(growable: false);
    expect(clicks, hasLength(1));
    final click = clicks.single;
    expect(click.feedRequestId, 'feed-request-works-span');
    expect(click.referralSource, ReferralSource.organicFeed);
    expect(click.intersectionId, 'ix_works_span');
    expect(click.intersectionSourceRef, 'sharedFollowees');
    expect(click.intersectionEvidenceId, 'ev_works_span');
    expect(click.intersectionClass, 'fact');
    expect(
      AppRoutePaths.userProfile(userHandle: 'u_lin'),
      startsWith('/user/u_lin'),
    );
  });

  testWidgets('视频书交集显式对象 span 点击进入主页并透传归因', (tester) async {
    final behaviorRepo = RecordingContentBehaviorRepository();
    final tracker = ContentBehaviorTracker(
      reporter: behaviorRepo,
      maxBatchSize: 1,
      enablePeriodicFlush: false,
    );
    addTearDown(tracker.dispose);

    final post = _textMoment(
      intersectionReasons: <IntersectionReason>[
        _displayableIntersectionReason(
          intersectionId: 'ix_works_fallback',
          dimension: 'place',
          primaryText: '联系人林清越收藏过「剑门关」',
          displayBinding: 'explicit_link',
          objectKind: 'place',
          actionTargetId: 'hp_jianmen',
          primarySpans: <IntersectionTextSpan>[
            _plain('联系人'),
            IntersectionTextSpan(
              text: '林清越',
              role: 'object',
              target: _intersectionTargetFor(
                objectKind: 'person',
                objectId: 'u_lin',
              ),
            ),
            _plain('收藏过「'),
            IntersectionTextSpan(
              text: '剑门关',
              role: 'object',
              target: _intersectionTargetFor(
                objectKind: 'place',
                objectId: 'hp_jianmen',
              ),
            ),
            _plain('」'),
          ],
          totalPointCount: 2,
          source: 'coLikedEntity',
          tagRefs: const <String>['place/jianmen'],
          intersectionClass: 'fact',
          pointSummarySnapshotId: 'ev_works_fallback',
          sampleVisuals: <IntersectionVisual>[
            IntersectionVisual(
              assetKind: 'coverImage',
              imageUrl: 'media/image/s/homepage/hp_jianmen/cover.jpg',
              displayName: '剑门关',
              target: IntersectionTarget(
                objectType: 'homepage',
                objectId: 'hp_jianmen',
                objectKind: 'place',
                routeId: 'homepageDetail',
              ),
            ),
          ],
        ),
      ],
    );

    await tester.pumpWidget(
      _wrapWithRouter(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          feedRequestId: 'feed-request-works-object',
          rawPostsById: _viewerRawByPostId({
            post.id: <String, dynamic>{
              'postId': post.id,
              'type': 'micro',
              'contentType': 'micro',
              'authorId': post.authorId,
              'authorDisplayName': post.displayName,
              'authorAvatarUrl': post.avatarUrl,
              'title': '临时改地点提醒',
              'body': post.body,
            },
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
        overrides: [contentBehaviorTrackerProvider.overrideWithValue(tracker)],
      ),
    );
    await _pumpSettledFrames(tester);

    final richTextFinder = find.descendant(
      of: find.byKey(
        const ValueKey<String>('works-caption-intersection-reason'),
      ),
      matching: find.byType(RichText),
    );
    await _tapRichTextSubstring(tester, richTextFinder, '剑门关');
    await _pumpSettledFrames(tester);
    await tracker.flush();

    final clicks = behaviorRepo.recorded
        .where((event) => event.action == BehaviorEventType.tagClick)
        .toList(growable: false);
    expect(clicks, hasLength(1));
    final click = clicks.single;
    expect(click.feedRequestId, 'feed-request-works-object');
    expect(click.intersectionSourceRef, 'coLikedEntity');
    expect(click.intersectionEvidenceId, 'ev_works_fallback');
    expect(click.intersectionDimension, 'place');
    expect(
      AppRoutePaths.homepageDetail(id: 'hp_jianmen'),
      startsWith('/homepages/hp_jianmen'),
    );
  });

  testWidgets('视频书交集显式行动对象 span 点击进入对象并透传归因', (tester) async {
    final behaviorRepo = RecordingContentBehaviorRepository();
    final tracker = ContentBehaviorTracker(
      reporter: behaviorRepo,
      maxBatchSize: 1,
      enablePeriodicFlush: false,
    );
    addTearDown(tracker.dispose);

    final post = _textMoment(
      intersectionReasons: <IntersectionReason>[
        _displayableIntersectionReason(
          intersectionId: 'ix_works_action_target',
          dimension: 'location',
          primaryText: '联系人林清越也想去「滇池路线」',
          displayBinding: 'explicit_link',
          primarySpans: <IntersectionTextSpan>[
            _plain('联系人'),
            IntersectionTextSpan(
              text: '林清越',
              role: 'object',
              target: _intersectionTargetFor(
                objectKind: 'person',
                objectId: 'u_lin',
              ),
            ),
            _plain('也想去「'),
            IntersectionTextSpan(
              text: '滇池路线',
              role: 'object',
              target: _intersectionTargetFor(
                objectKind: 'route',
                objectId: 'hp_route_dianchi',
              ),
            ),
            _plain('」'),
          ],
          totalPointCount: 3,
          source: 'coWishlistedEntity',
          tagRefs: const <String>['location/wishlist'],
          intersectionClass: 'fact',
          pointSummarySnapshotId: 'ev_works_action_target',
          objectKind: 'route',
          actionTargetId: 'hp_route_dianchi',
        ),
      ],
    );

    await tester.pumpWidget(
      _wrapWithRouter(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          feedRequestId: 'feed-request-works-action',
          rawPostsById: _viewerRawByPostId({
            post.id: <String, dynamic>{
              'postId': post.id,
              'type': 'micro',
              'contentType': 'micro',
              'authorId': post.authorId,
              'authorDisplayName': post.displayName,
              'authorAvatarUrl': post.avatarUrl,
              'title': '临时改地点提醒',
              'body': post.body,
            },
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
        overrides: [contentBehaviorTrackerProvider.overrideWithValue(tracker)],
      ),
    );
    await _pumpSettledFrames(tester);

    final richTextFinder = find.descendant(
      of: find.byKey(
        const ValueKey<String>('works-caption-intersection-reason'),
      ),
      matching: find.byType(RichText),
    );
    await _tapRichTextSubstring(tester, richTextFinder, '滇池路线');
    await _pumpSettledFrames(tester);
    await tracker.flush();

    final clicks = behaviorRepo.recorded
        .where((event) => event.action == BehaviorEventType.tagClick)
        .toList(growable: false);
    expect(clicks, hasLength(1));
    final click = clicks.single;
    expect(click.contentId, 'hp_route_dianchi');
    expect(click.contentType, 'route');
    expect(click.feedRequestId, 'feed-request-works-action');
    expect(click.intersectionId, 'ix_works_action_target');
    expect(click.intersectionSourceRef, 'coWishlistedEntity');
    expect(click.intersectionEvidenceId, 'ev_works_action_target');
    expect(
      AppRoutePaths.homepageDetail(id: 'hp_route_dianchi'),
      startsWith('/homepages/hp_route_dianchi'),
    );
  });

  testWidgets('text-only moment 在 iPad 宽屏下顶部内容底部共享 text rail', (tester) async {
    tester.view.devicePixelRatio = 1.0;
    tester.view.physicalSize = const Size(1024, 1366);
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });

    final post = _textMoment();
    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: <String, dynamic>{
              'postId': post.id,
              'type': 'micro',
              'contentType': 'micro',
              'authorId': post.authorId,
              'authorDisplayName': post.displayName,
              'authorAvatarUrl': post.avatarUrl,
              'title': '临时改地点提醒',
              'body': post.body,
            },
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await _pumpImmersiveViewerFirstFrames(tester);

    final viewerRect = tester.getRect(find.byType(WorksImmersiveViewer));
    final topRailRect = tester.getRect(
      find.byKey(const ValueKey<String>('works-top-rail')),
    );
    final textRailRect = tester.getRect(
      find.byKey(const ValueKey<String>('works-text-stage-rail')),
    );
    final bottomRailRect = tester.getRect(
      find.byKey(const ValueKey('immersive-engagement-rail')),
    );
    final expectedRailWidth = (viewerRect.width - AppSpacing.containerMd * 2)
        .clamp(0.0, AppSpacing.feedMaxContentWidth);
    final expectedSideMargin = (viewerRect.width - expectedRailWidth) / 2;

    expect((topRailRect.left - expectedSideMargin).abs(), lessThan(1));
    expect((textRailRect.left - expectedSideMargin).abs(), lessThan(1));
    expect((bottomRailRect.left - expectedSideMargin).abs(), lessThan(1));
    expect(
      (viewerRect.right - topRailRect.right - expectedSideMargin).abs(),
      lessThan(1),
    );
    expect(
      (viewerRect.right - textRailRect.right - expectedSideMargin).abs(),
      lessThan(1),
    );
    expect(
      (viewerRect.right - bottomRailRect.right - expectedSideMargin).abs(),
      lessThan(1),
    );
  });

  testWidgets('canonical viewer 经 typed media facet 加载当前原图', (tester) async {
    final post = _photoPost();
    // 原图换签已收敛到 SignedMediaDeliveryCoordinator，短签校验（https +
    // sign + t）随之生效，夹具必须给出真实签名形态的交付地址。
    final originalUrl = Uri.parse(
      'https://cdn.example.com/original/photo-1.jpg?sign=sig-original&t=1893456300',
    );
    final mediaFacet = _RecordingContentMediaFacet(originalUrl);
    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: <ContentPostViewData>[post],
          externalPostViews: <ContentSurfaceView>[
            ContentSurfaceViewMapper.fromDto(post),
          ],
          rawPostsById: _viewerRawByPostId(<String, Map<String, dynamic>>{
            post.id: <String, dynamic>{
              'workId': post.id,
              'workType': 'image',
              'workIdentity': 'work',
              'imageUrls': post.imageUrls,
              'mediaAssetId': 'asset-photo-1',
              'mediaAssetVersion': 1,
              'mediaItems': <Map<String, dynamic>>[
                <String, dynamic>{
                  'kind': 'image',
                  'url': post.imageUrls.single,
                  'mediaAssetId': 'asset-photo-1',
                  'mediaAssetVersion': 1,
                },
              ],
            },
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
        overrides: [
          authSessionControllerProvider.overrideWith(
            _AuthenticatedViewerSession.new,
          ),
          workBrowserContentMediaFacetProvider.overrideWithValue(mediaFacet),
        ],
      ),
    );
    await _pumpImmersiveViewerFirstFrames(tester);

    await tester.tap(find.byIcon(CupertinoIcons.ellipsis));
    await _pumpSettledFrames(tester);
    expect(find.text(ContentText.viewOriginal), findsOneWidget);

    await tester.tap(find.text(ContentText.viewOriginal));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 32));
    _consumeImageLoadExceptions(tester);

    expect(mediaFacet.requestedMediaIds, <String>['asset-photo-1']);
    expect(
      tester
          .widget<ImageBookCanvas>(find.byType(ImageBookCanvas))
          .deliveries
          .map((binding) => binding.publicUrl)
          .toList(growable: false),
      <String>[originalUrl.toString()],
    );
    expect(find.text(MediaText.imageOriginalLoaded), findsOneWidget);
  });

  testWidgets('沉浸举报登录成功后续接原 post 且关闭登录走安全首页', (tester) async {
    AuthGate.resetDebounce();
    await tester.binding.setSurfaceSize(const Size(375, 812));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final post = _photoPost();
    final reportWriter = _RecordingContentReportWriter();
    final reporter = RecordingContentBehaviorRepository();
    final behaviorTracker = ContentBehaviorTracker(
      reporter: reporter,
      enablePeriodicFlush: false,
    );
    final engagementTracker = ContentEngagementTracker(reporter: reporter);
    addTearDown(behaviorTracker.dispose);
    addTearDown(engagementTracker.dispose);
    final container = _testProviderContainer(
      overrides: [
        ...mockContentFacetOverrides(store: InMemoryContentPostStore()),
        authSessionControllerProvider.overrideWith(_FlippableViewerSession.new),
        workBrowserContentReportCommandWriterProvider.overrideWithValue(
          reportWriter,
        ),
        contentBehaviorTrackerProvider.overrideWithValue(behaviorTracker),
        contentEngagementTrackerProvider.overrideWithValue(engagementTracker),
      ],
    );
    addTearDown(container.dispose);
    final router = GoRouter(
      routes: <RouteBase>[
        GoRoute(
          path: '/',
          builder: (context, state) => Scaffold(
            body: WorksImmersiveViewer(
              showWorksToolbar: true,
              showTopNavigation: false,
              externalPosts: <ContentPostViewData>[post],
              externalPostViews: <ContentSurfaceView>[
                ContentSurfaceViewMapper.fromDto(post),
              ],
              onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
              onAssistantTap: () {},
            ),
          ),
        ),
        GoRoute(
          path: AppRoutePaths.loginPathTemplate,
          builder: (context, state) => const Scaffold(
            key: ValueKey<String>('viewer-report-login'),
            body: SizedBox.shrink(),
          ),
        ),
      ],
    );
    addTearDown(router.dispose);
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: ScreenUtilInit(
          designSize: const Size(375, 812),
          builder: (context, _) =>
              MaterialApp.router(theme: ThemeData.dark(), routerConfig: router),
        ),
      ),
    );
    await _pumpImmersiveViewerFirstFrames(tester);

    await tester.tap(find.byIcon(CupertinoIcons.ellipsis));
    await _pumpSettledFrames(tester);
    await tester.ensureVisible(find.text(ContentText.report));
    await tester.pump();
    await tester.tap(find.text(ContentText.report));
    final selectedReason = find.text(ContentText.profileReportReasonSpam);
    for (
      var attempt = 0;
      attempt < 20 && selectedReason.evaluate().isEmpty;
      attempt += 1
    ) {
      await tester.pump(const Duration(milliseconds: 50));
    }
    expect(selectedReason, findsOneWidget);
    await tester.pump(const Duration(milliseconds: 300));
    await tester.tap(selectedReason);
    final loginPage = find.byKey(const ValueKey<String>('viewer-report-login'));
    for (
      var attempt = 0;
      attempt < 20 && loginPage.evaluate().isEmpty;
      attempt += 1
    ) {
      await tester.pump(const Duration(milliseconds: 50));
    }

    expect(loginPage, findsOneWidget);
    expect(reportWriter.commands, isEmpty);
    final pending = container.read(authContinuationProvider);
    expect(pending, isA<SubmitContentReportContinuation>());
    final reportContinuation = pending! as SubmitContentReportContinuation;
    expect(reportContinuation.postId, post.id);
    expect(reportContinuation.reason, ReportReason.spam);
    expect(
      GoRouterState.of(
        tester.element(
          find.byKey(const ValueKey<String>('viewer-report-login')),
        ),
      ).uri.queryParameters[loginGuestDismissPopQueryParam],
      LoginDismissPolicy.safeFallback.name,
    );

    (container.read(
      authSessionControllerProvider.notifier,
    ) as _FlippableViewerSession).loginNow();
    router.pop();
    await _pumpSettledFrames(tester);
    await tester.pump();

    expect(reportWriter.commands, hasLength(1));
    expect(reportWriter.commands.single.targetId, post.id);
    expect(container.read(authContinuationProvider), isNull);
  });

  test('internal feed bridge 保留 blockingError 与 canonical emptyReason', () {
    final blockingError = StateError('service unavailable');
    final container = ProviderContainer(
      overrides: <Override>[
        discoveryFeedProvider('photo').overrideWithValue(
          const AsyncData<DiscoveryFeedState>(
            DiscoveryFeedState(
              emptyReason: ContentFeedEmptyReason.noActiveRelease,
            ),
          ),
        ),
        discoveryFeedProvider('video').overrideWithValue(
          AsyncData<DiscoveryFeedState>(
            DiscoveryFeedState(blockingError: blockingError),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);

    expect(
      container.read(worksViewerFeedProvider('photo')).value?.emptyReason,
      ContentFeedEmptyReason.noActiveRelease,
    );
    expect(
      container.read(worksViewerFeedProvider('video')).value?.blockingError,
      same(blockingError),
    );
  });

  testWidgets('internal feed 加载态明确呈现且不退化为空黑页', (tester) async {
    await tester.pumpWidget(
      _wrap(
        _internalWorksViewer(),
        overrides: _worksInternalFeedOverrides(
          photo: const AsyncLoading<WorksViewerFeedSnapshot>(),
          video: const AsyncLoading<WorksViewerFeedSnapshot>(),
          article: const AsyncLoading<WorksViewerFeedSnapshot>(),
        ),
      ),
    );
    await tester.pump();

    expect(
      find.byKey(const ValueKey<String>('works-internal-feed-loading')),
      findsOneWidget,
    );
    expect(find.byType(AppRequestFeedback), findsOneWidget);
    expect(
      find.byKey(const ValueKey<String>('works-internal-feed-error')),
      findsNothing,
    );
  });

  testWidgets('internal feed 无 active release 呈现 canonical empty 且不显示 Retry', (
    tester,
  ) async {
    final canonicalEmpty = AsyncData<WorksViewerFeedSnapshot>(
      _worksFeedSnapshot(emptyReason: ContentFeedEmptyReason.noActiveRelease),
    );
    await tester.pumpWidget(
      _wrap(
        _internalWorksViewer(),
        overrides: _worksInternalFeedOverrides(
          photo: canonicalEmpty,
          video: canonicalEmpty,
          article: canonicalEmpty,
        ),
      ),
    );
    await tester.pump();

    expect(
      find.byKey(
        const ValueKey<String>('works-internal-feed-empty-no_active_release'),
      ),
      findsOneWidget,
    );
    expect(find.text(DiscoveryText.webPcFeedEmpty), findsOneWidget);
    expect(find.byType(AppRequestFeedback), findsNothing);
    expect(
      find.byKey(const ValueKey<String>('works-internal-feed-empty-retry')),
      findsNothing,
    );
    expect(find.text(ContentText.tryAgain), findsNothing);
  });

  testWidgets('internal feed 服务离线呈现 blocking error 且重试三路', (tester) async {
    final loadedChannels = <String>[];
    final offline = StateError('offline transport detail must stay hidden');
    final canonicalEmpty = AsyncData<WorksViewerFeedSnapshot>(
      _worksFeedSnapshot(emptyReason: ContentFeedEmptyReason.noEligibleContent),
    );
    await tester.pumpWidget(
      _wrap(
        _internalWorksViewer(),
        overrides: _worksInternalFeedOverrides(
          photo: AsyncError<WorksViewerFeedSnapshot>(
            offline,
            StackTrace.current,
          ),
          video: canonicalEmpty,
          article: canonicalEmpty,
          loadedChannels: loadedChannels,
          loadTerminals: const <String, DiscoveryFeedLoadTerminal>{
            'photo': DiscoveryFeedLoadTerminal.stillBlocked,
            'video': DiscoveryFeedLoadTerminal.stillBlocked,
            'article': DiscoveryFeedLoadTerminal.stillBlocked,
          },
        ),
      ),
    );
    await tester.pump();

    final errorFinder = find.byKey(
      const ValueKey<String>('works-internal-feed-error'),
    );
    expect(errorFinder, findsOneWidget);
    expect(find.textContaining('offline transport detail'), findsNothing);
    expect(find.byType(AppRequestFeedback), findsNothing);

    final errorState = tester.widget<AppPageErrorState>(errorFinder);
    expect(
      errorState.semantic.primaryAction?.type,
      anyOf(UiErrorActionType.retry, UiErrorActionType.resubmit),
    );
    final loadCountBeforeRetry = loadedChannels.length;
    final recoveryOutcome = await errorState.onRecovery!(
      errorState.semantic.primaryAction!,
    );
    expect(recoveryOutcome, UiRecoveryOutcome.stillBlocked);
    expect(loadedChannels.length, loadCountBeforeRetry + 3);
  });

  testWidgets('internal feed 重叠 Retry 只让最新 recovery generation 收口', (
    tester,
  ) async {
    final loadGate = Completer<void>();
    final offline = StateError('offline transport detail must stay hidden');
    final canonicalEmpty = AsyncData<WorksViewerFeedSnapshot>(
      _worksFeedSnapshot(emptyReason: ContentFeedEmptyReason.noEligibleContent),
    );
    await tester.pumpWidget(
      _wrap(
        _internalWorksViewer(),
        overrides: _worksInternalFeedOverrides(
          photo: AsyncError<WorksViewerFeedSnapshot>(
            offline,
            StackTrace.current,
          ),
          video: canonicalEmpty,
          article: canonicalEmpty,
          loadTerminals: const <String, DiscoveryFeedLoadTerminal>{
            'photo': DiscoveryFeedLoadTerminal.stillBlocked,
            'video': DiscoveryFeedLoadTerminal.stillBlocked,
            'article': DiscoveryFeedLoadTerminal.stillBlocked,
          },
          loadGate: loadGate.future,
        ),
      ),
    );
    await tester.pump();

    final errorState = tester.widget<AppPageErrorState>(
      find.byKey(const ValueKey<String>('works-internal-feed-error')),
    );
    final action = errorState.semantic.primaryAction!;
    final firstRecovery = errorState.onRecovery!(action);
    final latestRecovery = errorState.onRecovery!(action);
    loadGate.complete();
    await tester.pump();

    expect(await firstRecovery, UiRecoveryOutcome.superseded);
    expect(await latestRecovery, UiRecoveryOutcome.stillBlocked);
  });

  testWidgets('internal feed partial channel 有内容时优先进入可用终态', (tester) async {
    final post = _photoPost();
    await tester.pumpWidget(
      _wrap(
        _internalWorksViewer(),
        overrides: _worksInternalFeedOverrides(
          photo: AsyncData<WorksViewerFeedSnapshot>(
            _worksFeedSnapshot(items: <ContentPostViewData>[post]),
          ),
          video: AsyncError<WorksViewerFeedSnapshot>(
            StateError('video channel unavailable'),
            StackTrace.current,
          ),
          article: const AsyncLoading<WorksViewerFeedSnapshot>(),
        ),
      ),
    );
    await _pumpImmersiveViewerFirstFrames(tester);

    expect(
      find.byKey(ValueKey<String>('works-status-content-canvas-${post.id}')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('works-internal-feed-loading')),
      findsNothing,
    );
    expect(
      find.byKey(const ValueKey<String>('works-internal-feed-error')),
      findsNothing,
    );
  });

  testWidgets('internal feed 有内容时分页失败只呈现 append footer', (tester) async {
    final post = _photoPost();
    await tester.pumpWidget(
      _wrap(
        _internalWorksViewer(),
        overrides: _worksInternalFeedOverrides(
          photo: AsyncData<WorksViewerFeedSnapshot>(
            _worksFeedSnapshot(
              items: <ContentPostViewData>[post],
              hasMore: true,
              appendError: StateError('append unavailable'),
            ),
          ),
          video: AsyncData<WorksViewerFeedSnapshot>(
            _worksFeedSnapshot(
              emptyReason: ContentFeedEmptyReason.noEligibleContent,
            ),
          ),
          article: AsyncData<WorksViewerFeedSnapshot>(
            _worksFeedSnapshot(
              emptyReason: ContentFeedEmptyReason.noEligibleContent,
            ),
          ),
        ),
      ),
    );
    await _pumpImmersiveViewerFirstFrames(tester);

    expect(
      find.byKey(ValueKey<String>('works-status-content-canvas-${post.id}')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('works-internal-feed-error')),
      findsNothing,
    );

    await tester.drag(
      find.byKey(TestKeys.worksImmersivePager),
      const Offset(0, -600),
    );
    await tester.pumpAndSettle();
    expect(
      find.byKey(const ValueKey<String>('works-load-more-retry')),
      findsOneWidget,
    );
  });

  testWidgets('external 空内容六秒后提供可退出状态而非永久 spinner', (tester) async {
    var dismissed = false;
    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: const <ContentPostViewData>[],
          externalPostViews: const <ContentSurfaceView>[],
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
          onDismissed: (_) => dismissed = true,
        ),
      ),
    );
    await tester.pump();

    expect(find.byType(AppRequestFeedback), findsOneWidget);
    expect(
      find.byKey(const ValueKey<String>('works-external-empty-exit')),
      findsNothing,
    );

    await tester.pump(const Duration(seconds: 6));
    await tester.pump();
    expect(
      find.byKey(const ValueKey<String>('works-external-empty-exit')),
      findsOneWidget,
    );
    expect(
      find.text(SearchText.recoveryContentUnavailableTitle),
      findsOneWidget,
    );

    await tester.tap(find.text(SearchText.recoveryReturnAction));
    await tester.pump();
    expect(dismissed, isTrue);
  });

  testWidgets('canonical viewer 最后一条内容仅结算一次 dwell 并保留入口归因', (tester) async {
    final reporter = RecordingContentBehaviorRepository();
    final behaviorTracker = ContentBehaviorTracker(
      reporter: reporter,
      maxBatchSize: 1,
      enablePeriodicFlush: false,
    );
    final engagementTracker = ContentEngagementTracker(reporter: reporter);
    final post = _photoPost();

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: <ContentPostViewData>[post],
          externalPostViews: <ContentSurfaceView>[
            ContentSurfaceViewMapper.fromDto(post),
          ],
          referralSource: ReferralSource.friendShare,
          feedRequestId: 'feed-attribution-42',
          initialFeedPosition: 42,
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
        overrides: [
          contentBehaviorTrackerProvider.overrideWithValue(behaviorTracker),
          contentEngagementTrackerProvider.overrideWithValue(engagementTracker),
        ],
      ),
    );
    await _pumpImmersiveViewerFirstFrames(tester);
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 1100)),
    );

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    await behaviorTracker.flush();
    await engagementTracker.dispose();

    final visibleEnters = reporter.recorded
        .where(
          (event) =>
              event.contentId == post.id &&
              event.action == BehaviorEventType.impression &&
              event.state == 'visible',
        )
        .toList(growable: false);
    final dwells = reporter.recorded
        .where(
          (event) =>
              event.contentId == post.id &&
              event.action == BehaviorEventType.dwell,
        )
        .toList(growable: false);

    expect(visibleEnters, hasLength(1));
    expect(dwells, hasLength(1));
    expect(dwells.single.referralSource, ReferralSource.friendShare);
    expect(dwells.single.feedRequestId, 'feed-attribution-42');
    expect(dwells.single.position, 42);
  });

  testWidgets('沉浸式浏览器更多功能使用贴底非全屏面板', (tester) async {
    final post = _photoPost();
    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await _pumpSettledFrames(tester);

    await tester.tap(find.byIcon(CupertinoIcons.ellipsis));
    await _pumpSettledFrames(tester);

    final panel = find.byKey(TestKeys.modalBottomSheetPanel);
    final screenHeight =
        tester.view.physicalSize.height / tester.view.devicePixelRatio;

    expect(panel, findsOneWidget);
    expect(find.text('取消'), findsOneWidget);
    expect(tester.getTopLeft(panel).dy, greaterThan(0));
    expect(tester.getBottomRight(panel).dy, closeTo(screenHeight, 2.0));
  });

  testWidgets('沉浸式浏览器更多功能在不感兴趣上方提供深色「内容过滤」入口并支持多选', (tester) async {
    final post = _photoPost();
    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await _pumpSettledFrames(tester);

    await tester.tap(find.byIcon(CupertinoIcons.ellipsis));
    await _pumpSettledFrames(tester);

    final contentFilter = find.text('内容过滤');
    final notInterested = find.text('不感兴趣');
    expect(contentFilter, findsOneWidget);
    expect(notInterested, findsOneWidget);
    expect(
      tester.getTopLeft(contentFilter).dy,
      lessThan(tester.getTopLeft(notInterested).dy),
    );

    final panelContainer = tester.widget<Container>(
      find.byKey(TestKeys.modalBottomSheetPanel),
    );
    final panelDecoration = panelContainer.decoration! as BoxDecoration;
    expect(
      panelDecoration.color,
      equals(SettingsSemanticConstants.conversationSheetPanelBackground(true)),
    );

    await tester.tap(contentFilter);
    await _pumpSettledFrames(tester);

    expect(
      find.byKey(const ValueKey<String>('more-action-content-filter-panel')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('more-action-content-filter-image')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('more-action-content-filter-video')),
      findsOneWidget,
    );

    await tester.tap(
      find.byKey(const ValueKey<String>('more-action-content-filter-image')),
    );
    await _pumpSettledFrames(tester);
    await tester.tap(
      find.byKey(const ValueKey<String>('more-action-content-filter-video')),
    );
    await _pumpSettledFrames(tester);
    await tester.tap(find.text('完成'));
    await _pumpSettledFrames(tester);

    expect(find.text('图片 / 视频'), findsOneWidget);
  });

  testWidgets('内容过滤多选后作品流按组合筛选，不再显示未选中的文章', (tester) async {
    final photo = _photoPost();
    final video = _videoPost(width: 1920, height: 1080);
    final article = _articlePost();
    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [photo, video, article],
          externalPostViews: [
            ContentSurfaceViewMapper.fromDto(photo),
            ContentSurfaceViewMapper.fromDto(video),
            ContentSurfaceViewMapper.fromDto(article),
          ],
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await _pumpSettledFrames(tester);

    await tester.tap(find.byIcon(CupertinoIcons.ellipsis));
    await _pumpSettledFrames(tester);
    await tester.tap(find.text('内容过滤'));
    await _pumpSettledFrames(tester);

    await tester.tap(
      find.byKey(const ValueKey<String>('more-action-content-filter-image')),
    );
    await _pumpSettledFrames(tester);
    await tester.tap(
      find.byKey(const ValueKey<String>('more-action-content-filter-video')),
    );
    await _pumpSettledFrames(tester);
    await tester.tap(find.text('完成'));
    await _pumpSettledFrames(tester);
    expect(find.text(article.title), findsNothing);
    expect(find.byType(VideoPlayerWidget), findsNothing);
    expect(find.text('图片 / 视频'), findsOneWidget);
  });

  testWidgets('过滤移除并恢复当前视频时不复用失效会话', (tester) async {
    _installImmersiveVideoTestPlatform();
    final video = _videoPost(width: 1920, height: 1080, coverUrl: '');
    final photo = _photoPost(
      imageUrls: const <String>[''],
      coverUrl: '',
      avatarUrl: '',
    );
    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [video, photo],
          externalPostViews: [
            ContentSurfaceViewMapper.fromDto(video),
            ContentSurfaceViewMapper.fromDto(photo),
          ],
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
        overrides: [
          mediaDownloadCacheProvider.overrideWithValue(
            _NoopMediaDownloadCache(),
          ),
        ],
      ),
    );
    await _waitForVideoTimelineMeasurementFrame(tester);
    expect(VideoPlayerWidget.debugActiveControllerCount, 1);
    final duration = find.byKey(
      const ValueKey<String>('works-video-transient-duration'),
    );
    await tester.pump();
    expect(tester.widget<Opacity>(duration).opacity, 1);
    await tester.pump(const Duration(seconds: 3));

    void openMoreActions() {
      final button = find.descendant(
        of: find.byKey(const ValueKey<String>('works-top-more')),
        matching: find.byType(CupertinoButton),
      );
      expect(button, findsOneWidget);
      tester.widget<CupertinoButton>(button).onPressed?.call();
    }

    openMoreActions();
    await _pumpSettledFrames(tester);
    await tester.tap(find.text('内容过滤'));
    await _pumpSettledFrames(tester);
    await tester.tap(
      find.byKey(const ValueKey<String>('more-action-content-filter-image')),
    );
    await _pumpSettledFrames(tester);
    await tester.tap(find.text('完成'));
    await _pumpSettledFrames(tester);
    expect(find.byType(VideoPlayerWidget), findsNothing);
    for (
      var attempt = 0;
      attempt < 20 && VideoPlayerWidget.debugActiveControllerCount > 0;
      attempt += 1
    ) {
      await tester.runAsync(() async {
        await Future<void>.delayed(Duration.zero);
      });
      await tester.pump();
    }
    expect(VideoPlayerWidget.debugActiveControllerCount, 0);

    openMoreActions();
    await _pumpSettledFrames(tester);
    await tester.tap(find.text('内容过滤'));
    await _pumpSettledFrames(tester);
    await tester.tap(
      find.byKey(const ValueKey<String>('more-action-content-filter-video')),
    );
    await tester.tap(
      find.byKey(const ValueKey<String>('more-action-content-filter-image')),
    );
    await _pumpSettledFrames(tester);
    await tester.tap(find.text('完成'));
    await _pumpSettledFrames(tester);
    expect(
      find.byType(VideoPlayerWidget),
      findsOneWidget,
      reason: '恢复视频筛选后应先重建唯一当前视频播放器。',
    );
    await _waitForVideoTimelineMeasurementFrame(tester);
    expect(VideoPlayerWidget.debugActiveControllerCount, 1);
    expect(
      tester.widget<Opacity>(duration).opacity,
      0,
      reason: '过滤临时移除并恢复同一媒体不属于真实切集，不能重启五秒窗口。',
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('图片滑到边界后从内容区继续横滑不会切换主 tab', (tester) async {
    final post = _photoPost(
      imageUrls: const [
        'media/image/s/fixture/photo.jpg',
        'media/image/s/fixture/photo-2.jpg',
      ],
    );
    var switchedToCircles = false;

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          initialImageIndex: 1,
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
          onSwitchToCircles: () {
            switchedToCircles = true;
          },
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await _pumpSettledFrames(tester);

    await tester.dragFrom(
      tester.getCenter(find.byType(WorksImmersiveViewer)),
      const Offset(-220, 0),
    );
    await _pumpSettledFrames(tester);

    expect(switchedToCircles, isFalse);
  });

  testWidgets('图片作品使用公共翻书组件，首图左滑翻到下一张且不触发退出', (tester) async {
    final post = _photoPost(
      imageUrls: const [
        'media/image/s/fixture/photo.jpg',
        'media/image/s/fixture/photo-2.jpg',
      ],
    );
    var dismissed = false;

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: false,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          initialImageIndex: 0,
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
          onTapBack: () {
            dismissed = true;
          },
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await _pumpSettledFrames(tester);

    expect(
      find.byKey(const ValueKey<String>('works-photo-stage')),
      findsNothing,
    );
    final photoStage = find.byKey(
      const ValueKey<String>('works-photo-book-stage'),
    );
    expect(photoStage, findsOneWidget);
    expect(
      find.byKey(const ValueKey<String>('media-pageflip-gesture-layer')),
      findsOneWidget,
    );
    expect(
      tester
          .widget<MediaPageFlipBook>(find.byType(MediaPageFlipBook))
          .pageCount,
      2,
    );
    expect(
      find.byKey(const ValueKey<String>('media-pageflip-static-page-0')),
      findsOneWidget,
    );
    final initialRect = tester.getRect(
      find.byKey(const ValueKey<String>('media-pageflip-gesture-layer')),
    );
    final gesture = await tester.startGesture(initialRect.center);
    await gesture.moveBy(const Offset(-12, 0));
    await tester.pump(const Duration(milliseconds: 16));
    _consumeImageLoadExceptions(tester);
    expect(
      find.byKey(const ValueKey<String>('media-pageflip-flipping-layer')),
      findsOneWidget,
      reason: 'Work Browser 父级 Listener 与图片书子级手势层共存时，第一页中心小幅左滑也必须立即前翻跟手。',
    );
    await gesture.moveBy(const Offset(-180, 0));
    await tester.pump();
    await gesture.moveBy(const Offset(-180, 0));
    for (var i = 0; i < 8; i += 1) {
      await tester.pump(const Duration(milliseconds: 16));
      _consumeImageLoadExceptions(tester);
    }

    expect(dismissed, isFalse);
    expect(
      find.byKey(const ValueKey<String>('media-pageflip-flipping-layer')),
      findsOneWidget,
      reason: '图片视频书按住横滑时必须进入同源动态翻页层，而不是 release 后才换页。',
    );

    await gesture.up();
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 1100));
    await _pumpSettledFrames(tester);

    expect(dismissed, isFalse);
    expect(
      find.byKey(const ValueKey<String>('media-pageflip-static-page-1')),
      findsOneWidget,
    );
  });

  testWidgets('图片视频书横向带角度拖动只翻页不切换作品', (tester) async {
    final first = _photoPost(
      imageUrls: const [
        'media/image/s/fixture/photo.jpg',
        'media/image/s/fixture/photo-2.jpg',
      ],
    );
    final second = _photoPost(
      id: 'photo-2',
      imageUrls: const ['media/image/s/fixture/photo-3.jpg'],
      body: 'second body',
    );
    final changedPosts = <int>[];

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: false,
          showTopNavigation: false,
          externalPosts: [first, second],
          externalPostViews: [
            ContentSurfaceViewMapper.fromDto(first),
            ContentSurfaceViewMapper.fromDto(second),
          ],
          initialImageIndex: 0,
          onPostIndexChanged: changedPosts.add,
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await _pumpSettledFrames(tester);

    final gestureLayer = find.byKey(
      const ValueKey<String>('media-pageflip-gesture-layer'),
    );
    final rect = tester.getRect(gestureLayer);
    final gesture = await tester.startGesture(rect.center);
    await gesture.moveBy(const Offset(-120, -68));
    await tester.pump();
    await gesture.moveBy(const Offset(-120, -68));
    for (var i = 0; i < 8; i += 1) {
      await tester.pump(const Duration(milliseconds: 16));
      _consumeImageLoadExceptions(tester);
    }

    expect(
      find.byKey(const ValueKey<String>('media-pageflip-flipping-layer')),
      findsOneWidget,
    );

    await gesture.up();
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 1100));
    await _pumpSettledFrames(tester);

    expect(changedPosts, isNot(contains(1)));
    expect(
      find.byKey(const ValueKey<String>('works-status-content-canvas-photo-1')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('media-pageflip-static-page-1')),
      findsOneWidget,
    );
  });

  testWidgets('图片视频书纵向带角度拖动只切换作品不启动翻页', (tester) async {
    final first = _photoPost(
      imageUrls: const [
        'media/image/s/fixture/photo.jpg',
        'media/image/s/fixture/photo-2.jpg',
      ],
    );
    final second = _photoPost(
      id: 'photo-2',
      imageUrls: const ['media/image/s/fixture/photo-3.jpg'],
      body: 'second body',
    );
    final changedPosts = <int>[];

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: false,
          showTopNavigation: false,
          externalPosts: [first, second],
          externalPostViews: [
            ContentSurfaceViewMapper.fromDto(first),
            ContentSurfaceViewMapper.fromDto(second),
          ],
          initialImageIndex: 0,
          onPostIndexChanged: changedPosts.add,
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await _pumpSettledFrames(tester);

    final gestureLayer = find.byKey(
      const ValueKey<String>('media-pageflip-gesture-layer'),
    );
    await tester.timedDrag(
      gestureLayer,
      const Offset(-72, -272),
      const Duration(milliseconds: 420),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 1500));
    _consumeImageLoadExceptions(tester);

    expect(
      find.byKey(const ValueKey<String>('media-pageflip-flipping-layer')),
      findsNothing,
    );
    expect(changedPosts, contains(1));
    expect(
      find.byKey(const ValueKey<String>('works-status-content-canvas-photo-2')),
      findsOneWidget,
    );
  });

  testWidgets('图片作品末图继续左滑不触发退出', (tester) async {
    final post = _photoPost(
      imageUrls: const [
        'media/image/s/fixture/photo.jpg',
        'media/image/s/fixture/photo-2.jpg',
      ],
    );
    var dismissed = false;

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: false,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          initialImageIndex: 1,
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
          onTapBack: () {
            dismissed = true;
          },
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await _pumpSettledFrames(tester);

    final photoStage = find.byKey(
      const ValueKey<String>('works-photo-book-stage'),
    );
    expect(photoStage, findsOneWidget);
    final initialRect = tester.getRect(
      find.byKey(const ValueKey<String>('media-pageflip-gesture-layer')),
    );
    final gesture = await tester.startGesture(initialRect.center);
    await gesture.moveBy(const Offset(-240, 0));
    await tester.pump();

    expect(dismissed, isFalse);

    await gesture.up();
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 1100));
    await _pumpSettledFrames(tester);

    expect(dismissed, isFalse);
    expect(
      find.byKey(const ValueKey<String>('media-pageflip-static-page-1')),
      findsOneWidget,
    );
  });

  testWidgets('文章翻页到边界后从内容区继续横滑不会切换主 tab', (tester) async {
    final post = _articlePost();
    var switchedToCircles = false;

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: _articleMarkdownRaw(post, _multiPageArticleMarkdown(post)),
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
          onSwitchToCircles: () {
            switchedToCircles = true;
          },
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await _pumpSettledFrames(tester);

    await _flipArticleToLastPage(tester);
    _expectArticleAdvancedPastFirstPage(tester);

    await tester.dragFrom(
      tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomRight)),
      const Offset(-260, -40),
    );
    await _pumpSettledFrames(tester);

    expect(switchedToCircles, isFalse);
  });

  testWidgets('文章纵向带角度拖动只切换作品不抢成翻页', (tester) async {
    final article = _articlePost();
    final nextPhoto = _photoPost(
      id: 'photo-2',
      imageUrls: const ['media/image/s/fixture/photo-next.jpg'],
      body: 'next photo body',
    );
    final changedPosts = <int>[];

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: false,
          showTopNavigation: false,
          externalPosts: [article, nextPhoto],
          externalPostViews: [
            ContentSurfaceViewMapper.fromDto(article),
            ContentSurfaceViewMapper.fromDto(nextPhoto),
          ],
          rawPostsById: _viewerRawByPostId({
            article.id: _articleMarkdownRaw(
              article,
              _multiPageArticleMarkdown(article),
            ),
          }),
          onPostIndexChanged: changedPosts.add,
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await _pumpSettledFrames(tester);

    final stage = find.byKey(const ValueKey<String>('article-boundary-stage'));
    await tester.timedDrag(
      stage,
      const Offset(-72, -272),
      const Duration(milliseconds: 420),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 1500));
    _consumeImageLoadExceptions(tester);

    expect(changedPosts, contains(1));
    expect(
      find.byKey(const ValueKey<String>('works-status-content-canvas-photo-2')),
      findsOneWidget,
      reason: '文章内容区纵向优势斜拖应进入作品流切换，不能被页角翻页 pan 抢走。',
    );
  });

  testWidgets('多页文章在首页从内容区继续横滑时会出现回弹并恢复原位', (tester) async {
    final post = _articlePost();
    var dismissed = false;

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: _articleMarkdownRaw(post, _multiPageArticleMarkdown(post)),
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
          onTapBack: () {
            dismissed = true;
          },
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await _pumpSettledFrames(tester);

    final stage = find.byKey(const ValueKey<String>('article-boundary-stage'));
    final stageRect = tester.getRect(stage);
    final gesture = await tester.startGesture(
      Offset(stageRect.left + 120, stageRect.center.dy),
    );
    await gesture.moveBy(const Offset(24, 0));
    await tester.pump();
    await gesture.moveBy(const Offset(48, 0));
    await tester.pump();
    await gesture.moveBy(const Offset(48, 0));
    await tester.pump();

    final draggedTransform = tester.widget<AnimatedContainer>(stage).transform;
    expect(draggedTransform, isNotNull);
    expect(draggedTransform!.storage[12], greaterThan(8));
    expect(dismissed, isFalse);

    await gesture.up();
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 260));
    await _pumpSettledFrames(tester);

    final settledTransform = tester.widget<AnimatedContainer>(stage).transform;
    expect(settledTransform, isNotNull);
    expect(settledTransform!.storage[12], closeTo(0, 0.5));
    expect(dismissed, isFalse);
  });

  testWidgets('多页文章在末页从内容区继续横滑时会出现回弹并恢复原位', (tester) async {
    final post = _articlePost();
    var dismissed = false;

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: _articleMarkdownRaw(post, _multiPageArticleMarkdown(post)),
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
          onTapBack: () {
            dismissed = true;
          },
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await _pumpSettledFrames(tester);

    await _flipArticleToLastPage(tester);

    final stage = find.byKey(const ValueKey<String>('article-boundary-stage'));
    final gesture = await tester.startGesture(
      tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomRight)),
    );
    await gesture.moveBy(const Offset(-24, 0));
    await tester.pump();
    await gesture.moveBy(const Offset(-48, 0));
    await tester.pump();
    await gesture.moveBy(const Offset(-48, 0));
    await tester.pump();

    final draggedTransform = tester.widget<AnimatedContainer>(stage).transform;
    expect(draggedTransform, isNotNull);
    expect(draggedTransform!.storage[12], lessThan(-8));
    expect(dismissed, isFalse);

    await gesture.up();
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 260));
    await _pumpSettledFrames(tester);

    final settledTransform = tester.widget<AnimatedContainer>(stage).transform;
    expect(settledTransform, isNotNull);
    expect(settledTransform!.storage[12], closeTo(0, 0.5));
    expect(dismissed, isFalse);
  });

  testWidgets('长正文文章底部页码跟随真实排版页数而不是 fallback 单页', (tester) async {
    final post = _articlePost();
    final markdownSections = List<String>.generate(
      14,
      (index) =>
          '## 小节${index + 1}\n\n这是一段用于沉浸式文章自动分页的长正文，需要被继续拆到后续页面中，不能仍然停留在 1/1。',
    ).join('\n\n');
    final articleMarkdown =
        '---\n'
        'title: ${post.title}\n'
        'template: ${post.articleTemplate}\n'
        'fontPreset: ${post.articleFontPreset}\n'
        '---\n\n'
        '$markdownSections\n';

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: <String, dynamic>{
              'postId': post.id,
              'type': 'article',
              'contentType': 'article',
              'authorId': post.authorId,
              'authorDisplayName': post.displayName,
              'authorAvatarUrl': post.avatarUrl,
              'title': post.title,
              'body': post.body,
              'summary': post.summary,
              'coverUrl': post.coverUrl,
              'articleTemplate': post.articleTemplate,
              'articleFontPreset': post.articleFontPreset,
              'articleMarkdown': articleMarkdown,
              'markdownDialect': 'qwq-rich-md',
              'articleAssetManifest': const <String, dynamic>{
                'schema': 'article-asset-manifest',
                'markdownDialect': 'qwq-rich-md',
                'articleMarkdownDigest': 'fixture:test-long',
                'assets': <Map<String, dynamic>>[],
              },
              'articleRenderProfile': <String, dynamic>{
                'template': post.articleTemplate,
                'fontPreset': post.articleFontPreset,
              },
              'cards': const <Map<String, dynamic>>[],
            },
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await _pumpSettledFrames(tester);

    expect(
      find.byKey(const ValueKey<String>('works-article-page-progress')),
      findsOneWidget,
    );
    final progressLabel = tester.widget<Text>(
      find.byKey(const ValueKey<String>('works-article-page-progress')),
    );
    expect(
      progressLabel.data,
      isNot(UITextConstants.workArticlePageProgress(1, 1)),
    );

    // 页码两侧 chevron `‹ ›` 可点切页（正文后、作者工具栏前）。
    final prevChevron = find.byKey(
      const ValueKey<String>('works-article-page-prev'),
    );
    final nextChevron = find.byKey(
      const ValueKey<String>('works-article-page-next'),
    );
    expect(prevChevron, findsOneWidget);
    expect(nextChevron, findsOneWidget);

    await tester.tap(nextChevron);
    _consumeImageLoadExceptions(tester);
    await _pumpSettledFrames(tester);
    final advancedLabel = tester.widget<Text>(
      find.byKey(const ValueKey<String>('works-article-page-progress')),
    );
    expect(advancedLabel.data, startsWith('2 / '));

    await tester.tap(prevChevron);
    _consumeImageLoadExceptions(tester);
    await _pumpSettledFrames(tester);
    final restoredLabel = tester.widget<Text>(
      find.byKey(const ValueKey<String>('works-article-page-progress')),
    );
    expect(restoredLabel.data, startsWith('1 / '));
  });

  testWidgets('单页文章从内容区横滑时只回弹不进入翻页宿主', (tester) async {
    final post = _articlePost();
    var dismissed = false;

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: _articleMarkdownRaw(
              post,
              '---\n'
              'title: 单页文章\n'
              'template: ${post.articleTemplate}\n'
              'fontPreset: ${post.articleFontPreset}\n'
              '---\n\n'
              '这是一页内就能装下的短正文。\n',
            ),
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
          onTapBack: () {
            dismissed = true;
          },
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await _pumpSettledFrames(tester);

    expect(
      find.text(UITextConstants.workArticlePageProgress(1, 1)),
      findsOneWidget,
    );
    expect(find.byKey(TestKeys.articlePageCurlLayer), findsNothing);

    final stage = find.byKey(const ValueKey<String>('article-boundary-stage'));
    final stageRect = tester.getRect(stage);
    final gesture = await tester.startGesture(stageRect.center);
    await gesture.moveBy(const Offset(24, 0));
    await tester.pump();
    await gesture.moveBy(const Offset(48, 0));
    await tester.pump();
    await gesture.moveBy(const Offset(48, 0));
    await tester.pump();

    final draggedTransform = tester.widget<AnimatedContainer>(stage).transform;
    expect(draggedTransform, isNotNull);
    expect(draggedTransform!.storage[12], greaterThan(8));
    expect(dismissed, isFalse);

    await gesture.up();
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 260));
    await _pumpSettledFrames(tester);

    final settledTransform = tester.widget<AnimatedContainer>(stage).transform;
    expect(settledTransform, isNotNull);
    expect(settledTransform!.storage[12], closeTo(0, 0.5));
    expect(dismissed, isFalse);
  });

  testWidgets('Android 下图片左边缘横滑会退出当前沉浸页', (tester) async {
    final post = _photoPost(
      imageUrls: const [
        'media/image/s/fixture/photo.jpg',
        'media/image/s/fixture/photo-2.jpg',
      ],
    );
    var dismissed = false;

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: false,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          initialImageIndex: 0,
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
          onTapBack: () {
            dismissed = true;
          },
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await _pumpSettledFrames(tester);

    final viewerRect = tester.getRect(find.byType(WorksImmersiveViewer));
    await tester.dragFrom(
      Offset(viewerRect.left + 6, viewerRect.center.dy),
      const Offset(220, 0),
    );
    await _pumpSettledFrames(tester);

    expect(dismissed, isTrue);
  });

  testWidgets('视频从内容区横滑到首末边界时不会退出，仍由屏幕边缘手势返回', (tester) async {
    final post = _videoPost(width: 1920, height: 1080);
    var dismissed = false;

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: false,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
          onTapBack: () {
            dismissed = true;
          },
        ),
      ),
    );
    // 聚焦视频默认 autoPlay，其加载占位的 CupertinoActivityIndicator 是 by-design
    // 永续动画（测试环境视频永不就绪），pumpAndSettle 永不收敛。用有界 pump 推进帧并
    // 让横滑回弹/settle（debounce 100ms）收敛后断言真实的边界手势行为。
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    final viewerRect = tester.getRect(find.byType(WorksImmersiveViewer));

    await tester.dragFrom(
      Offset(viewerRect.center.dx, viewerRect.center.dy),
      const Offset(220, 0),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 350));
    expect(dismissed, isFalse);

    await tester.dragFrom(
      Offset(viewerRect.left + 6, viewerRect.center.dy),
      const Offset(220, 0),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 350));
    expect(dismissed, isTrue);
  });

  testWidgets('iOS 下右边缘横滑不会触发沉浸式返回', (tester) async {
    final post = _photoPost(
      imageUrls: const ['media/image/s/fixture/photo-only.jpg'],
    );
    var dismissed = false;
    final container = _testProviderContainer(
      overrides: [
        ...mockContentFacetOverrides(store: InMemoryContentPostStore()),
      ],
    );

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp(
          theme: ThemeData(platform: TargetPlatform.iOS),
          home: Scaffold(
            body: MediaQuery(
              data: const MediaQueryData(size: Size(390, 844)),
              child: WorksImmersiveViewer(
                showWorksToolbar: false,
                showTopNavigation: false,
                externalPosts: [post],
                externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
                onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
                onAssistantTap: () {},
                onTapBack: () {
                  dismissed = true;
                },
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await _pumpSettledFrames(tester);

    final viewerRect = tester.getRect(find.byType(WorksImmersiveViewer));
    await tester.dragFrom(
      Offset(viewerRect.right - 6, viewerRect.center.dy),
      const Offset(-220, 0),
    );
    await _pumpSettledFrames(tester);

    expect(dismissed, isFalse);

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    container.dispose();
  });

  testWidgets('文章第二页左边缘右拉优先后翻，不误退出沉浸页', (tester) async {
    final post = _articlePost();
    var dismissed = false;

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: _articleMarkdownRaw(post, _multiPageArticleMarkdown(post)),
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
          onTapBack: () {
            dismissed = true;
          },
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await _pumpSettledFrames(tester);

    await _flipArticleToSecondPage(tester);
    expect(_articleProgressLabel(tester), startsWith('2 / '));
    expect(
      find.byKey(const ValueKey<String>('works-edge-dismiss-previous')),
      findsNothing,
      reason: '文章当前页可后翻时，左边缘退出热区必须退场，把右拉手势交给翻页层。',
    );

    await tester.dragFrom(
      tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomLeft)),
      const Offset(220, -20),
    );
    await _pumpSettledFrames(tester);

    expect(dismissed, isFalse);
  });

  testWidgets('Android 下文章末页右边缘继续前翻会退出当前沉浸页', (tester) async {
    final post = _articlePost();
    var dismissed = false;

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: _articleMarkdownRaw(post, _multiPageArticleMarkdown(post)),
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
          onTapBack: () {
            dismissed = true;
          },
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await _pumpSettledFrames(tester);

    await _flipArticleToLastPage(tester);
    _expectArticleAdvancedPastFirstPage(tester);

    final deckRect = tester.getRect(find.byType(ArticleReadOnlyBookDeck));
    final rightHotzoneRect = tester.getRect(
      find.byKey(TestKeys.articlePageCurlHotzoneBottomRight),
    );
    expect(rightHotzoneRect.right, closeTo(deckRect.right, 0.1));

    await tester.drag(
      find.byKey(const ValueKey<String>('works-edge-dismiss-next')),
      const Offset(-220, -20),
    );
    await _pumpSettledFrames(tester);

    expect(dismissed, isTrue);
  });

  testWidgets('文章沉浸浏览使用与图片视频一致的深色状态栏', (tester) async {
    final post = _articlePost();

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          topChromeSafeInset: AppSpacing.twenty,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: _articleMarkdownRaw(post, _multiPageArticleMarkdown(post)),
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await _pumpSettledFrames(tester);

    final styles = tester
        .widgetList<AnnotatedRegion<SystemUiOverlayStyle>>(
          find.byType(AnnotatedRegion<SystemUiOverlayStyle>),
        )
        .map((region) => region.value);
    expect(
      styles,
      contains(
        isA<SystemUiOverlayStyle>()
            .having(
              (style) => style.statusBarColor,
              'statusBarColor',
              AppColors.black,
            )
            .having(
              (style) => style.statusBarIconBrightness,
              'statusBarIconBrightness',
              Brightness.light,
            )
            .having(
              (style) => style.statusBarBrightness,
              'statusBarBrightness',
              Brightness.dark,
            ),
      ),
    );
    final statusScrim = tester.getRect(
      find.byKey(const ValueKey<String>('works-article-status-bar-scrim')),
    );
    expect(statusScrim.height, moreOrLessEquals(AppSpacing.twenty));
  });

  testWidgets('文章阅读使用底部页码且标题封面在首屏、正文翻页可达', (tester) async {
    final post = _articlePost();

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: <String, dynamic>{
              'postId': post.id,
              'type': 'article',
              'contentType': 'article',
              'authorId': post.authorId,
              'authorDisplayName': post.displayName,
              'authorAvatarUrl': post.avatarUrl,
              'title': post.title,
              'body': post.body,
              'summary': post.summary,
              'coverUrl': post.coverUrl,
              'articleTemplate': post.articleTemplate,
              'articleFontPreset': post.articleFontPreset,
              'articleMarkdown':
                  '---\n'
                  'title: ${post.title}\n'
                  'template: ${post.articleTemplate}\n'
                  'fontPreset: ${post.articleFontPreset}\n'
                  'cover_asset_id: cover\n'
                  '---\n\n'
                  '# ${post.title}\n\n'
                  ':::figure id="cover" layout="fullWidth" caption=""\n'
                  'asset://cover\n'
                  ':::\n\n'
                  '第一页前言。\n\n'
                  '第二段落继续展开说明。\n\n'
                  '第三段落把正文推到下一页。\n',
              'markdownDialect': 'qwq-rich-md',
              'articleAssetManifest': <String, dynamic>{
                'schema': 'article-asset-manifest',
                'markdownDialect': 'qwq-rich-md',
                'articleMarkdownDigest': 'fixture:test',
                'assets': <Map<String, dynamic>>[
                  {
                    'assetId': 'cover',
                    'cdnUrl': post.coverUrl,
                    'role': 'cover',
                  },
                ],
              },
              'articleRenderProfile': <String, dynamic>{
                'template': post.articleTemplate,
                'fontPreset': post.articleFontPreset,
              },
            },
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await _pumpSettledFrames(tester);

    expect(
      find.byKey(const ValueKey<String>('works-top-back')),
      findsOneWidget,
    );
    // 文章页码在正文下方、作者工具栏上方，禁止顶部页码与点指示器。
    expect(
      find.byKey(const ValueKey<String>('works-top-progress-label')),
      findsNothing,
    );
    expect(
      find.byKey(const ValueKey<String>('works-article-page-progress')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('works-page-indicator')),
      findsNothing,
    );
    expect(find.textContaining('/'), findsWidgets);
    expect(find.byType(MediaBlurCaptionOverlay), findsNothing);
    expect(
      find.byKey(const ValueKey<String>('article-frontispiece-image')),
      findsNothing,
    );
    expect(find.text(post.title), findsWidgets);
    // 首屏以标题+封面为确定性结构；正文具体分布由真实画布几何与 4:3
    // 后备比例决定，不把某一句必须同页写成第二套排版真相源。
    expect(_articleProgressLabel(tester), startsWith('1 / '));

    // Dark Paper：文章作品默认深色纸张舞台，页码两侧带可点 chevron。
    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget is ColoredBox &&
            widget.color == ArticlePaperPaletteColors.darkPaperPaper,
      ),
      findsWidgets,
    );
    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget is ColoredBox &&
            widget.color == ArticlePaperPaletteColors.darkPaperStage,
      ),
      findsNothing,
    );
    expect(
      find.byKey(const ValueKey<String>('works-article-page-prev')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('works-article-page-next')),
      findsOneWidget,
    );

    await _flipArticleToLastPage(tester);
    _expectArticleAdvancedPastFirstPage(tester);
    expect(
      find.textContaining('第一页前言'),
      findsWidgets,
      reason: '标题/封面占用前置分页时正文必须在后续页可达，不得丢失',
    );
  });

  testWidgets('文章图片状态转换保持分页几何，打开关闭图片书记录 catalog 并恢复阅读页', (tester) async {
    final post = _articlePost();
    final analytics = _FakeAnalyticsService();
    final telemetry = RecordingAppTelemetryRecorder();
    final articleObjectKey =
        'media/image/s/test/article/image-viewer/v1/'
        'inline-${DateTime.now().microsecondsSinceEpoch}.jpg';
    MediaLoadFailureCache.instance.clear();
    addTearDown(MediaLoadFailureCache.instance.clear);
    final articleIdentity = resolveContentMediaUrl(
      articleObjectKey,
      endpointConfig: _testMediaEndpointConfig,
    );
    MediaLoadFailureCache.instance.recordFailure(
      articleIdentity,
      error: const _HttpStatusTestException(404, 'controlled initial failure'),
      candidateUrl: articleIdentity,
    );
    final rawArticle = _articleMarkdownRaw(
      post,
      '---\n'
      'title: ${post.title}\n'
      'template: ${post.articleTemplate}\n'
      'fontPreset: ${post.articleFontPreset}\n'
      '---\n\n'
      ':::figure id="article-image" layout="fullWidth" caption=""\n'
      'asset://article-image\n'
      ':::\n',
      extra: <String, dynamic>{
        'articleAssetManifest': <String, dynamic>{
          'schema': 'article-asset-manifest',
          'markdownDialect': 'qwq-rich-md',
          'articleMarkdownDigest': 'fixture:image-viewer',
          'assets': <Map<String, dynamic>>[
            <String, dynamic>{
              'assetId': 'article-image',
              'publicSliceKey': articleObjectKey,
              'accessMode': 'public',
              'role': 'inline',
              'width': 1200,
              'height': 900,
            },
          ],
        },
      },
    );

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: <ContentPostViewData>[post],
          externalPostViews: <ContentSurfaceView>[
            ContentSurfaceViewMapper.fromDto(post),
          ],
          rawPostsById: _viewerRawByPostId(<String, Map<String, dynamic>>{
            post.id: rawArticle,
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
        overrides: <Override>[
          postArticleDetailProjectorProvider.overrideWithValue(
            _EndpointBoundPostArticleDetailProjector(_testMediaEndpointConfig),
          ),
          analyticsProvider.overrideWithValue(analytics),
          appTelemetryReporterProvider.overrideWithValue(telemetry),
        ],
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await _pumpSettledFrames(tester);

    final nextPage = find.byKey(
      const ValueKey<String>('works-article-page-next'),
    );
    // DEC-033：内嵌图经 typed 交付入口分流后才渲染文章自有原子，手势件与原子
    // 之间因此多了一层。锚在「包含该原子的可点手势件」上，不锚具体层级结构。
    Finder tappableArticleImages() => find
        .ancestor(
          of: find.byType(ArticleAdaptiveImage),
          matching: find.byWidgetPredicate(
            (widget) => widget is GestureDetector && widget.onTap != null,
          ),
        )
        .hitTestable();
    var articleImages = tappableArticleImages();
    for (
      var pageGuard = 0;
      articleImages.evaluate().isEmpty && pageGuard < 20;
      pageGuard += 1
    ) {
      expect(nextPage, findsOneWidget, reason: '含图片文章必须能通过真实分页到达图片页。');
      await tester.tap(nextPage);
      await _pumpSettledFrames(tester);
      articleImages = tappableArticleImages();
    }
    expect(articleImages, findsWidgets);

    Finder articleGesture() => tappableArticleImages().first;
    Finder articleImage() => find
        .descendant(
          of: articleGesture(),
          matching: find.byType(ArticleAdaptiveImage),
        )
        .first;
    Finder articleNetworkImage() => find.descendant(
      of: articleImage(),
      matching: find.byType(AppCachedNetworkImage),
    );
    Finder articleState(Key key) =>
        find.descendant(of: articleImage(), matching: find.byKey(key));
    final frameSize = tester.getSize(articleImage());
    final progressBeforeTransitions = _articleProgressLabel(tester);
    void expectStableArticleGeometry(String reason) {
      expect(tester.getSize(articleImage()), frameSize, reason: reason);
      expect(
        _articleProgressLabel(tester),
        progressBeforeTransitions,
        reason: '$reason；文章当前页与总页数均不得变化。',
      );
    }

    expect(
      tester.widget<ArticleAdaptiveImage>(articleImage()).imageUrl,
      articleIdentity,
      reason: '文章投影与图片组件必须消费同一测试媒体端点。',
    );
    expect(articleNetworkImage(), findsOneWidget);
    expect(articleState(articleImageSourceAbsentKey), findsNothing);
    expect(articleState(articleImageFailedSurfaceKey), findsOneWidget);
    expectStableArticleGeometry('终态失败必须保留图片预留框与文章页数');
    final imageStateBeforeRetry = tester.state(articleImage());
    final failedGeneration = tester
        .widget<AppCachedNetworkImage>(articleNetworkImage())
        .key;

    await tester.tap(articleState(articleImageRetryKey));
    await tester.pump();
    expect(articleState(articleImageDelayedIndicatorKey), findsOneWidget);
    expect(
      MediaLoadFailureCache.instance.shouldSkipNetwork(articleIdentity),
      isFalse,
      reason: '显式 Retry 必须先清除当前交付 identity 的负缓存。',
    );
    expect(
      tester.widget<AppCachedNetworkImage>(articleNetworkImage()).key,
      isNot(failedGeneration),
      reason: 'Retry 必须以新 generation 重建真实图片加载链路。',
    );
    expect(tester.state(articleImage()), same(imageStateBeforeRetry));
    expectStableArticleGeometry('failure → retry/loading 必须沿用原占位框');

    var networkImage = tester.widget<AppCachedNetworkImage>(
      articleNetworkImage(),
    );
    networkImage.onLoadFailed!(StateError('controlled retry failure'));
    await tester.pump(const Duration(milliseconds: 16));
    expect(articleState(articleImageDelayedIndicatorKey), findsOneWidget);
    expect(articleState(articleImageFailedSurfaceKey), findsNothing);
    expectStableArticleGeometry('loading → pending failure 不得触发重新分页');
    await tester.pump(ImmersiveMediaWaitMotion.indicatorMinDisplay);
    await tester.pump(const Duration(milliseconds: 16));
    expect(articleState(articleImageFailedSurfaceKey), findsOneWidget);
    expectStableArticleGeometry('loading → failure 不得触发重新分页');

    await tester.tap(articleState(articleImageRetryKey));
    await tester.pump();
    expect(articleState(articleImageDelayedIndicatorKey), findsOneWidget);
    expectStableArticleGeometry('failure → retry/loading（第二次）必须沿用原占位框');
    networkImage = tester.widget<AppCachedNetworkImage>(articleNetworkImage());
    networkImage.onLoadSucceeded!();
    await tester.pump(ImmersiveMediaWaitMotion.indicatorMinDisplay);
    await tester.pump(const Duration(milliseconds: 16));
    expect(articleState(articleImageFailedSurfaceKey), findsNothing);
    expect(
      tester
          .widget<AnimatedOpacity>(
            articleState(articleImagePresentedContentKey),
          )
          .opacity,
      1,
      reason: '最短展示窗口结束后图片内容必须进入 ready。',
    );
    await tester.pump(ImmersiveMediaWaitMotion.crossFade);
    await tester.pump(const Duration(milliseconds: 16));
    expect(
      articleState(articleImageDelayedIndicatorKey),
      findsNothing,
      reason: '交叉淡出完成后不得残留等待层。',
    );
    expectStableArticleGeometry('loading → success 不得触发重新分页');

    final progressBeforeOpen = _articleProgressLabel(tester);
    await tester.tap(articleGesture());
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.byKey(worksArticleImageViewerSurfaceKey), findsOneWidget);
    final openEvents = telemetry.recorded.where(
      (event) =>
          event.eventType == 'product_action' &&
          event.extensions['journey'] == 'article_reader' &&
          event.action == 'image_viewer_open',
    );
    expect(openEvents, hasLength(1));
    expect(openEvents.single.pageName, PageNames.workBrowser);
    expect(openEvents.single.extensions['objectId'], post.id);
    expect(openEvents.single.extensions['targetId'], 'article-image');

    final canvas = tester.widget<ImageBookCanvas>(find.byType(ImageBookCanvas));
    canvas.onMediaLoad!(
      const ImageBookMediaLoadEvent(
        result: 'success',
        durationMs: 12,
        candidatesTried: 1,
      ),
    );
    await tester.pump();

    final matchingImageViewerLoads = telemetry.recorded.where(
      (event) =>
          event.eventType == 'media_load_state' &&
          event.extensions['mediaType'] == 'image' &&
          event.extensions['result'] == 'success' &&
          event.extensions['objectId'] == post.id &&
          event.extensions['durationMs'] == 12 &&
          event.extensions['candidatesTried'] == 1,
    );
    expect(matchingImageViewerLoads, hasLength(1));
    final imageViewerLoad = matchingImageViewerLoads.single;
    expect(imageViewerLoad.pageName, PageNames.workBrowser);
    expect(
      imageViewerLoad.extensions['surfaceId'],
      AppUiSurfaces.workBrowser.id,
    );
    expect(imageViewerLoad.extensions['objectType'], 'contentPost');
    expect(imageViewerLoad.extensions['objectId'], post.id);
    expect(imageViewerLoad.extensions['durationMs'], 12);
    expect(imageViewerLoad.extensions['candidatesTried'], 1);

    await tester.tap(find.byKey(worksArticleImageViewerCloseKey));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.byKey(worksArticleImageViewerSurfaceKey), findsNothing);
    expect(_articleProgressLabel(tester), progressBeforeOpen);
    final closeEvents = telemetry.recorded.where(
      (event) =>
          event.eventType == 'product_action' &&
          event.extensions['journey'] == 'article_reader' &&
          event.action == 'image_viewer_close',
    );
    expect(closeEvents, hasLength(1));
    expect(closeEvents.single.pageName, PageNames.workBrowser);
    expect(closeEvents.single.extensions['objectId'], post.id);
    expect(closeEvents.single.extensions['targetId'], 'article-image');
  });

  testWidgets('文章交集句位于翻页指示器下方并保持在内容区底部', (tester) async {
    final post = _articlePost(
      intersectionReasons: <IntersectionReason>[
        _displayableIntersectionReason(
          dimension: 'article',
          primaryText: '联系人林清越读过并评论过',
          totalPointCount: 9,
          source: 'article_reader',
          actionTargetId: 'article-1',
        ),
      ],
    );

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: _articleMarkdownRaw(
              post,
              _multiPageArticleMarkdown(post, sections: 4),
            ),
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await _pumpSettledFrames(tester);

    final progressRect = tester.getRect(
      find.byKey(const ValueKey<String>('works-article-page-progress')),
    );
    final intersectionRect = tester.getRect(
      find.byKey(const ValueKey<String>('works-caption-intersection-reason')),
    );
    final toolbarRect = tester.getRect(find.byType(ImmersiveEngagementBar));

    expect(
      intersectionRect.top,
      greaterThan(progressRect.bottom),
      reason: '文章交集句应位于翻页指示器下方。',
    );
    expect(
      toolbarRect.top - intersectionRect.bottom,
      moreOrLessEquals(AppSpacing.intraGroupXs, epsilon: 1),
      reason: '文章交集句应贴近底部工具栏，但仍属于内容区。',
    );

    final viewerRect = tester.getRect(find.byType(WorksImmersiveViewer));
    final bottomRailRect = tester.getRect(
      find.byKey(const ValueKey('immersive-engagement-rail')),
    );
    final barContext = tester.element(find.byType(ImmersiveEngagementBar));
    final expectedSideInset = ImmersiveViewerLayout.horizontalPadding(
      barContext,
      layoutSpec: ImmersiveViewerStageLayoutSpec.articleStage,
    );

    expect(
      (intersectionRect.left - expectedSideInset).abs(),
      lessThan(1),
      reason: '文章交集句左缘应与正文/底栏共用 bottom chrome inset。',
    );
    expect(
      (viewerRect.right - intersectionRect.right - expectedSideInset).abs(),
      lessThan(1),
      reason: '文章交集句右缘应与正文/底栏共用 bottom chrome inset。',
    );
    expect((bottomRailRect.left - intersectionRect.left).abs(), lessThan(1));
    expect((bottomRailRect.right - intersectionRect.right).abs(), lessThan(1));
  });

  testWidgets('文章使用统一默认深色纸张且阅读设置可实时切换', (tester) async {
    final post = _articlePost();

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: _articleMarkdownRaw(
              post,
              _multiPageArticleMarkdown(post),
              extra: const <String, dynamic>{
                'articleRenderProfile': <String, dynamic>{
                  'template': 'journal',
                  'fontPreset': 'clean',
                  'paperThemeMode': 'system',
                },
              },
            ),
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await _pumpSettledFrames(tester);

    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget is ColoredBox &&
            widget.color == ArticlePaperPaletteColors.darkPaperPaper,
      ),
      findsWidgets,
    );
    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget is ColoredBox &&
            widget.color == ArticlePaperPaletteColors.darkPaperStage,
      ),
      findsNothing,
    );
    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget is ColoredBox &&
            widget.color == ArticlePaperPaletteColors.warmBlackStage,
      ),
      findsNothing,
    );

    await tester.tap(find.byKey(const ValueKey<String>('works-top-more')));
    await _pumpSettledFrames(tester);
    expect(find.text('阅读设置'), findsOneWidget);
    await tester.tap(find.text('阅读设置'));
    await _pumpSettledFrames(tester);
    expect(
      find.byKey(const ValueKey<String>('more-action-reading-settings-panel')),
      findsOneWidget,
    );
    await tester.tap(
      find.byKey(const ValueKey<String>('more-action-reading-theme-coolGray')),
    );
    await _pumpSettledFrames(tester);

    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget is ColoredBox &&
            widget.color == ArticlePaperPaletteColors.coolGrayPaper,
      ),
      findsWidgets,
    );
    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget is ColoredBox &&
            widget.color == ArticlePaperPaletteColors.coolGrayStage,
      ),
      findsNothing,
    );
  });

  testWidgets('文章实体标签点击进入 homepageDetail metadata 路由', (tester) async {
    final post = _articlePost();
    final detail = _articleMarkdownRaw(
      post,
      '---\n'
      'title: 杭州一日游\n'
      'template: journal\n'
      'fontPreset: clean\n'
      '---\n\n'
      '# 杭州一日游\n\n'
      '@[灵隐寺](entity:sight:west_lake)\n',
      extra: const <String, dynamic>{
        'entityMentions': <Map<String, dynamic>>[
          {
            'subjectType': 'entity',
            'subjectId': 'entity:sight:west_lake',
            'homepageId': 'homepage_sight_west_lake',
            'displayName': '灵隐寺',
            'rangeStart': 3,
            'rangeEnd': 6,
          },
        ],
      },
    );
    final repository = _ConfigurableContentDetailReader(
      detailById: <String, Map<String, dynamic>>{post.id: detail},
    );

    await tester.pumpWidget(
      _wrapWithRouter(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({post.id: detail}),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
        detailReader: repository,
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await _pumpSettledFrames(tester);

    final entityText = find.byKey(
      const ValueKey<String>('article-entity-rich-text'),
    );
    expect(entityText, findsWidgets);
    await _tapRichTextSubstring(tester, entityText.hitTestable().first, '灵隐寺');
    await _pumpSettledFrames(tester);

    expect(
      find.byKey(const ValueKey<String>('homepage-detail-probe')),
      findsOneWidget,
    );
    expect(find.text('homepage:homepage_sight_west_lake'), findsOneWidget);
  });

  testWidgets('文章未知实体标签不会把原始 entity id 推进主页错误页', (tester) async {
    final post = _articlePost();

    await tester.pumpWidget(
      _wrapWithRouter(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: _articleMarkdownRaw(
              post,
              '---\n'
              'title: 未知实体\n'
              'template: journal\n'
              'fontPreset: clean\n'
              '---\n\n'
              '# 未知实体\n\n'
              '@[未知地点](entity:photo_spot:unknown)\n',
              extra: const <String, dynamic>{
                'entityMentions': <Map<String, dynamic>>[
                  {
                    'subjectType': 'entity',
                    'subjectId': 'entity:photo_spot:unknown',
                    'homepageId': '',
                    'displayName': '未知地点',
                    'rangeStart': 3,
                    'rangeEnd': 7,
                  },
                ],
              },
            ),
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await _pumpSettledFrames(tester);

    final entityText = find.byKey(
      const ValueKey<String>('article-entity-rich-text'),
    );
    expect(entityText, findsWidgets);
    await _tapRichTextSubstring(tester, entityText.hitTestable().first, '未知地点');
    await _pumpSettledFrames(tester);

    expect(
      find.byKey(const ValueKey<String>('homepage-detail-probe')),
      findsNothing,
    );
    expect(find.textContaining('homepage:entity'), findsNothing);
  });

  testWidgets('文章标签内联点击进入按 tagRef 搜索的 metadata 路由', (tester) async {
    final post = _articlePost();

    await tester.pumpWidget(
      _wrapWithRouter(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: _articleMarkdownRaw(
              post,
              '---\n'
              'title: 城市漫步指南\n'
              'template: journal\n'
              'fontPreset: clean\n'
              '---\n\n'
              '# 城市漫步指南\n\n'
              '午后沿着@[城市漫步](tag:topic:city_walk)的路线散步。\n',
            ),
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await _pumpSettledFrames(tester);

    final mentionText = find.byKey(
      const ValueKey<String>('article-entity-rich-text'),
    );
    expect(mentionText, findsWidgets);
    await _tapRichTextSubstring(
      tester,
      mentionText.hitTestable().first,
      '城市漫步',
    );
    await _pumpSettledFrames(tester);

    expect(
      find.byKey(const ValueKey<String>('search-network-probe')),
      findsOneWidget,
    );
    expect(find.text('search:topic:city_walk'), findsOneWidget);
  });

  testWidgets('文章阅读不显示底部 caption rail 且页码只保留正文下方一处', (tester) async {
    final post = _articlePost();

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: _articleMarkdownRaw(post, _multiPageArticleMarkdown(post)),
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await _pumpSettledFrames(tester);

    expect(
      find.byKey(const ValueKey<String>('works-top-progress-label')),
      findsNothing,
    );
    expect(
      find.byKey(const ValueKey<String>('works-article-page-progress')),
      findsOneWidget,
    );
    final progressLabel = _articleProgressLabel(tester);
    expect(progressLabel, startsWith('1 / '));
    expect(progressLabel, isNot(UITextConstants.workArticlePageProgress(1, 1)));
    expect(
      find.byKey(const ValueKey<String>('works-caption-rail')),
      findsNothing,
    );
  });

  testWidgets('文章阅读纸面页头展示创作与更新时间语义', (tester) async {
    final post = _articlePost(
      createdAt: DateTime(2025, 5, 15),
      updatedAt: DateTime(2025, 6, 20),
    );

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: _articleMarkdownRaw(post, _multiPageArticleMarkdown(post)),
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await _pumpSettledFrames(tester);

    expect(find.textContaining('创作于'), findsWidgets);
    expect(find.textContaining('更新于'), findsWidgets);
  });

  testWidgets('文章阅读支持页角热区翻页', (tester) async {
    final post = _articlePost();

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: _articleMarkdownRaw(post, _multiPageArticleMarkdown(post)),
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await _pumpSettledFrames(tester);

    expect(find.byType(ArticleReaderFlipHost), findsOneWidget);
    expect(find.byKey(TestKeys.articlePageCurlLayer), findsOneWidget);

    // 页角热区向内拖拽会揭开相邻页：断言页码前进（翻页行为本身）。
    // 不绑定特定小节落在第几页——页容量由渲染几何单源决定（GWT-015），
    // 内容分布断言会随几何修正漂移。
    final deckRect = tester.getRect(find.byType(ArticleReadOnlyBookDeck));
    await tester.dragFrom(
      Offset(deckRect.right - 2, deckRect.bottom - 80),
      const Offset(-260, -40),
    );
    await _pumpSettledFrames(tester);

    _expectArticleAdvancedPastFirstPage(tester);
  });

  testWidgets('长文阅读会自动降级为 book-style pager', (tester) async {
    final post = _articlePost();
    // 触发页数 > maxPageCurlPages(80) 的长文：以足量长正文小节驱动排版流分页，
    // markdown-only 后不再用 cards 借壳页数。
    final longMarkdown = _multiPageArticleMarkdown(
      post,
      sections: 420,
      paragraphsPerSection: 6,
    );

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: _articleMarkdownRaw(post, longMarkdown),
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await _pumpSettledFrames(tester);

    expect(find.byKey(TestKeys.articleBookStylePager), findsOneWidget);
    expect(find.byKey(TestKeys.articlePageCurlLayer), findsNothing);
  });

  testWidgets('沉浸文章宿主消费远端 page curl=false 后进入既有分页器且保持可读', (tester) async {
    final post = _articlePost();
    final analytics = _FakeAnalyticsService();
    final configRepository = _ConfigurableContentConfigRepository(
      appConfig: <String, dynamic>{
        'content': <String, dynamic>{
          'feature_flags': <String, dynamic>{
            'enable_article_book_reader': true,
            'enable_article_page_curl': false,
          },
        },
      },
    );

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: _articleMarkdownRaw(post, _multiPageArticleMarkdown(post)),
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
        overrides: [analyticsProvider.overrideWithValue(analytics)],
        useProductionRuntimeConfig: true,
        configRepository: configRepository,
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await _pumpSettledFrames(tester);

    expect(find.byType(ArticleReadOnlyBookDeck), findsOneWidget);
    expect(find.byKey(TestKeys.articleBookStylePager), findsOneWidget);
    expect(find.byKey(TestKeys.articlePageCurlLayer), findsNothing);

    final progressBeforeStep = _articleProgressLabel(tester);
    await tester.tap(
      find.byKey(const ValueKey<String>('works-article-page-next')),
    );
    await _pumpSettledFrames(tester);
    expect(_articleProgressLabel(tester), isNot(progressBeforeStep));

    final fallbackEvents = analytics.events.where(
      (event) =>
          event.eventName == 'article_reader_fallback_rate' &&
          event.properties['reason'] == 'page_curl_disabled',
    );
    expect(fallbackEvents, hasLength(1));
  });

  testWidgets('文章 book reader 总开关关闭时仍使用统一阅读器并上报 feature 关闭 fallback', (
    tester,
  ) async {
    final post = _articlePost();
    final analytics = _FakeAnalyticsService();
    final configRepository = _ConfigurableContentConfigRepository(
      appConfig: <String, dynamic>{
        'content': <String, dynamic>{
          'feature_flags': <String, dynamic>{
            'enable_article_book_reader': false,
            'enable_article_page_curl': true,
          },
        },
      },
    );
    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: _articleMarkdownRaw(post, _multiPageArticleMarkdown(post)),
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
        overrides: [analyticsProvider.overrideWithValue(analytics)],
        useProductionRuntimeConfig: true,
        configRepository: configRepository,
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await _pumpSettledFrames(tester);

    expect(find.byType(ArticleReadOnlyBookDeck), findsOneWidget);
    expect(find.byKey(TestKeys.articlePageCurlLayer), findsOneWidget);

    await _flipArticleToLastPage(tester);
    _expectArticleAdvancedPastFirstPage(tester);
    final fallbackEvent = analytics.events.firstWhere(
      (event) => event.eventName == 'article_reader_fallback_rate',
    );
    expect(fallbackEvent.properties['reason'], equals('feature_flag_disabled'));
  });

  testWidgets('文章摘要快照会异步水合详情并上报 hydration 埋点', (tester) async {
    final post = _articlePost();
    final analytics = _FakeAnalyticsService();
    final repo = _ConfigurableContentDetailReader(
      detailById: <String, Map<String, dynamic>>{
        post.id: <String, dynamic>{
          'postId': post.id,
          'contentType': 'article',
          'authorId': post.authorId,
          'authorDisplayName': post.displayName,
          'authorAvatarUrl': post.avatarUrl,
          'title': '水合后的标题',
          'body': '水合后的正文第一段。\n\n水合后的正文第二段。',
          'coverUrl': post.coverUrl,
          'articleTemplate': post.articleTemplate,
          'articleFontPreset': post.articleFontPreset,
          'articleMarkdown':
              '---\n'
              'title: 水合后的标题\n'
              'template: ${post.articleTemplate}\n'
              'fontPreset: ${post.articleFontPreset}\n'
              '---\n\n'
              '## 水合章节\n\n'
              '水合后的正文第一段。\n\n'
              '水合后的正文第二段。\n',
          'markdownDialect': 'qwq-rich-md',
          'articleAssetManifest': const <String, dynamic>{
            'schema': 'article-asset-manifest',
            'markdownDialect': 'qwq-rich-md',
            'articleMarkdownDigest': 'fixture:hydrated',
            'assets': <Map<String, dynamic>>[],
          },
          'articleRenderProfile': <String, dynamic>{
            'template': post.articleTemplate,
            'fontPreset': post.articleFontPreset,
          },
        },
      },
    );
    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: <String, dynamic>{
              'postId': post.id,
              'contentType': 'article',
              'authorId': post.authorId,
              'authorDisplayName': post.displayName,
              'authorAvatarUrl': post.avatarUrl,
              'title': '分发标题',
              'body': '分发摘要正文',
              'coverUrl': post.coverUrl,
            },
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
        overrides: [analyticsProvider.overrideWithValue(analytics)],
        detailReader: repo,
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await _pumpSettledFrames(tester);
    for (
      var attempt = 0;
      attempt < 40 && find.text('水合后的标题').evaluate().isEmpty;
      attempt += 1
    ) {
      await tester.pump(const Duration(milliseconds: 16));
      _consumeImageLoadExceptions(tester);
    }

    expect(repo.getPostCallCount, equals(1));
    final hydrationEvent = analytics.events.firstWhere(
      (event) => event.eventName == 'article_reader_hydration_ms',
    );
    expect(hydrationEvent.properties['result'], equals('success'));
    expect(find.text('水合后的标题'), findsWidgets);
    expect(find.textContaining('水合后的正文第一段'), findsWidgets);

    final structureFallback = analytics.events.firstWhere(
      (event) =>
          event.eventName == 'article_reader_fallback_rate' &&
          (event.properties['reason'] as String).startsWith(
            'document_structure:',
          ),
    );
    expect(structureFallback.properties['reason'], contains('empty'));
  });

  testWidgets('文章水合在滑到非文章作品时取消且迟到请求不进入错误态', (tester) async {
    final article = _articlePost();
    final photo = _photoPost().copyWith(id: 'photo-after-article');
    final analytics = _FakeAnalyticsService();
    final repo = _BlockingArticleHydrationRepository(
      lateSuccessDetail: <String, dynamic>{
        'contentType': 'article',
        'authorId': article.authorId,
        'authorDisplayName': article.displayName,
        'authorAvatarUrl': article.avatarUrl,
        'title': '迟到的水合标题',
        'articleMarkdown': '## 迟到章节\n\n迟到的水合正文。',
        'markdownDialect': 'qwq-rich-md',
      },
    );

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [article, photo],
          externalPostViews: [
            ContentSurfaceViewMapper.fromDto(article),
            ContentSurfaceViewMapper.fromDto(photo),
          ],
          rawPostsById: _viewerRawByPostId({
            article.id: <String, dynamic>{
              'postId': article.id,
              'contentType': 'article',
              'authorId': article.authorId,
              'authorDisplayName': article.displayName,
              'authorAvatarUrl': article.avatarUrl,
              'title': '分发标题',
              'body': '分发摘要正文',
              'coverUrl': article.coverUrl,
            },
            photo.id: _canonicalPostWire(photo),
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
        overrides: [analyticsProvider.overrideWithValue(analytics)],
        detailReader: repo,
      ),
    );
    await tester.pump();
    for (
      var attempt = 0;
      attempt < 20 && repo.startedPostIds.isEmpty;
      attempt += 1
    ) {
      await tester.pump(const Duration(milliseconds: 16));
    }
    expect(repo.startedPostIds, <String>[article.id]);

    final outerViewer = find.byWidgetPredicate(
      (widget) => widget is PageView && widget.scrollDirection == Axis.vertical,
    );
    expect(outerViewer, findsOneWidget);
    await tester.fling(outerViewer, const Offset(0, -700), 1200);
    await _pumpSettledFrames(tester);

    expect(repo.cancelledPostIds, <String>[article.id]);
    expect(repo.maxActiveRequests, 1);
    expect(repo.activeRequests, 0);
    expect(
      find.byKey(ValueKey<String>('article-hydration-error-${article.id}')),
      findsNothing,
    );
    expect(find.textContaining('迟到的水合正文'), findsNothing);
    expect(
      analytics.events.any(
        (event) =>
            event.eventName == 'article_reader_hydration_ms' &&
            event.properties['result'] == 'superseded',
      ),
      isTrue,
    );
  });

  testWidgets('文章详情水合 404 遵循 canonical contentUnavailable dismiss 终态', (
    tester,
  ) async {
    final post = _articlePost();
    final analytics = _FakeAnalyticsService();
    final repo = _ConfigurableContentDetailReader();

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: <String, dynamic>{
              'postId': post.id,
              'type': 'article',
              'contentType': 'article',
              'authorId': post.authorId,
              'authorDisplayName': post.displayName,
              'authorAvatarUrl': post.avatarUrl,
              'title': '分发标题',
              'body': '分发摘要正文',
              'coverUrl': post.coverUrl,
            },
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
        overrides: [analyticsProvider.overrideWithValue(analytics)],
        detailReader: repo,
      ),
    );

    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await _pumpSettledFrames(tester);

    expect(repo.getPostCallCount, equals(1));
    expect(
      find.byKey(ValueKey<String>('article-hydration-error-${post.id}')),
      findsOneWidget,
    );

    await tester.pump();
    await _pumpSettledFrames(tester);
    expect(repo.getPostCallCount, equals(1));

    final hydrationEvent = analytics.events.firstWhere(
      (event) => event.eventName == 'article_reader_hydration_ms',
    );
    expect(hydrationEvent.properties['result'], equals('error'));

    final errorState = tester.widget<AppPageErrorState>(
      find.byKey(ValueKey<String>('article-hydration-error-${post.id}')),
    );
    expect(
      errorState.semantic.userRecoveryGroup,
      AppUserRecoveryGroup.contentUnavailable,
    );
    expect(errorState.semantic.primaryAction?.type, UiErrorActionType.dismiss);
    final recoveryOutcome = await errorState.onRecovery!(
      errorState.semantic.primaryAction!,
    );

    expect(recoveryOutcome, UiRecoveryOutcome.cancelled);
    expect(repo.getPostCallCount, equals(1));
    expect(
      find.byKey(ValueKey<String>('article-hydration-error-${post.id}')),
      findsOneWidget,
    );
  });

  testWidgets('沉浸式阅读器中的文章回翻保持统一 book deck 宿主', (tester) async {
    final post = _articlePost();

    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: [post],
          externalPostViews: [ContentSurfaceViewMapper.fromDto(post)],
          rawPostsById: _viewerRawByPostId({
            post.id: _articleMarkdownRaw(post, _multiPageArticleMarkdown(post)),
          }),
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
        ),
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await _pumpSettledFrames(tester);

    expect(find.byType(ArticleReadOnlyBookDeck), findsOneWidget);
    expect(find.byKey(TestKeys.articlePageCurlLayer), findsOneWidget);

    await tester.dragFrom(
      tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomRight)),
      const Offset(-260, -40),
    );
    await _pumpSettledFrames(tester);
    await tester.dragFrom(
      tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomLeft)),
      const Offset(260, -40),
    );
    await _pumpSettledFrames(tester);

    expect(find.byType(ArticleReadOnlyBookDeck), findsOneWidget);
    expect(find.byKey(TestKeys.articlePageCurlLayer), findsOneWidget);
  });
}
