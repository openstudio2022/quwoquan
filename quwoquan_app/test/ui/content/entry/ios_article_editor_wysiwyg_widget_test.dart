import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/ios_article_editor.dart';
import 'package:quwoquan_app/ui/content/entry/models/publish_settings_models.dart';
import 'package:quwoquan_app/ui/content/widgets/article_content_block_renderer.dart';

class _EditorHarness extends StatefulWidget {
  const _EditorHarness();

  @override
  State<_EditorHarness> createState() => _EditorHarnessState();
}

class _EditorHarnessState extends State<_EditorHarness> {
  late final TextEditingController _titleController;
  late final FocusNode _titleFocusNode;
  int _seed = 10;
  CreateEditorStateV2 state = CreateEditorStateV2(
    editorKind: CreateEditorKind.text,
    mediaKind: CreateMediaKind.none,
    imagePaths: const <String>[],
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
    body: '首段内容\n清单事项\n环绕段落内容',
    articleBlocks: const <CreateTextBlock>[
      CreateTextBlock(
        id: 'p1',
        type: CreateTextBlockType.paragraph,
        text: '首段内容',
      ),
      CreateTextBlock(
        id: 'o1',
        type: CreateTextBlockType.orderedItem,
        text: '清单事项',
      ),
      CreateTextBlock(
        id: 'i1',
        type: CreateTextBlockType.image,
        imagePath: 'https://example.com/demo.jpg',
        imageLayout: CreateTextImageLayout.wrapLeft,
      ),
      CreateTextBlock(
        id: 'p2',
        type: CreateTextBlockType.paragraph,
        text: '环绕段落内容',
      ),
    ],
    activeArticleBlockId: 'p1',
    titlePresentation: TitlePresentation.collapsed,
    titleHintDismissed: false,
    settings: const PublishSettings(),
  );

  @override
  void initState() {
    super.initState();
    _titleController = TextEditingController();
    _titleFocusNode = FocusNode();
  }

  @override
  void dispose() {
    _titleController.dispose();
    _titleFocusNode.dispose();
    super.dispose();
  }

  void _updateBlocks(List<CreateTextBlock> blocks, {String? activeId}) {
    setState(() {
      state = state.copyWith(
        articleBlocks: blocks,
        body: buildArticlePlainText(blocks),
        imagePaths: extractArticleImagePaths(blocks),
        activeArticleBlockId: activeId ?? state.activeArticleBlockId,
      );
    });
  }

  String _nextId(String prefix) => '${prefix}_${_seed++}';

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      home: CupertinoPageScaffold(
        child: SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: IosArticleEditor(
              state: state,
              titleController: _titleController,
              titleFocusNode: _titleFocusNode,
              onTitleChanged: (value) {
                setState(() => state = state.copyWith(title: value));
              },
              onInsertParagraph: (afterBlockId) {
                final id = _nextId('paragraph');
                final next = List<CreateTextBlock>.from(state.articleBlocks);
                final index = afterBlockId == null
                    ? next.length
                    : next.indexWhere((block) => block.id == afterBlockId) + 1;
                next.insert(
                  index.clamp(0, next.length),
                  CreateTextBlock.paragraph(id: id),
                );
                _updateBlocks(next, activeId: id);
                return id;
              },
              onInsertOrderedItem: (afterBlockId) {
                final id = _nextId('ordered');
                final next = List<CreateTextBlock>.from(state.articleBlocks);
                final index = afterBlockId == null
                    ? next.length
                    : next.indexWhere((block) => block.id == afterBlockId) + 1;
                next.insert(
                  index.clamp(0, next.length),
                  CreateTextBlock.orderedItem(id: id),
                );
                _updateBlocks(next, activeId: id);
                return id;
              },
              onInsertImages: (afterBlockId) async {},
              onUpdateTextBlock: (blockId, text) {
                final next = state.articleBlocks
                    .map(
                      (block) => block.id == blockId
                          ? block.copyWith(text: text)
                          : block,
                    )
                    .toList(growable: false);
                _updateBlocks(next, activeId: blockId);
              },
              onRemoveBlock: (blockId) {
                final next = state.articleBlocks
                    .where((block) => block.id != blockId)
                    .toList(growable: false);
                String? nextActiveId;
                for (final block in next) {
                  if (block.isTextLike) {
                    nextActiveId = block.id;
                    break;
                  }
                }
                _updateBlocks(next, activeId: nextActiveId);
              },
              onReplaceImage: (blockId) async {},
              onUpdateImageLayout: (blockId, layout) {
                final next = state.articleBlocks
                    .map(
                      (block) => block.id == blockId
                          ? block.copyWith(imageLayout: layout)
                          : block,
                    )
                    .toList(growable: false);
                _updateBlocks(next, activeId: blockId);
              },
              onActiveBlockChanged: (blockId) {
                setState(() {
                  state = state.copyWith(activeArticleBlockId: blockId);
                });
              },
              immersive: true,
            ),
          ),
        ),
      ),
    );
  }
}

void main() {
  testWidgets('文章编辑器未选中块按阅读态显示，点击后原位切换编辑', (tester) async {
    await tester.pumpWidget(const _EditorHarness());
    await tester.pump();

    expect(find.byType(CupertinoTextField), findsNWidgets(2));
    expect(find.byType(ArticleContentBlockRenderer), findsNWidgets(2));
    expect(find.text('清单事项'), findsOneWidget);
    expect(find.text('环绕段落内容'), findsOneWidget);

    await tester.tap(find.text('清单事项'));
    await tester.pump();

    expect(find.byType(CupertinoTextField), findsNWidgets(2));
    expect(find.byType(ArticleContentBlockRenderer), findsNWidgets(2));
    final orderedField = tester.widget<CupertinoTextField>(
      find.byKey(TestKeys.createMomentInput),
    );
    expect(orderedField.controller?.text, '清单事项');

    await tester.tap(find.text('环绕段落内容'));
    await tester.pump();

    expect(find.byType(CupertinoTextField), findsNWidgets(2));
    expect(find.text('轻点替换图片'), findsOneWidget);
    final wrappedField = tester.widget<CupertinoTextField>(
      find.byKey(TestKeys.createMomentInput),
    );
    expect(wrappedField.controller?.text, '环绕段落内容');
  });
}
