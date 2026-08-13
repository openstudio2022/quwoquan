// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/error-permission-display-semantics/spec.md#gwt-009
import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/errors/generated/content/content_errors.g.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/adapters/media_download_cache.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_app/design_system/avatar/rounded_square_avatar.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/video_player_widget.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/video_playback_session_models.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/presentation/interactive_intersection_text.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/l10n/copy/app_concept_constants.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/l10n/copy/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/spacing/discovery_feed_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/service/product_ops_service/product_ops/event_record/adapters/event_record_batch_writer.dart';
import 'package:quwoquan_app/runtime/auth/auth_continuation.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/transport/cloud_api_query_defaults.dart';
import 'package:quwoquan_app/service/content_service/content/intersection_visit_state/adapters/intersection_repository.dart';
import 'package:quwoquan_app/runtime/di/ops_event_record_dependencies.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/content_behavior_tracker.dart';
import 'package:quwoquan_app/design_system/layout/app_terminal_viewport.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/discovery_feed_provider.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/home_multi_form_feed.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        AssistantUsePolicy,
        BehaviorEventType,
        ContentFeedEmptyReason,
        IntersectionActionHint,
        IntersectionActorEvidence,
        IntersectionInboxSummary,
        IntersectionReason,
        IntersectionRepresentativeActor,
        IntersectionTarget,
        IntersectionTextSpan,
        IntersectionVisual;
import 'package:quwoquan_cloud_contracts/generated/ops_contracts.dart' as ops;
import 'package:quwoquan_runtime_errors/runtime_errors.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../../../../support/service/content_service/content/content_behavior_fact/recording_content_behavior_repository.dart';
import '../../../../../support/service/content_service/content/post/content_facet_overrides.dart';
import '../../../../../support/service/content_service/content/post/content_post_test_builder.dart';
import '../../../../../support/service/content_service/content/post/content_post_typed_doubles.dart';
import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import 'package:http/testing.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';

TextSpan _spanByText(RichText richText, String text) {
  TextSpan? result;
  richText.text.visitChildren((span) {
    if (span is TextSpan && span.text == text) {
      result = span;
      return false;
    }
    return true;
  });
  return result!;
}

int _fontWeightValue(TextSpan span) =>
    span.style?.fontWeight?.value ?? FontWeight.normal.value;

IntersectionReason _canonicalReason({
  required String dimension,
  required String intersectionId,
  required String intersectionClass,
  required String objectKind,
  required String source,
  required String actionTargetId,
  required String pointSummarySnapshotId,
  required String displayBinding,
  required int actorEvidenceTotalCount,
  required String actorEvidenceCompleteness,
  required String primaryText,
  required List<IntersectionTextSpan> primarySpans,
  IntersectionRepresentativeActor? representativeActor,
  List<IntersectionActorEvidence> actorEvidence =
      const <IntersectionActorEvidence>[],
  List<IntersectionVisual> sampleVisuals = const <IntersectionVisual>[],
  List<IntersectionActionHint> actionHints = const <IntersectionActionHint>[],
}) {
  return IntersectionReason(
    kind: 'content',
    vertical: 'travel',
    dimension: dimension,
    tagRefs: const <String>[],
    relationKind: source,
    objectKind: objectKind,
    relationObjectId: actionTargetId,
    strength: 1,
    primaryText: primaryText,
    primaryTextL10nKey: '',
    displayBinding: displayBinding,
    secondaryText: '',
    weightTier: 'high',
    actionType: 'open',
    actionTargetId: actionTargetId,
    source: source,
    intersectionId: intersectionId,
    intersectionClass: intersectionClass,
    avatarUrl: representativeActor?.avatarUrl ?? '',
    displayName: representativeActor?.displayName ?? '',
    confidenceLabel: 'high',
    modelReasonBucket: 'local_contract',
    freshAt: '2026-01-01T00:00:00Z',
    expiresAt: '2027-01-01T00:00:00Z',
    intersectionPoints: const [],
    pointSummarySnapshotId: pointSummarySnapshotId,
    actorEvidenceTotalCount: actorEvidenceTotalCount,
    actorEvidenceCompleteness: actorEvidenceCompleteness,
    actorEvidence: actorEvidence,
    factPointCount: intersectionClass == 'fact' ? 1 : 0,
    recommendedPointCount: intersectionClass == 'recommended' ? 1 : 0,
    totalPointCount: 1,
    dimensionPointSummary: const [],
    pointClassLabel: intersectionClass,
    connectionSummary: primaryText,
    lastRecommendedAt: '',
    seenAt: '',
    rankState: 'active',
    primarySpans: primarySpans,
    sampleVisuals: sampleVisuals,
    representativeActor: representativeActor,
    actionHints: actionHints,
    lifecycleState: 'active',
    previousStrength: 0,
    strengthDelta: 1,
    edgeWeight: 1,
    iconKey: '',
    tone: 'neutral',
    timeBucket: 'current',
    dedupeKey: intersectionId,
    anchorUserWeight: 1,
    mutualCount: actorEvidenceTotalCount,
    moment: '',
    subjectId: actionTargetId,
    subjectContext: dimension,
  );
}

IntersectionReason _reason({
  String intersectionClass = 'fact',
  String? postId,
}) {
  final resolvedPostId =
      postId ?? 'post_intersection_demo_${intersectionClass}_1';
  final target = IntersectionTarget(
    objectType: 'user',
    objectId: 'fixture_user_lin',
    objectKind: 'person',
    routeId: 'userProfile',
  );
  return _canonicalReason(
    dimension: 'content',
    intersectionId: 'ix_post_lin',
    intersectionClass: intersectionClass,
    objectKind: 'content',
    source: 'coCommented',
    actionTargetId: resolvedPostId,
    pointSummarySnapshotId: 'snap_lin',
    displayBinding: 'host_implicit',
    actorEvidenceTotalCount: 3,
    actorEvidenceCompleteness: 'complete',
    representativeActor: IntersectionRepresentativeActor(
      actorId: 'fixture_user_lin',
      displayName: '林清越',
      avatarUrl: 'https://example.invalid/media/avatar/fixture_user_lin.webp',
      relationLabel: '联系人',
      privacyState: 'visible',
      target: target,
      evidenceRank: 5,
      snapshotVersion: 'snap_lin',
    ),
    actorEvidence: <IntersectionActorEvidence>[
      IntersectionActorEvidence(
        actorId: 'fixture_user_lin',
        displayName: '林清越',
        avatarUrl: 'https://example.invalid/media/avatar/fixture_user_lin.webp',
        relationLabel: '联系人',
        relationSourceRef: 'contact',
        relationObjectId: '',
        relationObjectName: '',
        sourcePointId: 'ix_post_lin_actor_1',
        sourceRef: 'commonContact',
        actionSummaryText: '赞过川西雪山和校园摄影路线',
        likeCount: 1,
        commentCount: 0,
        shareCount: 0,
        privacyState: 'visible',
        target: target,
        evidenceRank: 5,
        snapshotVersion: 'snap_lin',
        sortKey: 1,
      ),
      IntersectionActorEvidence(
        actorId: 'fixture_user_zhou',
        displayName: '周屿',
        avatarUrl:
            'https://example.invalid/media/avatar/fixture_user_zhou.webp',
        relationLabel: '你关注的人',
        relationSourceRef: 'followee',
        relationObjectId: '',
        relationObjectName: '',
        sourcePointId: 'ix_post_lin_actor_2',
        sourceRef: 'sharedFollowees',
        actionSummaryText: '赞过川西雪山和校园摄影路线',
        likeCount: 1,
        commentCount: 0,
        shareCount: 0,
        privacyState: 'visible',
        evidenceRank: 10,
        snapshotVersion: 'snap_lin',
        sortKey: 2,
      ),
      IntersectionActorEvidence(
        actorId: 'fixture_user_gunan',
        displayName: '顾南',
        avatarUrl:
            'https://example.invalid/media/avatar/fixture_user_gunan.webp',
        relationLabel: '城市漫游圈圈友',
        relationSourceRef: 'sharedCircle',
        relationObjectId: 'fixture_circle_city_walk',
        relationObjectName: '城市漫游圈',
        sourcePointId: 'ix_post_lin_actor_3',
        sourceRef: 'sharedCircle',
        actionSummaryText: '评论过川西雪山和校园摄影路线',
        likeCount: 0,
        commentCount: 1,
        shareCount: 0,
        privacyState: 'visible',
        evidenceRank: 20,
        snapshotVersion: 'snap_lin',
        sortKey: 3,
      ),
    ],
    primaryText: '联系人林清越等3人赞过和评论过',
    primarySpans: <IntersectionTextSpan>[
      IntersectionTextSpan(text: '联系人', role: 'plain'),
      IntersectionTextSpan(text: '林清越', role: 'object', target: target),
      IntersectionTextSpan(text: '等', role: 'plain'),
      IntersectionTextSpan(
        text: '3',
        role: 'count',
        target: IntersectionTarget(
          objectType: 'dimension',
          objectId: 'content',
          objectKind: 'dimension',
          routeId: 'myIntersections',
        ),
      ),
      IntersectionTextSpan(text: '人赞过和评论过', role: 'plain'),
    ],
    sampleVisuals: <IntersectionVisual>[
      IntersectionVisual(
        assetKind: 'avatar',
        imageUrl: '',
        displayName: '林清越',
        target: target,
      ),
    ],
  );
}

IntersectionReason _photoSpotReason() {
  final actorTarget = IntersectionTarget(
    objectType: 'user',
    objectId: 'sys_travel_9018_sub_01',
    objectKind: 'person',
    routeId: 'userProfile',
  );
  final objectTarget = IntersectionTarget(
    objectType: 'homepage',
    objectId: 'fixture_homepage_photo_spot_hengshu_studio',
    objectKind: 'photo_spot',
    routeId: 'homepageDetail',
  );
  return _canonicalReason(
    dimension: 'photo_work',
    intersectionId: 'ix_post_photo_spot',
    intersectionClass: 'fact',
    objectKind: 'photo_spot',
    source: 'home_showcase',
    actionTargetId: 'fixture_homepage_photo_spot_hengshu_studio',
    pointSummarySnapshotId: 'snap_photo_spot',
    displayBinding: 'explicit_link',
    actorEvidenceTotalCount: 7,
    actorEvidenceCompleteness: 'complete',
    representativeActor: IntersectionRepresentativeActor(
      actorId: 'sys_travel_9018_sub_01',
      displayName: '山川手账',
      avatarUrl:
          'https://example.invalid/media/avatar/sys_travel_9018_sub_01.webp',
      relationLabel: '你关注的人',
      privacyState: 'visible',
      target: actorTarget,
      evidenceRank: 10,
      snapshotVersion: 'snap_photo_spot',
    ),
    primaryText: '你关注的人山川手账等7人也关注了「横竖影像馆取景地」',
    primarySpans: <IntersectionTextSpan>[
      IntersectionTextSpan(text: '你关注的人', role: 'plain'),
      IntersectionTextSpan(text: '山川手账', role: 'object', target: actorTarget),
      IntersectionTextSpan(text: '等', role: 'plain'),
      IntersectionTextSpan(
        text: '7',
        role: 'count',
        target: IntersectionTarget(
          objectType: 'dimension',
          objectId: 'photo_work',
          objectKind: 'dimension',
          routeId: 'myIntersections',
        ),
      ),
      IntersectionTextSpan(text: '人也关注了「', role: 'plain'),
      IntersectionTextSpan(
        text: '横竖影像馆取景地',
        role: 'object',
        target: objectTarget,
      ),
      IntersectionTextSpan(text: '」', role: 'plain'),
    ],
  );
}

