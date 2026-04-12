import 'package:quwoquan_app/ui/content/article_document_models.dart';

/// 文章 `articleDocument` wire 根对象（与 SSOT
/// `quwoquan_service/contracts/metadata/content/post/article_document_schema.yaml` 对齐）。
///
/// 节点多态在协议层未完全锁死前，[nodes] 保留 JSON 边界类型；编辑器侧统一经
/// [toArticleDocumentData] 进入 [ArticleDocumentData]。
class ArticleDocumentWireDto {
  const ArticleDocumentWireDto({
    required this.nodes,
    this.template,
    this.fontPreset,
    this.coverImageUrl,
    this.titleStyle,
  });

  final List<Map<String, dynamic>> nodes;
  final String? template;
  final String? fontPreset;
  final String? coverImageUrl;
  final String? titleStyle;

  factory ArticleDocumentWireDto.fromMap(Map<String, dynamic> m) {
    final rawNodes =
        (m['nodes'] as List?) ?? (m['blocks'] as List?) ?? const <Object?>[];
    final nodes = rawNodes
        .whereType<Map>()
        .map((e) => Map<String, dynamic>.from(e))
        .toList(growable: false);
    return ArticleDocumentWireDto(
      nodes: nodes,
      template: m['template']?.toString(),
      fontPreset: m['fontPreset']?.toString(),
      coverImageUrl: m['coverImageUrl']?.toString(),
      titleStyle: m['titleStyle']?.toString(),
    );
  }

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      if (template != null && template!.isNotEmpty) 'template': template,
      if (fontPreset != null && fontPreset!.isNotEmpty) 'fontPreset': fontPreset,
      if (coverImageUrl != null && coverImageUrl!.isNotEmpty)
        'coverImageUrl': coverImageUrl,
      if (titleStyle != null && titleStyle!.isNotEmpty) 'titleStyle': titleStyle,
      'nodes': nodes,
    };
  }

  /// 进入编辑器/阅读器统一模型（兼容 legacy title/body/blocks 字段由 [ArticleDocumentData.fromMap] 处理）。
  ArticleDocumentData toArticleDocumentData() =>
      ArticleDocumentData.fromMap(toMap());
}
