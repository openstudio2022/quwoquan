import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/service/content_service/content/post/generated/semantic_document.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show AssistantUsePolicy;

const String qwqRichMarkdownVersion = 'qwq-rich-md';

enum QwqMarkdownBlockKind {
  heading,
  paragraph,
  orderedItem,
  bulletItem,
  quote,
  codeBlock,
  image,
  figure,
  gallery,
  callout,
  card,
  section,
  spacer,
  horizontalRule,
  table,
  groupedDirectory,
  definitionList,
  footnote,
  unsupported,
}

typedef QwqMarkdownInlineKind = SemanticInlineKind;

enum QwqMarkdownAssetKind { image, video, attachment }

enum QwqMarkdownImageLayout { fullWidth, wrapLeft, wrapRight }

enum QwqMarkdownGalleryLayout { grid, masonry, carousel }

enum QwqMarkdownCalloutType { note, tip, warning, risk }

@immutable
class QwqMarkdownDocument {
  const QwqMarkdownDocument({
    required this.source,
    this.version = qwqRichMarkdownVersion,
    this.frontMatter = const QwqMarkdownFrontMatter(),
    this.blocks = const <QwqMarkdownBlock>[],
    this.assetRefs = const <QwqMarkdownAssetRef>[],
    this.diagnostics = const <QwqMarkdownDiagnostic>[],
    this.semanticEnvelope,
  });

  final String source;
  final String version;
  final QwqMarkdownFrontMatter frontMatter;
  final List<QwqMarkdownBlock> blocks;
  final List<QwqMarkdownAssetRef> assetRefs;
  final List<QwqMarkdownDiagnostic> diagnostics;
  final DocumentEnvelope? semanticEnvelope;

  bool get hasBlockingDiagnostics =>
      diagnostics.any((diagnostic) => diagnostic.isBlocking);

  bool get isReadOnly =>
      version != qwqRichMarkdownVersion ||
      hasBlockingDiagnostics ||
      blocks.any((block) => block.isReadOnly);

  bool get canSave => !isReadOnly;

  Set<String> get referencedAssetIds => assetRefs
      .map((asset) => asset.assetId)
      .where((assetId) => assetId.trim().isNotEmpty)
      .toSet();

  Set<String> get bodyEntityAnchorRefs {
    final refs = <String>{};
    final refPattern = RegExp(r'\(([^()]+)\)');
    var inEntitySection = false;
    var entityHeadingLevel = 0;
    for (final block in blocks) {
      if (block.kind == QwqMarkdownBlockKind.heading) {
        final heading = block.text.trim();
        if (heading == '实体锚点') {
          inEntitySection = true;
          entityHeadingLevel = block.level;
          continue;
        }
        if (inEntitySection &&
            block.level > 0 &&
            block.level <= entityHeadingLevel) {
          break;
        }
      }
      if (!inEntitySection || block.text.trim().isEmpty) {
        continue;
      }
      for (final match in refPattern.allMatches(block.text)) {
        final ref = match.group(1)?.trim() ?? '';
        if (ref.startsWith('trees/')) {
          refs.add(ref);
        }
      }
    }
    return refs;
  }

  Map<String, Object?> toMap() {
    return <String, Object?>{
      'version': version,
      'frontMatter': frontMatter.toMap(),
      'blocks': blocks.map((block) => block.toMap()).toList(growable: false),
      'assetRefs': assetRefs
          .map((asset) => asset.toMap())
          .toList(growable: false),
      if (semanticEnvelope != null)
        'semanticFingerprint': semanticEnvelope!.semanticFingerprint,
      'diagnostics': diagnostics
          .map((diagnostic) => diagnostic.toMap())
          .toList(growable: false),
    };
  }
}

