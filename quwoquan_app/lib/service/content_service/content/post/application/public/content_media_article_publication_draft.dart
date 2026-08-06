import 'package:quwoquan_app/service/content_service/content/post/application/public/article_document_models.dart';

/// Media Upload 消费文章发布草稿时所需的最小稳定投影。
final class ContentMediaArticlePublicationDraft {
  const ContentMediaArticlePublicationDraft({
    required this.document,
    required this.imagePaths,
    required this.coverImagePath,
    required this.template,
    required this.fontPreset,
    required this.markdownDialect,
    required this.isPublic,
    required this.assistantUsePolicy,
  });

  final ArticleDocumentData document;
  final List<String> imagePaths;
  final String coverImagePath;
  final String template;
  final String fontPreset;
  final String markdownDialect;
  final bool isPublic;
  final String assistantUsePolicy;
}

typedef ContentMediaArticleMarkdownEncoder =
    String Function({
      required ArticleDocumentData document,
      required String summary,
      required List<String> tagRefs,
      required List<String> entityRefs,
      required String visibility,
      required String assistantUsePolicy,
      required String coverAssetId,
      required String coverImageUrl,
    });
