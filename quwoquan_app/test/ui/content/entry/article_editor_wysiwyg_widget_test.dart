import 'dart:io';

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

const _transparentPng = <int>[
  0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x00,
  0x00, 0x0D, 0x49, 0x48, 0x44, 0x52, 0x00, 0x00, 0x00, 0x01,
  0x00, 0x00, 0x00, 0x01, 0x08, 0x06, 0x00, 0x00, 0x00, 0x1F,
  0x15, 0xC4, 0x89, 0x00, 0x00, 0x00, 0x0A, 0x49, 0x44, 0x41,
  0x54, 0x78, 0x9C, 0x62, 0x00, 0x00, 0x00, 0x02, 0x00, 0x01,
  0xE5, 0x27, 0xDE, 0xFC, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45,
  0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82,
];

late String _testImagePath;

Finder _fieldContainingText(String text) {
  return find.byWidgetPredicate(
    (widget) =>
        widget is CupertinoTextField &&
        (widget.controller?.text ?? '').contains(text),
  );
}

/// 构建带有 nodes 的 ArticleDocumentData。
ArticleDocumentData _buildDocument({
  String title = '',
  String body = '',
  List<ArticleDocumentAsset> assets = const <ArticleDocumentAsset>[],
}) {
  return createDefaultArticleDocument(
    title: title,
    body: body,
    imagePaths: assets.map((a) => a.imageUrl).toList(),
  );
}

/// 构建带有 figure + paragraph nodes 的文档。
ArticleDocumentData _buildDocumentWithNodes(
  List<ArticleDocumentNode> nodes, {
  String template = 'gentle',
  String fontPreset = 'clean',
}) {
  return ArticleDocumentData(
    nodes: nodes,
    template: template,
    fontPreset: fontPreset,
  );
}

class _EditorHarness extends StatefulWidget {
  const _EditorHarness({
    this.wrapInScrollView = false,
    this.seedDocument,
    this.onInsertImageAfter,
    this.onStateReady,
  });

  final bool wrapInScrollView;
  final ArticleDocumentData? seedDocument;
  final Future<void> Function(String?)? onInsertImageAfter;
  final ValueChanged<CreateEditorState>? onStateReady;

  @override
  State<_EditorHarness> createState() => _EditorHarnessState();
}

class _EditorHarnessState extends State<_EditorHarness> {
  late CreateEditorState state;
  late TextEditingController _titleController;
  late FocusNode _titleFocusNode;

  @override
  void initState() {
    super.initState();
    _titleController = TextEditingController();
    _titleFocusNode = FocusNode(debugLabel: 'title');

    final document = widget.seedDocument ?? _buildDocument();
    final pages = buildArticlePagesSnapshotFromDocument(document);
    final blocks = buildArticleBlocksFromDocument(document);
    state = CreateEditorState(
      editorKind: CreateEditorKind.text,
      mediaKind: CreateMediaKind.none,
      imagePaths: extractArticleImagePathsFromDocument(document),
      videoPath: '',
      originalVideoPath: '',
      videoThumbnail: '',
      videoDurationMs: 0,
      videoTrimStartMs: 0,
      videoTrimEndMs: 0,
      videoCoverTimeMs: 0,
      videoMuted: false,
      currentMediaIndex: 0,
      title: document.title,
      body: document.body,
      articleDocument: document,
      articleTemplate: ArticleTemplatePreset.gentle,
      articlePaperTexture: ArticlePaperTexture.white,
      articleFontPreset: ArticleFontPreset.clean,
      articlePages: pages,
      articleBlocks: blocks,
      activeArticlePageId: pages.isNotEmpty ? pages.first.id : null,
      activeArticleBlockId: blocks.isNotEmpty ? blocks.first.id : null,
      articleCoverImagePath: '',
      titlePresentation: TitlePresentation.collapsed,
      titleHintDismissed: false,
      settings: const PublishSettings(),
    );
    _titleController.text = document.title;
    widget.onStateReady?.call(state);
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
        onTitleChanged: (value) {},
        onTitleStyleChanged: (style) {},
        onUpdateNodeText: (nodeId, value) {},
        onUpdateNodeImageLayout: (nodeId, layout) {},
        onUpdateNodeCaption: (nodeId, caption) {},
        onEditNodeImage: (nodeId) async {},
        onRemoveNodeImage: (nodeId) {},
        onInsertImageAfter: (afterNodeId) async {
          await widget.onInsertImageAfter?.call(afterNodeId);
        },
        onActiveBlockChanged: (blockId) {
          setState(() => state = state.copyWith(activeArticleBlockId: blockId));
        },
        onInsertTextNodeAfter: (afterNodeId, {String initialText = ''}) {
          return '';
        },
        immersive: true,
        onUndo: () {},
        onRedo: () {},
        canUndo: false,
        canRedo: false,
      ),
    );

    return ProviderScope(
      child: MaterialApp(
        home: CupertinoPageScaffold(
          child: SafeArea(
            child: SizedBox(
              width: 430,
              height: 1280,
              child: widget.wrapInScrollView
                  ? SingleChildScrollView(child: editor)
                  : editor,
            ),
          ),
        ),
      ),
    );
  }
}