ContentPostViewData _microPost({
  String? id,
  List<String> imageUrls = const <String>[
    'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
  ],
  String? videoUrl,
  IntersectionReason? reason,
  String avatarUrl = '',
}) {
  final reasonClass = reason?.intersectionClass ?? 'fact';
  final postId =
      id ?? 'post_intersection_demo_${reasonClass}_${imageUrls.length}';
  final effectiveReason =
      reason ?? _reason(intersectionClass: reasonClass, postId: postId);
  return ContentPostViewData(
    id: postId,
    type: 'micro',
    identity: 'moment',
    displayFormat: videoUrl != null
        ? 'video'
        : imageUrls.isNotEmpty
        ? 'image'
        : 'note',
    authorId: 'user_demo',
    displayName: '小趣用户',
    avatarUrl: avatarUrl,
    authorBackgroundUrl: null,
    authorRoleLabel: '旅行创作者',
    authorIdentityTags: const <String>['摄影', '川西'],
    authorVerified: true,
    assistantUsePolicy: AssistantUsePolicy.inherit,
    likeCount: 12,
    commentCount: 3,
    shareCount: 1,
    createdAt: DateTime(2026),
    updatedAt: null,
    publishedAt: null,
    body: '川西雪山和校园摄影路线',
    imageUrls: imageUrls,
    videoUrl: videoUrl,
    durationMs: null,
    intersectionReasons: <IntersectionReason>[effectiveReason],
  );
}

ContentPostViewData _photoPost({
  required int width,
  required int height,
  List<String> imageUrls = const <String>[
    'media/image/s/archived-image/post/fixture_photo_002/v1/cover.png',
  ],
  IntersectionReason? reason,
}) {
  final postId = 'photo_${width}_${height}_${imageUrls.length}';
  final effectiveReason = reason ?? _reason(postId: postId);
  return ContentPostViewData(
    id: postId,
    type: 'image',
    identity: 'work',
    displayFormat: 'image',
    assistantUsePolicy: AssistantUsePolicy.inherit,
    authorId: 'user_photo',
    displayName: '影像作者',
    avatarUrl: '',
    authorBackgroundUrl: null,
    authorRoleLabel: '摄影师',
    authorIdentityTags: const <String>['风光'],
    authorVerified: false,
    body: '不同素材宽高比测试',
    coverUrl: imageUrls.first,
    imageUrls: imageUrls,
    width: width,
    height: height,
    likeCount: 1,
    commentCount: 2,
    shareCount: 3,
    createdAt: DateTime(2026),
    updatedAt: null,
    publishedAt: null,
    intersectionReasons: <IntersectionReason>[effectiveReason],
  );
}

ContentPostViewData _videoPost({required int width, required int height}) {
  final postId = 'video_${width}_$height';
  return ContentPostViewData(
    id: postId,
    type: 'video',
    identity: 'work',
    displayFormat: 'video',
    assistantUsePolicy: AssistantUsePolicy.inherit,
    authorId: 'user_video',
    displayName: '视频作者',
    avatarUrl: '',
    authorBackgroundUrl: null,
    authorRoleLabel: '旅行视频',
    authorIdentityTags: const <String>['影像'],
    authorVerified: false,
    body: '视频画面下方的配文',
    videoUrl:
        'media/video/s/video-primary-0001/post/video-content-0001/v1/source.mp4',
    thumbnailUrl:
        'media/image/s/archived-image/post/fixture_video_001/v1/cover.png',
    coverUrl:
        'media/image/s/archived-image/post/fixture_video_001/v1/cover.png',
    width: width,
    height: height,
    durationMs: 65000,
    likeCount: 1,
    commentCount: 2,
    shareCount: 3,
    createdAt: DateTime(2026),
    updatedAt: null,
    publishedAt: null,
    intersectionReasons: <IntersectionReason>[_reason(postId: postId)],
  );
}

ContentPostViewData _homeShowcasePost() {
  return _microPost();
}

