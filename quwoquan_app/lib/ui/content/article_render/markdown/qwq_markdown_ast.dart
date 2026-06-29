import 'package:flutter/foundation.dart';

const String qwqRichMarkdownVersion = 'qwq-rich-md/1';

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
}

enum QwqMarkdownInlineKind { text, emphasis, strong, link, code }

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
  });

  final String source;
  final String version;
  final QwqMarkdownFrontMatter frontMatter;
  final List<QwqMarkdownBlock> blocks;
  final List<QwqMarkdownAssetRef> assetRefs;
  final List<QwqMarkdownDiagnostic> diagnostics;

  bool get hasBlockingDiagnostics =>
      diagnostics.any((diagnostic) => diagnostic.isBlocking);

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
      'diagnostics': diagnostics
          .map((diagnostic) => diagnostic.toMap())
          .toList(growable: false),
    };
  }
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
    this.assistantUsePolicy = '',
    this.extra = const <String, Object?>{},
  });

  factory QwqMarkdownFrontMatter.fromMap(Map<String, Object?> map) {
    final coverAssetId = _stringValue(
      map['cover_asset_id'] ?? map['coverAssetId'],
    );
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
      entityRefs: _stringListValue(map['entity_refs'] ?? map['entityRefs']),
      tagRefs: _stringListValue(map['tag_refs'] ?? map['tagRefs']),
      sourceUrls: _stringListValue(map['source_urls'] ?? map['sourceUrls']),
      visibility: _stringValue(map['visibility']),
      assistantUsePolicy: _stringValue(map['assistantUsePolicy']),
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
  final String assistantUsePolicy;
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
      if (assistantUsePolicy.isNotEmpty)
        'assistantUsePolicy': assistantUsePolicy,
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
    this.inlines = const <QwqMarkdownInline>[],
    this.assetRef,
    this.assetRefs = const <QwqMarkdownAssetRef>[],
    this.children = const <QwqMarkdownBlock>[],
    this.attributes = const <String, Object?>{},
    this.sourceStartLine = 0,
    this.sourceEndLine = 0,
  });

  final String id;
  final QwqMarkdownBlockKind kind;
  final String text;
  final int level;
  final String language;
  final List<QwqMarkdownInline> inlines;
  final QwqMarkdownAssetRef? assetRef;
  final List<QwqMarkdownAssetRef> assetRefs;
  final List<QwqMarkdownBlock> children;
  final Map<String, Object?> attributes;
  final int sourceStartLine;
  final int sourceEndLine;

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
    };
  }
}

@immutable
class QwqMarkdownInline {
  const QwqMarkdownInline({
    required this.kind,
    required this.text,
    this.href = '',
  });

  final QwqMarkdownInlineKind kind;
  final String text;
  final String href;

  Map<String, Object?> toMap() {
    return <String, Object?>{
      'kind': kind.name,
      'text': text,
      if (href.isNotEmpty) 'href': href,
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
  'coverAssetId',
  'coverImage',
  'locationName',
  'entity_refs',
  'entityRefs',
  'tag_refs',
  'tagRefs',
  'source_urls',
  'sourceUrls',
  'visibility',
  'assistantUsePolicy',
};

String _stringValue(Object? value) => value?.toString().trim() ?? '';

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
