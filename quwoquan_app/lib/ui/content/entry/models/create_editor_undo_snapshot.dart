import 'package:quwoquan_app/ui/content/article_document_models.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';

/// 文章编辑撤销点（与 [CreateEditorState] 中文章相关字段一致，用于 undo/redo）。
abstract final class CreateEditorUndoSnapshot {
  static const int maxStack = 25;

  static Map<String, dynamic> serialize(CreateEditorState state) {
    return <String, dynamic>{
      'title': state.title,
      'body': state.body,
      'articleDocument': state.articleDocument.toMap(),
      'articlePages': state.articlePages
          .map((page) => page.toMap())
          .toList(growable: false),
      'articleBlocks': state.articleBlocks
          .map((block) => block.toMap())
          .toList(growable: false),
      'activeArticlePageId': state.activeArticlePageId,
      'activeArticleBlockId': state.activeArticleBlockId,
      'articleTemplate': state.articleTemplate.name,
      'articleFontPreset': state.articleFontPreset.name,
      'articleCoverImagePath': state.articleCoverImagePath,
      'imagePaths': List<String>.from(state.imagePaths),
      'titlePresentation': state.titlePresentation.name,
      'titleHintDismissed': state.titleHintDismissed,
    };
  }

  static CreateEditorState deserialize(
    CreateEditorState base,
    Map<String, dynamic> map,
  ) {
    final docRaw = map['articleDocument'];
    final document = docRaw is Map
        ? ArticleDocumentData.fromMap(Map<String, dynamic>.from(docRaw))
        : base.articleDocument;
    final pages = buildArticlePagesSnapshotFromDocument(
      document,
      fontPreset: articleFontPresetFromString(map['articleFontPreset']?.toString()),
    );
    final blocksRaw = map['articleBlocks'];
    final blocks = blocksRaw is List
        ? blocksRaw
              .whereType<Map>()
              .map(
                (e) => CreateTextBlock.fromMap(Map<String, dynamic>.from(e)),
              )
              .toList(growable: false)
        : buildArticleBlocksFromDocument(document);
    final activePageId = (map['activeArticlePageId'] as String?)?.trim();
    final activeBlockId = (map['activeArticleBlockId'] as String?)?.trim();
    final template = articleTemplatePresetFromString(
      map['articleTemplate']?.toString(),
    );
    final font = articleFontPresetFromString(map['articleFontPreset']?.toString());
    final pathsRaw = map['imagePaths'];
    final imagePaths = pathsRaw is List
        ? pathsRaw.map((e) => e.toString()).toList(growable: false)
        : base.imagePaths;
    final cover = (map['articleCoverImagePath'] ?? '').toString();
    final tp =
        (map['titlePresentation']?.toString() ?? 'collapsed') == 'expanded'
        ? TitlePresentation.expanded
        : TitlePresentation.collapsed;
    return base.copyWith(
      title: (map['title'] ?? '').toString(),
      body: (map['body'] ?? '').toString(),
      articleDocument: document,
      articlePages: pages.isNotEmpty ? pages : base.articlePages,
      articleBlocks: blocks.isNotEmpty ? blocks : base.articleBlocks,
      activeArticlePageId: activePageId != null && activePageId.isNotEmpty
          ? activePageId
          : base.activeArticlePageId,
      activeArticleBlockId: activeBlockId != null && activeBlockId.isNotEmpty
          ? activeBlockId
          : base.activeArticleBlockId,
      articleTemplate: template,
      articleFontPreset: font,
      articleCoverImagePath: cover,
      imagePaths: imagePaths,
      titlePresentation: tp,
      titleHintDismissed: map['titleHintDismissed'] == true,
    );
  }
}
