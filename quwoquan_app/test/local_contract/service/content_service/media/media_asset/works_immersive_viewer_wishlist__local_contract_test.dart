// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#req-008
// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#req-009

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/auth/auth_continuation.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/di/runtime_observability_dependencies.dart'
    show runtimeLoggerProvider;
import 'package:quwoquan_app/runtime/observability/runtime_log_ports.dart';
import 'package:quwoquan_app/runtime/observability/runtime_log_record.dart';
import 'package:quwoquan_app/runtime/observability/runtime_logger.dart';
import 'package:quwoquan_app/runtime/transport/cloud_api_query_defaults.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/content_behavior_tracker.dart';
import 'package:quwoquan_app/service/content_service/content/intersection_visit_state/adapters/intersection_repository.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/content_repository_contract.dart'
    show ContentEntityWishlistStateReader;
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/public/media_viewer_extra.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/video_preview_track_query.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/immersive_engagement_bar.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/works_immersive_viewer.dart';
import 'package:quwoquan_app/runtime/di/video_preview_track_dependencies.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart'
    show ActivePersonaContextViewData;
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../../../support/service/content_service/content/content_behavior_fact/recording_content_behavior_repository.dart';
import '../../../../../support/service/content_service/content/post/content_facet_overrides.dart';
import '../../../../../support/service/content_service/content/post/content_post_typed_doubles.dart';
import '../../../../../support/service/recommendation_service/recommendation/recommendation_feature_profile_view/intersection_fixtures.dart';

// 详情态想去按钮契约（Aha 1 最小版）：
// - 锚点真相源：作品 wire 的 primaryHomepageId + primaryHomepageType，
//   类型门复用 codegen wishlistHomepageTypes；锚点缺失或类型不符不渲染按钮。
// - 点击成功后的即时反馈诚实两态：有对象交集点名共同人数并给查看入口，
//   无交集只确认动作本身，不伪造社交证明。
// - 未登录点击必须走 WishlistHomepageContinuation 双目标续接，不静默丢失。

ContentPostViewData _photoPost({String id = 'photo-wish-1'}) {
  return ContentPostViewData.fromWire(
    ContentPostProjection(
      postId: id,
      contentType: 'image',
      contentIdentity: 'work',
      assistantUsePolicy: AssistantUsePolicy.inherit,
      authorId: 'author-1',
      authorDisplayName: '摄影师',
      authorAvatarUrl: 'https://example.com/avatar.jpg',
      authorRoleLabel: '',
      authorIdentityTags: const <String>[],
      authorVerified: false,
      body: '雪山写真',
      coverUrl: 'media/image/s/fixture/photo.jpg',
      mediaUrls: const <String>['media/image/s/fixture/photo.jpg'],
      likeCount: 0,
      commentCount: 0,
      shareCount: 0,
      createdAt: DateTime.now(),
    ),
  );
}

Map<String, dynamic> _photoRaw(
  ContentPostViewData post, {
  String? homepageId,
  String homepageType = 'sight',
}) {
  return <String, dynamic>{
    'postId': post.id,
    'contentType': 'image',
    'authorId': post.authorId,
    'authorDisplayName': post.displayName,
    'authorAvatarUrl': post.avatarUrl,
    'body': post.body,
    if (homepageId != null) 'primaryHomepageId': homepageId,
    if (homepageId != null) 'primaryHomepageType': homepageType,
    if (homepageId != null)
      'primaryHomepageSnapshot': <String, Object?>{'title': '黄龙雪山'},
  };
}

final class _WishlistStateReaderDouble
    implements ContentEntityWishlistStateReader {
  _WishlistStateReaderDouble({this.wishlisted = false});

  bool wishlisted;
  int calls = 0;

  @override
  Future<EntityWishlistState> getEntityWishlistState({
    required String objectId,
    required String objectKind,
  }) async {
    calls += 1;
    return EntityWishlistState(
      objectId: objectId,
      objectKind: objectKind,
      wishlisted: wishlisted,
    );
  }
}

final class _ObjectIntersectionRepositoryDouble
    implements IntersectionRepository {
  _ObjectIntersectionRepositoryDouble({
    this.reasons = const <IntersectionReason>[],
  });

  final List<IntersectionReason> reasons;

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
  }) async {
    return reasons;
  }
}

final class _UnusedVideoPreviewTrackQuery implements VideoPreviewTrackQuery {
  const _UnusedVideoPreviewTrackQuery();