ContentPostViewData _articleLayoutPost({
  required String id,
  String bodyValue = '正文第一行，正文第二行，正文第三行，正文第四行会被折叠进全文入口。',
  String coverUrlValue = '',
}) {
  return ContentPostViewData(
    id: id,
    type: 'article',
    identity: 'work',
    displayFormat: 'note',
    assistantUsePolicy: AssistantUsePolicy.inherit,
    authorId: 'user_article',
    displayName: '文章作者',
    avatarUrl: '',
    authorRoleLabel: '旅行作者',
    authorIdentityTags: const <String>['长文'],
    authorVerified: false,
    title: '川西路线长文标题',
    body: bodyValue,
    summary: bodyValue,
    coverUrl: coverUrlValue,
    likeCount: 1,
    commentCount: 2,
    shareCount: 3,
    createdAt: DateTime(2026),
    intersectionReasons: <IntersectionReason>[_reason(postId: id)],
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

class _NoopMediaDownloadCache extends MediaDownloadCache {
  _NoopMediaDownloadCache() : super(client: _unreachableDataPlaneClient());

  @override
  Future<String?> getCachedFilePath(String url) async => null;
}

final class _InMemoryOpsEventRecordBatchWriter
    implements OpsEventRecordBatchWriter {
  @override
  Future<ops.EventRecordBatchReceipt> reportEventBatch(
    ops.EventRecordBatchRequest request, {
    required String idempotencyKey,
  }) async {
    return const ops.EventRecordBatchReceipt(
      acceptedCount: 0,
      duplicateBatch: false,
    );
  }

  @override
  Future<ops.EventRecordBatchReceipt> reportRuntimeLogBatch(
    ops.RuntimeLogBatchRequest request, {
    required String idempotencyKey,
  }) async {
    return const ops.EventRecordBatchReceipt(
      acceptedCount: 0,
      duplicateBatch: false,
    );
  }
}

List<Override> _boundaryOverrides({List<Override> extra = const <Override>[]}) {
  return <Override>[
    ...sealedCloudBoundaryOverrides(),
    opsEventRecordBatchWriterProvider.overrideWithValue(
      _InMemoryOpsEventRecordBatchWriter(),
    ),
    ...extra,
  ];
}

final MediaEndpointConfig _testMediaEndpointConfig = MediaEndpointConfig(
  avatarBaseUrl: 'https://cdn.alpha.quwoquan.com:17100/media/avatar',
  imageBaseUrl: 'https://cdn.alpha.quwoquan.com:17100/media/image',
  videoBaseUrl: 'https://cdn.alpha.quwoquan.com:17100/media/video',
  attachmentBaseUrl: 'https://cdn.alpha.quwoquan.com:17100/media/image',
);

Widget _buildFeed(
  ContentPostViewData post, {
  ContentBehaviorTracker? tracker,
  bool authenticated = false,
  List<Override> extraOverrides = const <Override>[],
  void Function(
    ContentPostViewData post,
    int index, {
    List<ContentPostViewData>? feedPosts,
  })?
  onPostTap,
}) {
  return ProviderScope(
    key: ValueKey<String>('feed-scope-${post.id}'),
    overrides: _boundaryOverrides(
      extra: <Override>[
        ...mockContentFacetOverrides(store: InMemoryContentPostStore()),
        mediaEndpointConfigProvider.overrideWithValue(_testMediaEndpointConfig),
        discoveryFeedMapProvider.overrideWith(
          () => _SinglePostFeedMapNotifier(post),
        ),
        mediaDownloadCacheProvider.overrideWithValue(_NoopMediaDownloadCache()),
        if (authenticated)
          authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
        if (tracker != null)
          contentBehaviorTrackerProvider.overrideWithValue(tracker),
        ...extraOverrides,
      ],
    ),
    child: CupertinoApp(
      home: ScreenUtilInit(
        designSize: const Size(390, 844),
        child: MediaQuery(
          data: const MediaQueryData(size: Size(390, 844)),
          child: HomeMultiFormFeed(
            isDark: false,
            channelId: 'recommend',
            template: 'single_column_multiform',
            onUserTap: (_, {avatarUrl, backgroundUrl, displayName}) {},
            onPostTap: onPostTap,
          ),
        ),
      ),
    ),
  );
}

Widget _buildRealProviderFeed() {
  final post = contentPostViewDataBuilder(
    postId: 'real-provider-photo',
    contentType: 'image',
    authorId: 'nature_photographer',
    authorDisplayName: '自然摄影师',
    mediaUrls: const <String>[testContentImageUrl],
  );
  return ProviderScope(
    overrides: _boundaryOverrides(
      extra: <Override>[
        ...mockContentFacetOverrides(
          store: InMemoryContentPostStore(posts: <ContentPostViewData>[post]),
        ),
        mediaEndpointConfigProvider.overrideWithValue(_testMediaEndpointConfig),
      ],
    ),
    child: CupertinoApp(
      home: ScreenUtilInit(
        designSize: const Size(390, 844),
        child: MediaQuery(
          data: MediaQueryData(size: Size(390, 844)),
          child: HomeMultiFormFeed(
            isDark: false,
            channelId: 'recommend',
            template: 'single_column_multiform',
            onUserTap: _noopUserTap,
          ),
        ),
      ),
    ),
  );
}

void _noopUserTap(
  String userId, {
  String? avatarUrl,
  String? displayName,
  String? backgroundUrl,
}) {}

void main() {
  testWidgets('单列 post 内展示作者身份、媒体、交集与底部互动', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(_buildFeed(_microPost()));
    await tester.pump();

    expect(
      find.byKey(const ValueKey('home-relation-card-header')),
      findsOneWidget,
    );
    expect(find.text('旅行创作者 · 摄影 · 川西'), findsOneWidget);
    expect(find.text('关注'), findsOneWidget);
    expect(find.byIcon(CupertinoIcons.checkmark_seal_fill), findsOneWidget);
    expect(
      find.byKey(const ValueKey('home-relation-card-media')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('home-relation-card-reason')),
      findsOneWidget,
    );
    expect(
      find.text(DiscoveryFeedText.homeFeedIntersectionReasonLabel),
      findsNothing,
    );
    expect(find.byKey(const ValueKey('home-intersection-glyph')), findsNothing);
    final reasonBox = tester.widget<DecoratedBox>(
      find.byKey(const ValueKey('home-relation-card-reason')),
    );
    final reasonDecoration = reasonBox.decoration as BoxDecoration;
    expect(reasonDecoration.color, isNotNull);
    expect(reasonDecoration.border, isNotNull);
    final reasonRadius = reasonDecoration.borderRadius! as BorderRadius;
    expect(
      reasonRadius.topLeft.x,
      DiscoveryFeedSpacing.homeFeedMediaCornerRadius,
    );
    final richText = tester.widget<RichText>(
      find.descendant(
        of: find.byType(InteractiveIntersectionText),
        matching: find.byType(RichText),
      ),
    );
    expect(richText.text.toPlainText(), '联系人林清越等3人赞过和评论过');
    final textContext = tester.element(
      find.byType(InteractiveIntersectionText),
    );
    final plainColor = AppColors.iosLabel(textContext);
    final isDark = CupertinoTheme.of(textContext).brightness == Brightness.dark;
    final accentColor = isDark
        ? AppColors.profileSloganAccentDark
        : AppColors.profileSloganAccentLight;
    expect(_spanByText(richText, '联系人').style?.color, plainColor);
    expect(_spanByText(richText, '等').style?.color, plainColor);
    expect(_spanByText(richText, '人赞过和评论过').style?.color, plainColor);
    expect(plainColor, isNot(AppColors.iosSecondaryLabel(textContext)));
    expect(_spanByText(richText, '林清越').style?.color, accentColor);
    expect(_spanByText(richText, '3').style?.color, accentColor);
    expect(
      _fontWeightValue(_spanByText(richText, '林清越')),
      greaterThan(_fontWeightValue(_spanByText(richText, '联系人'))),
    );
    expect(
      _fontWeightValue(_spanByText(richText, '3')),
      greaterThan(_fontWeightValue(_spanByText(richText, '等'))),
    );
    final widget = tester.widget<InteractiveIntersectionText>(
      find.byType(InteractiveIntersectionText),
    );
    expect(
      widget.baseStyle?.fontSize,
      AppTypography.feedBodyResponsive(textContext),
    );
    expect(
      find.byKey(const ValueKey('home-relation-card-actions')),
      findsOneWidget,
    );
    expect(find.text('更多'), findsNothing);
    expect(
      find.byKey(const ValueKey<String>('home-feed-more-0')),
      findsOneWidget,
    );
  });

  testWidgets('推荐卡片把头像、图片、视频统一投影为注入媒体端点', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(
      _buildFeed(
        _microPost(
          avatarUrl:
              'media/avatar/s/archived-avatar/circle/fixture_circle_city/v1/avatar.png',
        ),
      ),
    );
    await tester.pump();

    final avatarImages = tester
        .widgetList<AppCachedNetworkImage>(find.byType(AppCachedNetworkImage))
        .where((widget) => widget.cdnPreset == CdnImagePreset.avatar)
        .toList(growable: false);
    expect(avatarImages, hasLength(1));
    final avatarCandidates =
        avatarImages.single.imageUrlCandidates ?? const <String>[];
    expect(avatarCandidates, <String>[
      'https://cdn.alpha.quwoquan.com:17100/media/avatar/s/archived-avatar/circle/fixture_circle_city/v1/avatar.png',
    ]);

    final contentImages = tester
        .widgetList<AppCachedNetworkImage>(find.byType(AppCachedNetworkImage))
        .where((widget) => widget.cdnPreset != CdnImagePreset.avatar)
        .toList(growable: false);
    expect(contentImages, isNotEmpty);
    expect(
      contentImages.any(
        (widget) =>
            widget.imageUrlCandidates?.contains(
              'https://cdn.alpha.quwoquan.com:17100/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
            ) ??
            false,
      ),
      isTrue,
    );

    await tester.pumpWidget(_buildFeed(_videoPost(width: 1080, height: 1920)));
    await tester.pump();

    final player = tester.widget<VideoPlayerWidget>(
      find.byType(VideoPlayerWidget),
    );
    expect(
      player.deliveryReference.url,
      'https://cdn.alpha.quwoquan.com:17100/media/video/s/video-primary-0001/post/video-content-0001/v1/source.mp4',
    );
    expect(player.deliveryReference.url, isNot(contains('https://10.0.2.2')));
  });

  testWidgets('首页推荐瀑布流不会把图片 cover 当成视频源初始化', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    const coverObjectKey =
        'media/image/s/archived-image/post/fixture_photo_002/v1/cover.png';
    await tester.pumpWidget(
      _buildFeed(
        _microPost(
          imageUrls: const <String>[coverObjectKey],
          videoUrl: coverObjectKey,
        ),
      ),
    );
    await tester.pump();

    expect(find.byType(VideoPlayerWidget), findsNothing);
    final contentImages = tester
        .widgetList<AppCachedNetworkImage>(find.byType(AppCachedNetworkImage))
        .where((widget) => widget.cdnPreset != CdnImagePreset.avatar)
        .toList(growable: false);
    expect(
      contentImages.any(
        (widget) =>
            widget.imageUrlCandidates?.contains(
              'https://cdn.alpha.quwoquan.com:17100/$coverObjectKey',
            ) ??
            false,
      ),
      isTrue,
    );
  });

  testWidgets('默认 Provider 加载最小 typed post 时保留作者头像 media candidates', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    SharedPreferences.setMockInitialValues(const <String, Object>{});

    await tester.pumpWidget(_buildRealProviderFeed());
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));

    expect(find.text('自然摄影师'), findsWidgets);

    final avatars = tester
        .widgetList<RoundedSquareAvatar>(find.byType(RoundedSquareAvatar))
        .toList(growable: false);
    expect(avatars, isNotEmpty);
    expect(avatars.first.imageUrl, testContentAvatarUrl);

    final avatarImages = tester
        .widgetList<AppCachedNetworkImage>(find.byType(AppCachedNetworkImage))
        .where((widget) => widget.cdnPreset == CdnImagePreset.avatar)
        .toList(growable: false);
    expect(avatarImages, isNotEmpty);
    expect(avatarImages.first.imageUrlCandidates, <String>[
      'https://cdn.alpha.quwoquan.com:17100/$testContentAvatarUrl',
    ]);
  });

  testWidgets('任务B·分层强度：推测型交集证据行弱于事实型', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    double bgAlphaOf(WidgetTester t) {
      final box = t.widget<DecoratedBox>(
        find.byKey(const ValueKey('home-relation-card-reason')),
      );
      return ((box.decoration as BoxDecoration).color!).a;
    }

    double borderAlphaOf(WidgetTester t) {
      final box = t.widget<DecoratedBox>(
        find.byKey(const ValueKey('home-relation-card-reason')),
      );
      final border = (box.decoration as BoxDecoration).border! as Border;
      return border.top.color.a;
    }

    await tester.pumpWidget(
      _buildFeed(_microPost(reason: _reason(intersectionClass: 'fact'))),
    );
    await tester.pump();
    final factBgAlpha = bgAlphaOf(tester);
    final factBorderAlpha = borderAlphaOf(tester);

    await tester.pumpWidget(
      _buildFeed(_microPost(reason: _reason(intersectionClass: 'recommended'))),
    );
    await tester.pump();
    final recommendedBgAlpha = bgAlphaOf(tester);
    final recommendedBorderAlpha = borderAlphaOf(tester);

    // 事实型（共同关注/到访/收藏）必须比推测型视觉更强。
    expect(recommendedBgAlpha, lessThan(factBgAlpha));
    expect(recommendedBorderAlpha, lessThan(factBorderAlpha));
    // 但推测型仍保留具体证据行（不消失），泛化标签不出现。
    expect(
      find.text(DiscoveryFeedText.homeFeedIntersectionReasonLabel),
      findsNothing,
    );
  });

  testWidgets('任务A·加载态：空数据加载中展示骨架屏而非白屏', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(
      _buildFeedScope(
        notifier: _LoadingFeedMapNotifier.new,
        disableAnimations: true,
      ),
    );
    await tester.pump();

    expect(find.byKey(const ValueKey('home-feed-skeleton')), findsOneWidget);
    expect(find.byKey(const ValueKey('home-feed-empty')), findsNothing);
  });

  testWidgets('首页空白阻塞进入慢阶段时只在骨架屏下显示一次提示', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(
      _buildFeedScope(
        notifier: _SlowLoadingFeedMapNotifier.new,
        disableAnimations: true,
      ),
    );
    await tester.pump();

    expect(find.byKey(const ValueKey('home-feed-skeleton')), findsOneWidget);
    expect(find.byKey(const ValueKey('home_feed_slow_hint')), findsOneWidget);
    expect(find.text(FoundationText.requestWaitSlow), findsOneWidget);
    expect(find.byType(CupertinoActivityIndicator), findsNothing);
  });

  testWidgets('用户深滚后回到顶部只触发一次前页恢复', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final notifier = _PreviousPageRecoveryFeedMapNotifier(
      List<ContentPostViewData>.generate(
        48,
        (index) => _microPost(
          id: 'post_previous_page_${index.toString().padLeft(2, '0')}',
          imageUrls: const <String>[],
        ),
        growable: false,
      ),
    );

    await tester.pumpWidget(
      _buildFeedScope(
        notifier: () => notifier,
        scopeId: 'previous-page-user-behavior',
      ),
    );
    await tester.pump();

    final scrollView = find.byType(CustomScrollView);
    expect(scrollView, findsOneWidget);
    await tester.fling(scrollView, const Offset(0, -5000), 5000);
    await tester.pumpAndSettle();
    expect(notifier.prependCalls, 0);

    await tester.fling(scrollView, const Offset(0, 6000), 5000);
    await tester.pumpAndSettle();

    expect(notifier.prependCalls, 1);
  });

  testWidgets('生产滚动容器经 provider 驱动八页并越过 retained 边界', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final notifier = _EightPageScrollFeedMapNotifier();

    await tester.pumpWidget(
      _buildFeedScope(
        notifier: () => notifier,
        scopeId: 'eight-page-long-scroll',
      ),
    );
    await tester.pump();

    final scrollView = find.byType(CustomScrollView);
    expect(scrollView, findsOneWidget);
    for (
      var attempt = 0;
      attempt < 12 && notifier.loadedPageCount < 8;
      attempt += 1
    ) {
      await tester.fling(scrollView, const Offset(0, -8000), 6000);
      await tester.pumpAndSettle();
    }

    expect(notifier.loadedPageCount, 8);
    expect(notifier.appendCalls, 7);
    final feed = notifier.currentFeed;
    expect(feed.items, hasLength(80));
    expect(feed.items.first.id, 'widget_page_4_post_0');
    expect(feed.items.last.id, 'widget_page_7_post_19');
    expect(feed.seenItemIds, hasLength(160));
    expect(feed.residentPageCount, 4);
    expect(feed.retainedPageCount, 6);

    WidgetsBinding.instance.handleMemoryPressure();
    await tester.pump();
    expect(find.byType(CustomScrollView), findsOneWidget);
  });

  testWidgets('关注空态准确说明尚无动态且没有插画或错误重试', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(
      _buildFeedScope(
        notifier: _FollowingEmptyFeedMapNotifier.new,
        channelId: 'following',
      ),
    );
    await tester.pump();

    expect(
      find.byKey(const ValueKey('home-following-feed-empty')),
      findsOneWidget,
    );
    expect(
      find.text(DiscoveryFeedText.followingFeedEmptyTitle),
      findsOneWidget,
    );
    expect(
      find.text(DiscoveryFeedText.followingFeedEmptyDescription),
      findsOneWidget,
    );
    expect(find.byType(Icon), findsNothing);
    expect(find.text('暂时没有推荐内容'), findsNothing);
    expect(find.textContaining('关注更多内容后'), findsNothing);
    expect(find.text(SearchText.reload), findsNothing);
    expect(find.byKey(const ValueKey('home-feed-skeleton')), findsNothing);
    expect(
      find.ancestor(
        of: find.byKey(const ValueKey('home-following-feed-empty')),
        matching: find.byType(AppTerminalViewport),
      ),
      findsOneWidget,
    );
  });

  testWidgets('缺少 canonical empty reason 的推荐空响应按协议错误阻断', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(
      _buildFeedScope(notifier: _RecommendEmptyFeedMapNotifier.new),
    );
    await tester.pump();

    expect(
      find.byKey(const ValueKey('home-following-feed-empty')),
      findsNothing,
    );
    expect(find.text(SearchText.recoveryInvalidContentTitle), findsOneWidget);
    expect(find.text(SearchText.recoveryInvalidContentMessage), findsOneWidget);
    expect(find.text(SearchText.reload), findsOneWidget);
    expect(find.byType(Icon), findsNothing);
    expect(find.text('暂时没有推荐内容'), findsNothing);
    expect(find.textContaining('关注更多内容后'), findsNothing);
  });

  testWidgets('推荐健康空态仅显示内容加载完毕且没有错误恢复控件', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(
      _buildFeedScope(notifier: _RecommendCanonicalEmptyFeedMapNotifier.new),
    );
    await tester.pump();

    expect(
      find.byKey(const ValueKey('home-feed-completed-empty')),
      findsOneWidget,
    );
    expect(
      find.text(DiscoveryFeedText.contentLoadingCompleted),
      findsOneWidget,
    );
    expect(find.text(SearchText.recoveryReloadLaterTitle), findsNothing);
    expect(find.text(SearchText.reload), findsNothing);
    expect(find.byType(Icon), findsNothing);
    expect(
      find.ancestor(
        of: find.byKey(const ValueKey('home-feed-completed-empty')),
        matching: find.byType(AppTerminalViewport),
      ),
      findsOneWidget,
    );
  });

  testWidgets('test_live 无 active release 显示 typed unavailable 并可重试', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final notifier = _NoActiveReleaseFeedMapNotifier();

    await tester.pumpWidget(
      _buildFeedScope(notifier: () => notifier, scopeId: 'no-active-release'),
    );
    await tester.pump();

    expect(
      find.byKey(const ValueKey('home-feed-no-active-release')),
      findsOneWidget,
    );
    expect(
      find.text(SearchText.recoveryContentUnavailableTitle),
      findsOneWidget,
    );
    expect(
      find.text(SearchText.recoveryContentUnavailableMessage),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('home-feed-completed-empty')),
      findsNothing,
    );
    expect(notifier.forceLoadCalls, 0);

    await tester.tap(
      find.byKey(const ValueKey('home-feed-no-active-release-retry')),
    );
    await tester.pump();

    expect(notifier.forceLoadCalls, 1);
  });

  testWidgets('feed 离线、超时和依赖不可用使用准确恢复组且不展示技术字段', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final cases = <({RuntimeFailure failure, String title, String message})>[
      (
        failure: _feedFailure(
          code: RuntimeFailureCodes.appNetworkOffline,
          kind: RuntimeFailureKind.network,
          reason: 'device_offline',
        ),
        title: SearchText.recoveryConnectNetworkTitle,
        message: SearchText.recoveryConnectNetworkMessage,
      ),
      (
        failure: _feedFailure(
          code: RuntimeFailureCodes.appTimeoutRequestTimeout,
          kind: RuntimeFailureKind.timeout,
          reason: 'feed_timeout',
        ),
        title: SearchText.recoveryRequestTimedOutTitle,
        message: SearchText.recoveryRequestTimedOutMessage,
      ),
      (
        failure: _feedFailure(
          code: ContentErrorCode.requiredDependencyUnavailable.code,
          kind: RuntimeFailureKind.unavailable,
          reason: 'feed_dependency_unavailable',
        ),
        title: SearchText.recoveryServiceUnavailableTitle,
        message: SearchText.recoveryServiceUnavailableMessage,
      ),
    ];

    for (final entry in cases) {
      await tester.pumpWidget(
        _buildFeedScope(
          notifier: () => _BlockingErrorFeedMapNotifier(entry.failure),
          scopeId: entry.failure.code,
        ),
      );
      await tester.pump();

      expect(find.text(entry.title), findsOneWidget);
      expect(find.text(entry.message), findsOneWidget);
      expect(find.text(SearchText.reload), findsOneWidget);
      expect(find.byType(Icon), findsNothing);
      expect(find.textContaining(entry.failure.code), findsNothing);
      expect(find.textContaining(entry.failure.semanticReason), findsNothing);
      expect(find.textContaining('discovery_feed_provider'), findsNothing);
    }
  });

  testWidgets('首页关注按钮登录态点击后同步为已关注', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(_buildFeed(_microPost(), authenticated: true));
    await tester.pump();

    expect(find.text(FoundationText.follow), findsOneWidget);
    final followButton = find.byKey(
      const ValueKey<String>('home-post-author-follow-button'),
    );
    expect(followButton, findsOneWidget);
    final followWidth = tester.getSize(followButton).width;
    expect(followWidth, AppSpacing.followButtonWidthCompact);
    expect(tester.getSize(followButton).height, AppSpacing.buttonHeightXs);

    await tester.tap(find.text(FoundationText.follow));
    await tester.pump();

    expect(find.text(FoundationText.following), findsOneWidget);
    final followingButton = find.byKey(
      const ValueKey<String>('home-post-author-follow-button'),
    );
    expect(followingButton, findsOneWidget);
    final followingWidth = tester.getSize(followingButton).width;
    expect(followingWidth, AppSpacing.followButtonWidthCompact);
    expect(followingWidth, followWidth);
  });

  testWidgets('首页 canonical mock feed 往返后保留交集 span 强调与点击目标', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    final showcasePost = _homeShowcasePost();
    final reason = showcasePost.intersectionReasons!.first;
    expect(reason.actorEvidenceTotalCount, 3);
    expect(reason.actorEvidenceCompleteness, 'complete');
    expect(reason.actorEvidence, hasLength(3));
    expect(reason.actorEvidence.first.relationLabel, '联系人');
    expect(reason.actorEvidence.first.actionSummaryText, '赞过川西雪山和校园摄影路线');

    await tester.pumpWidget(_buildFeed(showcasePost));
    await tester.pump();

    final richText = tester.widget<RichText>(
      find.descendant(
        of: find.byType(InteractiveIntersectionText),
        matching: find.byType(RichText),
      ),
    );
    final textContext = tester.element(
      find.byType(InteractiveIntersectionText),
    );
    final nameSpan = _spanByText(richText, '林清越');
    final countSpan = _spanByText(richText, '3');

    final isDark = CupertinoTheme.of(textContext).brightness == Brightness.dark;
    final accentColor = isDark
        ? AppColors.profileSloganAccentDark
        : AppColors.profileSloganAccentLight;
    expect(nameSpan.style?.color, accentColor);
    expect(countSpan.style?.color, accentColor);
    expect(
      _fontWeightValue(nameSpan),
      greaterThan(_fontWeightValue(_spanByText(richText, '联系人'))),
    );
    expect(nameSpan.recognizer, isA<TapGestureRecognizer>());
    expect(countSpan.recognizer, isA<TapGestureRecognizer>());
  });

  testWidgets('首页实体对象并入交集句，不再单独渲染孤立实体标签', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(
      _buildFeed(
        _photoPost(width: 1080, height: 1920, reason: _photoSpotReason()),
      ),
    );
    await tester.pump();

    expect(
      find.byKey(const ValueKey<String>('home-connection-badges-row')),
      findsNothing,
    );
    final richText = tester.widget<RichText>(
      find.descendant(
        of: find.byType(InteractiveIntersectionText),
        matching: find.byType(RichText),
      ),
    );
    expect(richText.text.toPlainText(), '你关注的人山川手账等7人也关注了「横竖影像馆取景地」');
    expect(
      _spanByText(richText, '横竖影像馆取景地').recognizer,
      isA<TapGestureRecognizer>(),
    );
  });

  testWidgets('约伴徽标只由云侧重社交 actionHint 驱动（有 start_gathering 展示有人同行）', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    final reason = _canonicalReason(
      dimension: 'interest',
      intersectionId: 'ix_companion_demo',
      intersectionClass: 'recommended',
      objectKind: 'person',
      source: 'coWishlistedEntity',
      actionTargetId: 'fixture_user_companion',
      pointSummarySnapshotId: 'snap_companion_demo',
      displayBinding: 'host_implicit',
      actorEvidenceTotalCount: 0,
      actorEvidenceCompleteness: 'complete',
      primaryText: '',
      primarySpans: const <IntersectionTextSpan>[],
      actionHints: <IntersectionActionHint>[
        IntersectionActionHint(
          actionKey: 'start_gathering',
          label: '发起结伴',
          isPrimary: true,
          priority: 0,
          actionTier: 'heavy',
          requiredGates: const <String>[],
          dispatch: 'gathering',
        ),
      ],
    );
    await tester.pumpWidget(_buildFeed(_microPost(reason: reason)));
    await tester.pump();

    expect(find.text(AppConceptConstants.feedBadgeCompanion), findsOneWidget);
  });

  testWidgets('内容含地名但无 actionHint 不伪造约伴徽标（防地名启发式回归）', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    // _microPost 的 body 含「川西」：旧实现按 travelHints 地名字符串误判展示约伴徽标，
    // 修复后端只读云侧 actionHint（守元数据驱动 + §24.10 诚实红线），不再按内容猜测行动。
    final reason = _canonicalReason(
      dimension: 'content',
      intersectionId: 'ix_plain_demo',
      intersectionClass: 'fact',
      objectKind: 'content',
      source: 'coCommented',
      actionTargetId: 'post_plain_demo',
      pointSummarySnapshotId: 'snap_plain_demo',
      displayBinding: 'host_implicit',
      actorEvidenceTotalCount: 0,
      actorEvidenceCompleteness: 'complete',
      primaryText: '',
      primarySpans: const <IntersectionTextSpan>[],
    );
    await tester.pumpWidget(_buildFeed(_microPost(reason: reason)));
    await tester.pump();

    expect(find.text(AppConceptConstants.feedBadgeCompanion), findsNothing);
  });

  testWidgets('个人记录图片按 1-9+ 图规则展示并在末格聚合剩余张数', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    Future<void> pumpMomentGrid(int count) async {
      await tester.pumpWidget(
        _buildFeed(
          _microPost(
            imageUrls: List<String>.generate(
              count,
              (index) =>
                  'media/image/s/archived-image/post/fixture_photo_001/v1/image-$index.png',
            ),
          ),
        ),
      );
      await tester.pump();
    }

    await pumpMomentGrid(1);
    expect(find.byKey(const ValueKey('home-moment-grid')), findsOneWidget);
    expect(
      find.byKey(const ValueKey('home-moment-grid-tile-0')),
      findsOneWidget,
    );
    expect(find.byKey(const ValueKey('home-moment-grid-more')), findsNothing);
    final bodyTop = tester
        .getTopLeft(find.byKey(const ValueKey('home-relation-card-body')))
        .dy;
    final gridTop = tester
        .getTopLeft(find.byKey(const ValueKey('home-relation-card-media')))
        .dy;
    final reasonTop = tester
        .getTopLeft(find.byKey(const ValueKey('home-post-inline-intersection')))
        .dy;
    expect(bodyTop, lessThan(reasonTop));
    expect(gridTop, lessThan(reasonTop));
    final singleGrid = tester.getSize(
      find.byKey(const ValueKey('home-moment-grid')),
    );
    final singleCard = tester.getSize(
      find.byKey(const ValueKey('home-feed-card-0')),
    );
    expect(singleGrid.width, closeTo((singleCard.width - 32) / 3, 8));
    final singleTile = tester.getSize(
      find.byKey(const ValueKey('home-moment-grid-tile-0')),
    );
    expect(singleTile.width, closeTo(singleGrid.width, 1));

    await pumpMomentGrid(2);
    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget.key is ValueKey<String> &&
            (widget.key! as ValueKey<String>).value.startsWith(
              'home-moment-grid-tile-',
            ),
      ),
      findsNWidgets(2),
    );
    final doubleGrid = tester.getSize(
      find.byKey(const ValueKey('home-moment-grid')),
    );
    final doubleCard = tester.getSize(
      find.byKey(const ValueKey('home-feed-card-0')),
    );
    expect(doubleGrid.width, closeTo((doubleCard.width - 32) * 2 / 3, 8));
    final doubleFirstTile = tester.getSize(
      find.byKey(const ValueKey('home-moment-grid-tile-0')),
    );
    expect(doubleFirstTile.width, closeTo(singleTile.width, 4));

    await pumpMomentGrid(4);
    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget.key is ValueKey<String> &&
            (widget.key! as ValueKey<String>).value.startsWith(
              'home-moment-grid-tile-',
            ),
      ),
      findsNWidgets(4),
    );
    expect(find.byKey(const ValueKey('home-moment-grid-more')), findsNothing);
    final fourGrid = tester.getSize(
      find.byKey(const ValueKey('home-moment-grid')),
    );
    expect(fourGrid.width, greaterThan(doubleGrid.width));

    await pumpMomentGrid(5);
    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget.key is ValueKey<String> &&
            (widget.key! as ValueKey<String>).value.startsWith(
              'home-moment-grid-tile-',
            ),
      ),
      findsNWidgets(3),
    );
    expect(find.text('+2'), findsOneWidget);
    expect(find.byKey(const ValueKey('home-moment-grid-more')), findsOneWidget);

    await pumpMomentGrid(6);
    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget.key is ValueKey<String> &&
            (widget.key! as ValueKey<String>).value.startsWith(
              'home-moment-grid-tile-',
            ),
      ),
      findsNWidgets(6),
    );
    expect(find.byKey(const ValueKey('home-moment-grid-more')), findsNothing);

    await pumpMomentGrid(7);
    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget.key is ValueKey<String> &&
            (widget.key! as ValueKey<String>).value.startsWith(
              'home-moment-grid-tile-',
            ),
      ),
      findsNWidgets(6),
    );
    expect(find.text('+1'), findsOneWidget);
    final moreTile = find.byKey(const ValueKey('home-moment-grid-tile-5'));
    final moreStack = tester.widget<Stack>(moreTile);
    expect(moreStack.children.first, isA<AppCachedNetworkImage>());
    expect(
      find.descendant(
        of: moreTile,
        matching: find.byType(AppCachedNetworkImage),
      ),
      findsOneWidget,
    );
    final scrim = tester.widget<DecoratedBox>(
      find.byKey(const ValueKey('home-moment-grid-more-scrim')),
    );
    final scrimDecoration = scrim.decoration as BoxDecoration;
    expect(scrimDecoration.color, isNull);
    expect(scrimDecoration.gradient, isA<LinearGradient>());
    final gradient = scrimDecoration.gradient! as LinearGradient;
    expect(gradient.colors, isNot(contains(AppColors.overlayStrong)));
    final morePill = tester.widget<DecoratedBox>(
      find.descendant(
        of: find.byKey(const ValueKey('home-moment-grid-more')),
        matching: find.byType(DecoratedBox),
      ),
    );
    final pillDecoration = morePill.decoration as BoxDecoration;
    expect(pillDecoration.color, isNot(AppColors.overlayStrong));
    expect(pillDecoration.color, isNot(AppColors.overlayMedium));
    expect(pillDecoration.borderRadius, isNotNull);
    final pillSize = tester.getSize(
      find.byKey(const ValueKey('home-moment-grid-more')),
    );
    final tileSize = tester.getSize(moreTile);
    expect(pillSize.height, DiscoveryFeedSpacing.homeFeedGridMorePillHeight);
    expect(pillSize.width, lessThan(tileSize.width * 0.5));

    await pumpMomentGrid(8);
    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget.key is ValueKey<String> &&
            (widget.key! as ValueKey<String>).value.startsWith(
              'home-moment-grid-tile-',
            ),
      ),
      findsNWidgets(6),
    );
    expect(find.text('+2'), findsOneWidget);

    await pumpMomentGrid(10);
    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget.key is ValueKey<String> &&
            (widget.key! as ValueKey<String>).value.startsWith(
              'home-moment-grid-tile-',
            ),
      ),
      findsNWidgets(9),
    );
    expect(find.text('+1'), findsOneWidget);
  });

  testWidgets('图片 post 单图满宽，多图使用横滑轮播、底部点状与右上角数字指示器', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(_buildFeed(_photoPost(width: 1600, height: 900)));
    await tester.pump();
    final card = tester.getSize(find.byKey(const ValueKey('home-feed-card-0')));
    final media = find.byKey(const ValueKey('home-relation-card-media'));
    final landscape = tester.getSize(
      find.descendant(of: media, matching: find.byType(ClipRRect)).first,
    );
    expect(landscape.width, closeTo(card.width - 32, 8));
    final landscapeClip = tester.widget<ClipRRect>(
      find.descendant(of: media, matching: find.byType(ClipRRect)).first,
    );
    final landscapeRadius = landscapeClip.borderRadius as BorderRadius;
    expect(
      landscapeRadius.topLeft.x,
      DiscoveryFeedSpacing.homeFeedMediaCornerRadius,
    );
    expect(
      find.descendant(
        of: media,
        matching: find.byType(InteractiveIntersectionText),
      ),
      findsNothing,
    );
    expect(
      find.descendant(
        of: find.byKey(const ValueKey('home-post-inline-intersection')),
        matching: find.byKey(const ValueKey('home-intersection-glyph')),
      ),
      findsNothing,
    );
    expect(
      find.descendant(
        of: media,
        matching: find.byKey(const ValueKey('home-intersection-glyph')),
      ),
      findsNothing,
    );
    expect(
      find.descendant(of: media, matching: find.byType(BackdropFilter)),
      findsNothing,
    );
    expect(
      find.descendant(of: media, matching: find.byIcon(CupertinoIcons.link)),
      findsNothing,
    );
    final mediaTop = tester.getTopLeft(media).dy;
    final reasonTop = tester
        .getTopLeft(find.byKey(const ValueKey('home-post-inline-intersection')))
        .dy;
    final bodyTop = tester
        .getTopLeft(find.byKey(const ValueKey('home-relation-card-body')))
        .dy;
    expect(mediaTop, lessThan(bodyTop));
    expect(bodyTop, lessThan(reasonTop));

    await tester.pumpWidget(
      _buildFeed(
        _photoPost(
          width: 1600,
          height: 900,
          imageUrls: List<String>.generate(
            8,
            (index) =>
                'media/image/s/archived-image/post/fixture_photo_002/v1/image-$index.png',
          ),
        ),
      ),
    );
    await tester.pump();
    expect(find.byType(PageView), findsWidgets);
    expect(
      find.byKey(const ValueKey('home-image-carousel-counter')),
      findsOneWidget,
    );
    expect(find.text('1/8'), findsOneWidget);
    expect(
      find.byKey(const ValueKey('home-image-carousel-dots')),
      findsOneWidget,
    );
    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget.key is ValueKey<String> &&
            (widget.key! as ValueKey<String>).value.startsWith(
              'home-image-carousel-dot-',
            ),
      ),
      findsNWidgets(6),
    );
    final dot = tester.widget<AnimatedContainer>(
      find.byKey(const ValueKey('home-image-carousel-dot-0')),
    );
    final dotDecoration = dot.decoration as BoxDecoration;
    expect(dotDecoration.color, isNot(AppColors.black));
    expect(dotDecoration.shape, BoxShape.circle);
  });

  testWidgets('视频 post 首帧先延迟初始化，避免焦点瞬间抢播', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    final post = _videoPost(width: 900, height: 1600);
    await tester.pumpWidget(_buildFeed(post));
    await tester.pump();

    final media = find.byKey(const ValueKey('home-relation-card-media'));
    expect(
      find.byKey(ValueKey<String>('home-video-focus-paused-${post.id}')),
      findsOneWidget,
    );
    expect(
      find.byKey(ValueKey<String>('home-video-player-${post.id}')),
      findsOneWidget,
    );
    expect(find.byType(VideoPlayerWidget), findsOneWidget);
    final player = tester.widget<VideoPlayerWidget>(
      find.byKey(ValueKey<String>('home-video-player-${post.id}')),
    );
    expect(player.initialize, isFalse);
    expect(player.autoPlay, isFalse);
    expect(
      find.descendant(
        of: find.byKey(const ValueKey('home-post-inline-intersection')),
        matching: find.byKey(const ValueKey('home-intersection-glyph')),
      ),
      findsNothing,
    );
    expect(
      find.descendant(
        of: media,
        matching: find.byType(InteractiveIntersectionText),
      ),
      findsNothing,
    );
    expect(find.text('视频画面下方的配文'), findsOneWidget);

    final reasonTop = tester
        .getTopLeft(find.byKey(const ValueKey('home-post-inline-intersection')))
        .dy;
    final mediaTop = tester.getTopLeft(media).dy;
    final bodyTop = tester.getTopLeft(find.text('视频画面下方的配文')).dy;
    expect(mediaTop, lessThan(bodyTop));
    expect(bodyTop, lessThan(reasonTop));
    final card = tester.getSize(find.byKey(const ValueKey('home-feed-card-0')));
    final video = tester.getSize(
      find.descendant(of: media, matching: find.byType(ClipRRect)).first,
    );
    expect(video.width, lessThan(card.width - 32));
    expect(video.width, greaterThan((card.width - 32) * 0.55));
  });

  testWidgets('首页视频卸载后的有效播放回调复用活跃帧端口，不读取失效 WidgetRef', (tester) async {
    final behaviorRepo = RecordingContentBehaviorRepository();
    final tracker = ContentBehaviorTracker(
      reporter: behaviorRepo,
      maxBatchSize: 1,
      enablePeriodicFlush: false,
    );
    addTearDown(tracker.dispose);

    await tester.pumpWidget(
      _buildFeed(_videoPost(width: 1080, height: 1920), tracker: tracker),
    );
    await tester.pump();
    final player = tester.widget<VideoPlayerWidget>(
      find.byType(VideoPlayerWidget),
    );
    final reportEffectivePlayback = player.onEffectivePlayback!;

    await tester.pumpWidget(const SizedBox.shrink());
    reportEffectivePlayback(
      const VideoEffectivePlaybackEvidence(
        playbackSessionId: 'video-session-after-home-deactivate',
        effectivePlayMs: 6000,
        consumedRatio: 0.35,
        totalUnits: 17,
      ),
    );
    await tracker.flush();

    expect(tester.takeException(), isNull);
    final event = behaviorRepo.recorded.single;
    expect(event.action, BehaviorEventType.effectivePlay);
    expect(event.playbackSessionId, 'video-session-after-home-deactivate');
  });

  test('视频 post 外层播放按钮只属于未初始化静态封面态', () {
    final source = File(
      'lib/service/content_service/content/post/presentation/home_multi_form_feed_media_grid.dart',
    ).readAsStringSync();
    expect(source, contains('if (!initialize && !autoPlay)'));
    expect(source, isNot(contains('if (!autoPlay)\n              Center(')));
  });

  test('视频快滑抑制事件走统一 cache telemetry sink', () {
    final postCardSource = File(
      'lib/service/content_service/content/post/presentation/home_multi_form_feed_post_cards.dart',
    ).readAsStringSync();
    final mediaSource = File(
      'lib/service/content_service/content/post/presentation/home_multi_form_feed_media.dart',
    ).readAsStringSync();

    expect(postCardSource, contains('cacheTelemetrySinkProvider'));
    expect(postCardSource, contains('video.init.suppressed_fast_scroll'));
    expect(mediaSource, isNot(contains('developer.log')));
  });

  testWidgets('文章 post 支持无图短文、无图长文、上文下图和左文右图', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(
      _buildFeed(
        _articleLayoutPost(
          id: 'article_text_short',
          bodyValue: '这是一段三行内能读完的短文摘要。',
        ),
      ),
    );
    await tester.pump();
    expect(find.byKey(const ValueKey('home-article-card')), findsOneWidget);
    expect(
      find.byKey(const ValueKey('home-article-layout-text-only')),
      findsOneWidget,
    );
    expect(find.byKey(const ValueKey('home-article-full-text')), findsNothing);
    final titleText = tester.widget<Text>(
      find.byKey(const ValueKey('home-post-title')),
    );
    expect(titleText.maxLines, 1);
    final summaryText = tester.widget<Text>(find.text('这是一段三行内能读完的短文摘要。'));
    expect(summaryText.style?.fontWeight, FontWeight.normal);
    final inlineTop = tester
        .getTopLeft(
          find.byKey(const ValueKey('home-article-inline-intersection')),
        )
        .dy;
    expect(
      find.descendant(
        of: find.byKey(const ValueKey('home-article-inline-intersection')),
        matching: find.byKey(const ValueKey('home-intersection-glyph')),
      ),
      findsNothing,
    );
    final bodyTop = tester.getTopLeft(find.textContaining('这是一段')).dy;
    expect(bodyTop, lessThan(inlineTop));

    await tester.pumpWidget(
      _buildFeed(
        _articleLayoutPost(
          id: 'article_text_long',
          bodyValue:
              '这是一段无图长文摘要，用来验证首页文章卡在超过三行时才展示全文入口。它继续补充场景、人物和路线，让文本在手机宽度下自然溢出第三行，并且点击整卡或全文入口都进入同一篇文章浏览器。',
        ),
      ),
    );
    await tester.pump();
    expect(
      find.byKey(const ValueKey('home-article-layout-text-only')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('home-article-full-text')),
      findsOneWidget,
    );

    await tester.pumpWidget(
      _buildFeed(
        _articleLayoutPost(
          id: 'article_side',
          bodyValue: '短图文保持左文右图，快速扫读也能看到封面。',
          coverUrlValue:
              'media/image/s/archived-image/post/fixture_article_001/v1/cover.png',
        ),
      ),
    );
    await tester.pump();
    expect(
      find.byKey(const ValueKey('home-article-layout-side-image')),
      findsOneWidget,
    );
    final sideSummary = tester.widget<Text>(find.text('短图文保持左文右图，快速扫读也能看到封面。'));
    expect(sideSummary.style?.fontWeight, FontWeight.normal);
    final titleRect = tester.getRect(
      find.byKey(const ValueKey('home-post-title')),
    );
    final thumbRect = tester.getRect(
      find.byKey(const ValueKey('home-article-side-thumb')),
    );
    final thumbAspectRatio = thumbRect.width / thumbRect.height;
    expect(
      thumbAspectRatio,
      closeTo(DiscoveryFeedSpacing.homeFeedArticleSideThumbAspectRatio, 0.02),
    );
    final bodyRect = tester.getRect(find.text('短图文保持左文右图，快速扫读也能看到封面。'));
    final intersectionRect = tester.getRect(
      find.byKey(const ValueKey('home-article-inline-intersection')),
    );
    final cardRect = tester.getRect(
      find.byKey(const ValueKey('home-feed-card-0')),
    );
    expect(thumbRect.top, greaterThan(titleRect.bottom - 1));
    expect((bodyRect.top - thumbRect.top).abs(), lessThan(2));
    expect(bodyRect.right, lessThan(thumbRect.left + 1));
    expect(intersectionRect.top, greaterThan(thumbRect.bottom - 1));
    expect(intersectionRect.right, greaterThanOrEqualTo(bodyRect.right - 1));
    expect(intersectionRect.right, lessThanOrEqualTo(cardRect.right));

    await tester.pumpWidget(
      _buildFeed(
        _articleLayoutPost(
          id: 'article_top',
          bodyValue:
              '有图长文在摘要较长时采用上文下图，让图片承担情绪收束，正文先交代推荐理由和阅读入口。这里继续补充一段描述，让布局明确进入上文下图状态。',
          coverUrlValue:
              'media/image/s/archived-image/post/fixture_article_001/v1/image-2.png',
        ),
      ),
    );
    await tester.pump();
    expect(
      find.byKey(const ValueKey('home-article-layout-top-image')),
      findsOneWidget,
    );
  });

  testWidgets('文章整卡与全文入口点击进入同一沉浸 pageflip 打开链路', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    final opened = <ContentPostViewData>[];
    await tester.pumpWidget(
      _buildFeed(
        _articleLayoutPost(
          id: 'article_open',
          bodyValue:
              '这是一段用于点击测试的长文摘要，用来确保全文入口出现。它继续补充场景、人物和路线，让文本在手机宽度下自然溢出第三行，并且点击整卡或全文入口都进入同一篇文章浏览器。',
        ),
        onPostTap: (post, _, {feedPosts}) => opened.add(post),
      ),
    );
    await tester.pump();

    await tester.tap(find.byKey(const ValueKey('home-article-card')));
    await tester.pump();
    expect(opened.map((post) => post.id), <String>['article_open']);

    await tester.tap(find.byKey(const ValueKey('home-article-full-text')));
    await tester.pump();
    expect(opened.map((post) => post.id), <String>[
      'article_open',
      'article_open',
    ]);
  });

  testWidgets('内容卡曝光与媒体点击透传 referralSource、position、feedRequestId', (
    tester,
  ) async {
    final behaviorRepo = RecordingContentBehaviorRepository();
    final tracker = ContentBehaviorTracker(
      reporter: behaviorRepo,
      maxBatchSize: 1,
      enablePeriodicFlush: false,
    );
    addTearDown(tracker.dispose);

    var opened = false;
    await tester.pumpWidget(
      _buildFeed(
        _microPost(),
        tracker: tracker,
        onPostTap: (_, _, {feedPosts}) => opened = true,
      ),
    );
    await tester.pump();
    // impressed 只允许由真实视口可见比例 ≥50% 且连续停留 ≥1s 产生。
    await tester.pump(const Duration(milliseconds: 1250));

    final impressions = behaviorRepo.recorded
        .where(
          (event) =>
              event.action == BehaviorEventType.impression &&
              event.contentId == 'post_intersection_demo_fact_1',
        )
        .toList(growable: false);
    expect(impressions, hasLength(1));
    expect(impressions.single.position, 0);
    expect(impressions.single.referralSource, ReferralSource.organicFeed);

    await tester.tap(find.byKey(const ValueKey('home-moment-grid-tile-0')));
    await tester.pump();
    expect(opened, isTrue);
    final clicks = behaviorRepo.recorded
        .where((event) => event.action == BehaviorEventType.click)
        .toList(growable: false);
    expect(clicks, hasLength(1));
    expect(clicks.single.position, 0);
    expect(clicks.single.referralSource, ReferralSource.organicFeed);
    expect(clicks.single.feedRequestId, isNotEmpty);
  });

  // ── N6：交集 span 点击埋点带全归因，且保持 tag_click 推荐权重语义 ──
  testWidgets(
    '点击交集名字 span → trackTagClick 透传 intersectionSourceRef + evidenceId',
    (tester) async {
      await tester.binding.setSurfaceSize(const Size(390, 844));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      final behaviorRepo = RecordingContentBehaviorRepository();
      final tracker = ContentBehaviorTracker(
        reporter: behaviorRepo,
        maxBatchSize: 1,
        enablePeriodicFlush: false,
      );
      addTearDown(tracker.dispose);

      await tester.pumpWidget(_routedFeed(_microPost(), tracker: tracker));
      await tester.pump();

      final richText = tester.widget<RichText>(
        find.descendant(
          of: find.byType(InteractiveIntersectionText),
          matching: find.byType(RichText),
        ),
      );
      final nameSpan = _spanByText(richText, '林清越');
      (nameSpan.recognizer! as TapGestureRecognizer).onTap!();
      await tester.pump();
      await tracker.flush();

      final clicks = behaviorRepo.recorded
          .where((event) => event.action == BehaviorEventType.tagClick)
          .toList(growable: false);
      expect(clicks, hasLength(1));
      final click = clicks.single;
      // 关键回归：sourceRef / evidenceId 由 attribution 真正转发到埋点（此前被丢）。
      expect(click.intersectionSourceRef, equals('coCommented'));
      expect(click.intersectionEvidenceId, equals('snap_lin'));
      expect(click.intersectionId, equals('ix_post_lin'));
      expect(click.intersectionDimension, equals('content'));
      expect(click.intersectionTagRefs, isNotNull);
    },
  );

  // ── 首页卡想去动作（意图环 L0 氛围层，B10 三表面之三）──
  // spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/text-post-commercial-publication/spec.md#gwt-006

  testWidgets('无实体锚点的内容卡不渲染想去动作，不做本地推断', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(_buildFeed(_microPost()));
    await tester.pump();

    expect(find.byKey(_kHomeCardWishlistKey), findsNothing);
  });

  testWidgets('实体锚点内容卡渲染想去动作；游客点击设置双目标续接不静默丢失', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    final behaviorRepo = RecordingContentBehaviorRepository();
    final tracker = ContentBehaviorTracker(
      reporter: behaviorRepo,
      maxBatchSize: 1,
      enablePeriodicFlush: false,
    );
    addTearDown(tracker.dispose);

    late final ProviderContainer container;
    await tester.pumpWidget(
      _routedFeed(
        _wishlistAnchoredPost(),
        tracker: tracker,
        extraOverrides: <Override>[
          intersectionRepositoryProvider.overrideWithValue(
            _EmptyObjectIntersectionRepository(),
          ),
        ],
      ),
    );
    await tester.pump();
    container = ProviderScope.containerOf(
      tester.element(find.byType(HomeMultiFormFeed)),
    );

    final wishlistAction = find.byKey(_kHomeCardWishlistKey);
    expect(wishlistAction, findsOneWidget);

    await tester.ensureVisible(wishlistAction);
    await tester.tap(wishlistAction, warnIfMissed: false);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    final pending = container.read(authContinuationProvider);
    expect(pending, isA<WishlistHomepageContinuation>());
    expect(
      (pending! as WishlistHomepageContinuation).homepageId,
      'homepage-wish-card-1',
    );
    expect(
      behaviorRepo.recorded.where(
        (event) => event.action == BehaviorEventType.wishlistAdd,
      ),
      isEmpty,
      reason: '未登录不得发出 wishlist 行为事实',
    );
  });

  testWidgets('登录后点击想去 → wishlist 行为事实上报并诚实确认（无交集不伪造）', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    final behaviorRepo = RecordingContentBehaviorRepository();
    final tracker = ContentBehaviorTracker(
      reporter: behaviorRepo,
      maxBatchSize: 1,
      enablePeriodicFlush: false,
    );
    addTearDown(tracker.dispose);

    await tester.pumpWidget(
      _routedFeed(
        _wishlistAnchoredPost(),
        tracker: tracker,
        authenticated: true,
        extraOverrides: <Override>[
          intersectionRepositoryProvider.overrideWithValue(
            _EmptyObjectIntersectionRepository(),
          ),
        ],
      ),
    );
    await tester.pump();

    final wishlistAction = find.byKey(_kHomeCardWishlistKey);
    await tester.ensureVisible(wishlistAction);
    await tester.tap(wishlistAction, warnIfMissed: false);
    for (var i = 0; i < 8; i += 1) {
      await tester.pump(const Duration(milliseconds: 60));
    }

    final wishlistEvents = behaviorRepo.recorded
        .where((event) => event.action == BehaviorEventType.wishlistAdd)
        .toList(growable: false);
    expect(wishlistEvents, hasLength(1));
    expect(wishlistEvents.single.contentId, 'homepage-wish-card-1');
    expect(
      find.text(ObjectHomepageText.wishlistAddedFeedback),
      findsOneWidget,
      reason: '无交集时只确认动作本身，不伪造社会证明',
    );
    // 排空 toast 自动消失 Timer，避免测试结束时残留计时器。
    await tester.pump(const Duration(seconds: 4));
  });
}

