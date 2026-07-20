import 'dart:async';
import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart' show RenderObject, RenderParagraph;
import 'package:flutter/services.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/media/media_download_cache.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/source_attribution_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_representative_actor.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_target.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_visual.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_app_config_wire.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_detail_payload.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/cloud/services/content/feed_item_discovery_wire_map.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart'
    show ActivePersonaContextViewData;
import '../../../../support/cloud_services/content/content_mock_data.dart';
import 'package:quwoquan_app/components/media/image/book/image_book_canvas.dart';
import 'package:quwoquan_app/components/media/shared/pageflip/media_page_flip_book.dart';
import 'package:quwoquan_app/components/media/shared/viewer/media_caption_widgets.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/di/app_data_source_mode.dart';
import 'package:quwoquan_app/core/auth/auth_continuation.dart';
import 'package:quwoquan_app/core/auth/auth_gate.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/constants/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/core/trackers/content_engagement_tracker.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/icons/app_custom_icons.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/components/media/shared/toolbar/immersive_engagement_bar.dart';
import 'package:quwoquan_app/components/media/shared/viewer/immersive_viewer_layout.dart';
import 'package:quwoquan_app/components/media/video/player/video_player_widget.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/host/article_read_only_book_deck.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/host/article_reader_flip_host.dart';
import 'package:quwoquan_app/ui/discovery/pages/unified_media_viewer_page.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view_mapper.dart';
import 'package:quwoquan_app/ui/content/widgets/article_paged_canvas.dart';
import 'package:quwoquan_app/ui/discovery/providers/discovery_feed_provider.dart';
import 'package:quwoquan_app/ui/discovery/widgets/works_immersive_viewer.dart';
import 'package:video_player_platform_interface/video_player_platform_interface.dart';
import '../../../../support/cloud_services/content_facet_overrides.dart';
import '../../../../support/video/fake_video_player_platform.dart';
import '../../../../support/cloud_services/content/mock_content_repository.dart';
import '../../../../support/sqflite_ffi_test_support.dart';

Map<String, MediaViewerPostWireRow> _viewerRawByPostId(
  Map<String, Map<String, dynamic>> raw,
) => raw.map(
  (id, row) => MapEntry(id, MediaViewerPostWireRow.fromDynamicMap(row)),
);

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
  return IntersectionReason(
    intersectionId: intersectionId,
    dimension: dimension,
    primaryText: text,
    displayBinding: displayBinding,
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
      relationLabel: '联系人',
      privacyState: 'visible',
      target: _intersectionTargetFor(objectKind: 'person', objectId: 'u_lin'),
    ),
  );
}

IntersectionTextSpan _plain(String text) => IntersectionTextSpan(text: text);

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

class _ConfigurableContentRepository extends MockContentRepository {
  _ConfigurableContentRepository({
    this.appConfig,
    this.detailById = const <String, Map<String, dynamic>>{},
  });

  final Map<String, dynamic>? appConfig;
  final Map<String, Map<String, dynamic>> detailById;
  int getPostCallCount = 0;

  @override
  Future<ContentAppConfigWire> getAppConfig() async {
    if (appConfig != null) {
      return ContentAppConfigWire.fromResponseObject(
        Map<String, dynamic>.from(appConfig!),
      );
    }
    return super.getAppConfig();
  }

  @override
  Future<ContentPostDetailPayload> getPost({required String postId}) async {
    getPostCallCount += 1;
    final detail = detailById[postId];
    if (detail != null) {
      return ContentPostDetailPayload.fromWire(
        Map<String, dynamic>.from(detail),
      );
    }
    return super.getPost(postId: postId);
  }
}

class _PagedFeaturedContentRepository extends MockContentRepository {
  _PagedFeaturedContentRepository();

  final int pageSize = 2;
  final Duration appendDelay = const Duration(seconds: 4);
  int appendCallCount = 0;

