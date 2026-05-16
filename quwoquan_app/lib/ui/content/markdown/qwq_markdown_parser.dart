import 'package:yaml/yaml.dart';

import 'qwq_markdown_ast.dart';

class QwqMarkdownParseResult {
  const QwqMarkdownParseResult({required this.document});

  final QwqMarkdownDocument document;

  bool get isValid => !document.hasBlockingDiagnostics;
}

class QwqMarkdownParser {
  const QwqMarkdownParser();

  QwqMarkdownParseResult parse(String source) {
    final normalized = source.replaceAll('\r\n', '\n');
    final split = _splitFrontMatter(normalized);
    final diagnostics = <QwqMarkdownDiagnostic>[...split.diagnostics];
    final blocks = <QwqMarkdownBlock>[];
    final assetRefs = <QwqMarkdownAssetRef>[];
    final lines = split.body.split('\n');
    var index = 0;
    var blockSeed = 0;

    String nextId(String prefix) => '${prefix}_${++blockSeed}';

    while (index < lines.length) {
      final line = lines[index];
      final trimmed = line.trim();
      final lineNumber = split.bodyStartLine + index;
      if (trimmed.isEmpty) {
        index += 1;
        continue;
      }

      if (_looksLikeHtml(trimmed)) {
        diagnostics.add(
          QwqMarkdownDiagnostic(
            code: 'html_not_allowed',
            message: 'QWQ Rich Markdown v1 不允许任意 HTML',
            line: lineNumber,
            isBlocking: true,
          ),
        );
        blocks.add(
          QwqMarkdownBlock(
            id: nextId('paragraph'),
            kind: QwqMarkdownBlockKind.paragraph,
            text: trimmed,
            inlines: _parseInlines(trimmed),
            sourceStartLine: lineNumber,
            sourceEndLine: lineNumber,
          ),
        );
        index += 1;
        continue;
      }

      if (trimmed.startsWith(':::')) {
        final parsedDirective = _parseDirective(
          lines,
          index,
          split.bodyStartLine,
          nextId,
        );
        blocks.add(parsedDirective.block);
        assetRefs.addAll(parsedDirective.assetRefs);
        diagnostics.addAll(parsedDirective.diagnostics);
        index = parsedDirective.nextIndex;
        continue;
      }

      if (trimmed.startsWith('```')) {
        final parsedCode = _parseCodeBlock(
          lines,
          index,
          split.bodyStartLine,
          nextId,
        );
        blocks.add(parsedCode.block);
        index = parsedCode.nextIndex;
        continue;
      }

      final headingMatch = RegExp(r'^(#{1,3})\s+(.+)$').firstMatch(trimmed);
      if (headingMatch != null) {
        final text = headingMatch.group(2)!.trim();
        blocks.add(
          QwqMarkdownBlock(
            id: nextId('heading'),
            kind: QwqMarkdownBlockKind.heading,
            text: text,
            level: headingMatch.group(1)!.length,
            inlines: _parseInlines(text),
            sourceStartLine: lineNumber,
            sourceEndLine: lineNumber,
          ),
        );
        index += 1;
        continue;
      }

      if (RegExp(r'^-{3,}$').hasMatch(trimmed)) {
        blocks.add(
          QwqMarkdownBlock(
            id: nextId('hr'),
            kind: QwqMarkdownBlockKind.horizontalRule,
            sourceStartLine: lineNumber,
            sourceEndLine: lineNumber,
          ),
        );
        index += 1;
        continue;
      }

      final imageMatch = RegExp(
        r'^!\[([^\]]*)\]\(([^)]+)\)$',
      ).firstMatch(trimmed);
      if (imageMatch != null) {
        final asset = QwqMarkdownAssetRef.fromAssetUri(
          imageMatch.group(2)!,
          alt: imageMatch.group(1) ?? '',
        );
        assetRefs.add(asset);
        blocks.add(
          QwqMarkdownBlock(
            id: nextId('image'),
            kind: QwqMarkdownBlockKind.image,
            assetRef: asset,
            sourceStartLine: lineNumber,
            sourceEndLine: lineNumber,
          ),
        );
        index += 1;
        continue;
      }

      final orderedMatch = RegExp(r'^\d+\.\s+(.+)$').firstMatch(trimmed);
      if (orderedMatch != null) {
        final text = orderedMatch.group(1)!.trim();
        blocks.add(
          QwqMarkdownBlock(
            id: nextId('ordered'),
            kind: QwqMarkdownBlockKind.orderedItem,
            text: text,
            inlines: _parseInlines(text),
            sourceStartLine: lineNumber,
            sourceEndLine: lineNumber,
          ),
        );
        index += 1;
        continue;
      }

      final bulletMatch = RegExp(r'^[-*+]\s+(.+)$').firstMatch(trimmed);
      if (bulletMatch != null) {
        final text = bulletMatch.group(1)!.trim();
        blocks.add(
          QwqMarkdownBlock(
            id: nextId('bullet'),
            kind: QwqMarkdownBlockKind.bulletItem,
            text: text,
            inlines: _parseInlines(text),
            sourceStartLine: lineNumber,
            sourceEndLine: lineNumber,
          ),
        );
        index += 1;
        continue;
      }

      if (trimmed.startsWith('>')) {
        final text = trimmed.replaceFirst(RegExp(r'^>\s?'), '').trim();
        blocks.add(
          QwqMarkdownBlock(
            id: nextId('quote'),
            kind: QwqMarkdownBlockKind.quote,
            text: text,
            inlines: _parseInlines(text),
            sourceStartLine: lineNumber,
            sourceEndLine: lineNumber,
          ),
        );
        index += 1;
        continue;
      }

      final paragraphLines = <String>[trimmed];
      final startLine = lineNumber;
      index += 1;
      while (index < lines.length) {
        final next = lines[index].trim();
        if (next.isEmpty ||
            next.startsWith(':::') ||
            next.startsWith('```') ||
            RegExp(r'^(#{1,3})\s+').hasMatch(next) ||
            RegExp(r'^!\[[^\]]*\]\([^)]+\)$').hasMatch(next) ||
            RegExp(r'^\d+\.\s+').hasMatch(next) ||
            RegExp(r'^[-*+]\s+').hasMatch(next) ||
            next.startsWith('>') ||
            RegExp(r'^-{3,}$').hasMatch(next)) {
          break;
        }
        paragraphLines.add(next);
        index += 1;
      }
      final text = paragraphLines.join(' ');
      blocks.add(
        QwqMarkdownBlock(
          id: nextId('paragraph'),
          kind: QwqMarkdownBlockKind.paragraph,
          text: text,
          inlines: _parseInlines(text),
          sourceStartLine: startLine,
          sourceEndLine: split.bodyStartLine + index - 1,
        ),
      );
    }

    return QwqMarkdownParseResult(
      document: QwqMarkdownDocument(
        source: normalized,
        frontMatter: split.frontMatter,
        blocks: blocks,
        assetRefs: assetRefs,
        diagnostics: diagnostics,
      ),
    );
  }
}

