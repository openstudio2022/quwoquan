import 'dart:math' as math;

import 'package:yaml/yaml.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/create_page_text_constants.dart';
import 'package:quwoquan_app/service/content_service/content/post/generated/semantic_document.g.dart';

import 'qwq_markdown_ast.dart';

class QwqMarkdownParseResult {
  const QwqMarkdownParseResult({required this.document});

  final QwqMarkdownDocument document;

  bool get isValid => !document.hasBlockingDiagnostics;
}

class QwqMarkdownParser {
  const QwqMarkdownParser();

  QwqMarkdownParseResult parse(String source, {bool requireVersion = false}) {
    final normalized = source.replaceAll('\r\n', '\n');
    final split = _splitFrontMatter(normalized);
    final diagnostics = <QwqMarkdownDiagnostic>[...split.diagnostics];
    final dialect = split.markdownDialect;
    if (dialect.isEmpty && requireVersion) {
      diagnostics.add(
        const QwqMarkdownDiagnostic(
          code: 'markdown_version_missing',
          message: '缺少 markdownDialect 版本声明。',
          line: 1,
          isBlocking: true,
        ),
      );
    } else if (dialect.isNotEmpty && dialect != qwqRichMarkdownVersion) {
      diagnostics.add(
        QwqMarkdownDiagnostic(
          code: 'markdown_version_unsupported',
          message: '不支持的 markdownDialect: $dialect',
          line: 1,
          isBlocking: true,
        ),
      );
    }
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
            message: CreatePageText.markdownHtmlNotAllowed,
            line: lineNumber,
            isBlocking: true,
          ),
        );
        blocks.add(
          QwqMarkdownBlock(
            id: nextId('paragraph'),
            kind: QwqMarkdownBlockKind.paragraph,
            text: trimmed,
            inlines: parseQwqMarkdownInlines(trimmed),
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
        diagnostics.addAll(parsedCode.diagnostics);
        index = parsedCode.nextIndex;
        continue;
      }

      if (_isTableStart(lines, index)) {
        final parsedTable = _parseTable(
          lines,
          index,
          split.bodyStartLine,
          nextId,
        );
        blocks.add(parsedTable.block);
        index = parsedTable.nextIndex;
        continue;
      }

      final footnoteMatch = RegExp(r'^\[\^([^\]]+)\]:\s*(.+)$')
          .firstMatch(trimmed);
      if (footnoteMatch != null) {
        final footnote = QwqMarkdownFootnote(
          label: footnoteMatch.group(1)!,
          text: footnoteMatch.group(2)!,
        );
        blocks.add(
          QwqMarkdownBlock(
            id: nextId('footnote'),
            kind: QwqMarkdownBlockKind.footnote,
            text: footnote.text,
            footnote: footnote,
            inlines: parseQwqMarkdownInlines(footnote.text),
            rawSource: line,
            isReadOnly: true,
            sourceStartLine: lineNumber,
            sourceEndLine: lineNumber,
          ),
        );
        index += 1;
        continue;
      }

      if (index + 1 < lines.length &&
          RegExp(r'^:\s+.+$').hasMatch(lines[index + 1].trim())) {
        final definition = QwqMarkdownDefinition(
          term: trimmed,
          definition: lines[index + 1].trim().substring(1).trim(),
        );
        blocks.add(
          QwqMarkdownBlock(
            id: nextId('definition'),
            kind: QwqMarkdownBlockKind.definitionList,
            text: '${definition.term}: ${definition.definition}',
            definitions: <QwqMarkdownDefinition>[definition],
            rawSource: '$line\n${lines[index + 1]}',
            isReadOnly: true,
            sourceStartLine: lineNumber,
            sourceEndLine: lineNumber + 1,
          ),
        );
        index += 2;
        continue;
      }

      final headingMatch = RegExp(r'^(#{1,6})\s+(.+)$').firstMatch(trimmed);
      if (headingMatch != null) {
        final text = headingMatch.group(2)!.trim();
        blocks.add(
          QwqMarkdownBlock(
            id: nextId('heading'),
            kind: QwqMarkdownBlockKind.heading,
            text: text,
            level: headingMatch.group(1)!.length,
            inlines: parseQwqMarkdownInlines(text),
            rawSource: line,
            isReadOnly: headingMatch.group(1)!.length > 3,
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

      final imageMatch = RegExp(r'^!\[([^\]]*)\]\(([^)]+)\)$')
          .firstMatch(trimmed);
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

      // 嵌套列表：两空格缩进为一级，最多 2 级（qwq dialect 约定）。
      final listIndent = line.length - line.trimLeft().length;
      final listDepth = math.min(2, listIndent ~/ 2);

      final orderedMatch = RegExp(r'^\d+\.\s+(.+)$').firstMatch(trimmed);
      if (orderedMatch != null) {
        final text = orderedMatch.group(1)!.trim();
        blocks.add(
          QwqMarkdownBlock(
            id: nextId('ordered'),
            kind: QwqMarkdownBlockKind.orderedItem,
            text: text,
            listDepth: listDepth,
            inlines: parseQwqMarkdownInlines(text),
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
            listDepth: listDepth,
            inlines: parseQwqMarkdownInlines(text),
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
            inlines: parseQwqMarkdownInlines(text),
            rawSource: line,
            isReadOnly: true,
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
            RegExp(r'^(#{1,6})\s+').hasMatch(next) ||
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
          inlines: parseQwqMarkdownInlines(text),
          sourceStartLine: startLine,
          sourceEndLine: split.bodyStartLine + index - 1,
        ),
      );
    }

    final envelope = buildQwqSemanticEnvelope(
      source: normalized,
      blocks: blocks,
      assetRefs: assetRefs,
    );
    final validation = validateSemanticDocumentEnvelope(
      semanticEnvelopeValidationMap(envelope),
      semanticDocumentCapabilityIds,
    );
    if (validation.code != SemanticDocumentValidationCode.ok) {
      diagnostics.add(
        QwqMarkdownDiagnostic(
          code: 'semantic_${validation.code.name}',
          message: validation.detail ?? validation.code.name,
          isBlocking: true,
        ),
      );
    }
    return QwqMarkdownParseResult(
      document: QwqMarkdownDocument(
        source: normalized,
        version: dialect.isEmpty ? qwqRichMarkdownVersion : dialect,
        frontMatter: split.frontMatter,
        blocks: blocks,
        assetRefs: assetRefs,
        diagnostics: diagnostics,
        semanticEnvelope: envelope,
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
    required this.markdownDialect,
  });

  final QwqMarkdownFrontMatter frontMatter;
  final String body;
  final int bodyStartLine;
  final List<QwqMarkdownDiagnostic> diagnostics;
  final String markdownDialect;
}

_FrontMatterSplit _splitFrontMatter(String source) {
  if (!source.startsWith('---\n')) {
    return _FrontMatterSplit(
      frontMatter: const QwqMarkdownFrontMatter(),
      body: source,
      bodyStartLine: 1,
      diagnostics: const <QwqMarkdownDiagnostic>[],
      markdownDialect: '',
    );
  }
  final closing = source.indexOf('\n---', 4);
  if (closing < 0) {
    return _FrontMatterSplit(
      frontMatter: const QwqMarkdownFrontMatter(),
      body: source,
      bodyStartLine: 1,
      markdownDialect: '',
      diagnostics: const <QwqMarkdownDiagnostic>[
        QwqMarkdownDiagnostic(
          code: 'front_matter_unclosed',
          message: CreatePageText.markdownFrontMatterUnclosed,
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
      markdownDialect: _stringValue(map['markdownDialect']),
    );
  } catch (_) {
    return _FrontMatterSplit(
      frontMatter: const QwqMarkdownFrontMatter(),
      body: body,
      bodyStartLine: bodyStartLine,
      markdownDialect: '',
      diagnostics: <QwqMarkdownDiagnostic>[
        QwqMarkdownDiagnostic(
          code: 'front_matter_invalid',
          message: CreatePageText.markdownFrontMatterInvalid,
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
  final match = RegExp(r'^(:{3,})([A-Za-z][A-Za-z0-9_-]*)(.*)$')
      .firstMatch(opener);
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
          message: CreatePageText.markdownDirectiveInvalid,
          line: openerLine,
          isBlocking: true,
        ),
      ],
      nextIndex: startIndex + 1,
    );
  }

  final fence = match.group(1)!;
  final name = match.group(2)!.trim();
  final attributes = _parseDirectiveAttributes(match.group(3) ?? '');
  final content = <String>[];
  var index = startIndex + 1;
  while (index < lines.length && lines[index].trim() != fence) {
    content.add(lines[index]);
    index += 1;
  }
  final closed = index < lines.length && lines[index].trim() == fence;
  final nextIndex = closed ? index + 1 : lines.length;
  final endLine = closed ? bodyStartLine + index : bodyStartLine + startIndex;
  final rawSource = lines.sublist(startIndex, nextIndex).join('\n');
  final diagnostics = <QwqMarkdownDiagnostic>[
    if (!closed)
      QwqMarkdownDiagnostic(
        code: 'directive_unclosed',
        message: CreatePageText.markdownDirectiveUnclosed(name),
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
          rawSource: rawSource,
          isReadOnly: true,
          text: text,
          inlines: parseQwqMarkdownInlines(text),
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
    case 'align':
      // 段落对齐指令：:::align value="center|right"，内容为段落文本。
      final alignText = content.join('\n').trim();
      final alignValue = switch (_stringAttr(attributes, 'value')) {
        'center' => 'center',
        'right' => 'right',
        _ => '',
      };
      return _ParsedDirective(
        block: QwqMarkdownBlock(
          id: nextId('paragraph'),
          kind: QwqMarkdownBlockKind.paragraph,
          text: alignText,
          textAlign: alignValue,
          inlines: parseQwqMarkdownInlines(alignText),
          attributes: attributes,
          sourceStartLine: openerLine,
          sourceEndLine: endLine,
        ),
        assetRefs: const <QwqMarkdownAssetRef>[],
        diagnostics: diagnostics,
        nextIndex: nextIndex,
      );
    case 'groupedDirectory':
      final groups = <String, List<String>>{};
      String current = '';
      for (final raw in content) {
        final value = raw.trim();
        if (value.startsWith('## ')) {
          current = value.substring(3).trim();
          groups.putIfAbsent(current, () => <String>[]);
        } else if (current.isNotEmpty && RegExp(r'^[-*+]\s+').hasMatch(value)) {
          groups[current]!.add(value.replaceFirst(RegExp(r'^[-*+]\s+'), ''));
        }
      }
      return _ParsedDirective(
        block: QwqMarkdownBlock(
          id: nextId('directory'),
          kind: QwqMarkdownBlockKind.groupedDirectory,
          text: content.join('\n').trim(),
          groupedDirectory: QwqMarkdownGroupedDirectory(groups: groups),
          rawSource: lines.sublist(startIndex, nextIndex).join('\n'),
          isReadOnly: true,
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
          rawSource: rawSource,
          isReadOnly: true,
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
          rawSource: rawSource,
          isReadOnly: true,
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
            message: CreatePageText.markdownDirectiveNotAllowed(name),
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
  const _ParsedCodeBlock({
    required this.block,
    required this.nextIndex,
    required this.diagnostics,
  });
  final QwqMarkdownBlock block;
  final int nextIndex;
  final List<QwqMarkdownDiagnostic> diagnostics;
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
      rawSource: lines
          .sublist(startIndex, closed ? index + 1 : lines.length)
          .join('\n'),
      isReadOnly: true,
      sourceStartLine: bodyStartLine + startIndex,
      sourceEndLine: closed
          ? bodyStartLine + index
          : bodyStartLine + startIndex,
    ),
    nextIndex: closed ? index + 1 : lines.length,
    diagnostics: <QwqMarkdownDiagnostic>[
      if (!closed)
        QwqMarkdownDiagnostic(
          code: 'code_fence_unclosed',
          message: '代码围栏未闭合。',
          line: bodyStartLine + startIndex,
          isBlocking: true,
        ),
    ],
  );
}

List<QwqMarkdownInline> parseQwqMarkdownInlines(String source) {
  final plain = StringBuffer();
  final spans = <QwqMarkdownInline>[];
  final open = <String, int>{};
  const tokens = <String>['***', '**', '~~', '++', '*', '`'];
  final mentionPattern = RegExp(r'@\[([^\]]+)\]\((entity|tag):([^\)]+)\)');
  final linkPattern = RegExp(r'\[([^\]]+)\]\(([^\)\s]+)\)');
  var index = 0;
  while (index < source.length) {
    final mention = mentionPattern.matchAsPrefix(source, index);
    final link = source.startsWith('[', index)
        ? linkPattern.matchAsPrefix(source, index)
        : null;
    if (mention != null || link != null) {
      final match = mention ?? link!;
      final label = match.group(1) ?? '';
      final target = mention != null
          ? '${match.group(2)}:${match.group(3)}'
          : (match.group(2) ?? '');
      final validEntityLink =
          target.startsWith('/entity/') &&
          target.split('/').where((part) => part.isNotEmpty).length >= 4;
      final validLink =
          mention != null ||
          validEntityLink ||
          Uri.tryParse(target)?.scheme.toLowerCase() == 'http' ||
          Uri.tryParse(target)?.scheme.toLowerCase() == 'https';
      if (validLink) {
        final start = plain.length;
        plain.write(label);
        spans.add(
          QwqMarkdownInline(
            kind: mention != null
                ? SemanticInlineKind.mention
                : SemanticInlineKind.link,
            text: label,
            href: mention == null ? target : '',
            targetType: mention?.group(2) ?? '',
            targetId: target,
            start: start,
            end: plain.length,
          ),
        );
        index = match.end;
        continue;
      }
    }
    String? token;
    for (final candidate in tokens) {
      if (source.startsWith(candidate, index)) {
        token = candidate;
        break;
      }
    }
    if (token != null) {
      final opened = open.remove(token);
      if (opened != null) {
        spans.add(
          QwqMarkdownInline(
            kind: token == '`'
                ? SemanticInlineKind.code
                : token == '++'
                ? SemanticInlineKind.underline
                : token == '~~'
                ? SemanticInlineKind.strikethrough
                : token == '*'
                ? SemanticInlineKind.italic
                : SemanticInlineKind.bold,
            text: plain.toString().substring(opened),
            start: opened,
            end: plain.length,
            bold: token == '**' || token == '***',
            italic: token == '*' || token == '***',
            underline: token == '++',
            strikethrough: token == '~~',
          ),
        );
      } else if (source.indexOf(token, index + token.length) >= 0) {
        open[token] = plain.length;
      } else {
        plain.write(token);
      }
      index += token.length;
      continue;
    }
    plain.write(source[index++]);
  }
  if (open.isNotEmpty) {
    return <QwqMarkdownInline>[
      QwqMarkdownInline(
        kind: SemanticInlineKind.text,
        text: source,
        end: source.length,
      ),
    ];
  }
  spans.sort((a, b) => a.start.compareTo(b.start));
  return <QwqMarkdownInline>[
    QwqMarkdownInline(
      kind: SemanticInlineKind.text,
      text: plain.toString(),
      end: plain.length,
    ),
    ...spans,
  ];
}

class _ParsedTable {
  const _ParsedTable(this.block, this.nextIndex);
  final QwqMarkdownBlock block;
  final int nextIndex;
}

bool _isTableStart(List<String> lines, int index) =>
    index + 1 < lines.length &&
    lines[index].contains('|') &&
    RegExp(r'^\s*\|?\s*:?-{3,}').hasMatch(lines[index + 1]);

_ParsedTable _parseTable(
  List<String> lines,
  int start,
  int bodyStartLine,
  String Function(String) nextId,
) {
  List<String> cells(String line) => line
      .trim()
      .replaceFirst(RegExp(r'^\|'), '')
      .replaceFirst(RegExp(r'\|$'), '')
      .split('|')
      .map((e) => e.trim())
      .toList(growable: false);
  final rows = <List<String>>[cells(lines[start])];
  final alignment = cells(lines[start + 1])
      .map(
        (cell) => cell.startsWith(':') && cell.endsWith(':')
            ? 'center'
            : cell.endsWith(':')
            ? 'right'
            : 'left',
      )
      .toList(growable: false);
  var index = start + 2;
  while (index < lines.length &&
      lines[index].trim().isNotEmpty &&
      lines[index].contains('|')) {
    rows.add(cells(lines[index++]));
  }
  final table = QwqMarkdownTable(rows: rows, alignment: alignment);
  return _ParsedTable(
    QwqMarkdownBlock(
      id: nextId('table'),
      kind: QwqMarkdownBlockKind.table,
      text: rows.expand((e) => e).join(' '),
      table: table,
      rawSource: lines.sublist(start, index).join('\n'),
      isReadOnly: true,
      sourceStartLine: bodyStartLine + start,
      sourceEndLine: bodyStartLine + index - 1,
    ),
    index,
  );
}

bool _looksLikeHtml(String trimmed) {
  return RegExp(r'<\s*/?\s*[A-Za-z][^>]*>').hasMatch(trimmed) ||
      RegExp(r'<!--|-->|<!DOCTYPE', caseSensitive: false).hasMatch(trimmed);
}

String _stringValue(Object? value) => value?.toString().trim() ?? '';
