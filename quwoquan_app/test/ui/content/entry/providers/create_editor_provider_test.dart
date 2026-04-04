import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/ui/content/article_document_models.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
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
}