const _kHomeCardWishlistKey = ValueKey<String>('home-card-wishlist-action');

/// 锚定到支持想去类型实体主页（sight）的内容卡 fixture。
ContentPostViewData _wishlistAnchoredPost() {
  return ContentPostViewData(
    id: 'post_wishlist_card_1',
    type: 'image',
    identity: 'work',
    displayFormat: 'image',
    assistantUsePolicy: AssistantUsePolicy.inherit,
    authorId: 'user_wish_author',
    displayName: '风光摄影师',
    avatarUrl: '',
    authorBackgroundUrl: null,
    authorRoleLabel: '',
    authorIdentityTags: const <String>[],
    authorVerified: false,
    body: '黄龙五彩池的秋天',
    imageUrls: const <String>[
      'media/image/s/archived-image/post/fixture_wish_001/v1/cover.png',
    ],
    likeCount: 3,
    commentCount: 1,
    shareCount: 0,
    createdAt: DateTime(2026),
    primaryHomepageId: 'homepage-wish-card-1',
    primaryHomepageType: 'sight',
  );
}

/// 对象级 typed double：对象交集恒为空（诚实空态分支）。
final class _EmptyObjectIntersectionRepository implements IntersectionRepository {
  @override
  Future<IntersectionInboxSummary> getMyIntersectionSummary() {
    throw StateError('该 contract 不应读取交集收件箱摘要');
  }

