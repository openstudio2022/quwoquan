import 'package:quwoquan_app/service/content_service/content/post/generated/semantic_document.g.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/public/media_asset_manifest_resolver.dart';
import 'package:quwoquan_app/runtime/transport/media/content_media_url.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_document_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/qwq_markdown_ast.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/qwq_markdown_parser.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show AssistantUsePolicy;

const MediaAssetManifestResolver _articleAssetManifestResolver =
    MediaAssetManifestResolver(resolveReference: _resolveArticleMediaReference);

/// Markdown <-> 编辑器文档的统一转换层。
///
/// 云端与数据工程以 QWQ Rich Markdown 作为跨边界真相源；编辑器内部仍使用
/// [ArticleDocumentData.nodes] 承载交互态结构。本文件负责唯一转换，避免各入口
/// 各自从 title/body/cards 拼第二套长文。
class _ReadOnlyOriginEntry {
  const _ReadOnlyOriginEntry({
    required this.nodeId,
    required this.ordinal,
    required this.rawMarkdown,
    required this.semanticType,
    required this.fingerprint,
  });
  final String nodeId;
  final int ordinal;
  final String rawMarkdown;
  final String semanticType;
  final String fingerprint;
}

class _MarkdownOriginAuthority {
  const _MarkdownOriginAuthority(this.entries);
  final List<_ReadOnlyOriginEntry> entries;
}

class ArticleMarkdownCodec {
  const ArticleMarkdownCodec._();

