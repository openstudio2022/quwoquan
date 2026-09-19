// spec_ref: specs/feature-tree/spec.md#uat-002
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/text-post-commercial-publication/spec.md#gwt-001
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/text-post-commercial-publication/spec.md#gwt-005

/// user_acceptance Patrol：写文字发布单条无断点旅程。
///
/// 守护：底栏「+」→ 发布内容 → 写文字 → 文章编辑器 → 发布去向确认 →
/// 发布 → 结果页（真实去向摘要）→ Remote 回读 canonical Post → workBrowser
/// 可加载。与 draft 深链版文字 UAT 互补：本条覆盖真实入口段，证明旅程从
/// 全局创作入口到消费回读无断点。
library;

import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show ContentType;
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_editor.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/works_viewer_article.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart'
    show CreationText;
import 'package:quwoquan_app/runtime/di/app_providers_content_extras.dart'
    show workBrowserContentPostDetailReaderProvider;
import 'package:quwoquan_app/runtime/di/app_providers_content_facets.dart'
    show contentPostDeleteCommandWriterProvider;
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_delete.dart'
    show contentPostDeleteIdempotencyKey;
import 'package:quwoquan_app/service/content_service/content/post/application/create_draft_store_provider.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/post_publication_intent_queue_provider.dart';

import '../../../../../support/runtime/patrol/home_create_entry.dart';
import '../../../../../support/runtime/patrol/patrol_test_support.dart';

void main() {
  patrolTest(
    'text publication entry journey — 底栏加号→文章编辑→去向确认→发布→回读无断点',
    tags: const <String>[
      'user-acceptance',
      'content',
      'text-publication',
      'entry-journey',
    ],
    skip: !kRunPatrolAcceptance,
    config: PatrolTesterConfig(
      visibleTimeout: const Duration(seconds: 15),
      printLogs: true,
    ),
    ($) async {
      await launchPatrolAppOnce($);

      final navigator = find.byType(Navigator).evaluate().first;
      final container = ProviderScope.containerOf(navigator);
      await container.read(createDraftStoreProvider.future);
      container.read(postPublicationIntentQueueProvider);

      final nonce = DateTime.now().microsecondsSinceEpoch;
      final marker = 'entry journey article publication $nonce';
      String? postId;
      String? acceptedState;
      ContentType? submittedType;
      // 入口旅程不预置 draftId，用正文 marker 归属本次发布意图。
      final subscription = container.listen<PostPublicationIntentQueueState>(
        postPublicationIntentQueueProvider,
        (_, next) {
          for (final intent in next.intents) {
            if (!(intent.command.articleMarkdown?.contains(marker) ?? false)) {
              continue;
            }
            submittedType = intent.command.contentType;
            final observedPostId = intent.postId?.trim() ?? '';
            if (observedPostId.isNotEmpty) {
              postId = observedPostId;
            }
            final state = intent.publicationState?.wireValue;
            if (state == 'pending_review' || state == 'published') {
              acceptedState = state;
            }
          }
        },
        fireImmediately: true,
      );

      try {
        // 入口段：底栏「+」→ 发布内容 → 写文字 → 统一编辑器。
        await openCreateActionSheet($);
        expect($(TestKeys.createActionPublishContent).visible, isTrue);
        await $(TestKeys.createActionPublishContent).tap();
        await $(TestKeys.createActionWrite).tap();
        await $(TestKeys.createPage)
            .waitUntilVisible(timeout: const Duration(seconds: 15));

        expect(find.byType(ArticleEditor), findsOneWidget);
        await $(TestKeys.createMomentInput).enterText(marker);
        expect(
          $.tester
              .widget<ArticleEditor>(find.byType(ArticleEditor))
              .state
              .articleDocument
              .body,
          marker,
          reason: '短纯文字必须由文章文档承载，不能进入另一种内容身份。',
        );
        await $(TestKeys.createPublishButton).tap();
        await $(TestKeys.createPublishConfirmSheet)
            .waitUntilVisible(timeout: const Duration(seconds: 15));

        // GWT-001：类型由文章编辑流程确定，确认面只设置公开范围和去向。
        final confirmSheet = find.byKey(TestKeys.createPublishConfirmSheet);
        for (final label in <String>[
          CreationText.whoCanSeeLabel,
          CreationText.visibilityPublic,
          CreationText.attachHomepageTitle,
          CreationText.selectPublishCirclesLabel,
        ]) {
          expect(
            find.descendant(of: confirmSheet, matching: find.text(label)),
            findsOneWidget,
            reason: '文章确认页必须保留真实发布设置：$label。',
          );
        }
        await $(TestKeys.createPublishConfirmButton).tap();

        // 结果页：真实分发去向摘要（公开发布）。
        await $(TestKeys.createPublishResultSheet)
            .waitUntilVisible(timeout: const Duration(seconds: 90));
        expect(
          find.byKey(TestKeys.createPublishResultDestinationSummary),
          findsOneWidget,
          reason: '发布结果页必须展示真实去向摘要。',
        );
        expect(
          find.textContaining(CreationText.publishDestinationPublic),
          findsWidgets,
          reason: '公开发布的去向摘要必须如实标注公开。',
        );

        expect(
          await _waitFor(
            $,
            () => postId != null && acceptedState != null,
            timeout: const Duration(minutes: 2),
          ),
          isTrue,
          reason: '入口旅程发布必须推进到受理状态并保留 canonical postId。',
        );
        await $(TestKeys.createPublishResultDoneButton).tap();

        // 消费回读：canonical 内容 + workBrowser 可加载。
        final detail = await container
            .read(workBrowserContentPostDetailReaderProvider)
            .getPost(postId: postId!);
        expect(submittedType, ContentType.article);
        expect(detail.post.id, postId);
        expect(detail.post.type, ContentType.article);
        expect(
          detail.post.normalizedBody,
          contains(marker),
          reason: 'Remote 回读必须保留入口旅程发布的 canonical 内容。',
        );

        await patrolGoTo($, AppRoutePaths.workBrowser(workId: postId!));
        expect(
          await _waitFor(
            $,
            () => find
                .byWidgetPredicate(
                  (widget) =>
                      widget is PostWorksViewerArticle &&
                      widget.post.id == postId &&
                      widget.post.type == ContentType.article &&
                      widget.article.document.body.contains(marker),
                )
                .evaluate()
                .isNotEmpty,
            timeout: const Duration(seconds: 30),
          ),
          isTrue,
          reason: '入口旅程必须以同一 Post 的文章阅读面展示刚发布的正文。',
        );
        expect(
          find.byKey(const ValueKey<String>('work-browser-entry-error')),
          findsNothing,
        );
      } finally {
        subscription.close();
        if (postId != null) {
          await container
              .read(contentPostDeleteCommandWriterProvider)
              .deletePost(
                postId: postId!,
                idempotencyKey: contentPostDeleteIdempotencyKey(postId!),
              );
        }
      }
    },
  );
}

Future<bool> _waitFor(
  PatrolIntegrationTester $,
  bool Function() predicate, {
  required Duration timeout,
}) async {
  final deadline = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    if (predicate()) {
      return true;
    }
    await $.pump(const Duration(milliseconds: 500));
  }
  return predicate();
}