  @override
  Future<List<IntersectionReason>> listMyIntersections({
    String? dimension,
    String? filter,
    String? sourceRef,
    String? timeBucket,
    String? cursor,
    int limit = CloudApiQueryDefaults.intersectionListLimit,
  }) {
    throw StateError('该 contract 不应列出我的交集');
  }

  @override
  Future<List<IntersectionReason>> getObjectIntersections({
    required String objectId,
    required String objectType,
    int limit = CloudApiQueryDefaults.objectIntersectionsLimit,
  }) async => const <IntersectionReason>[];
}

/// N6：带 GoRouter 的 feed 宿主，使交集 span 点击的 `context.push` 可达，
/// 从而验证 onTrack → trackTagClick 的归因字段透传（`/user/:userHandle` 复用
/// resolvePath(userProfile) 的 codegen 路由）。
Widget _routedFeed(
  ContentPostViewData post, {
  required ContentBehaviorTracker tracker,
  bool authenticated = false,
  List<Override> extraOverrides = const <Override>[],
}) {
  final router = GoRouter(
    initialLocation: '/',
    routes: <RouteBase>[
      GoRoute(
        path: '/',
        builder: (_, _) => ScreenUtilInit(
          designSize: const Size(390, 844),
          child: MediaQuery(
            data: const MediaQueryData(size: Size(390, 844)),
            child: HomeMultiFormFeed(
              isDark: false,
              channelId: 'recommend',
              template: 'single_column_multiform',
              onUserTap: (_, {avatarUrl, backgroundUrl, displayName}) {},
              onPostTap: null,
            ),
          ),
        ),
      ),
      GoRoute(path: '/login', builder: (_, _) => const SizedBox.shrink()),
      GoRoute(
        path: '/user/:userHandle',
        builder: (_, state) =>
            Text('USER:${state.pathParameters['userHandle']}'),
      ),
    ],
  );
  return ProviderScope(
    key: ValueKey<String>('routed-feed-scope-${post.id}'),
    overrides: _boundaryOverrides(
      extra: <Override>[
        ...mockContentFacetOverrides(store: InMemoryContentPostStore()),
        mediaEndpointConfigProvider.overrideWithValue(_testMediaEndpointConfig),
        discoveryFeedMapProvider.overrideWith(
          () => _SinglePostFeedMapNotifier(post),
        ),
        mediaDownloadCacheProvider.overrideWithValue(_NoopMediaDownloadCache()),
        contentBehaviorTrackerProvider.overrideWithValue(tracker),
        if (authenticated)
          authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
        ...extraOverrides,
      ],
    ),
    child: CupertinoApp.router(routerConfig: router),
  );
}

