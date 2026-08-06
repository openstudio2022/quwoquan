import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_document_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_pagination_engine.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/article_presentation_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_presentation_values.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/create_editor_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/publish_settings_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_editor.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_preview_book_pager.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
  });

  testWidgets('ArticlePreviewBookPager exposes PageView with test key', (
    WidgetTester tester,
  ) async {
    final doc = ArticleDocumentData(
      nodes: const <ArticleDocumentNode>[
        ArticleDocumentNode(
          id: 'document_title',
          type: ArticleDocumentNodeType.documentTitle,
          text: 'T',
        ),
        ArticleDocumentNode(
          id: 'paragraph_1',
          type: ArticleDocumentNodeType.paragraph,
          text: '正文一段',
        ),
        ArticleDocumentNode(
          id: 'paragraph_2',
          type: ArticleDocumentNodeType.paragraph,
          text: '第二段',
        ),
      ],
    );
    final pages = ArticlePaginationEngine.paginateSnapshot(
      document: doc,
      stageWidth: 400,
      contentHeightOverride: 420,
    );
    expect(pages, isNotEmpty);
    await tester.pumpWidget(
      CupertinoApp(
        home: Scaffold(
          body: ArticlePreviewBookPager(
            pages: pages,
            template: ArticleTemplatePreset.journal,
            fontPreset: ArticleFontPreset.clean,
            initialPageIndex: 0,
            onPageChanged: (_) {},
          ),
        ),
      ),
    );
    expect(find.byKey(TestKeys.articlePreviewBookPager), findsOneWidget);
    expect(find.byType(PageView), findsOneWidget);
  });

  testWidgets('ArticleEditor vertical layout uses ListView not PageView', (
    WidgetTester tester,
  ) async {
    final document = ArticleDocumentData(
      nodes: const <ArticleDocumentNode>[
        ArticleDocumentNode(
          id: 'paragraph_1',
          type: ArticleDocumentNodeType.paragraph,
          text: '仅一页正文',
        ),
      ],
    );
    final pages = ArticlePaginationEngine.paginateSnapshot(
      document: document,
      stageWidth: 400,
      contentHeightOverride: 520,
    );
    final state = CreateEditorState(
      editorKind: CreateEditorKind.text,
      draftFlowKind: CreateDraftFlowKind.article,
      mediaKind: CreateMediaKind.none,
      imagePaths: const <String>[],
      videoPath: '',
      originalVideoPath: '',
      videoThumbnail: '',
      videoDurationMs: 0,
      videoTrimStartMs: 0,
      videoTrimEndMs: 0,
      videoCoverTimeMs: 0,
      videoCoverStrategy: 'first_frame',
      videoWidth: 0,
      videoHeight: 0,
      videoMuted: false,
      currentMediaIndex: 0,
      title: '',
      body: document.body,
      articleDocument: document,
      articlePages: pages,
      activeArticlePageId: pages.first.id,
      activeArticleBlockId: document.nodes.first.id,
      articleTemplate: ArticleTemplatePreset.journal,
      articlePaperTexture: ArticlePaperTexture.darkPaper,
      articleFontPreset: ArticleFontPreset.clean,
      articleCoverImagePath: '',
      titlePresentation: TitlePresentation.collapsed,
      titleHintDismissed: false,
      settings: PublishSettings(),
    );
    final titleController = TextEditingController();
    final titleFocus = FocusNode();
    await tester.pumpWidget(
      CupertinoApp(
        home: Scaffold(
          body: SizedBox(
            height: 900,
            width: 400,
            child: ArticleEditor(
              state: state,
              titleController: titleController,
              titleFocusNode: titleFocus,
              onTitleChanged: (_) {},
              onTitleStyleChanged: (_) {},
              onUpdateNodeText: (String nodeId, String value) {},
              onUpdateWrapParagraphTexts:
                  (String figureNodeId, String narrowText, String belowText) {},
              onUpdateNodeImageLayout: (String nodeId, String layout) {},
              onUpdateNodeCaption: (String nodeId, String caption) {},
              onEditNodeImage: (String nodeId) async {},
              onRemoveNodeImage: (String nodeId) {},
              onInsertImageAfter: (String? afterNodeId) async {},
              onInsertImageAtSelection:
                  (String nodeId, int selectionOffset) async {},
              onActiveBlockChanged: (String? id) {},
              onInsertTextNodeAfter:
                  (String afterNodeId, {String initialText = ''}) {
                    return '';
                  },
              onEnsureWrapNodeGroup: (String figureNodeId, {int? splitOffset}) {
                return null;
              },
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.byType(PageView), findsNothing);
    expect(find.byType(SingleChildScrollView), findsWidgets);
    titleController.dispose();
    titleFocus.dispose();
  });
}
