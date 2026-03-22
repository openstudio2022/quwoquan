import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/models/publish_settings_models.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/ios_article_editor.dart';

class _EditorHarness extends StatefulWidget {
  const _EditorHarness({this.wrapInScrollView = false});

  final bool wrapInScrollView;

  @override
  State<_EditorHarness> createState() => _EditorHarnessState();
}

class _EditorHarnessState extends State<_EditorHarness> {
  late final TextEditingController _titleController;
  late final FocusNode _titleFocusNode;
  late CreateEditorStateV2 state;

  void _applyPages(List<ArticlePageData> pages, {String? activePageId}) {
    setState(() {
      state = state.copyWith(
        articlePages: pages,
        articleBlocks: buildArticleBlocksFromPages(pages),
        body: buildArticlePlainTextFromPages(pages),
        imagePaths: extractArticleImagePathsFromPages(pages),
        activeArticlePageId: activePageId ?? state.activeArticlePageId,
      );
    });
  }

  List<ArticlePageData> get _initialPages => const <ArticlePageData>[
    ArticlePageData(id: 'page_0', body: '第一页内容'),
    ArticlePageData(
      id: 'page_1',
      body: '第二页内容',
      imageUrl: 'https://example.com/demo.jpg',
      imageLayout: 'wrapLeft',
    ),
  ];

  @override
  void initState() {
    super.initState();
    _titleController = TextEditingController();
    _titleFocusNode = FocusNode();
    state = CreateEditorStateV2(
      editorKind: CreateEditorKind.text,
      mediaKind: CreateMediaKind.none,
      imagePaths: extractArticleImagePathsFromPages(_initialPages),
      videoPath: '',
      originalVideoPath: '',
      videoThumbnail: '',
      videoDurationMs: 0,
      videoTrimStartMs: 0,
      videoTrimEndMs: 0,
      videoCoverTimeMs: 0,
      videoMuted: false,
      currentMediaIndex: 0,
      title: '',
      body: buildArticlePlainTextFromPages(_initialPages),
      articlePages: _initialPages,
      articleBlocks: buildArticleBlocksFromPages(_initialPages),
      activeArticlePageId: _initialPages.first.id,
      activeArticleBlockId: buildArticleBlocksFromPages(_initialPages).first.id,
      articleTemplate: ArticleTemplatePreset.journal,
      articleFontPreset: ArticleFontPreset.clean,
      titlePresentation: TitlePresentation.collapsed,
      titleHintDismissed: false,
      settings: const PublishSettings(),
    );
  }

  @override
  void dispose() {
    _titleController.dispose();
    _titleFocusNode.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final editor = Padding(
      padding: const EdgeInsets.all(16),
      child: IosArticleEditor(
        state: state,
        titleController: _titleController,
        titleFocusNode: _titleFocusNode,
        onTitleChanged: (value) {
          setState(() => state = state.copyWith(title: value));
        },
        onUpdatePageText: (pageId, text) {
          final next = state.articlePages
              .map(
                (page) => page.id == pageId ? page.copyWith(body: text) : page,
              )
              .toList(growable: false);
          _applyPages(next, activePageId: pageId);
        },
        onEditPageImage: (pageId) async {},
        onUpdatePageImageLayout: (pageId, layout) {
          final next = state.articlePages
              .map(
                (page) => page.id == pageId
                    ? page.copyWith(imageLayout: layout)
                    : page,
              )
              .toList(growable: false);
          _applyPages(next, activePageId: pageId);
        },
        onRemovePage: (pageId) {
          final next = state.articlePages
              .where((page) => page.id != pageId)
              .toList(growable: false);
          _applyPages(next, activePageId: next.first.id);
        },
        onActivePageChanged: (pageId) {
          setState(() => state = state.copyWith(activeArticlePageId: pageId));
        },
        onTemplateChanged: (template) {
          setState(() => state = state.copyWith(articleTemplate: template));
        },
        onFontPresetChanged: (fontPreset) {
          setState(() => state = state.copyWith(articleFontPreset: fontPreset));
        },
        immersive: true,
      ),
    );

    return MaterialApp(
      home: CupertinoPageScaffold(
        child: SafeArea(
          child: widget.wrapInScrollView
              ? SingleChildScrollView(child: editor)
              : editor,
        ),
      ),
    );
  }
}

void main() {
  testWidgets('分页文章编辑器展示纸面和工具栏', (tester) async {
    await tester.pumpWidget(const _EditorHarness());
    await tester.pumpAndSettle();

    expect(find.byType(CupertinoTextField), findsNWidgets(2));
    expect(find.text('图片'), findsOneWidget);
    expect(find.text('表情'), findsOneWidget);
    expect(find.text('序号'), findsOneWidget);
    expect(find.text('模版'), findsOneWidget);
    expect(find.text('字体'), findsOneWidget);
    expect(find.byKey(TestKeys.createMomentInput), findsOneWidget);
  });

  testWidgets('点击序号后会在当前页插入编号', (tester) async {
    await tester.pumpWidget(const _EditorHarness());
    await tester.pumpAndSettle();

    await tester.tap(find.text('序号'));
    await tester.pump();

    final field = tester.widget<CupertinoTextField>(
      find.byKey(TestKeys.createMomentInput),
    );
    expect(field.controller?.text, contains('1. '));
  });

  testWidgets('打开模版弹层并展示多种模版', (tester) async {
    await tester.pumpWidget(const _EditorHarness());
    await tester.pumpAndSettle();

    await tester.tap(find.widgetWithText(CupertinoButton, '模版').first);
    await tester.pumpAndSettle();

    expect(find.text('柔和'), findsWidgets);
    expect(find.text('礼记'), findsWidgets);
    expect(find.text('手帐'), findsWidgets);
  });

  testWidgets('滚动容器内渲染文章编辑器不会触发无限高度异常', (tester) async {
    await tester.pumpWidget(const _EditorHarness(wrapInScrollView: true));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(find.byType(IosArticleEditor), findsOneWidget);
    expect(find.byKey(TestKeys.createMomentInput), findsOneWidget);
  });
}