class _AuthenticatedSession extends AuthSessionController {
  @override
  AuthSessionState build() {
    return const AuthSessionState(
      status: AuthSessionStatus.authenticated,
      accessToken: 'test-token',
      refreshToken: 'test-refresh-token',
      ownerId: 'test-user',
      activePersonaId: 'test-persona',
      accountState: 'active',
      identityOrigin: 'test',
      installId: 'test-install',
    );
  }
}

class _SinglePostFeedMapNotifier extends DiscoveryFeedMapNotifier {
  _SinglePostFeedMapNotifier(this.post);

  final ContentPostViewData post;

  @override
  Map<String, AsyncValue<DiscoveryFeedState>> build() {
    return <String, AsyncValue<DiscoveryFeedState>>{
      'recommend': AsyncData(
        DiscoveryFeedState(
          items: <ContentPostViewData>[post],
          feedRequestId: 'frq_local_contract_single_post',
          policyDigest:
              'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        ),
      ),
    };
  }

  @override
  Future<DiscoveryFeedLoadResult> load(
    String channelId, {
    bool force = false,
  }) async => DiscoveryFeedLoadResult(
    terminal: DiscoveryFeedLoadTerminal.content,
    generation: 0,
  );
}

class _FollowingEmptyFeedMapNotifier extends DiscoveryFeedMapNotifier {
  @override
  Map<String, AsyncValue<DiscoveryFeedState>> build() {
    return <String, AsyncValue<DiscoveryFeedState>>{
      'following': AsyncData(
        const DiscoveryFeedState(
          items: <ContentPostViewData>[],
          emptyReason: ContentFeedEmptyReason.followingEmpty,
        ),
      ),
    };
  }

