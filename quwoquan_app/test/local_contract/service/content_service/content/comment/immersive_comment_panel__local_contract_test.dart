// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-025
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/di/presentation/home_feed_cross_object_composition.dart';
import 'package:quwoquan_app/runtime/observability/analytics.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/service/content_service/content/comment/application/public/comment_remote_config.dart';
import 'package:quwoquan_app/service/content_service/content/comment/presentation/comment_detail_surface.dart';
import 'package:quwoquan_app/service/content_service/content/comment/presentation/comment_thread_view.dart';
import 'package:quwoquan_app/service/content_service/content/comment/presentation/comment_toolbar.dart';
import 'package:quwoquan_app/service/content_service/content/comment/presentation/immersive_comment_split_sheet.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/public/media_viewer_extra.dart';

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../../../support/service/content_service/content/comment/in_memory_content_comment_facet.dart';

void main() {
  for (final profileInteraction in [false, true]) {
    testWidgets('横向评论面板服从局部约束并透传操作：profile=$profileInteraction', (
      tester,
    ) async {
      const postId = 'landscape-panel-post';
      const hostKey = ValueKey('comment-panel-host');
      final scrollController = ScrollController();
      final panelSize = ValueNotifier(const Size(360, 280));
      addTearDown(scrollController.dispose);
      addTearDown(panelSize.dispose);
      final comments = InMemoryContentCommentFacet(
        items: [
          testCommentItem(
            id: 'panel-comment',
            postId: postId,
            content: '同一评论事实',
          ),
        ],
      );
      final commentContext = MediaViewerCommentContext(
        entrySource: profileInteraction
            ? MediaViewerCommentContext.entrySourceProfileInteraction
            : null,
      );
      var likeCalls = 0;
      var shareCalls = 0;
      var closeCalls = 0;
      void onLikeTap() => likeCalls++;
      void onShareTap() => shareCalls++;
      void onClose() => closeCalls++;

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            ...sealedCloudBoundaryOverrides(),
            workBrowserContentCommentFacetProvider.overrideWithValue(comments),
            analyticsProvider.overrideWithValue(AnalyticsService.forTesting()),
            commentRemoteConfigProvider.overrideWithValue(
              const CommentRemoteConfig(),
            ),
          ],
          child: CupertinoApp(
            theme: CupertinoThemeData(
              brightness: profileInteraction
                  ? Brightness.dark
                  : Brightness.light,
            ),
            locale: const Locale('zh'),
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            home: MediaQuery(
              // 全屏尺寸故意不同于右侧局部约束，防止复用竖屏 sheet 的固定屏高。
              data: const MediaQueryData(size: Size(430, 932)),
              child: Align(
                alignment: Alignment.topRight,
                child: ValueListenableBuilder<Size>(
                  valueListenable: panelSize,
                  builder: (context, size, _) => SizedBox(
                    key: hostKey,
                    width: size.width,
                    height: size.height,
                    child: HomeFeedCrossObjectComposition.immersiveCommentPanel(
                      postId: postId,
                      entryObservedCommentCount: 1,
                      commentContext: commentContext,
                      scrollController: scrollController,
                      likeCount: 8,
                      shareCount: 3,
                      isLiked: true,
                      onLikeTap: onLikeTap,
                      onShareTap: onShareTap,
                      onClose: onClose,
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final surfaceFinder = find.byType(CommentDetailSurface);
      final surface = tester.widget<CommentDetailSurface>(surfaceFinder);
      expect(surface.postId, postId);
      expect(surface.commentContext, same(commentContext));
      expect(surface.entryObservedCommentCount, 1);
      expect(surface.scrollController, same(scrollController));
      expect(surface.flexibleThread, isFalse);
      expect(surface.showDragHandle, isFalse);
      expect(surface.onHeaderVerticalDragUpdate, isNull);
      expect(surface.onLikeTap, same(onLikeTap));
      expect(surface.onShareTap, same(onShareTap));
      expect(surface.onClose, same(onClose));
      expect(
        surface.mode,
        profileInteraction
            ? CommentDetailSurfaceMode.profileInteraction
            : CommentDetailSurfaceMode.immersiveSplit,
      );
      expect(find.byType(ImmersiveCommentSplitSheet), findsNothing);
      expect(find.byType(CommentThreadView), findsOneWidget);
      expect(find.text('同一评论事实'), findsOneWidget);
      expect(comments.queryCalls, 1);
      expect(scrollController.hasClients, isTrue);
      expect(tester.getSize(surfaceFinder), panelSize.value);
      expect(
        tester.getRect(find.byType(CommentToolbar)).bottom,
        tester.getRect(find.byKey(hostKey)).bottom,
      );
      final background = tester.widget<ColoredBox>(
        find
            .descendant(
              of: find.byKey(hostKey),
              matching: find.byType(ColoredBox),
            )
            .first,
      );
      expect(
        background.color,
        AppColorsFunctional.getColor(
          profileInteraction,
          ColorType.backgroundPrimary,
        ),
      );
      final toolbar = tester.widget<CommentToolbar>(
        find.byType(CommentToolbar),
      );
      expect(toolbar.likeCount, 8);
      expect(toolbar.shareCount, 3);
      expect(toolbar.isLiked, isTrue);
      await tester.tap(find.byKey(TestKeys.likeButton));
      await tester.tap(find.byKey(TestKeys.shareButton));
      await tester.tap(find.byIcon(CupertinoIcons.xmark));
      expect((likeCalls, shareCalls, closeCalls), (1, 1, 1));

      final surfaceState = tester.state(surfaceFinder);
      panelSize.value = const Size(340, 260);
      await tester.pumpAndSettle();
      expect(tester.state(surfaceFinder), same(surfaceState));
      expect(tester.getSize(surfaceFinder), panelSize.value);
      expect(comments.queryCalls, 1);
      expect(tester.takeException(), isNull);

      await tester.pumpWidget(const SizedBox.shrink());
      expect(scrollController.hasClients, isFalse);
      // 卸载面板不释放宿主持有的 controller。
      scrollController.addListener(onClose);
      scrollController.removeListener(onClose);
    });
  }
}
