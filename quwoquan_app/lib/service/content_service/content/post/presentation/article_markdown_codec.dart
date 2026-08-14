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
            for (final line
                in _serializeInlineText(
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

  static ArticleDocumentData parseDocument(
    String markdown, {
    Map<String, Object?>? assetManifest,
    MediaAssetManifestResolver assetManifestResolver =
        _articleAssetManifestResolver,
  }) {
    final parsed = const QwqMarkdownParser().parse(markdown).document;
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
    for (final block in parsed.blocks) {
      switch (block.kind) {
        case QwqMarkdownBlockKind.heading:
          final inline = _parseInlineMentions(block.text);
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
        case QwqMarkdownBlockKind.card:
          final inline = _parseInlineMentions(block.text);
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
          final inline = _parseInlineMentions(block.text);
          if (inline.text.trim().isNotEmpty) {
            nodes.add(
              ArticleDocumentNode(
                id: block.id.isNotEmpty ? block.id : 'rich_${seed++}',
                type: block.kind == QwqMarkdownBlockKind.quote
                    ? ArticleDocumentNodeType.quote
                    : ArticleDocumentNodeType.callout,
                text: inline.text,
                spans: inline.spans,
              ),
            );
          }
          break;
        case QwqMarkdownBlockKind.codeBlock:
          if (block.text.trim().isNotEmpty) {
            nodes.add(
              ArticleDocumentNode(
                id: block.id.isNotEmpty ? block.id : 'code_${seed++}',
                type: ArticleDocumentNodeType.codeBlock,
                text: block.text,
                codeLanguage: block.language,
              ),
            );
          }
          break;
        case QwqMarkdownBlockKind.orderedItem:
          final inline = _parseInlineMentions(block.text);
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
          final inline = _parseInlineMentions(block.text);
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
            nodes.add(_figureNodeFromAssetRef(ref, block.id, assetsById));
          }
          break;
        case QwqMarkdownBlockKind.gallery:
          for (final ref in block.assetRefs) {
            nodes.add(_figureNodeFromAssetRef(ref, block.id, assetsById));
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

  static final RegExp _inlineMentionPattern = RegExp(
    r'@\[(.+?)\]\((entity|tag):([A-Za-z0-9_:/-]+)\)',
  );

  static final RegExp _inlineLinkPattern = RegExp(r'\[([^\]]+)\]\(([^)\s]+)\)');

  /// 行内解析（GWT-002）：单遍扫描 mention/link 记号与成对样式记号
  /// （`***`/`**`/`*`/`++`/`~~`），还原为等价 span；未闭合记号按字面量
  /// 处理不吞字，病态输入降级为纯文本，不得 crash。链接只接受白名单
  /// scheme（https/http），恶意 scheme 按字面量输出不产生 span。
  static _InlineMentionParseResult _parseInlineMentions(String source) {
    if (!source.contains('@[') &&
        !source.contains('[') &&
        !source.contains('*') &&
        !source.contains('++') &&
        !source.contains('~~')) {
      return _InlineMentionParseResult(text: source, spans: const []);
    }
    const styleTokens = <String>['***', '**', '*', '++', '~~'];
    final buffer = StringBuffer();
    final spans = <ArticleInlineSpan>[];
    // token -> (plain-text 开启偏移)。同一 token 不嵌套（qwq dialect 语义）。
    final openTokens = <String, int>{};
    var i = 0;
    while (i < source.length) {
      final mention = _inlineMentionPattern.matchAsPrefix(source, i);
      if (mention != null) {
        final label = mention.group(1) ?? '';
        final kind = mention.group(2) ?? '';
        final target = mention.group(3) ?? '';
        final prefix = '$kind:';
        final targetId = target.startsWith(prefix) ? target : '$prefix$target';
        final start = buffer.length;
        buffer.write(label);
        if (label.isNotEmpty && kind.isNotEmpty && targetId.isNotEmpty) {
          spans.add(
            ArticleInlineSpan(
              start: start,
              end: buffer.length,
              kind: kind,
              targetType: kind,
              targetId: targetId,
              displayText: label,
            ),
          );
        }
        i = mention.end;
        continue;
      }
      // 链接 [text](url)：mention 记号（@[...]）优先，其后才尝试 link。
      if (source.startsWith('[', i)) {
        final link = _inlineLinkPattern.matchAsPrefix(source, i);
        if (link != null) {
          final label = (link.group(1) ?? '').trim();
          final url = (link.group(2) ?? '').trim();
          // 站内实体链接（数据工程供稿 `/entity/...`）转 canonical entity
          // mention，与 `@[label](entity:...)` 记号同一渲染与跳转通道。
          if (label.isNotEmpty && url.startsWith('/entity/')) {
            final entityId = articleEntityIdFromPublishRef(url);
            if (entityId.isNotEmpty) {
              final start = buffer.length;
              buffer.write(label);
              spans.add(
                ArticleInlineSpan(
                  start: start,
                  end: buffer.length,
                  kind: 'entity',
                  targetType: 'entity',
                  targetId: entityId,
                  displayText: label,
                ),
              );
              i = link.end;
              continue;
            }
          }
          if (label.isNotEmpty && isArticleLinkTargetAllowed(url)) {
            final start = buffer.length;
            buffer.write(label);
            spans.add(
              ArticleInlineSpan(
                start: start,
                end: buffer.length,
                kind: 'link',
                targetId: url,
                displayText: label,
              ),
            );
            i = link.end;
            continue;
          }
        }
      }
      String? token;
      for (final candidate in styleTokens) {
        if (source.startsWith(candidate, i)) {
          token = candidate;
          break;
        }
      }
      if (token != null) {
        final openedAt = openTokens.remove(token);
        if (openedAt != null) {
          if (buffer.length > openedAt) {
            spans.add(
              ArticleInlineSpan(
                start: openedAt,
                end: buffer.length,
                bold: token == '***' || token == '**',
                italic: token == '***' || token == '*',
                underline: token == '++',
                strikethrough: token == '~~',
              ),
            );
          }
          i += token.length;
          continue;
        }
        // 只有后文存在同记号闭合时才视为开启；否则按字面量输出，不吞字。
        if (source.indexOf(token, i + token.length) != -1) {
          openTokens[token] = buffer.length;
        } else {
          buffer.write(token);
        }
        i += token.length;
        continue;
      }
      buffer.write(source[i]);
      i++;
    }
    if (spans.isEmpty && openTokens.isEmpty) {
      return _InlineMentionParseResult(text: source, spans: const []);
    }
    // 未闭合的开启记号（闭合被 mention 等结构消费的病态输入）：按字面量
    // 插回原开启位置，并平移其后的 span 偏移，保证不吞字。
    if (openTokens.isNotEmpty) {
      var text = buffer.toString();
      final pending = openTokens.entries.toList()
        ..sort((a, b) => b.value.compareTo(a.value));
      for (final entry in pending) {
        final offset = entry.value.clamp(0, text.length);
        text = text.substring(0, offset) + entry.key + text.substring(offset);
        for (var index = 0; index < spans.length; index++) {
          final span = spans[index];
          if (span.end <= offset) {
            continue;
          }
          spans[index] = ArticleInlineSpan(
            start: span.start >= offset
                ? span.start + entry.key.length
                : span.start,
            end: span.end + entry.key.length,
            bold: span.bold,
            italic: span.italic,
            underline: span.underline,
            strikethrough: span.strikethrough,
            kind: span.kind,
            targetType: span.targetType,
            targetId: span.targetId,
            displayText: span.displayText,
          );
        }
      }
      spans.sort((a, b) => a.start.compareTo(b.start));
      return _InlineMentionParseResult(text: text, spans: spans);
    }
    spans.sort((a, b) => a.start.compareTo(b.start));
    return _InlineMentionParseResult(text: buffer.toString(), spans: spans);
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
    Map<String, String> assetsById,
  ) {
    final assetId = ref.assetId.trim();
    final resolvedImageUrl = assetsById[assetId] ?? _directMediaUrlFor(assetId);
    return ArticleDocumentNode(
      id: blockId.isNotEmpty ? blockId : assetId,
      type: ArticleDocumentNodeType.figure,
      assetId: assetId,
      imageUrl: resolvedImageUrl.isNotEmpty
          ? resolvedImageUrl
          : 'asset://$assetId',
      imageLayout: ref.layout.name,
      caption: ref.caption,
    );
  }

  static String _directMediaUrlFor(String assetId) {
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