void main() {
  setUpAll(() async {
    final file = File(
      '${Directory.systemTemp.path}/article_editor_wysiwyg_test.png',
    );
    await file.writeAsBytes(_transparentPng, flush: true);
    _testImagePath = file.path;
  });

  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
  });

  testWidgets('纵向滚动编辑器展示标题、占位正文和图标工具栏', (tester) async {
    await tester.pumpWidget(const _EditorHarness());
    await tester.pumpAndSettle();

    // 标题 + 占位正文 = 2 个 CupertinoTextField
    expect(find.byType(CupertinoTextField), findsNWidgets(2));
    expect(find.byKey(TestKeys.createAccessoryBar), findsOneWidget);
    expect(find.byKey(TestKeys.createMediaAddButton), findsOneWidget);
    expect(find.byKey(TestKeys.createAccessoryEmojiButton), findsOneWidget);
    expect(find.byKey(TestKeys.createAccessoryStructureButton), findsOneWidget);
    expect(find.byKey(TestKeys.createAccessoryTemplateButton), findsOneWidget);
    expect(find.byKey(TestKeys.createAccessoryFontButton), findsOneWidget);
    // 空文档时显示占位正文输入框
    expect(find.byKey(TestKeys.createMomentInput), findsOneWidget);
  });

  testWidgets('点击序号面板后展示列表选项', (tester) async {
    await tester.pumpWidget(const _EditorHarness());
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(TestKeys.createAccessoryTemplateButton));
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey<String>('article_editor_list_panel')),
      findsOneWidget,
    );
    expect(find.text('序号'), findsOneWidget);
  });

  testWidgets('样式面板只展示无标题大标题小标题三档', (tester) async {
    await tester.pumpWidget(const _EditorHarness());
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(TestKeys.createAccessoryStructureButton));
    await tester.pumpAndSettle();

    expect(find.text('无标题'), findsOneWidget);
    expect(find.text('大标题'), findsOneWidget);
    expect(find.text('小标题'), findsOneWidget);
    expect(find.text('H1'), findsNothing);
    expect(find.text('H2'), findsNothing);
  });

  testWidgets('排版面板展示纸张质感和字体选项', (tester) async {
    await tester.pumpWidget(const _EditorHarness());
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(TestKeys.createAccessoryFontButton));
    await tester.pumpAndSettle();

    // 纸张质感选择器
    expect(find.text('纸张'), findsWidgets);
    expect(find.text('纯白'), findsOneWidget);
    expect(find.text('柔纸'), findsOneWidget);
    expect(find.text('暖黄'), findsOneWidget);

    // 字体选择器
    expect(find.text('字体'), findsWidgets);
    expect(find.text('黑体'), findsOneWidget);
    expect(find.text('宋体'), findsOneWidget);
  });

  testWidgets('表情面板展示 emoji 选择器', (tester) async {
    await tester.pumpWidget(const _EditorHarness());
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(TestKeys.createAccessoryEmojiButton));
    await tester.pumpAndSettle();

    expect(find.text('😀'), findsOneWidget);
  });

  testWidgets('编辑器在有限约束容器内正常渲染', (tester) async {
    // 新编辑器使用 Stack，需要有限约束。
    // 验证在 SizedBox 约束下不会触发布局异常。
    await tester.pumpWidget(const _EditorHarness(wrapInScrollView: false));
    await tester.pumpAndSettle();

    expect(find.byType(ArticleEditor), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('有正文内容时不显示占位输入框', (tester) async {
    final doc = _buildDocument(body: '第一段正文内容');
    await tester.pumpWidget(_EditorHarness(seedDocument: doc));
    await tester.pumpAndSettle();

    // 占位输入框不应出现
    expect(find.byKey(TestKeys.createMomentInput), findsNothing);
    // 正文内容应在 node 级 TextField 中
    expect(find.text('第一段正文内容'), findsOneWidget);
  });

  testWidgets('纵向滚动编辑器使用 SingleChildScrollView 而非 PageView', (tester) async {
    final doc = _buildDocument(body: '第一段正文\n第二段正文');
    await tester.pumpWidget(_EditorHarness(seedDocument: doc));
    await tester.pumpAndSettle();

    expect(find.byType(PageView), findsNothing);
    expect(find.byType(SingleChildScrollView), findsWidgets);
  });

  testWidgets('图片 node 渲染图片且可点击选中', (tester) async {
    final doc = _buildDocumentWithNodes(<ArticleDocumentNode>[
      const ArticleDocumentNode(
        id: 'title_0',
        type: ArticleDocumentNodeType.documentTitle,
        text: '测试标题',
      ),
      ArticleDocumentNode(
        id: 'fig_0',
        type: ArticleDocumentNodeType.figure,
        imageUrl: _testImagePath,
        imageLayout: 'fullWidth',
      ),
    ]);
    await tester.pumpWidget(_EditorHarness(seedDocument: doc));
    await tester.pumpAndSettle();

    // 图片应渲染
    expect(find.byType(Image), findsOneWidget);

    // 点击图片应展示工具栏
    await tester.tap(find.byType(Image));
    await tester.pumpAndSettle();

    expect(find.text('全宽'), findsOneWidget);
    expect(find.text('左图'), findsOneWidget);
    expect(find.text('右图'), findsOneWidget);
    expect(find.text('编辑'), findsOneWidget);
    expect(find.text('删除'), findsOneWidget);
  });

  testWidgets('环绕图片 node 渲染 Row 布局', (tester) async {
    final doc = _buildDocumentWithNodes(<ArticleDocumentNode>[
      const ArticleDocumentNode(
        id: 'title_0',
        type: ArticleDocumentNodeType.documentTitle,
        text: '',
      ),
      ArticleDocumentNode(
        id: 'fig_wrap',
        type: ArticleDocumentNodeType.figure,
        imageUrl: _testImagePath,
        imageLayout: 'wrapLeft',
      ),
      const ArticleDocumentNode(
        id: 'para_beside',
        type: ArticleDocumentNodeType.paragraph,
        text: '图旁正文内容',
      ),
    ]);
    await tester.pumpWidget(_EditorHarness(seedDocument: doc));
    await tester.pumpAndSettle();

    // 应有 Row 布局
    expect(find.byType(Row), findsWidgets);
    // 图旁正文应可见
    expect(find.text('图旁正文内容'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('连续环绕图不会触发 overflow', (tester) async {
    final capturedErrors = <FlutterErrorDetails>[];
    final originalOnError = FlutterError.onError;
    FlutterError.onError = (details) {
      capturedErrors.add(details);
    };

    final doc = _buildDocumentWithNodes(<ArticleDocumentNode>[
      const ArticleDocumentNode(
        id: 'title_0',
        type: ArticleDocumentNodeType.documentTitle,
        text: '',
      ),
      ArticleDocumentNode(
        id: 'fig_left',
        type: ArticleDocumentNodeType.figure,
        imageUrl: _testImagePath,
        imageLayout: 'wrapLeft',
      ),
      const ArticleDocumentNode(
        id: 'para_left',
        type: ArticleDocumentNodeType.paragraph,
        text: '左图旁正文需要足够长才能稳定占据图旁与图下区域。左图旁正文需要足够长才能稳定占据图旁与图下区域。',
      ),
      ArticleDocumentNode(
        id: 'fig_right',
        type: ArticleDocumentNodeType.figure,
        imageUrl: _testImagePath,
        imageLayout: 'wrapRight',
      ),
      const ArticleDocumentNode(
        id: 'para_right',
        type: ArticleDocumentNodeType.paragraph,
        text: '右图旁正文同样需要足够长才能覆盖连续多图时的紧缩高度场景。右图旁正文同样需要足够长才能覆盖连续多图时的紧缩高度场景。',
      ),
    ]);

    try {
      await tester.pumpWidget(_EditorHarness(seedDocument: doc));
      await tester.pumpAndSettle();
    } finally {
      FlutterError.onError = originalOnError;
    }

    final overflowErrors = capturedErrors
        .map((d) => d.exceptionAsString())
        .where((msg) => msg.contains('A RenderFlex overflowed'))
        .toList(growable: false);
    expect(overflowErrors, isEmpty);
  });

  testWidgets('主工具栏图片按钮触发插入新图而不是替换当前图', (tester) async {
    var insertTapCount = 0;
    await tester.pumpWidget(
      _EditorHarness(
        onInsertImageAfter: (afterNodeId) async {
          insertTapCount += 1;
        },
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(TestKeys.createMediaAddButton));
    await tester.pumpAndSettle();

    expect(insertTapCount, 1);
  });

  testWidgets('选中图片后展示布局切换工具栏', (tester) async {
    final doc = _buildDocumentWithNodes(<ArticleDocumentNode>[
      const ArticleDocumentNode(
        id: 'title_0',
        type: ArticleDocumentNodeType.documentTitle,
        text: '',
      ),
      ArticleDocumentNode(
        id: 'fig_0',
        type: ArticleDocumentNodeType.figure,
        imageUrl: _testImagePath,
        imageLayout: 'fullWidth',
      ),
    ]);
    await tester.pumpWidget(_EditorHarness(seedDocument: doc));
    await tester.pumpAndSettle();

    // 工具栏不应默认展示
    expect(find.text('全宽'), findsNothing);

    // 点击图片
    await tester.tap(find.byType(Image));
    await tester.pumpAndSettle();

    // 工具栏应展示
    expect(find.text('全宽'), findsOneWidget);
    expect(find.text('编辑'), findsOneWidget);
    expect(find.text('删除'), findsOneWidget);
  });

  testWidgets('双击图片切换选中状态', (tester) async {
    final doc = _buildDocumentWithNodes(<ArticleDocumentNode>[
      const ArticleDocumentNode(
        id: 'title_0',
        type: ArticleDocumentNodeType.documentTitle,
        text: '',
      ),
      ArticleDocumentNode(
        id: 'fig_0',
        type: ArticleDocumentNodeType.figure,
        imageUrl: _testImagePath,
        imageLayout: 'fullWidth',
      ),
    ]);
    await tester.pumpWidget(
      _EditorHarness(seedDocument: doc),
    );
    await tester.pumpAndSettle();

    // 第一次点击：选中，展示工具栏
    await tester.tap(find.byType(Image));
    await tester.pumpAndSettle();
    expect(find.text('编辑'), findsOneWidget);

    // 第二次点击：取消选中，隐藏工具栏
    await tester.tap(find.byType(Image));
    await tester.pumpAndSettle();
    expect(find.text('编辑'), findsNothing);
  });

  testWidgets('已有 caption 在编辑态居中展示', (tester) async {
    final doc = _buildDocumentWithNodes(<ArticleDocumentNode>[
      const ArticleDocumentNode(
        id: 'title_0',
        type: ArticleDocumentNodeType.documentTitle,
        text: '',
      ),
      ArticleDocumentNode(
        id: 'fig_0',
        type: ArticleDocumentNodeType.figure,
        imageUrl: _testImagePath,
        imageLayout: 'fullWidth',
        caption: '配图说明示例',
      ),
    ]);
    await tester.pumpWidget(_EditorHarness(seedDocument: doc));
    await tester.pumpAndSettle();

    // caption 应在 CupertinoTextField 中居中展示
    final captionField = tester.widget<CupertinoTextField>(
      find.byWidgetPredicate(
        (w) =>
            w is CupertinoTextField &&
            (w.controller?.text ?? '').contains('配图说明示例'),
      ),
    );
    expect(captionField.textAlign, TextAlign.center);
  });

  testWidgets('图文混排：图片和正文交替渲染', (tester) async {
    final doc = _buildDocumentWithNodes(<ArticleDocumentNode>[
      const ArticleDocumentNode(
        id: 'title_0',
        type: ArticleDocumentNodeType.documentTitle,
        text: '测试标题',
      ),
      const ArticleDocumentNode(
        id: 'para_0',
        type: ArticleDocumentNodeType.paragraph,
        text: '第一段正文',
      ),
      ArticleDocumentNode(
        id: 'fig_0',
        type: ArticleDocumentNodeType.figure,
        imageUrl: _testImagePath,
        imageLayout: 'fullWidth',
      ),
      const ArticleDocumentNode(
        id: 'para_1',
        type: ArticleDocumentNodeType.paragraph,
        text: '第二段正文',
      ),
    ]);
    await tester.pumpWidget(_EditorHarness(seedDocument: doc));
    await tester.pumpAndSettle();

    expect(find.text('第一段正文'), findsOneWidget);
    expect(find.byType(Image), findsOneWidget);
    expect(find.text('第二段正文'), findsOneWidget);
    expect(find.byKey(TestKeys.createMomentInput), findsNothing);
  });
}
