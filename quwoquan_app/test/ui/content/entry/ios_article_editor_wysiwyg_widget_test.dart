import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/article_document_models.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/models/publish_settings_models.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/article_editor.dart';
import 'package:shared_preferences/shared_preferences.dart';

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

  ArticleDocumentData _replaceBodyRange(
    ArticleDocumentData document, {
    required int start,
    required int end,
    required String replacement,
  }) {
    final nextBody = document.body.replaceRange(start, end, replacement);
    final delta = replacement.length - (end - start);
    final nextAssets = document.assets
        .map((asset) {
          final shouldShift =
              asset.offset > end || (end > start && asset.offset == end);
          return shouldShift
              ? asset.copyWith(offset: asset.offset + delta)
              : asset;
        })
        .toList(growable: false);
    return document.copyWith(body: nextBody, assets: nextAssets);
  }

  void _applyDocument(ArticleDocumentData document, {String? activePageId}) {
    final pages = buildArticlePagesSnapshotFromDocument(document);
    final blocks = buildArticleBlocksFromDocument(document);
    setState(() {
      state = state.copyWith(
        title: document.title,
        body: buildArticlePlainTextFromDocument(document),
        imagePaths: extractArticleImagePathsFromDocument(document),
        articleDocument: document,
        articlePages: pages,
        articleBlocks: blocks,
        activeArticlePageId: activePageId ?? pages.first.id,
        activeArticleBlockId: blocks.first.id,
      );
    });
  }

  void _applyBlocks(List<CreateTextBlock> blocks, {String? activeBlockId}) {
    final document = buildArticleDocumentFromBlocks(blocks, title: state.title);
    final pages = buildArticlePagesSnapshotFromDocument(
      document,
      fontPreset: state.articleFontPreset,
    );
    setState(() {
      state = state.copyWith(
        body: buildArticlePlainTextFromDocument(document),
        imagePaths: extractArticleImagePathsFromDocument(document),
        articleDocument: document,
        articlePages: pages,
        articleBlocks: blocks,
        activeArticlePageId: pages.first.id,
        activeArticleBlockId: activeBlockId ?? state.activeArticleBlockId,
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
    final initialDocument = buildArticleDocumentFromPages(_initialPages);
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
      articleDocument: initialDocument,
      articlePages: _initialPages,
      articleBlocks: buildArticleBlocksFromPages(_initialPages),
      activeArticlePageId: _initialPages.first.id,
      activeArticleBlockId: buildArticleBlocksFromPages(_initialPages).first.id,
      articleTemplate: ArticleTemplatePreset.journal,
      articleFontPreset: ArticleFontPreset.clean,
      articleCoverImagePath: '',
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
      child: ArticleEditor(
        state: state,
        titleController: _titleController,
        titleFocusNode: _titleFocusNode,
        onTitleChanged: (value) {
          _applyDocument(state.articleDocument.copyWith(title: value));
        },
        onUpdatePageText: (page, text) {
          final binding = page.binding!;
          final document = binding.hasBodySlice
              ? _replaceBodyRange(
                  state.articleDocument,
                  start: binding.bodyRange!.start,
                  end: binding.bodyRange!.end,
                  replacement: text,
                )
              : _replaceBodyRange(
                  state.articleDocument,
                  start: binding.insertOffset,
                  end: binding.insertOffset,
                  replacement: text,
                );
          _applyDocument(document, activePageId: page.id);
        },
        onEditPageImage: (page) async {},
        onUpdatePageImageLayout: (page, layout) {
          final binding = page.binding!;
          final nextAssets = state.articleDocument.assets
              .map(
                (asset) => asset.id == binding.assetId
                    ? asset.copyWith(imageLayout: layout)
                    : asset,
              )
              .toList(growable: false);
          _applyDocument(
            state.articleDocument.copyWith(assets: nextAssets),
            activePageId: page.id,
          );
        },
        onRemovePage: (page) {
          var document = state.articleDocument;
          if (page.binding!.hasBodySlice) {
            document = _replaceBodyRange(
              document,
              start: page.binding!.bodyRange!.start,
              end: page.binding!.bodyRange!.end,
              replacement: '',
            );
          }
          if (page.binding!.hasAsset) {
            document = document.copyWith(
              assets: document.assets
                  .where((asset) => asset.id != page.binding!.assetId)
                  .toList(growable: false),
            );
          }
          _applyDocument(document);
        },
        onActivePageChanged: (pageId) {
          setState(() => state = state.copyWith(activeArticlePageId: pageId));
        },
        onActiveBlockChanged: (blockId) {
          setState(() => state = state.copyWith(activeArticleBlockId: blockId));
        },
        onUpdateTextBlock: (blockId, value) {
          final next = state.articleBlocks
              .map(
                (block) =>
                    block.id == blockId ? block.copyWith(text: value) : block,
              )
              .toList(growable: false);
          _applyBlocks(next, activeBlockId: blockId);
        },
        onInsertTextBlock: (afterBlockId, type) {
          final nextId = '${type.name}_${state.articleBlocks.length + 1}';
          final block = switch (type) {
            CreateTextBlockType.heading2 => CreateTextBlock.heading2(
              id: nextId,
            ),
            CreateTextBlockType.heading3 => CreateTextBlock.heading3(
              id: nextId,
            ),
            CreateTextBlockType.sectionTitle => CreateTextBlock.sectionTitle(
              id: nextId,
            ),
            CreateTextBlockType.orderedItem => CreateTextBlock.orderedItem(
              id: nextId,
            ),
            CreateTextBlockType.bulletItem => CreateTextBlock.bulletItem(
              id: nextId,
            ),
            CreateTextBlockType.paragraph => CreateTextBlock.paragraph(
              id: nextId,
            ),
            CreateTextBlockType.image => CreateTextBlock.image(
              id: nextId,
              imagePath: '',
            ),
          };
          final blocks = List<CreateTextBlock>.from(state.articleBlocks);
          final insertIndex = afterBlockId == null
              ? blocks.length
              : blocks.indexWhere((item) => item.id == afterBlockId) + 1;
          blocks.insert(insertIndex.clamp(0, blocks.length), block);
          _applyBlocks(blocks, activeBlockId: nextId);
          return nextId;
        },
        onUpdateTextBlockType: (blockId, type) {
          final next = state.articleBlocks
              .map(
                (block) =>
                    block.id == blockId ? block.copyWith(type: type) : block,
              )
              .toList(growable: false);
          _applyBlocks(next, activeBlockId: blockId);
        },
        onRemoveTextBlock: (blockId) {
          final next = state.articleBlocks
              .where((block) => block.id != blockId)
              .toList(growable: false);
          _applyBlocks(next.isEmpty ? createDefaultArticleBlocks() : next);
        },
        onCoverChanged: (imagePath) {
          setState(
            () =>
                state = state.copyWith(articleCoverImagePath: imagePath ?? ''),
          );
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

    return ProviderScope(
      child: MaterialApp(
        home: CupertinoPageScaffold(
          child: SafeArea(
            child: widget.wrapInScrollView
                ? SingleChildScrollView(child: editor)
                : editor,
          ),
        ),
      ),
    );
  }
}

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
  });

  testWidgets('分页文章编辑器展示纸面和图标工具栏', (tester) async {
    await tester.pumpWidget(const _EditorHarness());
    await tester.pumpAndSettle();

    expect(find.byType(CupertinoTextField), findsNWidgets(2));
    expect(find.byKey(TestKeys.createAccessoryBar), findsOneWidget);
    expect(find.byKey(TestKeys.createMediaAddButton), findsOneWidget);
    expect(find.byKey(TestKeys.createAccessoryEmojiButton), findsOneWidget);
    expect(find.byKey(TestKeys.createAccessoryStructureButton), findsOneWidget);
    expect(find.byKey(TestKeys.createAccessoryTemplateButton), findsOneWidget);
    expect(find.byKey(TestKeys.createAccessoryFontButton), findsOneWidget);
    expect(find.text('图片'), findsNothing);
    expect(find.text('表情'), findsNothing);
    expect(find.text('序号'), findsNothing);
    expect(find.text('模版'), findsNothing);
    expect(find.text('字体'), findsNothing);
    expect(find.byKey(TestKeys.createMomentInput), findsOneWidget);
  });

  testWidgets('点击结构按钮后展示层级设置并插入编号', (tester) async {
    await tester.pumpWidget(const _EditorHarness());
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(TestKeys.createAccessoryStructureButton));
    await tester.pumpAndSettle();

    expect(find.byKey(TestKeys.createStructurePanel), findsOneWidget);
    expect(find.text('标题'), findsOneWidget);
    expect(find.text('序号'), findsOneWidget);
    expect(find.text('H1'), findsOneWidget);

    await tester.tap(find.text('1. 数字序号'));
    await tester.pumpAndSettle();

    final field = tester.widget<CupertinoTextField>(
      find.byKey(TestKeys.createMomentInput),
    );
    expect(field.controller?.text, contains('1. '));
  });

  testWidgets('点击表情按钮后以内联附件面板展示 emoji', (tester) async {
    await tester.pumpWidget(const _EditorHarness());
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(TestKeys.createAccessoryEmojiButton));
    await tester.pumpAndSettle();

    expect(find.byKey(TestKeys.createAccessoryPanel), findsOneWidget);
    expect(find.byKey(TestKeys.createEmojiPanel), findsOneWidget);
    expect(find.text('全部表情'), findsOneWidget);

    await tester.tap(find.byKey(TestKeys.createAccessoryEmojiButton));
    await tester.pumpAndSettle();

    expect(find.byKey(TestKeys.createEmojiPanel), findsNothing);
  });

  testWidgets('打开模版附件面板并展示多种模版', (tester) async {
    await tester.pumpWidget(const _EditorHarness());
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(TestKeys.createAccessoryTemplateButton));
    await tester.pumpAndSettle();

    expect(find.byKey(TestKeys.createTemplatePanel), findsOneWidget);
    expect(find.text('柔和'), findsWidgets);
    expect(find.text('礼记'), findsWidgets);
    expect(find.text('手帐'), findsWidgets);
  });

  testWidgets('模板面板可选择扉页封面并同步到第一页', (tester) async {
    await tester.pumpWidget(const _EditorHarness());
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(TestKeys.createAccessoryTemplateButton));
    await tester.pumpAndSettle();

    expect(find.byKey(TestKeys.createArticleCoverNoneOption), findsOneWidget);
    await tester.tap(
      find.byKey(const ValueKey<String>('create_article_cover_option_0')),
    );
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey<String>('article-editor-frontispiece-image')),
      findsOneWidget,
    );
    await tester.enterText(find.byType(CupertinoTextField).first, '封面标题');
    await tester.pumpAndSettle();
    expect(find.text('扉页封面'), findsNothing);
    final imageRect = tester.getRect(
      find.byKey(const ValueKey<String>('article-editor-frontispiece-image')),
    );
    final titleRect = tester.getRect(find.text('封面标题'));
    expect(titleRect.top, lessThan(imageRect.bottom));

    await tester.tap(find.byKey(TestKeys.createAccessoryTemplateButton));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(TestKeys.createArticleCoverNoneOption));
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey<String>('article-editor-frontispiece-image')),
      findsNothing,
    );
  });

  testWidgets('滚动容器内渲染文章编辑器不会触发无限高度异常', (tester) async {
    await tester.pumpWidget(const _EditorHarness(wrapInScrollView: true));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(find.byType(ArticleEditor), findsOneWidget);
    expect(find.byKey(TestKeys.createMomentInput), findsOneWidget);
  });
}