SemanticNodeKind semanticNodeKindForQwqBlock(QwqMarkdownBlockKind kind) {
  return switch (kind) {
    QwqMarkdownBlockKind.heading => SemanticNodeKind.heading,
    QwqMarkdownBlockKind.paragraph => SemanticNodeKind.paragraph,
    QwqMarkdownBlockKind.orderedItem ||
    QwqMarkdownBlockKind.bulletItem => SemanticNodeKind.listItem,
    QwqMarkdownBlockKind.quote => SemanticNodeKind.blockquote,
    QwqMarkdownBlockKind.codeBlock => SemanticNodeKind.codeBlock,
    QwqMarkdownBlockKind.image ||
    QwqMarkdownBlockKind.figure => SemanticNodeKind.figure,
    QwqMarkdownBlockKind.gallery => SemanticNodeKind.gallery,
    QwqMarkdownBlockKind.callout => SemanticNodeKind.callout,
    QwqMarkdownBlockKind.card ||
    QwqMarkdownBlockKind.section => SemanticNodeKind.section,
    QwqMarkdownBlockKind.spacer => SemanticNodeKind.paragraph,
    QwqMarkdownBlockKind.horizontalRule => SemanticNodeKind.divider,
    QwqMarkdownBlockKind.table => SemanticNodeKind.table,
    QwqMarkdownBlockKind.groupedDirectory => SemanticNodeKind.groupedDirectory,
    QwqMarkdownBlockKind.definitionList => SemanticNodeKind.definitionList,
    QwqMarkdownBlockKind.footnote => SemanticNodeKind.footnoteDefinition,
    QwqMarkdownBlockKind.unsupported => SemanticNodeKind.unsupportedOpaque,
  };
}

DocumentEnvelope buildQwqSemanticEnvelope({
  required String source,
  required List<QwqMarkdownBlock> blocks,
  required List<QwqMarkdownAssetRef> assetRefs,
}) {
  final nodes = <SemanticNode>[];
  var scalarOffset = 0;
  for (final block in blocks) {
    final kind = semanticNodeKindForQwqBlock(block.kind);
    final descriptor = semanticDocumentNodeRegistry[kind]!;
    final raw = block.rawSource.isNotEmpty ? block.rawSource : block.text;
    final start = scalarOffset;
    scalarOffset += raw.runes.length;
    final anchor = SourceAnchor(
      origin: 'markdown',
      start: start,
      end: scalarOffset,
      selector: block.id,
    );
    final fingerprint = qwqSemanticFingerprint(
      '${kind.name}\u0000${block.text}\u0000$raw',
    );
    nodes.add(
      SemanticNode(
        nodeId: block.id,
        kind: kind,
        disposition: kind == SemanticNodeKind.unsupportedOpaque
            ? ProcessingDisposition.unsupportedOpaque
            : ProcessingDisposition.preserved,
        policyVersion: semanticDocumentCanonicalizationVersion,
        requiredCapabilities: descriptor.requiredCapabilities.toList(
          growable: false,
        ),
        losses: const <SemanticLoss>[],
        semanticFingerprint: fingerprint,
        sourceAnchor: anchor,
        rawSlice: raw,
        rawSliceFingerprint: qwqSemanticFingerprint(raw),
        attributes: <String, Object?>{'text': block.text, 'level': block.level},
        inlines: block.inlines
            .where((inline) => inline.start < inline.end)
            .map(
              (inline) => SemanticInline(
                kind: inline.kind,
                start: inline.start,
                end: inline.end,
                attributes: inline.toMap(),
              ),
            )
            .toList(growable: false),
      ),
    );
    scalarOffset += 1;
  }
  final required = <CapabilityId>{
    for (final node in nodes) ...node.requiredCapabilities,
  }.toList()..sort();
  final documentFingerprint = qwqSemanticFingerprint(
    nodes
        .map(
          (node) =>
              '${node.nodeId}:${node.kind.name}:${node.semanticFingerprint}',
        )
        .join('|'),
  );
  return DocumentEnvelope(
    schemaVersion: semanticDocumentSchemaVersion,
    dialectVersion: semanticDocumentDialectVersion,
    canonicalizationVersion: semanticDocumentCanonicalizationVersion,
    offsetEncoding: semanticDocumentOffsetEncoding,
    nodes: nodes,
    requiredCapabilities: required,
    assets: <String, SemanticAsset>{
      for (final asset in assetRefs)
        asset.assetId: SemanticAsset(
          id: asset.assetId,
          attributes: asset.toMap(),
        ),
    },
    sourceMap: <String, SourceAnchor>{
      for (final node in nodes) node.nodeId: node.sourceAnchor,
    },
    policyVersion: semanticDocumentCanonicalizationVersion,
    losses: const <SemanticLoss>[],
    semanticFingerprint: documentFingerprint,
    canonicalDigest: qwqSemanticFingerprint(source),
  );
}