  @override
  Future<DiscoveryFeedLoadResult> load(
    String channelId, {
    bool force = false,
  }) async => DiscoveryFeedLoadResult(
    terminal: DiscoveryFeedLoadTerminal.canonicalEmpty,
    generation: 0,
  );
}

class _RecommendEmptyFeedMapNotifier extends DiscoveryFeedMapNotifier {
  @override
  Map<String, AsyncValue<DiscoveryFeedState>> build() {
    return <String, AsyncValue<DiscoveryFeedState>>{
      'recommend': AsyncData(
        const DiscoveryFeedState(items: <ContentPostViewData>[]),
      ),
    };
  }

  @override
  Future<DiscoveryFeedLoadResult> load(
    String channelId, {
    bool force = false,
  }) async => DiscoveryFeedLoadResult(
    terminal: DiscoveryFeedLoadTerminal.canonicalEmpty,
    generation: 0,
  );
}

class _RecommendCanonicalEmptyFeedMapNotifier extends DiscoveryFeedMapNotifier {
  @override
  Map<String, AsyncValue<DiscoveryFeedState>> build() {
    return <String, AsyncValue<DiscoveryFeedState>>{
      'recommend': AsyncData(
        const DiscoveryFeedState(
          items: <ContentPostViewData>[],
          emptyReason: ContentFeedEmptyReason.noEligibleContent,
        ),
      ),
    };
  }

