// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#req-009

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/l10n/copy/gathering_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/di/app_providers_content_extras.dart'
    show workBrowserSocialProofReaderProvider;
import 'package:quwoquan_app/runtime/di/runtime_observability_dependencies.dart'
    show runtimeLoggerProvider;
import 'package:quwoquan_app/runtime/observability/runtime_log_ports.dart';
import 'package:quwoquan_app/runtime/observability/runtime_log_record.dart';
import 'package:quwoquan_app/runtime/observability/runtime_logger.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/content_repository_contract.dart'
    show ContentGatheringSocialProofReader;
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/public/media_viewer_extra.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/video_preview_track_query.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/works_immersive_viewer.dart';
import 'package:quwoquan_app/runtime/di/video_preview_track_dependencies.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart'
    show ActivePersonaContextViewData;
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../../../support/service/content_service/content/post/content_facet_overrides.dart';
import '../../../../../support/service/content_service/content/post/content_post_typed_doubles.dart';

// 经历溯源轻标契约（L0 氛围层，与交集陈述互斥）：
// - 回顾内容（wire gatheringRef）→「来自一次共同行动」；
// - 种草内容（content 锚点社会证明成形级 > 0）→「他们从这条内容出发，一起去了」；
// - 两者都不成立或读取失败 → 不渲染，不伪造。

ContentPostViewData _photoPost({String id = 'photo-prov-1'}) {
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

final class _SocialProofReaderDouble
    implements ContentGatheringSocialProofReader {
  _SocialProofReaderDouble({this.formedCount = 0});

  final int formedCount;

  @override
  Future<GatheringSocialProofSummary> getGatheringSocialProof({
    required String anchorKind,
    required String objectId,
  }) async {
    return GatheringSocialProofSummary(
      anchorKind: anchorKind,
      objectId: objectId,
      publishedCount: formedCount,
      formedCount: formedCount,
      experiencedCount: 0,
    );
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

Widget _wrap(Widget child, {required List<Override> overrides}) {
  final router = GoRouter(
    routes: <RouteBase>[
      GoRoute(path: '/', builder: (context, state) => Scaffold(body: child)),
      GoRoute(
        path: '/gatherings/:id',
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
  String gatheringRef = '',
}) {
  return WorksImmersiveViewer(
    showWorksToolbar: true,
    showTopNavigation: false,
    externalPosts: <ContentPostViewData>[post],
    rawPostsById: <String, MediaViewerPostWireRow>{
      post.id: MediaViewerPostWireRow.fromDynamicMap(<String, dynamic>{
        'postId': post.id,
        'contentType': 'image',
        'authorId': post.authorId,
        'authorDisplayName': post.displayName,
        'authorAvatarUrl': post.avatarUrl,
        'body': post.body,
        if (gatheringRef.isNotEmpty) 'gatheringRef': gatheringRef,
      }),
    },
    onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
    onAssistantTap: () {},
  );
}

const _badgeKey = ValueKey<String>('works-provenance-badge');

void main() {
  testWidgets('回顾内容按 gatheringRef 渲染「来自一次共同行动」轻标', (tester) async {
    final post = _photoPost();
    await tester.pumpWidget(
      _wrap(
        _viewer(post, gatheringRef: 'gathering-prov-1'),
        overrides: <Override>[
          workBrowserSocialProofReaderProvider.overrideWithValue(
            _SocialProofReaderDouble(),
          ),
        ],
      ),
    );
    await _pumpFrames(tester);

    expect(find.byKey(_badgeKey), findsOneWidget);
    expect(find.text(GatheringText.provenanceRecapBadge), findsOneWidget);
  });

  testWidgets('种草内容成形级 >0 渲染「他们从这条内容出发一起去了」', (tester) async {
    final post = _photoPost(id: 'photo-prov-seed');
    await tester.pumpWidget(
      _wrap(
        _viewer(post),
        overrides: <Override>[
          workBrowserSocialProofReaderProvider.overrideWithValue(
            _SocialProofReaderDouble(formedCount: 2),
          ),
        ],
      ),
    );
    await _pumpFrames(tester);

    expect(find.byKey(_badgeKey), findsOneWidget);
    expect(find.text(GatheringText.provenanceSeedBadge), findsOneWidget);
  });

  testWidgets('无关联且无成形行动时不渲染，不伪造', (tester) async {
    final post = _photoPost(id: 'photo-prov-none');
    await tester.pumpWidget(
      _wrap(
        _viewer(post),
        overrides: <Override>[
          workBrowserSocialProofReaderProvider.overrideWithValue(
            _SocialProofReaderDouble(formedCount: 0),
          ),
        ],
      ),
    );
    await _pumpFrames(tester);

    expect(find.byKey(_badgeKey), findsNothing);
    expect(find.text(GatheringText.provenanceSeedBadge), findsNothing);
  });
}