Map<String, Object?> semanticEnvelopeValidationMap(DocumentEnvelope envelope) =>
    <String, Object?>{
      'schemaVersion': envelope.schemaVersion,
      'dialectVersion': envelope.dialectVersion,
      'canonicalizationVersion': envelope.canonicalizationVersion,
      'offsetEncoding': envelope.offsetEncoding,
      'nodes': envelope.nodes
          .map(
            (node) => <String, Object?>{
              'kind': node.kind.name,
              'disposition': node.disposition.name,
              'requiredCapabilities': node.requiredCapabilities,
              'inlines': node.inlines
                  .map(
                    (inline) => <String, Object?>{
                      'kind': inline.kind.name,
                      'start': inline.start,
                      'end': inline.end,
                    },
                  )
                  .toList(growable: false),
            },
          )
          .toList(growable: false),
      'requiredCapabilities': envelope.requiredCapabilities,
      'assets': envelope.assets,
      'sourceMap': envelope.sourceMap,
      'policyVersion': envelope.policyVersion,
      'losses': envelope.losses,
      'semanticFingerprint': envelope.semanticFingerprint,
      'canonicalDigest': envelope.canonicalDigest,
    };

String qwqSemanticFingerprint(String value) {
  var hash = 0x811c9dc5;
  for (final unit in value.codeUnits) {
    hash = ((hash ^ unit) * 0x01000193) & 0xffffffff;
  }
  return hash.toRadixString(16).padLeft(8, '0');
}

@immutable
class QwqMarkdownFrontMatter {
  const QwqMarkdownFrontMatter({
    this.title = '',
    this.summary = '',
    this.template = '',
    this.fontPreset = '',
    this.titleStyle = '',
    this.coverAssetId = '',
    this.coverImage = '',
    this.locationName = '',
    this.entityRefs = const <String>[],
    this.tagRefs = const <String>[],
    this.sourceUrls = const <String>[],
    this.visibility = '',
    this.assistantUsePolicy,
    this.extra = const <String, Object?>{},
  });

  factory QwqMarkdownFrontMatter.fromMap(Map<String, Object?> map) {
    final coverAssetId = _stringValue(map['cover_asset_id']);
    final coverImage = _stringValue(map['coverImage']);
    return QwqMarkdownFrontMatter(
      title: _stringValue(map['title']),
      summary: _stringValue(map['summary']),
      template: _stringValue(map['template']),
      fontPreset: _stringValue(map['fontPreset']),
      titleStyle: _stringValue(map['titleStyle']),
      coverAssetId: coverAssetId,
      coverImage: coverImage.isNotEmpty
          ? coverImage
          : (coverAssetId.isNotEmpty ? 'asset://$coverAssetId' : ''),
      locationName: _stringValue(map['locationName']),
      entityRefs: _stringListValue(map['entity_refs']),
      tagRefs: _stringListValue(map['tag_refs']),
      sourceUrls: _stringListValue(map['source_urls']),
      visibility: _stringValue(map['visibility']),
      assistantUsePolicy: _assistantUsePolicyValue(map['assistantUsePolicy']),
      extra: Map<String, Object?>.fromEntries(
        map.entries.where(
          (entry) => !_knownFrontMatterKeys.contains(entry.key),
        ),
      ),
    );
  }

  final String title;
  final String summary;
  final String template;
  final String fontPreset;
  final String titleStyle;
  final String coverAssetId;
  final String coverImage;
  final String locationName;
  final List<String> entityRefs;
  final List<String> tagRefs;
  final List<String> sourceUrls;
  final String visibility;
  final AssistantUsePolicy? assistantUsePolicy;
  final Map<String, Object?> extra;

  Map<String, Object?> toMap() {
    return <String, Object?>{
      if (title.isNotEmpty) 'title': title,
      if (summary.isNotEmpty) 'summary': summary,
      if (template.isNotEmpty) 'template': template,
      if (fontPreset.isNotEmpty) 'fontPreset': fontPreset,
      if (titleStyle.isNotEmpty) 'titleStyle': titleStyle,
      if (coverAssetId.isNotEmpty) 'cover_asset_id': coverAssetId,
      if (coverImage.isNotEmpty && coverAssetId.isEmpty)
        'coverImage': coverImage,
      if (locationName.isNotEmpty) 'locationName': locationName,
      if (entityRefs.isNotEmpty) 'entity_refs': entityRefs,
      if (tagRefs.isNotEmpty) 'tag_refs': tagRefs,
      if (sourceUrls.isNotEmpty) 'source_urls': sourceUrls,
      if (visibility.isNotEmpty) 'visibility': visibility,
      if (assistantUsePolicy != null)
        'assistantUsePolicy': assistantUsePolicy!.wireName,
      ...extra,
    };
  }
}