  @override
  Future<DiscoveryFeedLoadResult> load(
    String channelId, {
    bool force = false,
  }) async => DiscoveryFeedLoadResult(
    terminal: DiscoveryFeedLoadTerminal.canonicalEmpty,
    generation: 0,
  );
}

class _NoActiveReleaseFeedMapNotifier extends DiscoveryFeedMapNotifier {
  int forceLoadCalls = 0;

  @override
  Map<String, AsyncValue<DiscoveryFeedState>> build() {
    return <String, AsyncValue<DiscoveryFeedState>>{
      'recommend': const AsyncData(
        DiscoveryFeedState(
          items: <ContentPostViewData>[],
          emptyReason: ContentFeedEmptyReason.noActiveRelease,
        ),
      ),
    };
  }

  @override
  Future<DiscoveryFeedLoadResult> load(
    String channelId, {
    bool force = false,
  }) async {
    if (force) {
      forceLoadCalls += 1;
    }
    return DiscoveryFeedLoadResult(
      terminal: DiscoveryFeedLoadTerminal.canonicalEmpty,
      generation: 0,
    );
  }
}

class _BlockingErrorFeedMapNotifier extends DiscoveryFeedMapNotifier {
  _BlockingErrorFeedMapNotifier(this.error);

  final RuntimeFailure error;

  @override
  Map<String, AsyncValue<DiscoveryFeedState>> build() {
    return <String, AsyncValue<DiscoveryFeedState>>{
      'recommend': AsyncData(DiscoveryFeedState(blockingError: error)),
    };
  }

  @override
  Future<DiscoveryFeedLoadResult> load(
    String channelId, {
    bool force = false,
  }) async => DiscoveryFeedLoadResult(
    terminal: DiscoveryFeedLoadTerminal.stillBlocked,
    generation: 0,
  );
}

RuntimeFailure _feedFailure({
  required String code,
  required RuntimeFailureKind kind,
  required String reason,
}) {
  return RuntimeFailure(
    code: code,
    semanticReason: reason,
    origin: RuntimeFailureOrigin.localClient,
    kind: kind,
    nature: RuntimeFailureNature.transient,
    location: const RuntimeFailureLocation(
      businessObject: 'content.discovery_feed',
      functionModule: 'discovery_feed_provider',
    ),
    context: const RuntimeFailureContext(),
  );
}

class _LoadingFeedMapNotifier extends DiscoveryFeedMapNotifier {
  @override
  Map<String, AsyncValue<DiscoveryFeedState>> build() {
    return <String, AsyncValue<DiscoveryFeedState>>{
      'recommend': const AsyncLoading<DiscoveryFeedState>(),
    };
  }

  @override
  Future<DiscoveryFeedLoadResult> load(
    String channelId, {
    bool force = false,
  }) async => DiscoveryFeedLoadResult(
    terminal: DiscoveryFeedLoadTerminal.cancelled,
    generation: 0,
  );
}

class _SlowLoadingFeedMapNotifier extends DiscoveryFeedMapNotifier {
  @override
  Map<String, AsyncValue<DiscoveryFeedState>> build() {
    return <String, AsyncValue<DiscoveryFeedState>>{
      'recommend': const AsyncData(
        DiscoveryFeedState(isLoading: true, isSlow: true),
      ),
    };
  }

  @override
  Future<DiscoveryFeedLoadResult> load(
    String channelId, {
    bool force = false,
  }) async => DiscoveryFeedLoadResult(
    terminal: DiscoveryFeedLoadTerminal.cancelled,
    generation: 0,
  );
}

class _PreviousPageRecoveryFeedMapNotifier extends DiscoveryFeedMapNotifier {
  _PreviousPageRecoveryFeedMapNotifier(this.posts);

  final List<ContentPostViewData> posts;
  int prependCalls = 0;

  @override
  Map<String, AsyncValue<DiscoveryFeedState>> build() {
    return <String, AsyncValue<DiscoveryFeedState>>{
      'recommend': AsyncData(
        DiscoveryFeedState(
          items: posts,
          canRestorePreviousPage: true,
          residentPageCount: 4,
          retainedPageCount: 6,
        ),
      ),
    };
  }

  @override
  Future<DiscoveryFeedLoadResult> load(
    String channelId, {
    bool force = false,
  }) async => DiscoveryFeedLoadResult(
    terminal: DiscoveryFeedLoadTerminal.content,
    generation: 0,
  );

  @override
  Future<bool> prependPreviousPage(String channelId) async {
    prependCalls += 1;
    return true;
  }
}

class _EightPageScrollFeedMapNotifier extends DiscoveryFeedMapNotifier {
  int loadedPageCount = 1;
  int appendCalls = 0;
  final List<String> _seenItemIds = <String>[];

  DiscoveryFeedState get currentFeed => state['recommend']!.value!;

  List<ContentPostViewData> _page(int pageIndex) =>
      List<ContentPostViewData>.generate(
        20,
        (index) => _microPost(
          id: 'widget_page_${pageIndex}_post_$index',
          imageUrls: const <String>[],
        ),
        growable: false,
      );

  @override
  Map<String, AsyncValue<DiscoveryFeedState>> build() {
    final firstPage = _page(0);
    _seenItemIds.addAll(firstPage.map((post) => post.id));
    return <String, AsyncValue<DiscoveryFeedState>>{
      'recommend': AsyncData(
        DiscoveryFeedState(
          items: firstPage,
          seenItemIds: List<String>.unmodifiable(_seenItemIds),
          nextCursor: 'widget_cursor_1',
          residentPageCount: 1,
          retainedPageCount: 1,
        ),
      ),
    };
  }

  @override
  Future<DiscoveryFeedLoadResult> load(
    String channelId, {
    bool force = false,
  }) async => DiscoveryFeedLoadResult(
    terminal: DiscoveryFeedLoadTerminal.content,
    generation: 0,
  );

  @override
  Future<void> appendNextPage(String channelId) async {
    if (loadedPageCount >= 8) return;
    final current = state[channelId]?.value;
    if (current == null || current.isAppending) return;
    appendCalls += 1;
    state = <String, AsyncValue<DiscoveryFeedState>>{
      ...state,
      channelId: AsyncData(current.copyWith(isAppending: true)),
    };
    await Future<void>.delayed(Duration.zero);

    final nextPage = _page(loadedPageCount);
    _seenItemIds.addAll(nextPage.map((post) => post.id));
    loadedPageCount += 1;
    final combined = <ContentPostViewData>[...current.items, ...nextPage];
    final visible = combined.length <= 80
        ? combined
        : combined.sublist(combined.length - 80);
    state = <String, AsyncValue<DiscoveryFeedState>>{
      ...state,
      channelId: AsyncData(
        current.copyWith(
          items: List<ContentPostViewData>.unmodifiable(visible),
          seenItemIds: List<String>.unmodifiable(_seenItemIds),
          nextCursor: loadedPageCount < 8
              ? 'widget_cursor_$loadedPageCount'
              : null,
          canRestorePreviousPage: loadedPageCount > 4,
          residentPageCount: loadedPageCount > 4 ? 4 : loadedPageCount,
          retainedPageCount: loadedPageCount > 6 ? 6 : loadedPageCount,
          isAppending: false,
        ),
      ),
    };
  }
}

Widget _buildFeedScope({
  required DiscoveryFeedMapNotifier Function() notifier,
  bool disableAnimations = false,
  String channelId = 'recommend',
  String? scopeId,
  List<Override> extraOverrides = const <Override>[],
}) {
  return ProviderScope(
    key: ValueKey<String>('feed-scope-${scopeId ?? channelId}'),
    overrides: _boundaryOverrides(
      extra: <Override>[
        ...mockContentFacetOverrides(store: InMemoryContentPostStore()),
        mediaEndpointConfigProvider.overrideWithValue(_testMediaEndpointConfig),
        discoveryFeedMapProvider.overrideWith(notifier),
        ...extraOverrides,
      ],
    ),
    child: CupertinoApp(
      home: ScreenUtilInit(
        designSize: const Size(390, 844),
        child: MediaQuery(
          data: MediaQueryData(
            size: const Size(390, 844),
            disableAnimations: disableAnimations,
          ),
          child: HomeMultiFormFeed(
            isDark: false,
            channelId: channelId,
            template: 'single_column_multiform',
            onUserTap: (_, {avatarUrl, backgroundUrl, displayName}) {},
          ),
        ),
      ),
    ),
  );
}
