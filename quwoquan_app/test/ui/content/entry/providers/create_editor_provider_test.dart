import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/ui/content/article_document_models.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/entry/models/article_editor_projection.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/providers/create_editor_provider.dart';

void main() {
  test('重排图片后保持新的顺序结果', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    notifier.setImages(<String>[
      'a.png',
      'b.png',
      'c.png',
    ], editorKind: CreateEditorKind.media);
    notifier.setCurrentMediaIndex(2);

    notifier.reorderImages(2, 0);

    final state = container.read(createEditorProvider);
    expect(state.imagePaths, <String>['c.png', 'a.png', 'b.png']);
  });

  test('文章块更新时同步正文和活动块', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    final paragraphId = container
        .read(createEditorProvider)
        .articleBlocks
        .first
        .id;
    notifier.updateArticleTextBlock(paragraphId, '开头');
    final orderedId = notifier.insertArticleOrderedItem(
      afterBlockId: paragraphId,
    );
    notifier.updateArticleTextBlock(orderedId, '第二条');

    final state = container.read(createEditorProvider);
    expect(state.body, '开头\n1. 第二条');
    expect(state.activeArticleBlockId, orderedId);
  });

  test('插入正文 H2 会写入连续文档标题锚点并生成分页块', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    final paragraphId = container
        .read(createEditorProvider)
        .articleBlocks
        .first
        .id;
    notifier.updateArticleTextBlock(paragraphId, '正文第一段');
    final headingId = notifier.insertArticleTextBlock(
      afterBlockId: paragraphId,
      type: CreateTextBlockType.heading2,
    );
    notifier.updateArticleTextBlock(headingId, '章节一');

    final state = container.read(createEditorProvider);
    expect(
      state.articleDocument.blocks.any(
        (block) =>
            block.id == headingId &&
            block.type == ArticleDocumentBlockType.heading2 &&
            block.text == '章节一',
      ),
      isTrue,
    );
    expect(state.body, contains('章节一'));
    expect(
      state.articlePages.any(
        (page) => page.contentBlocks.any((block) => block.id == headingId),
      ),
      isTrue,
    );
  });

  test('插入文章图片块时同步图片路径', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    final anchorId = container
        .read(createEditorProvider)
        .articleBlocks
        .first
        .id;
    notifier.insertArticleImages(<String>[
      'a.png',
      'b.png',
    ], afterBlockId: anchorId);

    final state = container.read(createEditorProvider);
    expect(state.imagePaths, <String>['a.png', 'b.png']);
    expect(state.articleBlocks.where((block) => block.hasImage).length, 2);
  });

  test('文章图片块可更新环绕布局', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    final anchorId = container
        .read(createEditorProvider)
        .articleBlocks
        .first
        .id;
    notifier.insertArticleImages(<String>['a.png'], afterBlockId: anchorId);
    final imageBlock = container
        .read(createEditorProvider)
        .articleBlocks
        .firstWhere((block) => block.hasImage);

    notifier.updateArticleImageLayout(
      imageBlock.id,
      CreateTextImageLayout.wrapLeft,
    );

    final state = container.read(createEditorProvider);
    expect(
      state.articleBlocks
          .firstWhere((block) => block.id == imageBlock.id)
          .imageLayout,
      CreateTextImageLayout.wrapLeft,
    );
  });

  test('ensureArticleWrapNodeGroup 会补齐 narrow/below 双段节点', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    final figureId = notifier.insertImageAfterNode(
      kArticleEditorStartAnchorId,
      'wrap.png',
    );

    notifier.updateArticleNodeImageLayout(figureId, 'wrapLeft');
    final ensured = notifier.ensureArticleWrapNodeGroup(figureId);

    expect(ensured, isNotNull);
    expect(ensured!.figure.imageLayout, 'wrapLeft');
    expect(ensured.narrowParagraph, isNotNull);
    expect(ensured.belowParagraph, isNotNull);
  });

  test('updateArticleWrapParagraphTexts 会同步回写 narrow 与 below', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    final figureId = notifier.insertImageAfterNode(
      kArticleEditorStartAnchorId,
      'wrap.png',
    );

    notifier.updateArticleNodeImageLayout(figureId, 'wrapLeft');
    notifier.updateArticleWrapParagraphTexts(
      figureId,
      narrowText: '窄文段落',
      belowText: '下文段落',
    );

    final group = resolveArticleWrapNodeGroupByFigureId(
      container.read(createEditorProvider).articleDocument.nodes,
      figureId,
    );
    expect(group, isNotNull);
    expect(group!.narrowText, '窄文段落');
    expect(group.belowText, '下文段落');
    expect(
      container.read(createEditorProvider).articleDocument.body,
      '窄文段落下文段落',
    );
  });

  test('开头锚点插图会落在正文最前方', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    final firstBlock = container.read(createEditorProvider).articleBlocks.first;
    notifier.updateArticleTextBlock(firstBlock.id, '原始正文');

    final figureId = notifier.insertImageAfterNode(
      kArticleEditorStartAnchorId,
      'lead.png',
    );

    final nodes = container.read(createEditorProvider).articleDocument.nodes;
    final firstContentNode = nodes.firstWhere((node) => !node.isDocumentTitle);
    expect(firstContentNode.id, figureId);
    expect(firstContentNode.imageUrl, 'lead.png');
  });

  test('prepareTextNodeForImageInsertion 会按选区拆分段落', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    notifier.insertTextNodeAfter(
      kArticleEditorStartAnchorId,
      initialText: '第一段正文',
    );
    final firstNode = container
        .read(createEditorProvider)
        .articleDocument
        .nodes
        .firstWhere((node) => !node.isDocumentTitle);

    final anchorId = notifier.prepareTextNodeForImageInsertion(firstNode.id, 3);

    final nodes = container
        .read(createEditorProvider)
        .articleDocument
        .nodes
        .where((node) => !node.isDocumentTitle)
        .toList(growable: false);
    expect(anchorId, firstNode.id);
    expect(nodes.first.id, firstNode.id);
    expect(nodes.first.text, '第一段');
    expect(nodes[1].text, '正文');
  });

  test('文章封面选择在原图删除后会自动清空', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    final anchorId = container
        .read(createEditorProvider)
        .articleBlocks
        .first
        .id;
    notifier.insertArticleImages(<String>['cover.png'], afterBlockId: anchorId);
    final imageBlock = container
        .read(createEditorProvider)
        .articleBlocks
        .firstWhere((block) => block.hasImage);

    notifier.setArticleCoverImage('cover.png');
    expect(
      container.read(createEditorProvider).articleCoverImagePath,
      'cover.png',
    );

    notifier.removeArticleBlock(imageBlock.id);

    expect(container.read(createEditorProvider).articleCoverImagePath, isEmpty);
  });

  test('文章正文更新后可撤销与重做', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    final paragraphId = container
        .read(createEditorProvider)
        .articleBlocks
        .first
        .id;
    final before = container.read(createEditorProvider).body;
    notifier.updateArticleTextBlock(paragraphId, '改动后');
    expect(container.read(createEditorProvider).body, contains('改动后'));
    expect(notifier.canUndoArticle, isTrue);

    notifier.undoArticle();
    expect(container.read(createEditorProvider).body, before);
    expect(notifier.canRedoArticle, isTrue);

    notifier.redoArticle();
    expect(container.read(createEditorProvider).body, contains('改动后'));
  });

  test('视频编辑状态会保留原视频路径与裁切静音信息', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    notifier.setVideo(
      'edited.mp4',
      editorKind: CreateEditorKind.media,
      thumbnail: 'cover.jpg',
      originalPath: 'raw.mp4',
      durationMs: 7600,
      trimStartMs: 1200,
      trimEndMs: 6200,
      coverTimeMs: 2800,
      muted: true,
    );

    notifier.applyVideoEditing(
      videoPath: 'edited_v2.mp4',
      thumbnailPath: 'cover_v2.jpg',
      videoDurationMs: 6800,
      trimStartMs: 1400,
      trimEndMs: 5400,
      coverTimeMs: 3000,
      muted: false,
      originalVideoPath: 'raw.mp4',
    );

    final state = container.read(createEditorProvider);
    expect(state.videoPath, 'edited_v2.mp4');
    expect(state.originalVideoPath, 'raw.mp4');
    expect(state.videoThumbnail, 'cover_v2.jpg');
    expect(state.videoDurationMs, 6800);
    expect(state.videoTrimStartMs, 1400);
    expect(state.videoTrimEndMs, 5400);
    expect(state.videoCoverTimeMs, 3000);
    expect(state.videoMuted, isFalse);
  });

  test('通用插图在当前页已有图片时仍新增并按 asset 顺序落位', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    final firstPageId = container
        .read(createEditorProvider)
        .articlePages
        .first
        .id;
    final firstLanding = notifier.insertArticleImageAtBodyOffset(
      'a.png',
      bodyInsertOffset: 0,
      fallbackActivePageId: firstPageId,
    );

    final secondLanding = notifier.insertArticleImageAtBodyOffset(
      'b.png',
      bodyInsertOffset: 0,
      fallbackActivePageId: firstLanding,
    );

    final state = container.read(createEditorProvider);
    expect(state.articleDocument.assets.length, 2);
    expect(
      state.articleDocument.assets.map((asset) => asset.imageUrl).toList(),
      containsAll(<String>['a.png', 'b.png']),
    );
    expect(
      state.articleDocument.assets.every((asset) => asset.offset == 0),
      isTrue,
      reason: 'editor-only gap 不再写入 canonical body，同锚点图片保持同 offset',
    );
    expect(
      state.articleDocument.assets.map((asset) => asset.id).toList(),
      orderedEquals(<String>['asset_1', 'asset_2']),
      reason: '同 offset 连续插图依赖 asset 顺序维持图序',
    );
    expect(secondLanding, isNotEmpty);
  });

  test('insertArticleImageAfterPage 不再把图间占位写入正文', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    final firstPageId = container
        .read(createEditorProvider)
        .articlePages
        .first
        .id;
    final p1 = notifier.insertArticleImageAtBodyOffset(
      'a.png',
      bodyInsertOffset: 0,
      fallbackActivePageId: firstPageId,
    );
    final p2 = notifier.insertArticleImageAfterPage(p1, 'b.png');
    notifier.insertArticleImageAfterPage(p2, 'c.png');

    final doc = container.read(createEditorProvider).articleDocument;
    expect(doc.assets.length, 3);
    expect(doc.assets.every((asset) => asset.offset == 0), isTrue);
    expect(doc.body, isEmpty);
  });

  test('空白图前插文提交不会把 editor-only gap 写入文档', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    final firstPageId = container
        .read(createEditorProvider)
        .articlePages
        .first
        .id;
    notifier.insertArticleImageAtBodyOffset(
      'a.png',
      bodyInsertOffset: 0,
      fallbackActivePageId: firstPageId,
    );

    final assetId = container
        .read(createEditorProvider)
        .articleDocument
        .assets
        .first
        .id;
    notifier.insertArticleParagraphBeforeAsset(assetId);

    final doc = container.read(createEditorProvider).articleDocument;
    expect(doc.body, isEmpty);
    expect(doc.assets.single.offset, 0);
  });

  test('materializeArticleParagraphBeforeAsset 会返回承载新正文的 landing page', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    final firstPageId = container
        .read(createEditorProvider)
        .articlePages
        .first
        .id;
    notifier.insertArticleImageAtBodyOffset(
      'a.png',
      bodyInsertOffset: 0,
      fallbackActivePageId: firstPageId,
    );

    final assetId = container
        .read(createEditorProvider)
        .articleDocument
        .assets
        .first
        .id;
    final landingPageId = notifier.materializeArticleParagraphBeforeAsset(
      assetId,
      text: '图前正文',
    );

    final state = container.read(createEditorProvider);
    final page = state.articlePages.firstWhere(
      (page) => page.id == landingPageId,
    );
    expect(page.body, contains('图前正文'));
    expect(state.articleDocument.body.startsWith('\n'), isFalse);
    expect(state.activeArticlePageId, landingPageId);
    expect(state.articleDocument.assets.single.offset, greaterThan(0));
  });

  test('materializeArticleParagraphAfterAsset 会返回承载新正文的 landing page', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    final firstPageId = container
        .read(createEditorProvider)
        .articlePages
        .first
        .id;
    notifier.insertArticleImageAtBodyOffset(
      'a.png',
      bodyInsertOffset: 0,
      fallbackActivePageId: firstPageId,
    );

    final assetId = container
        .read(createEditorProvider)
        .articleDocument
        .assets
        .first
        .id;
    final landingPageId = notifier.materializeArticleParagraphAfterAsset(
      assetId,
      text: '图后正文',
    );

    final state = container.read(createEditorProvider);
    final page = state.articlePages.firstWhere(
      (page) => page.id == landingPageId,
    );
    expect(page.body, contains('图后正文'));
    expect(state.articleDocument.body, startsWith('图后正文'));
    expect(state.activeArticlePageId, landingPageId);
  });

  test('环绕图片分页会生成 wrapContent fragment 与布局数据', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    final paragraphId = container
        .read(createEditorProvider)
        .articleBlocks
        .first
        .id;
    notifier.updateArticleTextBlock(
      paragraphId,
      '这是一段足够长的正文，用于验证图文环绕分页结果会生成统一 fragments，并且能够携带图旁与图下续写所需的布局数据。',
    );
    final landing = notifier.insertArticleImageAtBodyOffset(
      'wrap.png',
      bodyInsertOffset: 0,
      fallbackActivePageId: container
          .read(createEditorProvider)
          .articlePages
          .first
          .id,
    );
    notifier.updateArticlePageImageLayout(landing, 'wrapLeft');

    final state = container.read(createEditorProvider);
    final page = state.articlePages.firstWhere((page) => page.id == landing);
    final wrap = page.fragments.firstWhere(
      (fragment) => fragment.kind == ArticleLayoutFragmentKind.wrapContent,
    );
    expect(wrap.asset?.imageUrl, 'wrap.png');
    expect(wrap.wrapLayout, isNotNull);
    expect(wrap.wrapLayout!.besideHeight, greaterThan(0));
    expect(wrap.wrapLayout!.splitOffset, greaterThanOrEqualTo(0));
  });

  test('无 bodySlice 时按锚点整段替换正文不重复拼接', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    notifier.insertArticleImageAtBodyOffset('a.png', bodyInsertOffset: 0);
    final assetId =
        container.read(createEditorProvider).articleDocument.assets.first.id;

    final binding = ArticlePageBinding(
      insertOffset: 0,
      assetOffset: 0,
      assetId: assetId,
    );

    notifier.updateArticlePageTextFromBinding(binding, 'x');
    expect(container.read(createEditorProvider).articleDocument.body, 'x');

    notifier.updateArticlePageTextFromBinding(binding, 'xy');
    expect(container.read(createEditorProvider).articleDocument.body, 'xy');
  });

  test('首图前插文草稿同步进 body 并推移文内图 offset', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    notifier.insertArticleImageAtBodyOffset('a.png', bodyInsertOffset: 0);
    final assetId =
        container.read(createEditorProvider).articleDocument.assets.first.id;

    notifier.syncParagraphDraftBeforeAsset(assetId, 'hello');
    var doc = container.read(createEditorProvider).articleDocument;
    expect(doc.body, 'hello');
    expect(doc.assets.first.offset, 5);

    notifier.syncParagraphDraftBeforeAsset(assetId, 'hello\nx');
    doc = container.read(createEditorProvider).articleDocument;
    expect(doc.body, 'hello\nx');
    expect(doc.assets.first.offset, 7);
  });

  // ── 阶段 1 回归测试：nodes 级操作 ──

  test('insertImageAfterNode 后 nodes 序列正确', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    // 初始化为文章编辑器
    notifier.setEditorKind(CreateEditorKind.text);
    notifier.updateTitle('测试');
    notifier.insertTextNodeAfter(kArticleEditorStartAnchorId, initialText: '第一段');

    final stateBefore = container.read(createEditorProvider);
    final nodesBefore = stateBefore.articleDocument.nodes;
    // 应有 title + paragraph
    expect(nodesBefore.length, 2);

    // 在第一段后插入图片
    final figureId = notifier.insertImageAfterNode(
      nodesBefore.last.id,
      '/test.jpg',
    );

    final stateAfter = container.read(createEditorProvider);
    final nodesAfter = stateAfter.articleDocument.nodes;
    // 应有 title + paragraph + figure
    expect(nodesAfter.length, 3);
    expect(nodesAfter.last.id, figureId);
    expect(nodesAfter.last.type, ArticleDocumentNodeType.figure);
    expect(nodesAfter.last.imageUrl, '/test.jpg');

    // body/assets 应自动投影
    expect(stateAfter.articleDocument.assets.length, 1);
    expect(stateAfter.articleDocument.assets.first.imageUrl, '/test.jpg');
  });

  // ── 阶段二：Node 级编辑命令单元测试 ──

  test('updateArticleNodeText 更新指定节点文本', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    notifier.setEditorKind(CreateEditorKind.text);
    notifier.updateTitle('测试标题');

    // 获取初始文档的段落节点
    final doc = container.read(createEditorProvider).articleDocument;
    final paragraphNodes = doc.nodes.where(
      (n) => n.type == ArticleDocumentNodeType.paragraph,
    );
    if (paragraphNodes.isEmpty) {
      // 插入一个段落
      final newId = notifier.insertTextNodeAfter(
        doc.nodes.first.id,
        initialText: '原始文本',
      );
      notifier.updateArticleNodeText(newId, '修改后的文本');
      final updated = container.read(createEditorProvider).articleDocument;
      final node = updated.nodes.firstWhere((n) => n.id == newId);
      expect(node.text, '修改后的文本');
    } else {
      final nodeId = paragraphNodes.first.id;
      notifier.updateArticleNodeText(nodeId, '修改后的文本');
      final updated = container.read(createEditorProvider).articleDocument;
      final node = updated.nodes.firstWhere((n) => n.id == nodeId);
      expect(node.text, '修改后的文本');
    }
  });

  test('updateArticleNodeImageLayout 切换图片布局', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    notifier.setEditorKind(CreateEditorKind.text);
    notifier.updateTitle('测试');

    final doc = container.read(createEditorProvider).articleDocument;
    final anchorId = doc.nodes.first.id;
    final figId = notifier.insertImageAfterNode(anchorId, '/img.jpg');

    notifier.updateArticleNodeImageLayout(figId, 'wrapLeft');
    final updated = container.read(createEditorProvider).articleDocument;
    final fig = updated.nodes.firstWhere((n) => n.id == figId);
    expect(fig.imageLayout, 'wrapLeft');

    notifier.updateArticleNodeImageLayout(figId, 'wrapRight');
    final updated2 = container.read(createEditorProvider).articleDocument;
    final fig2 = updated2.nodes.firstWhere((n) => n.id == figId);
    expect(fig2.imageLayout, 'wrapRight');
  });

  test('updateArticleNodeCaption 更新图片说明', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    notifier.setEditorKind(CreateEditorKind.text);
    notifier.updateTitle('测试');

    final doc = container.read(createEditorProvider).articleDocument;
    final anchorId = doc.nodes.first.id;
    final figId = notifier.insertImageAfterNode(anchorId, '/img.jpg');

    notifier.updateArticleNodeCaption(figId, '这是图片说明');
    final updated = container.read(createEditorProvider).articleDocument;
    final fig = updated.nodes.firstWhere((n) => n.id == figId);
    expect(fig.caption, '这是图片说明');
  });

  test('removeArticleNode 删除指定节点', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    notifier.setEditorKind(CreateEditorKind.text);
    notifier.updateTitle('测试');

    final doc = container.read(createEditorProvider).articleDocument;
    final anchorId = doc.nodes.first.id;
    final figId = notifier.insertImageAfterNode(anchorId, '/img.jpg');

    expect(
      container.read(createEditorProvider).articleDocument.nodes.any(
        (n) => n.id == figId,
      ),
      isTrue,
    );

    notifier.removeArticleNode(figId);
    expect(
      container.read(createEditorProvider).articleDocument.nodes.any(
        (n) => n.id == figId,
      ),
      isFalse,
    );
  });

  test('replaceArticleNodeImage 替换图片路径', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    notifier.setEditorKind(CreateEditorKind.text);
    notifier.updateTitle('测试');

    final doc = container.read(createEditorProvider).articleDocument;
    final anchorId = doc.nodes.first.id;
    final figId = notifier.insertImageAfterNode(anchorId, '/old.jpg');

    notifier.replaceArticleNodeImage(figId, '/new.jpg');
    final updated = container.read(createEditorProvider).articleDocument;
    final fig = updated.nodes.firstWhere((n) => n.id == figId);
    expect(fig.imageUrl, '/new.jpg');
  });

  test('updateArticleNodeType 段落切换为 H2 再切回段落', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    notifier.setEditorKind(CreateEditorKind.text);
    notifier.updateTitle('测试');

    final doc = container.read(createEditorProvider).articleDocument;
    final anchorId = doc.nodes.first.id;
    final paraId = notifier.insertTextNodeAfter(anchorId, initialText: '正文');

    // 切换为 headingMajor
    notifier.updateArticleNodeType(paraId, ArticleDocumentNodeType.headingMajor);
    final state1 = container.read(createEditorProvider);
    // 类型切换会生成新 id
    final h2Node = state1.articleDocument.nodes.firstWhere(
      (n) => n.type == ArticleDocumentNodeType.headingMajor && n.text == '正文',
    );
    expect(h2Node.text, '正文');

    // 切回段落
    notifier.updateArticleNodeType(
      h2Node.id,
      ArticleDocumentNodeType.paragraph,
    );
    final state2 = container.read(createEditorProvider);
    final paraNode = state2.articleDocument.nodes.firstWhere(
      (n) => n.text == '正文',
    );
    expect(paraNode.type, ArticleDocumentNodeType.paragraph);
  });

  test('updateArticleNodeType 对 figure 和 title 无效', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    notifier.setEditorKind(CreateEditorKind.text);
    notifier.updateTitle('测试');

    final doc = container.read(createEditorProvider).articleDocument;
    final anchorId = doc.nodes.first.id;
    final figId = notifier.insertImageAfterNode(anchorId, '/img.jpg');

    // 对 figure 调用应无效
    notifier.updateArticleNodeType(figId, ArticleDocumentNodeType.headingMajor);
    final updated = container.read(createEditorProvider).articleDocument;
    final fig = updated.nodes.firstWhere((n) => n.id == figId);
    expect(fig.type, ArticleDocumentNodeType.figure);

    // 对 title 调用应无效
    final titleNode = updated.nodes.firstWhere((n) => n.isDocumentTitle);
    notifier.updateArticleNodeType(
      titleNode.id,
      ArticleDocumentNodeType.headingMajor,
    );
    final updated2 = container.read(createEditorProvider).articleDocument;
    expect(
      updated2.nodes.firstWhere((n) => n.id == titleNode.id).isDocumentTitle,
      isTrue,
    );
  });

  test('toggleArticleInlineStyle 在范围内添加粗体', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    notifier.setEditorKind(CreateEditorKind.text);
    notifier.updateTitle('测试');

    final doc = container.read(createEditorProvider).articleDocument;
    final anchorId = doc.nodes.first.id;
    final paraId = notifier.insertTextNodeAfter(
      anchorId,
      initialText: 'Hello World',
    );

    // 给 [0, 5) 加粗
    notifier.toggleArticleInlineStyle(paraId, 0, 5, bold: true);
    final updated = container.read(createEditorProvider).articleDocument;
    final node = updated.nodes.firstWhere((n) => n.id == paraId);
    expect(node.spans.length, 1);
    expect(node.spans.first.start, 0);
    expect(node.spans.first.end, 5);
    expect(node.spans.first.bold, isTrue);
    expect(node.spans.first.italic, isFalse);
  });

  test('toggleArticleInlineStyle 关闭已有粗体', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    notifier.setEditorKind(CreateEditorKind.text);
    notifier.updateTitle('测试');

    final doc = container.read(createEditorProvider).articleDocument;
    final anchorId = doc.nodes.first.id;
    final paraId = notifier.insertTextNodeAfter(
      anchorId,
      initialText: 'Hello World',
    );

    // 先加粗
    notifier.toggleArticleInlineStyle(paraId, 0, 5, bold: true);
    // 再关闭
    notifier.toggleArticleInlineStyle(paraId, 0, 5, bold: false);
    final updated = container.read(createEditorProvider).articleDocument;
    final node = updated.nodes.firstWhere((n) => n.id == paraId);
    expect(node.spans.isEmpty, isTrue);
  });

  test('toggleArticleInlineStyle 部分重叠合并', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    notifier.setEditorKind(CreateEditorKind.text);
    notifier.updateTitle('测试');

    final doc = container.read(createEditorProvider).articleDocument;
    final anchorId = doc.nodes.first.id;
    final paraId = notifier.insertTextNodeAfter(
      anchorId,
      initialText: 'Hello World',
    );

    // [0, 5) 加粗
    notifier.toggleArticleInlineStyle(paraId, 0, 5, bold: true);
    // [3, 8) 加斜体
    notifier.toggleArticleInlineStyle(paraId, 3, 8, italic: true);

    final updated = container.read(createEditorProvider).articleDocument;
    final node = updated.nodes.firstWhere((n) => n.id == paraId);
    // 应有 3 个 span: [0,3) bold, [3,5) bold+italic, [5,8) italic
    expect(node.spans.length, 3);
    expect(node.spans[0].start, 0);
    expect(node.spans[0].end, 3);
    expect(node.spans[0].bold, isTrue);
    expect(node.spans[0].italic, isFalse);
    expect(node.spans[1].start, 3);
    expect(node.spans[1].end, 5);
    expect(node.spans[1].bold, isTrue);
    expect(node.spans[1].italic, isTrue);
    expect(node.spans[2].start, 5);
    expect(node.spans[2].end, 8);
    expect(node.spans[2].bold, isFalse);
    expect(node.spans[2].italic, isTrue);
  });

  test('commitArticleTextEdit 记录 undo 点使文本可撤销', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    notifier.setEditorKind(CreateEditorKind.text);
    notifier.updateTitle('测试');

    final doc = container.read(createEditorProvider).articleDocument;
    final anchorId = doc.nodes.first.id;
    final paraId = notifier.insertTextNodeAfter(anchorId, initialText: 'ABC');

    // 验证初始状态
    expect(
      container.read(createEditorProvider).articleDocument.nodes
          .firstWhere((n) => n.id == paraId)
          .text,
      'ABC',
    );

    // 手动提交 undo 点（记录当前 'ABC' 状态）
    notifier.commitArticleTextEdit();

    // 继续输入（不记录 undo）
    notifier.updateArticleNodeText(paraId, 'ABCDE');
    expect(
      container.read(createEditorProvider).articleDocument.nodes
          .firstWhere((n) => n.id == paraId)
          .text,
      'ABCDE',
    );

    // undo — 应回到 'ABC'
    notifier.undoArticle();
    final stateAfterUndo = container.read(createEditorProvider);
    final nodeAfterUndo = stateAfterUndo.articleDocument.nodes.firstWhere(
      (n) => n.id == paraId,
      orElse: () => const ArticleDocumentNode(
        id: '',
        type: ArticleDocumentNodeType.paragraph,
      ),
    );
    expect(nodeAfterUndo.text, 'ABC');
  });

  // ── undo/redo 对结构变更的覆盖 ──

  test('undo/redo 对插图操作可撤销', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    notifier.setEditorKind(CreateEditorKind.text);
    notifier.updateTitle('测试');

    final doc = container.read(createEditorProvider).articleDocument;
    final anchorId = doc.nodes.first.id;
    final nodeCountBefore = doc.nodes.length;

    final figId = notifier.insertImageAfterNode(anchorId, '/img.jpg');
    expect(
      container.read(createEditorProvider).articleDocument.nodes.length,
      nodeCountBefore + 1,
    );

    notifier.undoArticle();
    expect(
      container.read(createEditorProvider).articleDocument.nodes.length,
      nodeCountBefore,
    );

    notifier.redoArticle();
    expect(
      container.read(createEditorProvider).articleDocument.nodes.any(
        (n) => n.isFigure && n.id == figId && n.imageUrl == '/img.jpg',
      ),
      isTrue,
    );
  });

  test('undo/redo 对删除节点可撤销', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    notifier.setEditorKind(CreateEditorKind.text);
    notifier.updateTitle('测试');

    final doc = container.read(createEditorProvider).articleDocument;
    final anchorId = doc.nodes.first.id;
    final figId = notifier.insertImageAfterNode(anchorId, '/img.jpg');

    notifier.removeArticleNode(figId);
    expect(
      container.read(createEditorProvider).articleDocument.nodes.any(
        (n) => n.id == figId,
      ),
      isFalse,
    );

    notifier.undoArticle();
    expect(
      container.read(createEditorProvider).articleDocument.nodes.any(
        (n) => n.id == figId,
      ),
      isTrue,
    );
  });

  test('undo/redo 对布局切换可撤销', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    notifier.setEditorKind(CreateEditorKind.text);
    notifier.updateTitle('测试');

    final doc = container.read(createEditorProvider).articleDocument;
    final anchorId = doc.nodes.first.id;
    final figId = notifier.insertImageAfterNode(anchorId, '/img.jpg');

    notifier.updateArticleNodeImageLayout(figId, 'wrapLeft');
    expect(
      container.read(createEditorProvider).articleDocument.nodes
          .firstWhere((n) => n.id == figId)
          .imageLayout,
      'wrapLeft',
    );

    notifier.undoArticle();
    expect(
      container.read(createEditorProvider).articleDocument.nodes
          .firstWhere((n) => n.id == figId)
          .imageLayout,
      'fullWidth',
    );
  });

  test('undo/redo 对节点类型切换可撤销', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    notifier.setEditorKind(CreateEditorKind.text);
    notifier.updateTitle('测试');

    final doc = container.read(createEditorProvider).articleDocument;
    final anchorId = doc.nodes.first.id;
    final paraId = notifier.insertTextNodeAfter(anchorId, initialText: '正文');

    notifier.updateArticleNodeType(paraId, ArticleDocumentNodeType.headingMajor);
    final h2Node = container.read(createEditorProvider).articleDocument.nodes
        .firstWhere((n) => n.text == '正文');
    expect(h2Node.type, ArticleDocumentNodeType.headingMajor);

    notifier.undoArticle();
    final restored = container.read(createEditorProvider).articleDocument.nodes
        .firstWhere((n) => n.id == paraId);
    expect(restored.type, ArticleDocumentNodeType.paragraph);
  });

  test('undo/redo 对行内样式可撤销', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final notifier = container.read(createEditorProvider.notifier);
    notifier.setEditorKind(CreateEditorKind.text);
    notifier.updateTitle('测试');

    final doc = container.read(createEditorProvider).articleDocument;
    final anchorId = doc.nodes.first.id;
    final paraId = notifier.insertTextNodeAfter(
      anchorId,
      initialText: 'Hello World',
    );

    notifier.toggleArticleInlineStyle(paraId, 0, 5, bold: true);
    expect(
      container.read(createEditorProvider).articleDocument.nodes
          .firstWhere((n) => n.id == paraId)
          .spans
          .isNotEmpty,
      isTrue,
    );

    notifier.undoArticle();
    expect(
      container.read(createEditorProvider).articleDocument.nodes
          .firstWhere((n) => n.id == paraId)
          .spans
          .isEmpty,
      isTrue,
    );

    notifier.redoArticle();
    expect(
      container.read(createEditorProvider).articleDocument.nodes
          .firstWhere((n) => n.id == paraId)
          .spans
          .isNotEmpty,
      isTrue,
    );
  });
}