  @override
  Future<VideoPreviewTrackManifest> loadManifest(
    VideoPreviewTrackDescriptor descriptor,
  ) {
    throw StateError('该 Widget contract 不应请求视频预览轨');
  }
}

final class _AuthenticatedSession extends AuthSessionController {
  @override
  AuthSessionState build() {
    return const AuthSessionState(
      status: AuthSessionStatus.authenticated,
      accessToken: 'access-token',
      refreshToken: 'refresh-token',
      ownerId: 'owner-1',
      activePersonaId: 'persona-1',
      accountState: 'active',
      identityOrigin: 'phone',
      installId: 'install-1',
    );
  }
}

IntersectionReason _coWishlistedReason({int mutualCount = 3}) {
  return intersectionReasonFixture(
    kind: 'coWishlistedEntity',
    vertical: 'general',
    dimension: 'place',
    relationKind: 'coWishlistedEntity',
    relationObjectId: 'homepage-wish-1',
    strength: 1,
    primaryText: '3 位联系人也想去',
    mutualCount: mutualCount,
    source: 'coWishlistedEntity',
    intersectionClass: 'fact',
  );
}

Widget _wrap(
  Widget child, {
  required List<Override> overrides,
  bool authenticated = true,
}) {
  final router = GoRouter(
    routes: <RouteBase>[
      GoRoute(path: '/', builder: (context, state) => Scaffold(body: child)),
      GoRoute(
        path: '/homepage/:id',
        builder: (context, state) => const SizedBox.shrink(),
      ),
      GoRoute(
        path: '/login',
        builder: (context, state) => const SizedBox.shrink(),
      ),
    ],
  );
  return ProviderScope(
    overrides: <Override>[
      ...sealedCloudBoundaryOverrides(),
      ...mockContentFacetOverrides(store: InMemoryContentPostStore()),
      activePersonaContextProvider.overrideWith(
        (_) async => ActivePersonaContextViewData.fallback(
          personaId: 'persona-1',
          ownerUserId: 'owner-1',
          displayName: '测试用户',
          avatarUrl: '',
        ),
      ),
      if (authenticated)
        authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
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
      ...overrides,
    ],
    child: ScreenUtilInit(
      designSize: const Size(375, 812),
      builder: (context, _) =>
          MaterialApp.router(theme: ThemeData.dark(), routerConfig: router),
    ),
  );
}

Future<void> _pumpFrames(WidgetTester tester) async {
  for (var i = 0; i < 8; i += 1) {
    await tester.pump(const Duration(milliseconds: 60));
  }
}

WorksImmersiveViewer _viewer(
  ContentPostViewData post, {
  String? homepageId,
  String homepageType = 'sight',
}) {
  return WorksImmersiveViewer(
    showWorksToolbar: true,
    showTopNavigation: false,
    externalPosts: <ContentPostViewData>[post],
    rawPostsById: <String, MediaViewerPostWireRow>{
      post.id: MediaViewerPostWireRow.fromDynamicMap(
        _photoRaw(post, homepageId: homepageId, homepageType: homepageType),
      ),
    },
    onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
    onAssistantTap: () {},
  );
}

