import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/ui/content/article_document_models.dart';
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
}
