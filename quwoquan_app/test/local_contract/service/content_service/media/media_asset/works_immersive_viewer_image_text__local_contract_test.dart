// spec_ref: specs/feature-tree/discovery-content/content-type-framework/unified-presentation-model/spec.md#gwt-001
// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-018

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/di/runtime_observability_dependencies.dart';
import 'package:quwoquan_app/runtime/observability/runtime_log_ports.dart';
import 'package:quwoquan_app/runtime/observability/runtime_log_record.dart';
import 'package:quwoquan_app/runtime/observability/runtime_logger.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/public/media_viewer_extra.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/image_book_canvas.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/media_caption_widgets.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/works_immersive_viewer.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';

import 'package:quwoquan_app/service/content_service/content/post/application/content_repository_contract.dart';

import '../../../../../support/service/content_service/content/post/test_content_app_config.dart';

final class _ImageTextConfig implements ContentConfigRepository {
  @override
  Future<AppConfigSlice> getAppConfig() async => testAppConfigSlice();

  @override
  bool get requiresResolvedPersonaForMutations => false;
}

final class _ImageTextSocialProof implements ContentGatheringSocialProofReader {
  @override
  Future<GatheringSocialProofSummary> getGatheringSocialProof({
    required String anchorKind,
    required String objectId,
  }) async => GatheringSocialProofSummary(
    anchorKind: anchorKind,
    objectId: objectId,
    publishedCount: 0,
    formedCount: 0,
    experiencedCount: 0,
  );
}

final class _ImageTextBehavior implements ContentBehaviorFactAppender {
  @override
  Future<void> reportBehaviors(ReportContentBehaviorsCommand command) async {}
}

const _body = '整帖记录：同一天的山川与湖泊';
const _firstCaption = '第一张：清晨山峰';
const _secondCaption = '第二张：午后湖面';

Future<void> _pumpViewer(
  WidgetTester tester, {
  String body = '',
  String title = '',
  List<String?> captions = const [null],
  int initialImageIndex = 0,
}) async {
  final urls = [
    for (var i = 0; i < captions.length; i++)
      'media/image/s/fixture/image-$i.jpg',
  ];
  final post = ContentPostViewData.fromWire(
    ContentPostProjection(
      postId: 'image-text-post',
      contentType: ContentType.image,
      assistantUsePolicy: AssistantUsePolicy.inherit,
      authorId: 'image-author',
      authorDisplayName: '摄影师',
      authorAvatarUrl: '',
      authorRoleLabel: '',
      authorIdentityTags: const [],
      authorVerified: false,
      title: title,
      body: body,
      coverUrl: urls.first,
      mediaUrls: urls,
      likeCount: 0,
      commentCount: 0,
      shareCount: 0,
      createdAt: DateTime.utc(2026),
    ),
  );
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        ...sealedCloudBoundaryOverrides(),
        contentConfigRepositoryProvider.overrideWithValue(_ImageTextConfig()),
        workBrowserSocialProofReaderProvider.overrideWithValue(
          _ImageTextSocialProof(),
        ),
        contentBehaviorCommandWriterProvider.overrideWithValue(
          _ImageTextBehavior(),
        ),
        activePersonaContextProvider.overrideWith(
          (_) async => ActivePersonaContextViewData.fallback(
            personaId: 'persona-1',
            ownerUserId: 'owner-1',
            displayName: '测试用户',
            avatarUrl: '',
          ),
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
      ],
      child: ScreenUtilInit(
        designSize: const Size(375, 812),
        builder: (context, _) => MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: WorksImmersiveViewer(
              showWorksToolbar: true,
              showTopNavigation: false,
              initialImageIndex: initialImageIndex,
              externalPosts: [post],
              rawPostsById: {
                post.id: MediaViewerPostWireRow.fromDynamicMap({
                  'postId': post.id,
                  'contentType': 'image',
                  'title': title,
                  'body': body,
                  'mediaItems': [
                    for (var i = 0; i < urls.length; i++)
                      {
                        'kind': 'image',
                        'url': urls[i],
                        if (captions[i] != null) 'caption': captions[i],
                      },
                  ],
                }),
              },
              onUserTap: (_, {avatarUrl, displayName, backgroundUrl}) {},
              onAssistantTap: () {},
            ),
          ),
        ),
      ),
    ),
  );
  for (var i = 0; i < 4; i++) {
    await tester.pump(const Duration(milliseconds: 60));
  }
}

MediaCaptionBlock _block(WidgetTester tester) =>
    tester.widget<MediaCaptionBlock>(find.byType(MediaCaptionBlock));

void main() {
  testWidgets('单图无标题时仍显示整帖配文，保留图片画布', (tester) async {
    await _pumpViewer(tester, body: _body);
    expect(find.text(_body), findsOneWidget);
    expect(_block(tester).caption, _body);
    expect(_block(tester).imageCaption, isEmpty);
    expect(find.byType(ImageBookCanvas), findsOneWidget);
    expect(find.byKey(const ValueKey('works-caption-rail')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('无配文无逐图说明时不伪造文字区', (tester) async {
    await _pumpViewer(tester);
    expect(find.byType(MediaCaptionBlock), findsNothing);
    expect(find.byType(ImageBookCanvas), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('无整帖配文时仅显示真实逐图说明，不提升为正文', (tester) async {
    await _pumpViewer(tester, captions: [_firstCaption]);
    expect(find.text(_firstCaption), findsOneWidget);
    expect(_block(tester).caption, isEmpty);
    expect(tester.takeException(), isNull);
  });

  testWidgets('多图落页仅切换逐图说明，整帖配文保持独立且不填补空说明', (tester) async {
    await _pumpViewer(
      tester,
      body: _body,
      captions: [_firstCaption, _secondCaption, null],
    );
    expect(find.text(_body), findsOneWidget);
    expect(find.text(_firstCaption), findsOneWidget);
    expect(find.text(_secondCaption), findsNothing);
    final canvas = tester.widget<ImageBookCanvas>(find.byType(ImageBookCanvas));
    expect(canvas.deliveries, hasLength(3));
    // 模拟图片书提交落页的公开回调，不更换媒体翻页宿主。
    canvas.onImageChanged(1);
    await tester.pump();
    expect(find.text(_body), findsOneWidget);
    expect(find.text(_firstCaption), findsNothing);
    expect(find.text(_secondCaption), findsOneWidget);
    expect(_block(tester).caption, _body);
    canvas.onImageChanged(2);
    await tester.pump();
    expect(find.text(_body), findsOneWidget);
    expect(find.text(_secondCaption), findsNothing);
    expect(find.byType(ImageBookCanvas), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('任意媒体定位进入时显示所选图片说明并保留整帖配文', (tester) async {
    await _pumpViewer(
      tester,
      body: _body,
      captions: [_firstCaption, _secondCaption],
      initialImageIndex: 1,
    );
    expect(find.text(_body), findsOneWidget);
    expect(find.text(_firstCaption), findsNothing);
    expect(find.text(_secondCaption), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('长配文沿用全文与收起交互，不吞掉逐图说明', (tester) async {
    await _pumpViewer(tester, body: _body * 30, captions: [_firstCaption]);
    final expand = find.textContaining(
      CommunityText.fullText,
      findRichText: true,
    );
    expect(expand, findsOneWidget);
    await tester.tap(expand);
    await tester.pump();
    expect(_block(tester).isExpanded, isTrue);
    expect(find.text(_firstCaption), findsOneWidget);
    expect(
      find.textContaining(CommunityText.collapse, findRichText: true),
      findsOneWidget,
    );
    expect(tester.takeException(), isNull);
  });
}
