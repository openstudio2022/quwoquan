// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-013

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/content/generated/content_errors.g.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_detail_payload.dart';
import 'package:quwoquan_app/content/content/post/application/content_repository_contract.dart'
    show ContentPostDetailReader, contentPostDeleteIdempotencyKey;
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/core/media/media_delivery_reference.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/content/content/post/presentation/work_browser_entry_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../support/cloud_services/content_facet_overrides.dart';
import '../../../../support/content/content/post/mock_content_repository.dart';

void main() {
  final mediaEndpoints = MediaEndpointConfig(
    avatarBaseUrl: 'https://example.com/media/avatar',
    imageBaseUrl: 'https://example.com/media/image',
    videoBaseUrl: 'https://example.com/media/video',
    attachmentBaseUrl: 'https://example.com',
  );

  Future<String> firstReadablePostId(MockContentRepository repo) async {
    for (final category in <String>['article', 'photo', 'video', 'moment']) {
      final posts = await repo.listDiscoveryFeed(category: category, limit: 8);
      for (final post in posts) {
        try {
          await repo.getPost(postId: post.id);
          return post.id;
        } catch (_) {
          // skip unreadable seed rows
        }
      }
    }
    fail('seed feed 中应至少有一个 getPost 可读的帖');
  }

  testWidgets('直达入口：workId 在详情不可读时呈现显式错误态而非无关内容', (tester) async {
    final repo = MockContentRepository();

    await tester.pumpWidget(
      ProviderScope(
        overrides: [...mockContentFacetOverrides(repo)],
        child: ScreenUtilInit(
          designSize: const Size(375, 812),
          builder: (context, _) => MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            home: const WorkBrowserEntryPage(
              workId: 'definitely-missing-post-id',
              source: 'deep-link-test',
            ),
          ),
        ),
      ),
    );

    // 初始为加载态。
    expect(
      find.byKey(const ValueKey('work-browser-entry-loading')),
      findsOneWidget,
    );

    await tester.pumpAndSettle();

    // 详情拉取失败 → 显式错误态，绝不回退渲染发现页推荐流（先前断点）。
    expect(
      find.byKey(const ValueKey('work-browser-entry-error')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('work-browser-entry-loading')),
      findsNothing,
    );
  });

  testWidgets('直达入口：软删除内容按 410 墓碑展示删除态', (tester) async {
    final repo = MockContentRepository();
    final postId = await firstReadablePostId(repo);
    await repo.deletePost(
      postId: postId,
      idempotencyKey: contentPostDeleteIdempotencyKey(postId),
    );

    await tester.pumpWidget(
      ProviderScope(
        overrides: [...mockContentFacetOverrides(repo)],
        child: ScreenUtilInit(
          designSize: const Size(375, 812),
          builder: (context, _) => MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            home: WorkBrowserEntryPage(
              workId: postId,
              source: 'deleted-content-test',
            ),
          ),
        ),
      ),
    );

    expect(
      find.byKey(const ValueKey('work-browser-entry-loading')),
      findsOneWidget,
    );
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey('work-browser-entry-error')),
      findsOneWidget,
    );
    expect(find.text(SearchText.recoveryContentGoneTitle), findsOneWidget);
    expect(
      find.byKey(const ValueKey<String>('work-browser-entry-error-back')),
      findsOneWidget,
    );
  });

  testWidgets('直达入口：空 workId 直接进入错误态', (tester) async {
    final repo = MockContentRepository();

    await tester.pumpWidget(
      ProviderScope(
        overrides: [...mockContentFacetOverrides(repo)],
        child: ScreenUtilInit(
          designSize: const Size(375, 812),
          builder: (context, _) => MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            home: const WorkBrowserEntryPage(workId: '   '),
          ),
        ),
      ),
    );

    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey('work-browser-entry-error')),
      findsOneWidget,
    );
  });

  testWidgets('直达入口：环境 smoke 使用可读视频 seed 时渲染视频 stage', (tester) async {
    final repo = MockContentRepository();
    const videoWorkId = 'video_tokyo_midnight';

    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          ...mockContentFacetOverrides(repo),
          mediaEndpointConfigProvider.overrideWithValue(mediaEndpoints),
        ],
        child: ScreenUtilInit(
          designSize: const Size(375, 812),
          builder: (context, _) => MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            home: const WorkBrowserEntryPage(
              workId: videoWorkId,
              source: 'environmentSmoke',
            ),
          ),
        ),
      ),
    );

    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    await tester.pump(const Duration(seconds: 1));

    expect(
      find.byKey(const ValueKey('works-video-stage-$videoWorkId-0')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('work-browser-entry-error')),
      findsNothing,
    );
  });

  testWidgets('直达入口：浅色来源的失效内容错误页不继承深色沉浸上下文', (tester) async {
    final repo = MockContentRepository();

    await tester.pumpWidget(
      ProviderScope(
        overrides: [...mockContentFacetOverrides(repo)],
        child: const CupertinoApp(
          theme: CupertinoThemeData(brightness: Brightness.dark),
          home: WorkBrowserEntryPage(
            workId: 'definitely-missing-post-id',
            source: 'home_feed',
            sourceAppearanceMode: UiErrorAppearanceMode.light,
          ),
        ),
      ),
    );

    await tester.pumpAndSettle();

    final scaffold = tester.widget<CupertinoPageScaffold>(
      find.byType(CupertinoPageScaffold).first,
    );
    expect(scaffold.backgroundColor!.computeLuminance(), greaterThan(0.8));
    expect(
      find.byKey(const ValueKey('work-browser-entry-error')),
      findsOneWidget,
    );
  });

  testWidgets(
    '直达入口：transient RuntimeFailure 经 Retry 后由 typed Remote reader 恢复',
    (tester) async {
      final repo = MockContentRepository();
      final postId = await firstReadablePostId(repo);
      final reader = _FlakyContentPostDetailReader(delegate: repo);

      await tester.pumpWidget(
        ProviderScope(
          overrides: <Override>[
            ...mockContentFacetOverrides(repo, workBrowserDetailReader: reader),
            contentRuntimeConfigProvider.overrideWithValue(
              buildAlphaContentRuntimeConfigDefaults(),
            ),
          ],
          child: ScreenUtilInit(
            designSize: const Size(375, 812),
            builder: (context, _) => MaterialApp(
              localizationsDelegates: AppLocalizations.localizationsDelegates,
              supportedLocales: AppLocalizations.supportedLocales,
              home: WorkBrowserEntryPage(
                workId: postId,
                source: 'typed-remote-recovery-test',
              ),
            ),
          ),
        ),
      );

      await tester.pumpAndSettle();

      final errorState = tester.widget<AppPageErrorState>(
        find.byKey(const ValueKey('work-browser-entry-error')),
      );
      expect(
        errorState.semantic.sourceCode,
        ContentErrorCode.requiredDependencyUnavailable.code,
      );
      expect(errorState.semantic.primaryAction?.type, UiErrorActionType.retry);
      expect(reader.calls, 1);

      final outcome = await errorState.onRecovery!(
        const UiErrorAction(type: UiErrorActionType.retry, label: '重试'),
      );
      expect(outcome, UiRecoveryOutcome.recovered);
      await tester.pumpAndSettle();

      expect(reader.calls, greaterThanOrEqualTo(2));
      expect(
        find.byKey(const ValueKey('work-browser-entry-error')),
        findsNothing,
      );
    },
  );

  testWidgets('直达入口：评论原文跳转会消费 openComments 上下文', (tester) async {
    final repo = MockContentRepository();
    final postId = await firstReadablePostId(repo);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [...mockContentFacetOverrides(repo)],
        child: ScreenUtilInit(
          designSize: const Size(375, 812),
          builder: (context, _) => MaterialApp(
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            home: WorkBrowserEntryPage(
              workId: postId,
              source: 'profile-comments',
              commentContext: const MediaViewerCommentContext(
                openComments: true,
              ),
            ),
          ),
        ),
      ),
    );

    await tester.pump();
    await tester.pumpAndSettle();

    expect(find.byKey(TestKeys.immersiveCommentSplitSheet), findsOneWidget);
    expect(
      find.byKey(const ValueKey('work-browser-entry-error')),
      findsNothing,
    );
  });

  testWidgets('直达入口：失效内容会展示可理解提示并可安全返回首页', (tester) async {
    final repo = MockContentRepository();
    final router = GoRouter(
      initialLocation: AppRoutePaths.workBrowser(
        workId: 'definitely-missing-post-id',
        source: 'deep-link-test',
      ),
      routes: <RouteBase>[
        GoRoute(
          path: AppRoutePaths.home,
          builder: (_, _) => const Scaffold(body: Center(child: Text('HOME'))),
        ),
        GoRoute(
          path: AppRoutePaths.workBrowserPathTemplate.replaceAll(
            '{workId}',
            ':workId',
          ),
          builder: (context, state) => WorkBrowserEntryPage(
            workId: state.pathParameters['workId'] ?? '',
            source: state.uri.queryParameters['source'] ?? 'workBrowser',
          ),
        ),
      ],
    );

    await tester.pumpWidget(
      ProviderScope(
        overrides: [...mockContentFacetOverrides(repo)],
        child: ScreenUtilInit(
          designSize: const Size(375, 812),
          builder: (context, _) => MaterialApp.router(
            routerConfig: router,
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
          ),
        ),
      ),
    );

    await tester.pumpAndSettle();

    expect(
      find.text(SearchText.recoveryContentUnavailableTitle),
      findsOneWidget,
    );
    expect(
      find.text(SearchText.recoveryContentUnavailableMessage),
      findsOneWidget,
    );
    expect(find.text(SearchText.recoveryReturnAction), findsOneWidget);
    expect(
      find.byKey(const ValueKey<String>('work-browser-entry-error-back')),
      findsOneWidget,
    );

    await tester.tap(
      find.byKey(const ValueKey<String>('work-browser-entry-error-back')),
    );
    await tester.pumpAndSettle();

    expect(find.text('HOME'), findsOneWidget);
  });
}

final class _FlakyContentPostDetailReader implements ContentPostDetailReader {
  _FlakyContentPostDetailReader({required this.delegate});

  final ContentPostDetailReader delegate;
  int calls = 0;

  @override
  Future<ContentPostDetailPayload> getPost({
    required String postId,
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    calls += 1;
    if (calls == 1) {
      throw CloudErrorMapper.fromStatusCode(
        503,
        body:
            '{"code":"${ContentErrorCode.requiredDependencyUnavailable.code}","userMessage":"服务暂不可用"}',
        requestPath: ContentApiMetadata.getPostPath(postId: postId),
      );
    }
    return delegate.getPost(
      postId: postId,
      cancellation: cancellation,
      deadlineAt: deadlineAt,
    );
  }
}