class _FrontMatterSplit {
  const _FrontMatterSplit({
    required this.frontMatter,
    required this.body,
    required this.bodyStartLine,
    required this.diagnostics,
  });

  final QwqMarkdownFrontMatter frontMatter;
  final String body;
  final int bodyStartLine;
  final List<QwqMarkdownDiagnostic> diagnostics;
}

_FrontMatterSplit _splitFrontMatter(String source) {
  if (!source.startsWith('---\n')) {
    return _FrontMatterSplit(
      frontMatter: const QwqMarkdownFrontMatter(),
      body: source,
      bodyStartLine: 1,
      diagnostics: const <QwqMarkdownDiagnostic>[],
    );
  }
  final closing = source.indexOf('\n---', 4);
  if (closing < 0) {
    return _FrontMatterSplit(
      frontMatter: const QwqMarkdownFrontMatter(),
      body: source,
      bodyStartLine: 1,
      diagnostics: const <QwqMarkdownDiagnostic>[
        QwqMarkdownDiagnostic(
          code: 'front_matter_unclosed',
          message: 'front matter 缺少结束 ---',
          line: 1,
          isBlocking: true,
        ),
      ],
    );
  }
  final rawYaml = source.substring(4, closing).trim();
  final bodyOffset = closing + '\n---'.length;
  final body = source.substring(bodyOffset).replaceFirst(RegExp(r'^\n'), '');
  final bodyStartLine = source.substring(0, bodyOffset).split('\n').length;
  try {
    final decoded = loadYaml(rawYaml);
    final map = <String, Object?>{};
    if (decoded is YamlMap) {
      for (final entry in decoded.entries) {
        map[entry.key.toString()] = _yamlValue(entry.value);
      }
    }
    return _FrontMatterSplit(
      frontMatter: QwqMarkdownFrontMatter.fromMap(map),
      body: body,
      bodyStartLine: bodyStartLine,
      diagnostics: const <QwqMarkdownDiagnostic>[],
    );
  } catch (error) {
    return _FrontMatterSplit(
      frontMatter: const QwqMarkdownFrontMatter(),
      body: body,
      bodyStartLine: bodyStartLine,
      diagnostics: <QwqMarkdownDiagnostic>[
        QwqMarkdownDiagnostic(
          code: 'front_matter_invalid',
          message: 'front matter 解析失败: $error',
          line: 1,
          isBlocking: true,
        ),
      ],
    );
  }
}