  static String serializeDocument(
    ArticleDocumentData document, {
    String summary = '',
    List<String> tagRefs = const <String>[],
    List<String> entityRefs = const <String>[],
    String visibility = '',
    AssistantUsePolicy? assistantUsePolicy,
    String coverAssetId = '',
    String coverImageUrl = '',
  }) {
    _validateReadOnlyNodes(document);
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
      ..writeln('markdownDialect: $qwqRichMarkdownVersion');
    if (coverAssetId.trim().isNotEmpty) {
      buffer.writeln('coverImage: asset://${coverAssetId.trim()}');
    }
    _writeFrontMatterStringList(buffer, 'tag_refs', tagRefs);
    _writeFrontMatterStringList(buffer, 'entity_refs', entityRefs);
    if (visibility.trim().isNotEmpty) {
      buffer.writeln('visibility: ${visibility.trim()}');
    }
    if (assistantUsePolicy != null) {
      buffer.writeln('assistantUsePolicy: ${assistantUsePolicy.wireName}');
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
      final origin = _originForNode(document, node.id);
      if (origin != null) {
        buffer
          ..writeln(origin.rawMarkdown.trimRight())
          ..writeln();
        continue;
      }
      switch (node.type) {
        case ArticleDocumentNodeType.documentTitle:
          break;
        case ArticleDocumentNodeType.headingMajor:
          orderedIndex = 0;
          _writeTextBlock(
            buffer,
            '#' *
                (node.headingLevel.clamp(1, 6) == 1
                    ? 1
                    : node.headingLevel.clamp(1, 6)),
            node.text,
            spans: node.spans,
          );
          break;
        case ArticleDocumentNodeType.headingMinor:
          orderedIndex = 0;
          _writeTextBlock(
            buffer,
            '#' *
                (node.headingLevel.clamp(1, 6) <= 2
                    ? 3
                    : node.headingLevel.clamp(1, 6)),
            node.text,
            spans: node.spans,
          );
          break;
        case ArticleDocumentNodeType.paragraph:
          orderedIndex = 0;
          if (node.textAlign == 'center' || node.textAlign == 'right') {
            // 段落对齐经 :::align 指令承载（GWT-004）。
            final value = node.text.trim();
            if (value.isNotEmpty) {
              buffer
                ..writeln(':::align value="${node.textAlign}"')
                ..writeln(_serializeInlineText(value, node.spans))
                ..writeln(':::')
                ..writeln();
            }
            break;
          }
          _writeParagraph(buffer, node.text, spans: node.spans);
          break;
        case ArticleDocumentNodeType.divider:
          orderedIndex = 0;
          buffer
            ..writeln('---')
            ..writeln();
          break;
        case ArticleDocumentNodeType.orderedItem:
          orderedIndex += 1;
          if (node.text.trim().isNotEmpty) {
            buffer
              ..write(_listIndent(node.listDepth))
              ..write('$orderedIndex. ')
              ..writeln(_serializeInlineText(node.text.trim(), node.spans))
              ..writeln();
          }
          break;
        case ArticleDocumentNodeType.bulletItem:
          orderedIndex = 0;
          if (node.text.trim().isNotEmpty) {
            buffer
              ..write(_listIndent(node.listDepth))
              ..write('- ')
              ..writeln(_serializeInlineText(node.text.trim(), node.spans))
              ..writeln();
          }
          break;
        case ArticleDocumentNodeType.quote:
          // 富块原样写回（GWT-003）：编辑器加载不降级、序列化不改写。
          orderedIndex = 0;
          if (node.text.trim().isNotEmpty) {
            for (final line in _serializeInlineText(
              node.text.trim(),
              node.spans,
            ).split('\n')) {
              buffer.writeln('> $line');
            }
            buffer.writeln();
          }
          break;
        case ArticleDocumentNodeType.callout:
          orderedIndex = 0;
          if (node.text.trim().isNotEmpty) {
            buffer
              ..writeln(':::callout')
              ..writeln(_serializeInlineText(node.text.trim(), node.spans))
              ..writeln(':::')
              ..writeln();
          }
          break;
        case ArticleDocumentNodeType.codeBlock:
          orderedIndex = 0;
          if (node.text.trim().isNotEmpty) {
            buffer
              ..writeln('```${node.codeLanguage.trim()}')
              ..writeln(node.text.trimRight())
              ..writeln('```')
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

  static _ReadOnlyOriginEntry? _originForNode(
    ArticleDocumentData document,
    String nodeId,
  ) {
    final authority = document.markdownOriginAuthority;
    if (authority is! _MarkdownOriginAuthority) return null;
    for (final origin in authority.entries) {
      if (origin.nodeId == nodeId) return origin;
    }
    return null;
  }

  static void _validateReadOnlyNodes(ArticleDocumentData document) {
    final authority = document.markdownOriginAuthority;
    if (authority != null && authority is! _MarkdownOriginAuthority) {
      throw const FormatException('不可信 DTO 试图注入 markdown origin authority。');
    }
    final baseline = authority is _MarkdownOriginAuthority
        ? authority.entries
        : const <_ReadOnlyOriginEntry>[];
    if (baseline.isEmpty) {
      if (document.nodes.any(
        (node) =>
            node.isReadOnly ||
            node.isRichBlock ||
            node.headingLevel > 3 ||
            node.rawMarkdown.isNotEmpty ||
            node.semanticType.isNotEmpty,
      )) {
        throw const FormatException(
          '不可信 DTO 无 canonical markdown origin baseline。',
        );
      }
      return;
    }
    final currentReadOnly = document.nodes
        .where((node) => _originForNode(document, node.id) != null)
        .toList(growable: false);
    if (currentReadOnly.length != baseline.length) {
      throw const FormatException('只读节点被删除或 identity 已改变。');
    }
    for (var index = 0; index < baseline.length; index++) {
      final origin = baseline[index];
      final node = currentReadOnly[index];
      if (origin.ordinal != index ||
          origin.nodeId != node.id ||
          !node.isReadOnly) {
        throw const FormatException('只读节点 identity/order 已改变。');
      }
      if (origin.semanticType == QwqMarkdownBlockKind.unsupported.name) {
        throw const FormatException('opaque unsupported 节点尚无安全 serializer。');
      }
      final expected = _readOnlyFingerprint(
        origin.nodeId,
        origin.semanticType,
        origin.rawMarkdown,
      );
      if (expected != origin.fingerprint || !_rawMatchesNode(node, origin)) {
        throw const FormatException('只读节点 raw/semantic fingerprint 已改变。');
      }
    }
  }

  static bool _rawMatchesNode(
    ArticleDocumentNode node,
    _ReadOnlyOriginEntry origin,
  ) {
    final wrapped =
        '---\nmarkdownDialect: $qwqRichMarkdownVersion\n---\n${origin.rawMarkdown}';
    final parsed = const QwqMarkdownParser()
        .parse(wrapped, requireVersion: true)
        .document;
    if (parsed.hasBlockingDiagnostics || parsed.blocks.length != 1) {
      return false;
    }
    final block = parsed.blocks.single;
    final semanticType = block.kind == QwqMarkdownBlockKind.heading
        ? 'heading${block.level}'
        : block.kind.name;
    if (semanticType != origin.semanticType ||
        block.text != node.text ||
        node.semanticType != origin.semanticType ||
        node.rawMarkdown != origin.rawMarkdown) {
      return false;
    }
    if (node.type == ArticleDocumentNodeType.codeBlock &&
        block.language != node.codeLanguage) {
      return false;
    }
    return true;
  }

  static String _readOnlyFingerprint(
    String id,
    String semanticType,
    String raw,
  ) {
    var hash = 0x811c9dc5;
    for (final unit in '$id\u0000$semanticType\u0000$raw'.codeUnits) {
      hash = ((hash ^ unit) * 0x01000193) & 0xffffffff;
    }
    return hash.toRadixString(16).padLeft(8, '0');
  }

  static QwqMarkdownDocument parseMarkdown(String markdown) =>
      const QwqMarkdownParser().parse(markdown, requireVersion: true).document;

  static ArticleDocumentData parseDocument(
    String markdown, {
    Map<String, Object?>? assetManifest,
    MediaAssetManifestResolver assetManifestResolver =
        _articleAssetManifestResolver,
    String Function(String raw)? mediaUrlResolver,
    List<String> restoredNodeIds = const <String>[],
  }) {
    final parsed = const QwqMarkdownParser()
        .parse(markdown, requireVersion: true)
        .document;
    if (parsed.hasBlockingDiagnostics) {
      final codes = parsed.diagnostics
          .where((item) => item.isBlocking)
          .map((item) => item.code)
          .join(',');
      throw FormatException('QWQ Rich Markdown 拒绝解析: $codes');
    }
    final mediaAssetsById = resolveArticleAssetManifestVariants(
      assetManifest,
      resolver: assetManifestResolver,
    );
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
    var readOnlyOrdinal = 0;
    final readOnlyBaseline = <_ReadOnlyOriginEntry>[];
    ArticleDocumentNode readOnlyNode(
      ArticleDocumentNode node,
      QwqMarkdownBlock block,
    ) {
      final raw = block.rawSource;
      final semanticType = block.kind == QwqMarkdownBlockKind.heading
          ? 'heading${block.level}'
          : block.kind.name;
      final ordinal = readOnlyOrdinal++;
      readOnlyBaseline.add(
        _ReadOnlyOriginEntry(
          nodeId: node.id,
          ordinal: ordinal,
          rawMarkdown: raw,
          semanticType: semanticType,
          fingerprint: _readOnlyFingerprint(node.id, semanticType, raw),
        ),
      );
      return node.copyWith(
        isReadOnly: true,
        rawMarkdown: raw,
        semanticType: semanticType,
      );
    }

    for (final block in parsed.blocks) {
      switch (block.kind) {
        case QwqMarkdownBlockKind.heading:
          final inline = _articleInlineFromBlock(block);
          final text = inline.text.trim();
          if (block.level <= 1 && text == title) {
            break;
          }
          final headingNode = ArticleDocumentNode(
            id: block.id.isNotEmpty ? block.id : 'heading_${seed++}',
            type: block.level >= 3
                ? ArticleDocumentNodeType.headingMinor
                : ArticleDocumentNodeType.headingMajor,
            text: inline.text,
            spans: inline.spans,
            headingLevel: block.level,
          );
          nodes.add(
            block.level > 3 ? readOnlyNode(headingNode, block) : headingNode,
          );
          break;
        case QwqMarkdownBlockKind.paragraph:
        case QwqMarkdownBlockKind.card:
          final inline = _articleInlineFromBlock(block);
          if (inline.text.trim().isNotEmpty) {
            nodes.add(
              ArticleDocumentNode(
                id: block.id.isNotEmpty ? block.id : 'paragraph_${seed++}',
                type: ArticleDocumentNodeType.paragraph,
                text: inline.text,
                textAlign: block.textAlign,
                spans: inline.spans,
              ),
            );
          }
          break;
        // 富块不做有损压缩（GWT-003）：quote/callout/codeBlock 保留块语义。
        case QwqMarkdownBlockKind.quote:
        case QwqMarkdownBlockKind.callout:
          final inline = _articleInlineFromBlock(block);
          if (inline.text.trim().isNotEmpty) {
            nodes.add(
              readOnlyNode(
                ArticleDocumentNode(
                  id: block.id.isNotEmpty ? block.id : 'rich_${seed++}',
                  type: block.kind == QwqMarkdownBlockKind.quote
                      ? ArticleDocumentNodeType.quote
                      : ArticleDocumentNodeType.callout,
                  text: inline.text,
                  spans: inline.spans,
                ),
                block,
              ),
            );
          }
          break;
        case QwqMarkdownBlockKind.codeBlock:
          if (block.text.trim().isNotEmpty) {
            nodes.add(
              readOnlyNode(
                ArticleDocumentNode(
                  id: block.id.isNotEmpty ? block.id : 'code_${seed++}',
                  type: ArticleDocumentNodeType.codeBlock,
                  text: block.text,
                  codeLanguage: block.language,
                ),
                block,
              ),
            );
          }
          break;
        case QwqMarkdownBlockKind.orderedItem:
          final inline = _articleInlineFromBlock(block);
          nodes.add(
            ArticleDocumentNode(
              id: block.id.isNotEmpty ? block.id : 'ordered_${seed++}',
              type: ArticleDocumentNodeType.orderedItem,
              text: inline.text,
              listDepth: block.listDepth,
              spans: inline.spans,
            ),
          );
          break;
        case QwqMarkdownBlockKind.bulletItem:
          final inline = _articleInlineFromBlock(block);
          nodes.add(
            ArticleDocumentNode(
              id: block.id.isNotEmpty ? block.id : 'bullet_${seed++}',
              type: ArticleDocumentNodeType.bulletItem,
              text: inline.text,
              listDepth: block.listDepth,
              spans: inline.spans,
            ),
          );
          break;
        case QwqMarkdownBlockKind.image:
        case QwqMarkdownBlockKind.figure:
          final ref = block.assetRef;
          if (ref != null) {
            nodes.add(
              _figureNodeFromAssetRef(
                ref,
                block.id,
                assetsById,
                mediaUrlResolver: mediaUrlResolver,
                mediaVariants: mediaAssetsById[ref.assetId.trim()],
              ),
            );
          }
          break;
        case QwqMarkdownBlockKind.gallery:
          for (final ref in block.assetRefs) {
            nodes.add(
              _figureNodeFromAssetRef(
                ref,
                block.id,
                assetsById,
                mediaUrlResolver: mediaUrlResolver,
                mediaVariants: mediaAssetsById[ref.assetId.trim()],
              ),
            );
          }
          break;
        case QwqMarkdownBlockKind.horizontalRule:
          // 分隔线进入 Document 模型（GWT-004），阅读端渲染 divider。
          nodes.add(
            ArticleDocumentNode(
              id: block.id.isNotEmpty ? block.id : 'divider_${seed++}',
              type: ArticleDocumentNodeType.divider,
            ),
          );
          break;
        case QwqMarkdownBlockKind.section:
        case QwqMarkdownBlockKind.spacer:
        case QwqMarkdownBlockKind.table:
        case QwqMarkdownBlockKind.groupedDirectory:
        case QwqMarkdownBlockKind.definitionList:
        case QwqMarkdownBlockKind.footnote:
        case QwqMarkdownBlockKind.unsupported:
          nodes.add(
            readOnlyNode(
              ArticleDocumentNode(
                id: block.id.isNotEmpty ? block.id : 'readonly_${seed++}',
                type: ArticleDocumentNodeType.paragraph,
                text: block.text,
              ),
              block,
            ),
          );
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

    if (restoredNodeIds.isNotEmpty && restoredNodeIds.length != nodes.length) {
      throw const FormatException(
        '撤销快照 node identity 数量与 canonical markdown 不一致。',
      );
    }
    final restoredNodes = restoredNodeIds.isEmpty
        ? nodes
        : <ArticleDocumentNode>[
            for (var index = 0; index < nodes.length; index++)
              nodes[index].copyWith(id: restoredNodeIds[index]),
          ];
    final restoredBaseline = restoredNodeIds.isEmpty
        ? readOnlyBaseline
        : <_ReadOnlyOriginEntry>[
            for (final origin in readOnlyBaseline)
              _ReadOnlyOriginEntry(
                nodeId:
                    restoredNodeIds[nodes.indexWhere(
                      (node) => node.id == origin.nodeId,
                    )],
                ordinal: origin.ordinal,
                rawMarkdown: origin.rawMarkdown,
                semanticType: origin.semanticType,
                fingerprint: _readOnlyFingerprint(
                  restoredNodeIds[nodes.indexWhere(
                    (node) => node.id == origin.nodeId,
                  )],
                  origin.semanticType,
                  origin.rawMarkdown,
                ),
              ),
          ];
    return ArticleDocumentData(
      nodes: restoredNodes,
      template: parsed.frontMatter.template.isNotEmpty
          ? parsed.frontMatter.template
          : 'gentle',
      fontPreset: parsed.frontMatter.fontPreset.isNotEmpty
          ? parsed.frontMatter.fontPreset
          : 'clean',
      coverImageUrl: coverImageUrl,
      markdownOriginAuthority: _MarkdownOriginAuthority(
        List<_ReadOnlyOriginEntry>.unmodifiable(restoredBaseline),
      ),
      titleStyle: ArticleDocumentTitleStyle.values.firstWhere(
        (style) => style.name == parsed.frontMatter.titleStyle,
        orElse: () => ArticleDocumentTitleStyle.major,
      ),
    );
  }

  static _InlineMentionParseResult _articleInlineFromBlock(
    QwqMarkdownBlock block,
  ) {
    final parsed = block.inlines.isEmpty
        ? parseQwqMarkdownInlines(block.text)
        : block.inlines;
    final textInline = parsed.firstWhere(
      (inline) => inline.kind == SemanticInlineKind.text,
      orElse: () => QwqMarkdownInline(
        kind: SemanticInlineKind.text,
        text: block.text,
        end: block.text.length,
      ),
    );
    final spans = <ArticleInlineSpan>[];
    for (final inline in parsed) {
      if (inline.kind == SemanticInlineKind.text ||
          inline.start >= inline.end) {
        continue;
      }
      if (inline.kind == SemanticInlineKind.link) {
        if (inline.href.startsWith('/entity/')) {
          final entityId = articleEntityIdFromPublishRef(inline.href);
          if (entityId.isNotEmpty) {
            spans.add(
              ArticleInlineSpan(
                start: inline.start,
                end: inline.end,
                kind: 'entity',
                targetType: 'entity',
                targetId: entityId,
                displayText: inline.text,
              ),
            );
          }
        } else if (isArticleLinkTargetAllowed(inline.href)) {
          spans.add(
            ArticleInlineSpan(
              start: inline.start,
              end: inline.end,
              kind: 'link',
              targetId: inline.href,
              displayText: inline.text,
            ),
          );
        }
        continue;
      }
      if (inline.kind == SemanticInlineKind.mention) {
        spans.add(
          ArticleInlineSpan(
            start: inline.start,
            end: inline.end,
            kind: inline.targetType,
            targetType: inline.targetType,
            targetId: inline.targetId,
            displayText: inline.text,
          ),
        );
        continue;
      }
      spans.add(
        ArticleInlineSpan(
          start: inline.start,
          end: inline.end,
          bold: inline.bold,
          italic: inline.italic,
          underline: inline.underline,
          strikethrough: inline.strikethrough,
          kind: inline.kind == SemanticInlineKind.code ? 'code' : 'text',
        ),
      );
    }
    return _InlineMentionParseResult(text: textInline.text, spans: spans);
  }

  static String serializeMarkdownDocument(QwqMarkdownDocument document) {
    if (!document.canSave) {
      throw const FormatException('只读或诊断失败的 Markdown 文档禁止保存。');
    }
    return document.source;
  }

  static Map<String, String> resolveArticleAssetManifestUrls(
    Map<String, Object?>? manifest,
  ) {
    return _articleAssetManifestResolver.resolveManifestUrls(manifest);
  }

  static Map<String, MediaAssetVariants> resolveArticleAssetManifestVariants(
    Map<String, Object?>? manifest, {
    MediaAssetManifestResolver resolver = _articleAssetManifestResolver,
  }) {
    return resolver.resolveManifestVariants(manifest);
  }

  static ArticleDocumentNode _figureNodeFromAssetRef(
    QwqMarkdownAssetRef ref,
    String blockId,
    Map<String, String> assetsById, {
    String Function(String raw)? mediaUrlResolver,
    MediaAssetVariants? mediaVariants,
  }) {
    final assetId = ref.assetId.trim();
    final resolvedImageUrl =
        assetsById[assetId] ??
        _directMediaUrlFor(assetId, mediaUrlResolver: mediaUrlResolver);
    // 引用无法解析出交付 URL 时 imageUrl 保持空（缺席语义，GWT-016）：
    // 不得伪装成 asset:// URL 让加载栈以本地文件失败收场。
    // 资产身份由 assetId 携带，序列化写回不受影响。
    return ArticleDocumentNode(
      id: blockId.isNotEmpty ? blockId : assetId,
      type: ArticleDocumentNodeType.figure,
      assetId: assetId,
      // 交付形态只从 manifest 声明读取（DEC-033）；缺席保持空串，不按 URL
      // 形态反推，否则私有资产会被当成公开图去直连。
      accessMode: mediaVariants?.accessMode ?? '',
      imageUrl: resolvedImageUrl,
      imageLayout: ref.layout.name,
      caption: ref.caption,
      // manifest 声明的像素宽高（REQ-017）：分页与渲染据此预留占位框比例。
      imageWidth: mediaVariants?.displayWidth,
      imageHeight: mediaVariants?.displayHeight,
    );
  }

  static String _directMediaUrlFor(
    String assetId, {
    String Function(String raw)? mediaUrlResolver,
  }) {
    final injected = mediaUrlResolver?.call(assetId) ?? '';
    if (injected.isNotEmpty) {
      return injected;
    }
    final candidates = resolveContentMediaUrlCandidates(assetId);
    if (candidates.isEmpty) {
      return '';
    }
    final first = candidates.first;
    return first.startsWith('http://') || first.startsWith('https://')
        ? first
        : '';
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

  /// 行内序列化（GWT-002）：消费 [resolveArticleInlineSegments] 的唯一分段
  /// 真相源——mention 段写 `@[label](kind:id)`，样式段按「删除线→下划线→
  /// 粗/斜」固定包裹顺序写成对记号，普通段原样输出。
  static String _serializeInlineText(
    String text,
    List<ArticleInlineSpan> spans,
  ) {
    if (spans.isEmpty) return text;
    final segments = resolveArticleInlineSegments(text, spans);
    if (segments.isEmpty) return text;
    final buffer = StringBuffer();
    for (final segment in segments) {
      final raw = text.substring(segment.start, segment.end);
      final mention = segment.mention;
      if (mention != null) {
        final label = (mention.displayText ?? raw).trim();
        if (mention.isLink) {
          final url = mention.targetId?.trim() ?? '';
          if (label.isEmpty || url.isEmpty) {
            buffer.write(raw);
          } else {
            buffer.write('[$label]($url)');
          }
          continue;
        }
        final targetId = mention.targetId?.trim() ?? '';
        final prefix = '${mention.kind}:';
        final wireTarget = targetId.startsWith(prefix)
            ? targetId.substring(prefix.length)
            : targetId;
        if (label.isEmpty || wireTarget.isEmpty) {
          buffer.write(raw);
        } else {
          buffer.write('@[$label]($prefix$wireTarget)');
        }
        continue;
      }
      if (!segment.hasStyle || raw.trim().isEmpty) {
        buffer.write(raw);
        continue;
      }
      final emphasisToken = segment.bold && segment.italic
          ? '***'
          : segment.bold
          ? '**'
          : segment.italic
          ? '*'
          : '';
      final wrapped = StringBuffer();
      if (segment.strikethrough) wrapped.write('~~');
      if (segment.underline) wrapped.write('++');
      wrapped
        ..write(emphasisToken)
        ..write(raw)
        ..write(emphasisToken);
      if (segment.underline) wrapped.write('++');
      if (segment.strikethrough) wrapped.write('~~');
      buffer.write(wrapped);
    }
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

  /// 嵌套列表缩进（GWT-004）：两空格 = 一级，最多 2 级，与 parser 同一约定。
  static String _listIndent(int listDepth) {
    final depth = listDepth.clamp(0, 2);
    return depth <= 0 ? '' : '  ' * depth;
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

String _resolveArticleMediaReference(
  String raw, {
  String? gatewayBaseUrl,
  String? imageCdnBaseUrl,
  String? videoCdnBaseUrl,
}) => resolveContentMediaUrl(
  raw,
  gatewayBaseUrl: gatewayBaseUrl,
  imageCdnBaseUrl: imageCdnBaseUrl,
  videoCdnBaseUrl: videoCdnBaseUrl,
);

class _InlineMentionParseResult {
  const _InlineMentionParseResult({required this.text, required this.spans});

  final String text;
  final List<ArticleInlineSpan> spans;
}