@immutable
class QwqMarkdownBlock {
  const QwqMarkdownBlock({
    required this.id,
    required this.kind,
    this.text = '',
    this.level = 0,
    this.language = '',
    this.listDepth = 0,
    this.textAlign = '',
    this.inlines = const <QwqMarkdownInline>[],
    this.assetRef,
    this.assetRefs = const <QwqMarkdownAssetRef>[],
    this.children = const <QwqMarkdownBlock>[],
    this.attributes = const <String, Object?>{},
    this.sourceStartLine = 0,
    this.sourceEndLine = 0,
    this.table,
    this.groupedDirectory,
    this.definitions = const <QwqMarkdownDefinition>[],
    this.footnote,
    this.rawSource = '',
    this.isReadOnly = false,
  });

  final String id;
  final QwqMarkdownBlockKind kind;
  final String text;
  final int level;
  final String language;

  /// 列表嵌套级别（0 = 顶层；两空格缩进为一级，最多 2 级）。
  final int listDepth;

  /// 段落对齐（'' 默认 / center / right），由 `:::align` 指令承载。
  final String textAlign;
  final List<QwqMarkdownInline> inlines;
  final QwqMarkdownAssetRef? assetRef;
  final List<QwqMarkdownAssetRef> assetRefs;
  final List<QwqMarkdownBlock> children;
  final Map<String, Object?> attributes;
  final int sourceStartLine;
  final int sourceEndLine;
  final QwqMarkdownTable? table;
  final QwqMarkdownGroupedDirectory? groupedDirectory;
  final List<QwqMarkdownDefinition> definitions;
  final QwqMarkdownFootnote? footnote;
  final String rawSource;
  final bool isReadOnly;

  bool get isRichLayout =>
      kind == QwqMarkdownBlockKind.figure ||
      kind == QwqMarkdownBlockKind.gallery ||
      kind == QwqMarkdownBlockKind.callout ||
      kind == QwqMarkdownBlockKind.card ||
      kind == QwqMarkdownBlockKind.section ||
      kind == QwqMarkdownBlockKind.spacer;

  Map<String, Object?> toMap() {
    return <String, Object?>{
      'id': id,
      'kind': kind.name,
      if (text.isNotEmpty) 'text': text,
      if (level > 0) 'level': level,
      if (language.isNotEmpty) 'language': language,
      if (inlines.isNotEmpty)
        'inlines': inlines
            .map((inline) => inline.toMap())
            .toList(growable: false),
      if (assetRef != null) 'assetRef': assetRef!.toMap(),
      if (assetRefs.isNotEmpty)
        'assetRefs': assetRefs
            .map((asset) => asset.toMap())
            .toList(growable: false),
      if (children.isNotEmpty)
        'children': children
            .map((child) => child.toMap())
            .toList(growable: false),
      if (attributes.isNotEmpty) 'attributes': attributes,
      if (sourceStartLine > 0) 'sourceStartLine': sourceStartLine,
      if (sourceEndLine > 0) 'sourceEndLine': sourceEndLine,
      if (table != null) 'table': table!.toMap(),
      if (groupedDirectory != null)
        'groupedDirectory': groupedDirectory!.toMap(),
      if (definitions.isNotEmpty)
        'definitions': definitions
            .map((e) => e.toMap())
            .toList(growable: false),
      if (footnote != null) 'footnote': footnote!.toMap(),
      if (rawSource.isNotEmpty) 'rawSource': rawSource,
      if (isReadOnly) 'isReadOnly': true,
    };
  }
}

@immutable
class QwqMarkdownInline {
  const QwqMarkdownInline({
    required this.kind,
    required this.text,
    this.href = '',
    this.start = 0,
    this.end = 0,
    this.bold = false,
    this.italic = false,
    this.underline = false,
    this.strikethrough = false,
    this.targetType = '',
    this.targetId = '',
  });

  final QwqMarkdownInlineKind kind;
  final String text;
  final String href;
  final int start;
  final int end;
  final bool bold;
  final bool italic;
  final bool underline;
  final bool strikethrough;
  final String targetType;
  final String targetId;

  Map<String, Object?> toMap() {
    return <String, Object?>{
      'kind': kind.name,
      'text': text,
      if (href.isNotEmpty) 'href': href,
      if (start > 0) 'start': start,
      if (end > 0) 'end': end,
      if (bold) 'bold': true,
      if (italic) 'italic': true,
      if (underline) 'underline': true,
      if (strikethrough) 'strikethrough': true,
      if (targetType.isNotEmpty) 'targetType': targetType,
      if (targetId.isNotEmpty) 'targetId': targetId,
    };
  }
}