  List<PostBaseDto> _postsForCategory(String category) {
    List<FeedItemDto> source;
    switch (category) {
      case 'photo':
        source = ContentMockData.discoveryPhotoData
            .take(4)
            .toList(growable: false);
        break;
      case 'video':
        source = ContentMockData.discoveryVideoData
            .take(4)
            .toList(growable: false);
        break;
      case 'article':
        source = ContentMockData.discoveryArticleData
            .take(4)
            .toList(growable: false);
        break;
      default:
        return const <PostBaseDto>[];
    }
    return source
        .map((item) => postBaseDtoFromMap(item.toDiscoveryWireMap()))
        .toList(growable: false);
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

class _RemoteModeNotifier extends AppDataSourceModeNotifier {
  @override
  AppDataSourceMode build() => AppDataSourceMode.remote;
}

class _AuthenticatedViewerSession extends AuthSessionController {
  @override
  AuthSessionState build() {
    return const AuthSessionState(
      status: AuthSessionStatus.authenticated,
      accessToken: 'viewer-test-token',
      ownerId: 'viewer-test-owner',
      activeSubAccountId: 'viewer-test-persona',
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
      ownerId: 'viewer-resume-owner',
      activeSubAccountId: 'viewer-resume-persona',
    );
  }
}

class _RecordingContentReportWriter implements ContentReportCommandWriter {
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
  Future<ContentMediaOriginalAccessGrant> requestOriginalAccess(
    RequestContentMediaOriginalAccessCommand command,
  ) async {
    requestedMediaIds.add(command.mediaId);
    return ContentMediaOriginalAccessGrant(
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

PhotoPostDto _photoPost({
  List<String> imageUrls = const ['media/image/s/fixture/photo.jpg'],
  int? width,
  int? height,
  List<IntersectionReason>? intersectionReasons,
}) {
  return PhotoPostDto(
    id: 'photo-1',
    type: 'image',
    identity: 'work',
    assistantUsePolicy: 'inherit',
    authorId: 'author-1',
    displayName: '摄影师',
    avatarUrl: 'https://example.com/avatar.jpg',
    authorRoleLabel: '',
    authorIdentityTags: const <String>[],
    authorVerified: false,
    body: 'dto body',
    coverUrl: 'media/image/s/fixture/photo.jpg',
    imageUrls: imageUrls,
    width: width,
    height: height,
    likeCount: 0,
    commentCount: 0,
    shareCount: 0,
    createdAt: DateTime.now(),
    intersectionReasons: intersectionReasons,
  );
}

VideoPostDto _videoPost({
  int? width,
  int? height,
  String body = 'video body',
  String videoUrl =
      'media/video/s/video-primary-0001/post/video-content-0001/source.mp4',
  String coverUrl =
      'media/image/s/archived-image/post/fixture_video_001/v1/cover.png',
  SourceAttributionDto? sourceAttribution,
  List<IntersectionReason>? intersectionReasons,
}) {
  return VideoPostDto(
    id: 'video-1',
    type: 'video',
    identity: 'work',
    assistantUsePolicy: 'inherit',
    authorId: 'author-video',
    displayName: '视频作者',
    avatarUrl: '',
    authorRoleLabel: '',
    authorIdentityTags: const <String>[],
    authorVerified: false,
    body: body,
    sourceAttribution: sourceAttribution,
    videoUrl: videoUrl,
    thumbnailUrl: coverUrl,
    coverUrl: coverUrl,
    width: width,
    height: height,
    durationMs: 125000,
    likeCount: 0,
    commentCount: 0,
    shareCount: 0,
    createdAt: DateTime.now(),
    intersectionReasons: intersectionReasons,
  );
}

ArticlePostDto _articlePost({List<IntersectionReason>? intersectionReasons}) {
  return ArticlePostDto(
    id: 'article-1',
    type: 'article',
    identity: 'work',
    assistantUsePolicy: 'inherit',
    authorId: 'author-3',
    displayName: '写作者',
    avatarUrl: 'https://example.com/avatar-3.jpg',
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
    createdAt: DateTime.now(),
    intersectionReasons: intersectionReasons,
  );
}

/// 生成确定性多页文章 markdown（唯一内容真相源）。
/// 替代旧 `cards` 借壳分页：markdown-only 契约下，多页由排版流引擎按视口高度切分。
String _multiPageArticleMarkdown(
  ArticlePostDto post, {
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
  ArticlePostDto post,
  String markdown, {
  Map<String, dynamic> extra = const <String, dynamic>{},
}) {
  return <String, dynamic>{
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

MicroPostDto _textMoment({List<IntersectionReason>? intersectionReasons}) {
  return MicroPostDto(
    id: 'moment-1',
    type: 'micro',
    identity: 'moment',
    assistantUsePolicy: 'inherit',
    authorId: 'author-2',
    displayName: '圈友',
    avatarUrl: 'https://example.com/avatar-2.jpg',
    authorRoleLabel: '',
    authorIdentityTags: const <String>[],
    authorVerified: false,
    body: '今天风有点大，大家从南门集合。',
    imageUrls: const <String>[],
    likeCount: 0,
    commentCount: 0,
    shareCount: 0,
    createdAt: DateTime.now(),
    intersectionReasons: intersectionReasons,
  );
}

Widget _wrap(
  Widget child, {
  List overrides = const [],
  bool useRemoteMode = false,
  double? textScaleFactor,
  EdgeInsets? viewPadding,
  MockContentRepository? contentRepository,
}) {
  final allOverrides = [
    ...mockContentFacetOverrides(contentRepository ?? MockContentRepository()),
    if (!useRemoteMode)
      contentRuntimeConfigProvider.overrideWithValue(
        buildAlphaContentRuntimeConfigDefaults(),
      ),
    ...overrides,
    if (useRemoteMode)
      appDataSourceModeProvider.overrideWith(_RemoteModeNotifier.new),
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

final class _NoopMediaDownloadCache extends MediaDownloadCache {
  _NoopMediaDownloadCache() : super();

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

Widget _wrapWithRouter(Widget child, {List overrides = const []}) {
  final router = GoRouter(
    routes: [
      GoRoute(
        path: '/',
        builder: (context, state) => Scaffold(body: child),
      ),
      GoRoute(
        path: '/user/:username',
        builder: (context, state) => Text(
          'user:${state.pathParameters['username']}',
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
      ...mockContentFacetOverrides(MockContentRepository()),
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

  final PostBaseDto post;
  final Map<String, dynamic> rawRow;
  final Duration revealDelay;

  @override
  State<_DeferredPostWorksViewer> createState() =>
      _DeferredPostWorksViewerState();
}

class _DeferredPostWorksViewerState extends State<_DeferredPostWorksViewer> {
  List<PostBaseDto> _posts = const <PostBaseDto>[];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      await Future<void>.delayed(widget.revealDelay);
      if (!mounted) {
        return;
      }
      setState(() {
        _posts = <PostBaseDto>[widget.post];
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
          'lib/ui/discovery/widgets/works_immersive_viewer.dart',
        ).readAsStringSync() +
        File(
          'lib/ui/discovery/widgets/works_immersive_viewer_build.dart',
        ).readAsStringSync() +
        File(
          'lib/ui/discovery/widgets/works_immersive_viewer_canvas.dart',
        ).readAsStringSync() +
        File(
          'lib/ui/discovery/widgets/works_immersive_viewer_lifecycle.dart',
        ).readAsStringSync();
    final imageBookSource = File(
      'lib/components/media/image/book/image_book_canvas.dart',
    ).readAsStringSync();
    final mediaPageflipSource = File(
      'lib/components/media/shared/pageflip/media_page_flip_book.dart',
    ).readAsStringSync();
    final videoPlayerSource = File(
      'lib/components/media/video/player/video_player_widget.dart',
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
      contains('allowImplicitScrolling: false'),
      reason: '视频书滚动性能优先：不提前构建相邻视频页。',
    );
    expect(
      viewerSource,
      contains('final keepAlive = widget.isVisible && isCurrent'),
      reason: '视频书只保活当前可见帖子的当前视频页，切页后释放非活跃页。',
    );
    expect(
      viewerSource,
      contains('isVisible: index == _currentPage'),
      reason: '外层 PageView 预建相邻帖子时，非可见视频帖子不得初始化 decoder。',
    );
    expect(
      viewerSource,
      contains('initialize: widget.isVisible && isCurrent'),
      reason: '只有当前可见帖子内的当前分集可以创建 VideoPlayerController。',
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
    final files = Directory('lib/ui/discovery/widgets')
        .listSync()
        .whereType<File>()
        .where(
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
    final container = ProviderContainer(
      overrides: [
        ...mockContentFacetOverrides(repo),
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

  testWidgets('视频书顶部仅保留返回与更多入口（V1.0 取消形态分段与一级 tab）', (tester) async {
    final repo = _PagedFeaturedContentRepository();
    final container = ProviderContainer(
      overrides: [...mockContentFacetOverrides(repo)],
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

    // V1.0：顶部仅保留「返回 + 更多」，禁止形态分段 / 一级 tab。
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
    final container = ProviderContainer();

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
                dtoPosts: <PostBaseDto>[post],
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
                  scopeProfileIds: <String>{post.subAccountId},
                  followingUsers: <String>{post.subAccountId},
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
    expect(relationshipState.isFollowing(post.subAccountId), isTrue);
    expect(postInteractionState.isLiked(post.id), isTrue);
    expect(postInteractionState.commentCountFor(post.id), 4);
    expect(postInteractionState.shareCountFor(post.id), 3);

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    container.dispose();
  });

  testWidgets('UnifiedMediaViewerPage 文章底部工具栏沿统一安全轨道收口', (tester) async {
    final post = _articlePost();
    final container = ProviderContainer();

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
                dtoPosts: <PostBaseDto>[post],
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
    final barContext = tester.element(barFinder);
    final expectedSideInset =
        AppSpacing.containerLg +
        AppSpacing.appChromeBottomSafeSideInset(barContext, 34);

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
    // V1.0：禁止顶部页码；多图导航使用点指示器（内容下方、标题上方）。
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
      imageUrls: const ['media/image/s/fixture/home-second.jpg'],
    ).copyWith(id: 'photo-2', body: 'second body');

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
      imageUrls: const ['media/image/s/fixture/photo-second.jpg'],
    ).copyWith(id: 'photo-2', body: 'second body');
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
      sourceAttribution: SourceAttributionDto(
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
      find.byKey(
        const ValueKey<String>('works-video-source-attribution'),
      ),
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
            widget.properties.label ==
                UITextConstants.videoPlaybackProgressLabel &&
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
          contentFeatureFlagProvider(
            'enable_shared_video_timeline',
          ).overrideWith((ref) => false),
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
            widget.properties.label ==
                UITextConstants.videoPlaybackProgressLabel &&
            widget.properties.value == '0:00 / 2:05',
      ),
      findsOneWidget,
    );
  });

  testWidgets('切集为每个分集重新开启一次五秒窗口', (tester) async {
    _installImmersiveVideoTestPlatform();
    final post = _videoPost(width: 1920, height: 1080, coverUrl: '');
    final raw = _viewerRawByPostId({
      post.id: <String, dynamic>{
        ...post.toMap(),
        'workId': post.id,
        'workType': 'video',
        'workIdentity': 'work',
        'caption': post.body,
        'mediaItems': <Map<String, dynamic>>[
          <String, dynamic>{
            'kind': 'video',
            'url': 'media/video/s/video-series-001/post/video-1/episode-1.mp4',
            'durationMs': 125000,
          },
          <String, dynamic>{
            'kind': 'video',
            'url': 'media/video/s/video-series-001/post/video-1/episode-2.mp4',
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
          'url': 'media/video/s/video-series-001/post/video-1/episode-1.mp4',
          'durationMs': 125000,
        },
        <String, dynamic>{
          'kind': 'video',
          'url': 'media/video/s/video-series-001/post/video-1/episode-2.mp4',
          'durationMs': 125000,
        },
      ];
      return _viewerRawByPostId({
        post.id: <String, dynamic>{
          ...post.toMap(),
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
      'lib/ui/discovery/widgets/works_immersive_viewer_controls.dart',
    ).readAsStringSync();
    final chromeSource = File(
      'lib/ui/discovery/widgets/works_immersive_viewer_video_chrome.dart',
    ).readAsStringSync();
    final canvasSource = File(
      'lib/ui/discovery/widgets/works_immersive_viewer_canvas.dart',
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
        'lib/ui/discovery/widgets/works_immersive_viewer_lifecycle.dart',
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
    final expectedBottomInset =
        ImmersiveViewerLayout.bottomChromeHorizontalPadding(
          barContext,
          layoutSpec: ImmersiveViewerStageLayoutSpec.mediaStage,
        );
    expect((bottomRailRect.left - expectedBottomInset).abs(), lessThan(1));
    expect(
      (viewerRect.right - bottomRailRect.right - expectedBottomInset).abs(),
      lessThan(1),
    );
  });

  testWidgets('首帧帖子延后就绪时 follow 按钮随工具栏常驻可见（V1.0 无定时）', (tester) async {
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
    // V1.0：关注按钮随工具栏常驻，不再有出现定时。
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
    // V1.0：详情 sheet 为「为什么推荐给你」+ ✓ 证据列表。
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
    final behaviorRepo = MockBehaviorRepository();
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
            IntersectionTextSpan(text: '联系人'),
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
            IntersectionTextSpan(text: '收藏过'),
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
        .where((event) => event.action == BehaviorAction.tagClick)
        .toList(growable: false);
    expect(clicks, hasLength(1));
    final click = clicks.single;
    expect(click.feedRequestId, isNotNull);
    expect(click.feedRequestId!.trim(), isNotEmpty);
    expect(click.referralSource, ReferralSource.organicFeed);
    expect(click.intersectionId, 'ix_works_span');
    expect(click.intersectionSourceRef, 'sharedFollowees');
    expect(click.intersectionEvidenceId, 'ev_works_span');
    expect(click.intersectionClass, 'fact');
    expect(
      AppRoutePaths.userProfile(username: 'u_lin'),
      startsWith('/user/u_lin'),
    );
  });

  testWidgets('视频书交集显式对象 span 点击进入主页并透传归因', (tester) async {
    final behaviorRepo = MockBehaviorRepository();
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
            IntersectionTextSpan(text: '联系人'),
            IntersectionTextSpan(
              text: '林清越',
              role: 'object',
              target: _intersectionTargetFor(
                objectKind: 'person',
                objectId: 'u_lin',
              ),
            ),
            IntersectionTextSpan(text: '收藏过「'),
            IntersectionTextSpan(
              text: '剑门关',
              role: 'object',
              target: _intersectionTargetFor(
                objectKind: 'place',
                objectId: 'hp_jianmen',
              ),
            ),
            IntersectionTextSpan(text: '」'),
          ],
          totalPointCount: 2,
          source: 'coLikedEntity',
          tagRefs: const <String>['place/jianmen'],
          intersectionClass: 'fact',
          pointSummarySnapshotId: 'ev_works_fallback',
          sampleVisuals: <IntersectionVisual>[
            IntersectionVisual(
              assetKind: 'coverImage',
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
        .where((event) => event.action == BehaviorAction.tagClick)
        .toList(growable: false);
    expect(clicks, hasLength(1));
    final click = clicks.single;
    expect(click.feedRequestId, isNotNull);
    expect(click.feedRequestId!.trim(), isNotEmpty);
    expect(click.intersectionSourceRef, 'coLikedEntity');
    expect(click.intersectionEvidenceId, 'ev_works_fallback');
    expect(click.intersectionDimension, 'place');
    expect(
      AppRoutePaths.homepageDetail(id: 'hp_jianmen'),
      startsWith('/homepages/hp_jianmen'),
    );
  });

  testWidgets('视频书交集显式行动对象 span 点击进入对象并透传归因', (tester) async {
    final behaviorRepo = MockBehaviorRepository();
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
            IntersectionTextSpan(text: '联系人'),
            IntersectionTextSpan(
              text: '林清越',
              role: 'object',
              target: _intersectionTargetFor(
                objectKind: 'person',
                objectId: 'u_lin',
              ),
            ),
            IntersectionTextSpan(text: '也想去「'),
            IntersectionTextSpan(
              text: '滇池路线',
              role: 'object',
              target: _intersectionTargetFor(
                objectKind: 'route',
                objectId: 'hp_route_dianchi',
              ),
            ),
            IntersectionTextSpan(text: '」'),
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
        .where((event) => event.action == BehaviorAction.tagClick)
        .toList(growable: false);
    expect(clicks, hasLength(1));
    final click = clicks.single;
    expect(click.contentId, 'hp_route_dianchi');
    expect(click.contentType, 'route');
    expect(click.feedRequestId, isNotNull);
    expect(click.feedRequestId!.trim(), isNotEmpty);
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
    final originalUrl = Uri.parse(
      'https://cdn.example.com/original/photo-1.jpg',
    );
    final mediaFacet = _RecordingContentMediaFacet(originalUrl);
    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: <PostBaseDto>[post],
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
    expect(find.text(UITextConstants.viewOriginal), findsOneWidget);

    await tester.tap(find.text(UITextConstants.viewOriginal));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 32));
    _consumeImageLoadExceptions(tester);

    expect(mediaFacet.requestedMediaIds, <String>['asset-photo-1']);
    expect(
      tester.widget<ImageBookCanvas>(find.byType(ImageBookCanvas)).imageUrls,
      <String>[originalUrl.toString()],
    );
    expect(find.text(UITextConstants.imageOriginalLoaded), findsOneWidget);
  });

  testWidgets('沉浸举报登录成功后续接原 post 且关闭登录走安全首页', (tester) async {
    AuthGate.resetDebounce();
    await tester.binding.setSurfaceSize(const Size(375, 812));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final post = _photoPost();
    final reportWriter = _RecordingContentReportWriter();
    final reporter = MockBehaviorRepository();
    final behaviorTracker = ContentBehaviorTracker(
      reporter: reporter,
      enablePeriodicFlush: false,
    );
    final engagementTracker = ContentEngagementTracker(reporter: reporter);
    addTearDown(behaviorTracker.dispose);
    addTearDown(engagementTracker.dispose);
    final container = ProviderContainer(
      overrides: [
        ...mockContentFacetOverrides(MockContentRepository()),
        authSessionControllerProvider.overrideWith(_FlippableViewerSession.new),
        workBrowserContentReportCommandWriterProvider.overrideWithValue(
          reportWriter,
        ),
        contentBehaviorTrackerProvider.overrideWithValue(behaviorTracker),
        contentEngagementTrackerProvider.overrideWithValue(engagementTracker),
        activePersonaContextProvider.overrideWith(
          (_) async => ActivePersonaContextViewData.fallback(
            subAccountId: 'viewer-test-persona',
            ownerUserId: 'viewer-test-owner',
            displayName: 'Viewer',
            avatarUrl: '',
          ),
        ),
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
              externalPosts: <PostBaseDto>[post],
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
    await tester.ensureVisible(find.text(UITextConstants.report));
    await tester.pump();
    await tester.tap(find.text(UITextConstants.report));
    final selectedReason = find.text(UITextConstants.profileReportReasonSpam);
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
    expect(reportContinuation.reason, ContentReportReason.spam);
    expect(
      GoRouterState.of(
        tester.element(
          find.byKey(const ValueKey<String>('viewer-report-login')),
        ),
      ).uri.queryParameters[loginGuestDismissPopQueryParam],
      LoginDismissPolicy.safeFallback.name,
    );

    (container.read(authSessionControllerProvider.notifier)
            as _FlippableViewerSession)
        .loginNow();
    router.pop();
    await _pumpSettledFrames(tester);
    await tester.pump();

    expect(reportWriter.commands, hasLength(1));
    expect(reportWriter.commands.single.targetId, post.id);
    expect(container.read(authContinuationProvider), isNull);
  });

  testWidgets('external 空内容六秒后提供可退出状态而非永久 spinner', (tester) async {
    var dismissed = false;
    await tester.pumpWidget(
      _wrap(
        WorksImmersiveViewer(
          showWorksToolbar: true,
          showTopNavigation: false,
          externalPosts: const <PostBaseDto>[],
          externalPostViews: const <ContentSurfaceView>[],
          onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
          onAssistantTap: () {},
          onDismissed: (_) => dismissed = true,
        ),
      ),
    );
    await tester.pump();

    expect(find.byType(CupertinoActivityIndicator), findsWidgets);
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
    expect(find.text(UITextConstants.contentUnavailable), findsOneWidget);

    await tester.tap(find.text(UITextConstants.back));
    await tester.pump();
    expect(dismissed, isTrue);
  });

  testWidgets('canonical viewer 最后一条内容仅结算一次 dwell 并保留入口归因', (tester) async {
    final reporter = MockBehaviorRepository();
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
          externalPosts: <PostBaseDto>[post],
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
              event.action == BehaviorAction.impression &&
              event.state == 'visible',
        )
        .toList(growable: false);
    final dwells = reporter.recorded
        .where(
          (event) =>
              event.contentId == post.id &&
              event.action == BehaviorAction.dwell,
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
    ).copyWith(coverUrl: '', avatarUrl: '');
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
      imageUrls: const ['media/image/s/fixture/photo-3.jpg'],
    ).copyWith(id: 'photo-2', body: 'second body');
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
      imageUrls: const ['media/image/s/fixture/photo-3.jpg'],
    ).copyWith(id: 'photo-2', body: 'second body');
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
      imageUrls: const ['media/image/s/fixture/photo-next.jpg'],
    ).copyWith(id: 'photo-2', body: 'next photo body');
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

    // V1.0：页码两侧 chevron `‹ ›` 可点切页（正文后、作者工具栏前）。
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
    final container = ProviderContainer(
      overrides: [...mockContentFacetOverrides(MockContentRepository())],
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

  testWidgets('文章阅读使用底部页码且封面与标题正文共用第一页', (tester) async {
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
    // V1.0：文章页码在正文下方、作者工具栏上方，禁止顶部页码与点指示器。
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
    expect(find.textContaining('第一页前言'), findsWidgets);

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
    final expectedSideInset =
        ImmersiveViewerLayout.bottomChromeHorizontalPadding(
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

  testWidgets('文章按垂类默认使用深色纸张且阅读设置可实时切换', (tester) async {
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
                'contentVertical': 'travel',
                'articleRenderProfile': <String, dynamic>{
                  'template': 'journal',
                  'fontPreset': 'clean',
                  'contentVertical': 'travel',
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
            widget.color == ArticlePaperPaletteColors.warmBlackPaper,
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
              'title: 杭州一日游\n'
              'template: journal\n'
              'fontPreset: clean\n'
              '---\n\n'
              '# 杭州一日游\n\n'
              '@[灵隐寺](entity:sight:west_lake)\n',
              extra: const <String, dynamic>{
                'contentVertical': 'travel',
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
                'contentVertical': 'travel',
                'entityMentions': <Map<String, dynamic>>[
                  {
                    'subjectType': 'entity',
                    'subjectId': 'entity:photo_spot:unknown',
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
    final post = _articlePost().copyWith(
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

    // 页角热区向内拖拽会揭开相邻页：断言末节内容（位于第 2 页）被翻出到组件树。
    final deckRect = tester.getRect(find.byType(ArticleReadOnlyBookDeck));
    await tester.dragFrom(
      Offset(deckRect.right - 2, deckRect.bottom - 80),
      const Offset(-260, -40),
    );
    await _pumpSettledFrames(tester);

    expect(find.textContaining('小节14'), findsWidgets);
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

  testWidgets('文章 book reader 总开关关闭时仍使用统一阅读器并上报 feature 关闭 fallback', (
    tester,
  ) async {
    final post = _articlePost();
    final analytics = _FakeAnalyticsService();
    final repo = _ConfigurableContentRepository(
      appConfig: <String, dynamic>{
        'app_bootstrap': <String, dynamic>{
          'activationPolicy': <String, dynamic>{'default': 'immediate'},
        },
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
        useRemoteMode: true,
        contentRepository: repo,
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
    final repo = _ConfigurableContentRepository(
      detailById: <String, Map<String, dynamic>>{
        post.id: <String, dynamic>{
          'postId': post.id,
          'type': 'article',
          'contentType': 'article',
          'authorId': post.authorId,
          'authorDisplayName': post.displayName,
          'authorAvatarUrl': post.avatarUrl,
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
        contentRepository: repo,
      ),
    );
    await tester.pump();
    _consumeImageLoadExceptions(tester);
    await _pumpSettledFrames(tester);

    expect(repo.getPostCallCount, equals(1));
    expect(find.text('水合后的标题'), findsWidgets);
    expect(find.textContaining('水合后的正文第一段'), findsWidgets);

    final hydrationEvent = analytics.events.firstWhere(
      (event) => event.eventName == 'article_reader_hydration_ms',
    );
    expect(hydrationEvent.properties['result'], equals('success'));
    final structureFallback = analytics.events.firstWhere(
      (event) =>
          event.eventName == 'article_reader_fallback_rate' &&
          (event.properties['reason'] as String).startsWith(
            'document_structure:',
          ),
    );
    expect(structureFallback.properties['reason'], contains('empty'));
  });

  testWidgets('文章详情水合失败后进入显式错误态且不在当前会话内重复拉取', (tester) async {
    final post = _articlePost();
    final analytics = _FakeAnalyticsService();
    final repo = _ConfigurableContentRepository();

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
        contentRepository: repo,
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