void main() {
  testWidgets('无 primaryHomepage 锚点时不渲染想去按钮', (tester) async {
    final post = _photoPost();
    await tester.pumpWidget(
      _wrap(_viewer(post), overrides: const <Override>[]),
    );
    await _pumpFrames(tester);

    expect(find.byKey(ImmersiveEngagementBar.wishlistActionKey), findsNothing);
  });

  testWidgets('类型门外的 homepage 类型不渲染想去按钮', (tester) async {
    final post = _photoPost();
    await tester.pumpWidget(
      _wrap(
        _viewer(post, homepageId: 'homepage-wish-1', homepageType: 'person'),
        overrides: const <Override>[],
      ),
    );
    await _pumpFrames(tester);

    expect(find.byKey(ImmersiveEngagementBar.wishlistActionKey), findsNothing);
  });

  testWidgets('有锚点时想去成功且无交集 → 诚实确认，不伪造社会证明', (tester) async {
    final behaviorRepo = RecordingContentBehaviorRepository();
    final tracker = ContentBehaviorTracker(
      reporter: behaviorRepo,
      maxBatchSize: 1,
      enablePeriodicFlush: false,
    );
    addTearDown(tracker.dispose);
    final wishlistReader = _WishlistStateReaderDouble();

    final post = _photoPost();
    await tester.pumpWidget(
      _wrap(
        _viewer(post, homepageId: 'homepage-wish-1'),
        overrides: <Override>[
          contentBehaviorTrackerProvider.overrideWithValue(tracker),
          workBrowserEntityWishlistStateReaderProvider.overrideWithValue(
            wishlistReader,
          ),
          intersectionRepositoryProvider.overrideWithValue(
            _ObjectIntersectionRepositoryDouble(),
          ),
        ],
      ),
    );
    await _pumpFrames(tester);

    final wishlistAction = find.byKey(
      ImmersiveEngagementBar.wishlistActionKey,
    );
    expect(wishlistAction, findsOneWidget);
    expect(find.text(ObjectHomepageText.homepageWishlistAction), findsWidgets);
    expect(wishlistReader.calls, 1);

    await tester.tap(wishlistAction);
    await _pumpFrames(tester);

    final wishlistEvents = behaviorRepo.recorded
        .where((event) => event.action == BehaviorEventType.wishlistAdd)
        .toList();
    expect(wishlistEvents, hasLength(1));
    expect(wishlistEvents.single.contentId, 'homepage-wish-1');
    expect(
      find.text(ObjectHomepageText.wishlistAddedFeedback),
      findsOneWidget,
    );
    expect(
      find.text(ObjectHomepageText.homepageWishlistedAction),
      findsWidgets,
    );
  });

  testWidgets('有锚点时想去成功且有交集 → 点名共同人数并给查看入口', (tester) async {
    final behaviorRepo = RecordingContentBehaviorRepository();
    final tracker = ContentBehaviorTracker(
      reporter: behaviorRepo,
      maxBatchSize: 1,
      enablePeriodicFlush: false,
    );
    addTearDown(tracker.dispose);

    final post = _photoPost();
    await tester.pumpWidget(
      _wrap(
        _viewer(post, homepageId: 'homepage-wish-1'),
        overrides: <Override>[
          contentBehaviorTrackerProvider.overrideWithValue(tracker),
          workBrowserEntityWishlistStateReaderProvider.overrideWithValue(
            _WishlistStateReaderDouble(),
          ),
          intersectionRepositoryProvider.overrideWithValue(
            _ObjectIntersectionRepositoryDouble(
              reasons: <IntersectionReason>[_coWishlistedReason()],
            ),
          ),
        ],
      ),
    );
    await _pumpFrames(tester);

    await tester.tap(find.byKey(ImmersiveEngagementBar.wishlistActionKey));
    await _pumpFrames(tester);

    expect(
      find.text(ObjectHomepageText.wishlistSharedFeedback(3)),
      findsOneWidget,
    );
    expect(
      find.text(ObjectHomepageText.wishlistSharedFeedbackViewAction),
      findsOneWidget,
    );
  });

  testWidgets('未登录点击想去 → 设置双目标续接，不静默丢失', (tester) async {
    final behaviorRepo = RecordingContentBehaviorRepository();
    final tracker = ContentBehaviorTracker(
      reporter: behaviorRepo,
      maxBatchSize: 1,
      enablePeriodicFlush: false,
    );
    addTearDown(tracker.dispose);

    final post = _photoPost();
    late final ProviderContainer container;
    await tester.pumpWidget(
      _wrap(
        Consumer(
          builder: (context, ref, _) {
            container = ProviderScope.containerOf(context);
            return _viewer(post, homepageId: 'homepage-wish-1');
          },
        ),
        authenticated: false,
        overrides: <Override>[
          contentBehaviorTrackerProvider.overrideWithValue(tracker),
          workBrowserEntityWishlistStateReaderProvider.overrideWithValue(
            _WishlistStateReaderDouble(),
          ),
          intersectionRepositoryProvider.overrideWithValue(
            _ObjectIntersectionRepositoryDouble(),
          ),
        ],
      ),
    );
    await _pumpFrames(tester);

    await tester.tap(find.byKey(ImmersiveEngagementBar.wishlistActionKey));
    await _pumpFrames(tester);

    final pending = container.read(authContinuationProvider);
    expect(pending, isA<WishlistHomepageContinuation>());
    expect(
      (pending! as WishlistHomepageContinuation).homepageId,
      'homepage-wish-1',
    );
    expect(
      behaviorRepo.recorded.where(
        (event) => event.action == BehaviorEventType.wishlistAdd,
      ),
      isEmpty,
    );
  });
}
