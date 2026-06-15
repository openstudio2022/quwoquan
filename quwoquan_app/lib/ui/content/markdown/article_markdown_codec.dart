import 'package:quwoquan_app/core/media/asset_url_resolver.dart';
import 'package:quwoquan_app/core/media/content_media_url.dart';
import 'package:quwoquan_app/ui/content/article_document_models.dart';
import 'package:quwoquan_app/ui/content/markdown/qwq_markdown_ast.dart';
import 'package:quwoquan_app/ui/content/markdown/qwq_markdown_parser.dart';

/// Markdown <-> 编辑器文档的统一转换层。
///
/// 云端与数据工程以 QWQ Rich Markdown 作为跨边界真相源；编辑器内部仍使用
/// [ArticleDocumentData.nodes] 承载交互态结构。本文件负责唯一转换，避免各入口
/// 各自从 title/body/cards 拼第二套长文。
class ArticleMarkdownCodec {
  const ArticleMarkdownCodec._();

  static String serializeDocument(
    ArticleDocumentData document, {
    String summary = '',
    List<String> tagRefs = const <String>[],
    List<String> entityRefs = const <String>[],
    String visibility = '',
    String assistantUsePolicy = '',
    String coverAssetId = '',
    String coverImageUrl = '',
  }) {
    final buffer = StringBuffer()
      ..writeln('---')
      ..writeln('title: ${_frontMatterScalar(document.title)}');
    if (summary.trim().isNotEmpty) {
      buffer.writeln('summary: ${_frontMatterScalar(summary.trim())}');
    }
    buffer
      ..writeln('template: ${document.template}')
      ..writeln('fontPreset: ${document.fontPreset}')
      ..writeln('titleStyle: ${document.titleStyle.name}')
      ..writeln('articleMarkdownVersion: $qwqRichMarkdownVersion');
    if (coverAssetId.trim().isNotEmpty) {
      buffer.writeln('coverImage: asset://${coverAssetId.trim()}');
    }
    _writeFrontMatterStringList(buffer, 'tag_refs', tagRefs);
    _writeFrontMatterStringList(buffer, 'entity_refs', entityRefs);
    if (visibility.trim().isNotEmpty) {
      buffer.writeln('visibility: ${visibility.trim()}');
    }
    if (assistantUsePolicy.trim().isNotEmpty) {
      buffer.writeln('assistantUsePolicy: ${assistantUsePolicy.trim()}');
    }
    buffer
      ..writeln('---')
      ..writeln();

    final title = document.title.trim();
    if (title.isNotEmpty &&
        document.titleStyle != ArticleDocumentTitleStyle.none) {
      buffer
        ..write('# ')
        ..writeln(title)
        ..writeln();
    }

    final coverPath = coverImageUrl.trim();
    final hasCoverInDocument =
        coverPath.isNotEmpty &&
        document.nodes.any(
          (node) => node.isFigure && node.imageUrl.trim() == coverPath,
        );
    if (coverPath.isNotEmpty &&
        coverAssetId.trim().isNotEmpty &&
        !hasCoverInDocument) {
      _writeFigure(
        buffer,
        assetId: coverAssetId.trim(),
        layout: 'fullWidth',
        caption: '',
      );
    }

    var orderedIndex = 0;
    for (final node in document.nodes) {
      if (node.isDocumentTitle) {
        continue;
      }
      switch (node.type) {
        case ArticleDocumentNodeType.documentTitle:
          break;
        case ArticleDocumentNodeType.headingMajor:
          orderedIndex = 0;
          _writeTextBlock(buffer, '##', node.text, spans: node.spans);
          break;
        case ArticleDocumentNodeType.headingMinor:
          orderedIndex = 0;
          _writeTextBlock(buffer, '###', node.text, spans: node.spans);
          break;
        case ArticleDocumentNodeType.paragraph:
          orderedIndex = 0;
          _writeParagraph(buffer, node.text, spans: node.spans);
          break;
        case ArticleDocumentNodeType.orderedItem:
          orderedIndex += 1;
          if (node.text.trim().isNotEmpty) {
            buffer
              ..write('$orderedIndex. ')
              ..writeln(_serializeInlineText(node.text.trim(), node.spans))
              ..writeln();
          }
          break;
        case ArticleDocumentNodeType.bulletItem:
          orderedIndex = 0;
          if (node.text.trim().isNotEmpty) {
            buffer
              ..write('- ')
              ..writeln(_serializeInlineText(node.text.trim(), node.spans))
              ..writeln();
          }
          break;
        case ArticleDocumentNodeType.figure:
          orderedIndex = 0;
          final assetId = _assetIdForNode(node);
          if (assetId.isNotEmpty) {
            _writeFigure(
              buffer,
              assetId: assetId,
              layout: node.imageLayout,
              caption: node.caption,
            );
          }
          break;
      }
    }

    return buffer.toString().trimRight();
  }