@immutable
class QwqMarkdownAssetRef {
  const QwqMarkdownAssetRef({
    required this.assetId,
    this.kind = QwqMarkdownAssetKind.image,
    this.layout = QwqMarkdownImageLayout.fullWidth,
    this.caption = '',
    this.alt = '',
    this.sourceUrl = '',
    this.width,
    this.height,
  });

  factory QwqMarkdownAssetRef.fromAssetUri(
    String value, {
    QwqMarkdownImageLayout layout = QwqMarkdownImageLayout.fullWidth,
    String caption = '',
    String alt = '',
  }) {
    final trimmed = value.trim();
    final assetId = trimmed.startsWith('asset://')
        ? trimmed.substring('asset://'.length)
        : trimmed;
    return QwqMarkdownAssetRef(
      assetId: assetId,
      layout: layout,
      caption: caption,
      alt: alt,
    );
  }

  final String assetId;
  final QwqMarkdownAssetKind kind;
  final QwqMarkdownImageLayout layout;
  final String caption;
  final String alt;
  final String sourceUrl;
  final int? width;
  final int? height;

  Map<String, Object?> toMap() {
    return <String, Object?>{
      'assetId': assetId,
      'kind': kind.name,
      'layout': layout.name,
      if (caption.isNotEmpty) 'caption': caption,
      if (alt.isNotEmpty) 'alt': alt,
      if (sourceUrl.isNotEmpty) 'sourceUrl': sourceUrl,
      if (width != null) 'width': width,
      if (height != null) 'height': height,
    };
  }
}

@immutable
class QwqMarkdownTable {
  const QwqMarkdownTable({
    required this.rows,
    this.alignment = const <String>[],
  });
  final List<List<String>> rows;
  final List<String> alignment;
  int get columnCount =>
      rows.fold<int>(0, (value, row) => mathMax(value, row.length));
  List<List<String>> get logicalGrid => rows
      .map(
        (row) => <String>[
          ...row,
          ...List<String>.filled(columnCount - row.length, ''),
        ],
      )
      .toList(growable: false);
  Map<String, Object?> toMap() => <String, Object?>{
    'rows': rows,
    'alignment': alignment,
  };
}

@immutable
class QwqMarkdownGroupedDirectory {
  const QwqMarkdownGroupedDirectory({required this.groups});
  final Map<String, List<String>> groups;
  Map<String, Object?> toMap() => <String, Object?>{'groups': groups};
}

@immutable
class QwqMarkdownDefinition {
  const QwqMarkdownDefinition({required this.term, required this.definition});
  final String term;
  final String definition;
  Map<String, Object?> toMap() => <String, Object?>{
    'term': term,
    'definition': definition,
  };
}

@immutable
class QwqMarkdownFootnote {
  const QwqMarkdownFootnote({required this.label, required this.text});
  final String label;
  final String text;
  Map<String, Object?> toMap() => <String, Object?>{
    'label': label,
    'text': text,
  };
}

int mathMax(int left, int right) => left > right ? left : right;

@immutable
class QwqMarkdownDiagnostic {
  const QwqMarkdownDiagnostic({
    required this.code,
    required this.message,
    this.line = 0,
    this.isBlocking = false,
  });

  final String code;
  final String message;
  final int line;
  final bool isBlocking;

  Map<String, Object?> toMap() {
    return <String, Object?>{
      'code': code,
      'message': message,
      if (line > 0) 'line': line,
      'isBlocking': isBlocking,
    };
  }
}

const Set<String> _knownFrontMatterKeys = <String>{
  'title',
  'summary',
  'template',
  'fontPreset',
  'titleStyle',
  'cover_asset_id',
  'coverImage',
  'locationName',
  'entity_refs',
  'tag_refs',
  'source_urls',
  'visibility',
  'assistantUsePolicy',
  'markdownDialect',
};

String _stringValue(Object? value) => value?.toString().trim() ?? '';

/// front matter 里的 `assistantUsePolicy` 只认 canonical 取值；键缺失表示未声明，
/// 非法取值必须在解析阶段就被拒绝，不得退化成裸文本继续流转。
AssistantUsePolicy? _assistantUsePolicyValue(Object? value) {
  final text = _stringValue(value);
  if (text.isEmpty) return null;
  return AssistantUsePolicy.fromWire(
    text,
    'QwqMarkdownFrontMatter.assistantUsePolicy',
  );
}

List<String> _stringListValue(Object? value) {
  if (value is Iterable) {
    return value
        .map((item) => item.toString().trim())
        .where((item) => item.isNotEmpty)
        .toList(growable: false);
  }
  final single = _stringValue(value);
  return single.isEmpty ? const <String>[] : <String>[single];
}
