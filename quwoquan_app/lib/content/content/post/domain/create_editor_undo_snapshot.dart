import 'package:quwoquan_app/content/content/post/domain/article_document_models.dart';
import 'package:quwoquan_app/content/content/post/domain/article_presentation_models.dart';
import 'package:quwoquan_app/content/content/post/domain/create_editor_models.dart';

/// 文章编辑撤销点（与 [CreateEditorState] 中文章相关字段一致，用于 undo/redo）。
abstract final class CreateEditorUndoSnapshot {
  static const int maxStack = 25;

  static Map<String, dynamic> serialize(CreateEditorState state) {
    return <String, dynamic>{
      'articleDocument': state.articleDocument.toMap(),
      'activeArticlePageId': state.activeArticlePageId,
      'activeArticleBlockId': state.activeArticleBlockId,
      'articleTemplate': state.articleTemplate.name,
      'articleFontPreset': state.articleFontPreset.name,
      'articleCoverImagePath': state.articleCoverImagePath,
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
      fontPreset: articleFontPresetFromString(
        map['articleFontPreset']?.toString(),
      ),
    );
    final activePageId = (map['activeArticlePageId'] as String?)?.trim();
    final activeBlockId = (map['activeArticleBlockId'] as String?)?.trim();
    final template = articleTemplatePresetFromString(
      map['articleTemplate']?.toString(),
    );
    final font = articleFontPresetFromString(
      map['articleFontPreset']?.toString(),
    );
    final imagePaths = extractArticleImagePathsFromDocument(document);
    final cover = (map['articleCoverImagePath'] ?? '').toString();
    final tp =
        (map['titlePresentation']?.toString() ?? 'collapsed') == 'expanded'
        ? TitlePresentation.expanded
        : TitlePresentation.collapsed;
    return base.copyWith(
      title: document.title,
      body: buildArticlePlainTextFromDocument(document),
      articleDocument: document,
      articlePages: pages.isNotEmpty ? pages : base.articlePages,
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