  static ArticleDocumentData parseDocument(
    String markdown, {
    Map<String, dynamic>? assetManifest,
  }) {
    final parsed = const QwqMarkdownParser().parse(markdown).document;
    final mediaAssetsById = resolveArticleAssetManifestVariants(assetManifest);
    final assetsById = mediaAssetsById.map(
      (assetId, variants) =>
          MapEntry(assetId, variants.urlFor(MediaAssetVariantProfile.display)),
    )..removeWhere((_, url) => url.isEmpty);
    final nodes = <ArticleDocumentNode>[];
    final title = parsed.frontMatter.title.trim();
    if (title.isNotEmpty) {
      nodes.add(
        ArticleDocumentNode(
          id: 'document_title',
          type: ArticleDocumentNodeType.documentTitle,
          text: title,
        ),
      );
    }

    var seed = 0;
    for (final block in parsed.blocks) {
      switch (block.kind) {
        case QwqMarkdownBlockKind.heading:
          final inline = _parseEntityInlineText(block.text);
          final text = inline.text.trim();
          if (block.level <= 1 && text == title) {
            break;
          }
          nodes.add(
            ArticleDocumentNode(
              id: block.id.isNotEmpty ? block.id : 'heading_${seed++}',
              type: block.level >= 3
                  ? ArticleDocumentNodeType.headingMinor
                  : ArticleDocumentNodeType.headingMajor,
              text: inline.text,
              spans: inline.spans,
            ),
          );
          break;
        case QwqMarkdownBlockKind.paragraph:
        case QwqMarkdownBlockKind.quote:
        case QwqMarkdownBlockKind.callout:
        case QwqMarkdownBlockKind.card:
          final inline = _parseEntityInlineText(block.text);
          if (inline.text.trim().isNotEmpty) {
            nodes.add(
              ArticleDocumentNode(
                id: block.id.isNotEmpty ? block.id : 'paragraph_${seed++}',
                type: ArticleDocumentNodeType.paragraph,
                text: inline.text,
                spans: inline.spans,
              ),
            );
          }
          break;
        case QwqMarkdownBlockKind.orderedItem:
          final inline = _parseEntityInlineText(block.text);
          nodes.add(
            ArticleDocumentNode(
              id: block.id.isNotEmpty ? block.id : 'ordered_${seed++}',
              type: ArticleDocumentNodeType.orderedItem,
              text: inline.text,
              spans: inline.spans,
            ),
          );
          break;
        case QwqMarkdownBlockKind.bulletItem:
          final inline = _parseEntityInlineText(block.text);
          nodes.add(
            ArticleDocumentNode(
              id: block.id.isNotEmpty ? block.id : 'bullet_${seed++}',
              type: ArticleDocumentNodeType.bulletItem,
              text: inline.text,
              spans: inline.spans,
            ),
          );
          break;
        case QwqMarkdownBlockKind.image:
        case QwqMarkdownBlockKind.figure:
          final ref = block.assetRef;
          if (ref != null) {
            nodes.add(_figureNodeFromAssetRef(ref, block.id, assetsById));
          }
          break;
        case QwqMarkdownBlockKind.gallery:
          for (final ref in block.assetRefs) {
            nodes.add(_figureNodeFromAssetRef(ref, block.id, assetsById));
          }
          break;
        case QwqMarkdownBlockKind.section:
        case QwqMarkdownBlockKind.codeBlock:
        case QwqMarkdownBlockKind.spacer:
        case QwqMarkdownBlockKind.horizontalRule:
          break;
      }
    }

    final coverAssetId = parsed.frontMatter.coverAssetId.isNotEmpty
        ? parsed.frontMatter.coverAssetId
        : _assetIdFromUri(parsed.frontMatter.coverImage);
    final coverImageUrl =
        mediaAssetsById[coverAssetId]?.urlFor(MediaAssetVariantProfile.cover) ??
        assetsById[coverAssetId] ??
        resolveContentMediaUrl(parsed.frontMatter.coverImage);

    return ArticleDocumentData(
      nodes: nodes,
      template: parsed.frontMatter.template.isNotEmpty
          ? parsed.frontMatter.template
          : 'gentle',
      fontPreset: parsed.frontMatter.fontPreset.isNotEmpty
          ? parsed.frontMatter.fontPreset
          : 'clean',
      coverImageUrl: coverImageUrl,
      titleStyle: ArticleDocumentTitleStyle.values.firstWhere(
        (style) => style.name == parsed.frontMatter.titleStyle,
        orElse: () => ArticleDocumentTitleStyle.major,
      ),
    );
  }