Object? _yamlValue(Object? value) {
  if (value is YamlList) {
    return value.map(_yamlValue).toList(growable: false);
  }
  if (value is YamlMap) {
    return <String, Object?>{
      for (final entry in value.entries)
        entry.key.toString(): _yamlValue(entry.value),
    };
  }
  return value;
}

class _ParsedDirective {
  const _ParsedDirective({
    required this.block,
    required this.assetRefs,
    required this.diagnostics,
    required this.nextIndex,
  });

  final QwqMarkdownBlock block;
  final List<QwqMarkdownAssetRef> assetRefs;
  final List<QwqMarkdownDiagnostic> diagnostics;
  final int nextIndex;
}

_ParsedDirective _parseDirective(
  List<String> lines,
  int startIndex,
  int bodyStartLine,
  String Function(String prefix) nextId,
) {
  final opener = lines[startIndex].trim();
  final openerLine = bodyStartLine + startIndex;
  final match = RegExp(r'^:::([A-Za-z][A-Za-z0-9_-]*)(.*)$').firstMatch(opener);
  if (match == null) {
    return _ParsedDirective(
      block: QwqMarkdownBlock(
        id: nextId('paragraph'),
        kind: QwqMarkdownBlockKind.paragraph,
        text: opener,
        sourceStartLine: openerLine,
        sourceEndLine: openerLine,
      ),
      assetRefs: const <QwqMarkdownAssetRef>[],
      diagnostics: <QwqMarkdownDiagnostic>[
        QwqMarkdownDiagnostic(
          code: 'directive_invalid',
          message: '富布局指令格式不合法',
          line: openerLine,
          isBlocking: true,
        ),
      ],
      nextIndex: startIndex + 1,
    );
  }

  final name = match.group(1)!.trim();
  final attributes = _parseDirectiveAttributes(match.group(2) ?? '');
  final content = <String>[];
  var index = startIndex + 1;
  while (index < lines.length && lines[index].trim() != ':::') {
    content.add(lines[index]);
    index += 1;
  }
  final closed = index < lines.length && lines[index].trim() == ':::';
  final nextIndex = closed ? index + 1 : lines.length;
  final endLine = closed ? bodyStartLine + index : bodyStartLine + startIndex;
  final diagnostics = <QwqMarkdownDiagnostic>[
    if (!closed)
      QwqMarkdownDiagnostic(
        code: 'directive_unclosed',
        message: '$name 指令缺少结束 :::',
        line: openerLine,
        isBlocking: true,
      ),
  ];

  switch (name) {
    case 'figure':
      final assetUri = content
          .map((line) => line.trim())
          .firstWhere(
            (line) => line.isNotEmpty,
            orElse: () =>
                attributes['id'] == null ? '' : 'asset://${attributes['id']}',
          );
      final asset = QwqMarkdownAssetRef.fromAssetUri(
        assetUri,
        layout: _imageLayout(attributes['layout']),
        caption: _stringAttr(attributes, 'caption'),
      );
      return _ParsedDirective(
        block: QwqMarkdownBlock(
          id: nextId('figure'),
          kind: QwqMarkdownBlockKind.figure,
          assetRef: asset,
          attributes: attributes,
          sourceStartLine: openerLine,
          sourceEndLine: endLine,
        ),
        assetRefs: <QwqMarkdownAssetRef>[asset],
        diagnostics: diagnostics,
        nextIndex: nextIndex,
      );
    case 'gallery':
      final ids = _stringAttr(attributes, 'ids')
          .split(',')
          .map((id) => id.trim())
          .where((id) => id.isNotEmpty)
          .toList(growable: false);
      final assets = ids
          .map(
            (id) => QwqMarkdownAssetRef.fromAssetUri(
              'asset://$id',
              caption: _stringAttr(attributes, 'caption'),
            ),
          )
          .toList(growable: false);
      return _ParsedDirective(
        block: QwqMarkdownBlock(
          id: nextId('gallery'),
          kind: QwqMarkdownBlockKind.gallery,
          assetRefs: assets,
          attributes: attributes,
          sourceStartLine: openerLine,
          sourceEndLine: endLine,
        ),
        assetRefs: assets,
        diagnostics: diagnostics,
        nextIndex: nextIndex,
      );
    case 'callout':
      final text = content.join('\n').trim();
      return _ParsedDirective(
        block: QwqMarkdownBlock(
          id: nextId('callout'),
          kind: QwqMarkdownBlockKind.callout,
          text: text,
          inlines: _parseInlines(text),
          attributes: attributes,
          sourceStartLine: openerLine,
          sourceEndLine: endLine,
        ),
        assetRefs: const <QwqMarkdownAssetRef>[],
        diagnostics: diagnostics,
        nextIndex: nextIndex,
      );
    case 'card':
      return _ParsedDirective(
        block: QwqMarkdownBlock(
          id: nextId('card'),
          kind: QwqMarkdownBlockKind.card,
          text: content.join('\n').trim(),
          attributes: attributes,
          sourceStartLine: openerLine,
          sourceEndLine: endLine,
        ),
        assetRefs: const <QwqMarkdownAssetRef>[],
        diagnostics: diagnostics,
        nextIndex: nextIndex,
      );
    case 'section':
      return _ParsedDirective(
        block: QwqMarkdownBlock(
          id: nextId('section'),
          kind: QwqMarkdownBlockKind.section,
          text: content.join('\n').trim(),
          attributes: attributes,
          sourceStartLine: openerLine,
          sourceEndLine: endLine,
        ),
        assetRefs: const <QwqMarkdownAssetRef>[],
        diagnostics: diagnostics,
        nextIndex: nextIndex,
      );
    case 'spacer':
      return _ParsedDirective(
        block: QwqMarkdownBlock(
          id: nextId('spacer'),
          kind: QwqMarkdownBlockKind.spacer,
          attributes: attributes,
          sourceStartLine: openerLine,
          sourceEndLine: endLine,
        ),
        assetRefs: const <QwqMarkdownAssetRef>[],
        diagnostics: diagnostics,
        nextIndex: nextIndex,
      );
    default:
      return _ParsedDirective(
        block: QwqMarkdownBlock(
          id: nextId('paragraph'),
          kind: QwqMarkdownBlockKind.paragraph,
          text: content.join('\n').trim(),
          sourceStartLine: openerLine,
          sourceEndLine: endLine,
        ),
        assetRefs: const <QwqMarkdownAssetRef>[],
        diagnostics: <QwqMarkdownDiagnostic>[
          ...diagnostics,
          QwqMarkdownDiagnostic(
            code: 'directive_not_allowed',
            message: '未知富布局指令 $name',
            line: openerLine,
            isBlocking: true,
          ),
        ],
        nextIndex: nextIndex,
      );
  }
}

Map<String, Object?> _parseDirectiveAttributes(String raw) {
  final attrs = <String, Object?>{};
  final pattern = RegExp(r'([A-Za-z][A-Za-z0-9_-]*)="([^"]*)"');
  for (final match in pattern.allMatches(raw)) {
    attrs[match.group(1)!] = match.group(2) ?? '';
  }
  return attrs;
}

String _stringAttr(Map<String, Object?> attributes, String key) {
  return attributes[key]?.toString().trim() ?? '';
}

QwqMarkdownImageLayout _imageLayout(Object? value) {
  return switch (value?.toString().trim()) {
    'wrapLeft' => QwqMarkdownImageLayout.wrapLeft,
    'wrapRight' => QwqMarkdownImageLayout.wrapRight,
    _ => QwqMarkdownImageLayout.fullWidth,
  };
}

class _ParsedCodeBlock {
  const _ParsedCodeBlock({required this.block, required this.nextIndex});

  final QwqMarkdownBlock block;
  final int nextIndex;
}

_ParsedCodeBlock _parseCodeBlock(
  List<String> lines,
  int startIndex,
  int bodyStartLine,
  String Function(String prefix) nextId,
) {
  final opener = lines[startIndex].trim();
  final language = opener.substring(3).trim();
  final content = <String>[];
  var index = startIndex + 1;
  while (index < lines.length && lines[index].trim() != '```') {
    content.add(lines[index]);
    index += 1;
  }
  final closed = index < lines.length && lines[index].trim() == '```';
  return _ParsedCodeBlock(
    block: QwqMarkdownBlock(
      id: nextId('code'),
      kind: QwqMarkdownBlockKind.codeBlock,
      text: content.join('\n'),
      language: language,
      sourceStartLine: bodyStartLine + startIndex,
      sourceEndLine: closed
          ? bodyStartLine + index
          : bodyStartLine + startIndex,
    ),
    nextIndex: closed ? index + 1 : lines.length,
  );
}

List<QwqMarkdownInline> _parseInlines(String text) {
  final result = <QwqMarkdownInline>[];
  final linkPattern = RegExp(r'\[([^\]]+)\]\(([^)]+)\)');
  var cursor = 0;
  for (final match in linkPattern.allMatches(text)) {
    if (match.start > cursor) {
      result.addAll(
        _parseSimpleInlineText(text.substring(cursor, match.start)),
      );
    }
    result.add(
      QwqMarkdownInline(
        kind: QwqMarkdownInlineKind.link,
        text: match.group(1) ?? '',
        href: match.group(2) ?? '',
      ),
    );
    cursor = match.end;
  }
  if (cursor < text.length) {
    result.addAll(_parseSimpleInlineText(text.substring(cursor)));
  }
  return result;
}

List<QwqMarkdownInline> _parseSimpleInlineText(String text) {
  if (text.isEmpty) {
    return const <QwqMarkdownInline>[];
  }
  return <QwqMarkdownInline>[
    QwqMarkdownInline(kind: QwqMarkdownInlineKind.text, text: text),
  ];
}

bool _looksLikeHtml(String trimmed) {
  return RegExp(r'^</?[A-Za-z][\s\S]*>$').hasMatch(trimmed);
}