  static _EntityInlineParseResult _parseEntityInlineText(String source) {
    final pattern = RegExp(r'@\[(.+?)\]\(entity:([A-Za-z0-9_:/-]+)\)');
    final buffer = StringBuffer();
    final spans = <ArticleInlineSpan>[];
    var cursor = 0;
    for (final match in pattern.allMatches(source)) {
      buffer.write(source.substring(cursor, match.start));
      final label = match.group(1) ?? '';
      final target = match.group(2) ?? '';
      final targetId = target.startsWith('entity:') ? target : 'entity:$target';
      final targetType = 'entity';
      final start = buffer.length;
      buffer.write(label);
      final end = buffer.length;
      if (label.isNotEmpty && targetType.isNotEmpty && targetId.isNotEmpty) {
        spans.add(
          ArticleInlineSpan(
            start: start,
            end: end,
            kind: 'entity',
            targetType: targetType,
            targetId: targetId,
            displayText: label,
          ),
        );
      }
      cursor = match.end;
    }
    if (cursor == 0) {
      return _EntityInlineParseResult(text: source, spans: const []);
    }
    buffer.write(source.substring(cursor));
    return _EntityInlineParseResult(text: buffer.toString(), spans: spans);
  }

  static Map<String, String> resolveArticleAssetManifestUrls(
    Map<String, dynamic>? manifest,
  ) {
    return const AssetUrlResolver().resolveManifestUrls(
      manifest?.cast<String, Object?>(),
    );
  }

  static Map<String, MediaAssetVariants> resolveArticleAssetManifestVariants(
    Map<String, dynamic>? manifest,
  ) {
    return const AssetUrlResolver().resolveManifestVariants(
      manifest?.cast<String, Object?>(),
    );
  }

  static ArticleDocumentNode _figureNodeFromAssetRef(
    QwqMarkdownAssetRef ref,
    String blockId,
    Map<String, String> assetsById,
  ) {
    final assetId = ref.assetId.trim();
    return ArticleDocumentNode(
      id: blockId.isNotEmpty ? blockId : assetId,
      type: ArticleDocumentNodeType.figure,
      assetId: assetId,
      imageUrl: assetsById[assetId] ?? 'asset://$assetId',
      imageLayout: ref.layout.name,
      caption: ref.caption,
    );
  }

  static String _assetIdForNode(ArticleDocumentNode node) {
    final explicit = node.assetId.trim();
    if (explicit.isNotEmpty) {
      return explicit;
    }
    final nodeId = node.id.trim();
    if (nodeId.isNotEmpty) {
      return nodeId;
    }
    return _assetIdFromUri(node.imageUrl);
  }

  static String _assetIdFromUri(String value) {
    final trimmed = value.trim();
    if (trimmed.startsWith('asset://')) {
      return trimmed.substring('asset://'.length);
    }
    return trimmed;
  }

  static void _writeTextBlock(
    StringBuffer buffer,
    String marker,
    String text, {
    List<ArticleInlineSpan> spans = const <ArticleInlineSpan>[],
  }) {
    final value = text.trim();
    if (value.isEmpty) {
      return;
    }
    buffer
      ..write('$marker ')
      ..writeln(_serializeInlineText(value, spans))
      ..writeln();
  }

  static void _writeParagraph(
    StringBuffer buffer,
    String text, {
    List<ArticleInlineSpan> spans = const <ArticleInlineSpan>[],
  }) {
    final value = text.trim();
    if (value.isEmpty) {
      return;
    }
    buffer
      ..writeln(_serializeInlineText(value, spans))
      ..writeln();
  }

  static String _serializeInlineText(
    String text,
    List<ArticleInlineSpan> spans,
  ) {
    final entitySpans = spans.where((span) => span.isEntity).toList()
      ..sort((a, b) => a.start.compareTo(b.start));
    if (entitySpans.isEmpty) return text;
    final buffer = StringBuffer();
    var cursor = 0;
    for (final span in entitySpans) {
      final start = span.start.clamp(0, text.length);
      final end = span.end.clamp(start, text.length);
      if (start < cursor) continue;
      buffer.write(text.substring(cursor, start));
      final label = (span.displayText ?? text.substring(start, end)).trim();
      final targetId = span.targetId?.trim() ?? '';
      if (label.isEmpty || targetId.isEmpty) {
        buffer.write(text.substring(start, end));
      } else {
        final wireTarget = targetId.startsWith('entity:')
            ? targetId.substring('entity:'.length)
            : targetId;
        if (wireTarget.isEmpty) {
          buffer.write(text.substring(start, end));
        } else {
          buffer.write('@[$label](entity:$wireTarget)');
        }
      }
      cursor = end;
    }
    buffer.write(text.substring(cursor));
    return buffer.toString();
  }

  static void _writeFigure(
    StringBuffer buffer, {
    required String assetId,
    required String layout,
    required String caption,
  }) {
    buffer
      ..writeln(
        ':::figure id="$assetId" layout="${_canonicalLayout(layout)}" caption="${_escapeAttribute(caption.trim())}"',
      )
      ..writeln('asset://$assetId')
      ..writeln(':::')
      ..writeln();
  }

  static String _canonicalLayout(String value) {
    return switch (value.trim()) {
      'wrapLeft' => 'wrapLeft',
      'wrapRight' => 'wrapRight',
      _ => 'fullWidth',
    };
  }

  static String _frontMatterScalar(String value) {
    final escaped = value.replaceAll('"', '\\"');
    return '"$escaped"';
  }

  static void _writeFrontMatterStringList(
    StringBuffer buffer,
    String key,
    List<String> values,
  ) {
    final normalized = values
        .map((value) => value.trim())
        .where((value) => value.isNotEmpty)
        .toSet()
        .toList(growable: false);
    if (normalized.isEmpty) return;
    buffer.writeln('$key:');
    for (final value in normalized) {
      buffer.writeln('  - ${_frontMatterScalar(value)}');
    }
  }

  static String _escapeAttribute(String value) {
    return value.replaceAll('"', '\\"');
  }
}

class _EntityInlineParseResult {
  const _EntityInlineParseResult({required this.text, required this.spans});

  final String text;
  final List<ArticleInlineSpan> spans;
}
