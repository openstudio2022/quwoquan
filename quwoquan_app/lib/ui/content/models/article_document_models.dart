import 'package:flutter/foundation.dart';

enum ArticleDocumentNodeType {
  documentTitle,
  headingMajor,
  headingMinor,
  paragraph,
  orderedItem,
  bulletItem,
  figure,
}

enum ArticleDocumentTitleStyle { none, major, minor }

enum ArticleDocumentBlockType {
  paragraph,
  heading2,
  heading3,
  sectionTitle,
  orderedItem,
  bulletItem,
  image,
}

String _normalizeArticleText(String value) {
  return value.replaceAll('\r\n', '\n');
}

@immutable
class ArticleDocumentNode {
  const ArticleDocumentNode({
    required this.id,
    required this.type,
    this.text = '',
    this.assetId = '',
    this.imageUrl = '',
    this.imageLayout = 'fullWidth',
    this.caption = '',
    this.textAlign = '',
    this.listDepth = 0,
    this.spans = const <ArticleInlineSpan>[],
  });

  factory ArticleDocumentNode.fromMap(Map<String, dynamic> map) {
    final typeName = (map['type'] ?? 'paragraph').toString().trim();
    final type = switch (typeName) {
      'documentTitle' || 'title' => ArticleDocumentNodeType.documentTitle,
      'headingMajor' ||
      'heading2' ||
      'sectionTitle' => ArticleDocumentNodeType.headingMajor,
      'headingMinor' || 'heading3' => ArticleDocumentNodeType.headingMinor,
      'orderedItem' => ArticleDocumentNodeType.orderedItem,
      'bulletItem' => ArticleDocumentNodeType.bulletItem,
      'figure' || 'image' => ArticleDocumentNodeType.figure,
      _ => ArticleDocumentNodeType.paragraph,
    };
    final spansRaw = (map['spans'] as List?) ?? const <Object?>[];
    final spans = spansRaw
        .whereType<Map>()
        .map(
          (entry) =>
              ArticleInlineSpan.fromMap(Map<String, dynamic>.from(entry)),
        )
        .toList(growable: false);
    return ArticleDocumentNode(
      id: (map['id'] ?? '').toString(),
      type: type,
      text: (map['text'] ?? '').toString(),
      assetId: (map['assetId'] ?? '').toString(),
      imageUrl: (map['imageUrl'] ?? '').toString(),
      imageLayout: (map['imageLayout'] ?? 'fullWidth').toString(),
      caption: (map['caption'] ?? '').toString(),
      textAlign: (map['textAlign'] ?? '').toString(),
      listDepth: (map['listDepth'] as num?)?.toInt() ?? 0,
      spans: spans,
    );
  }

  final String id;
  final ArticleDocumentNodeType type;
  final String text;
  final String assetId;
  final String imageUrl;
  final String imageLayout;
  final String caption;
  final String textAlign;
  final int listDepth;
  final List<ArticleInlineSpan> spans;

  bool get hasText => text.trim().isNotEmpty;
  bool get hasImage => imageUrl.trim().isNotEmpty;
  bool get isDocumentTitle => type == ArticleDocumentNodeType.documentTitle;
  bool get isHeading =>
      type == ArticleDocumentNodeType.headingMajor ||
      type == ArticleDocumentNodeType.headingMinor;
  bool get isFigure => type == ArticleDocumentNodeType.figure;
  bool get isBodyText =>
      type == ArticleDocumentNodeType.paragraph ||
      type == ArticleDocumentNodeType.orderedItem ||
      type == ArticleDocumentNodeType.bulletItem;
  bool get usesWrappedLayout =>
      imageLayout == 'wrapLeft' || imageLayout == 'wrapRight';

  ArticleDocumentNode copyWith({
    String? id,
    ArticleDocumentNodeType? type,
    String? text,
    String? assetId,
    String? imageUrl,
    String? imageLayout,
    String? caption,
    String? textAlign,
    int? listDepth,
    List<ArticleInlineSpan>? spans,
  }) {
    return ArticleDocumentNode(
      id: id ?? this.id,
      type: type ?? this.type,
      text: text ?? this.text,
      assetId: assetId ?? this.assetId,
      imageUrl: imageUrl ?? this.imageUrl,
      imageLayout: imageLayout ?? this.imageLayout,
      caption: caption ?? this.caption,
      textAlign: textAlign ?? this.textAlign,
      listDepth: listDepth ?? this.listDepth,
      spans: spans ?? this.spans,
    );
  }

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      'id': id,
      'type': type.name,
      if (hasText) 'text': text,
      if (assetId.trim().isNotEmpty) 'assetId': assetId,
      if (hasImage) 'imageUrl': imageUrl,
      if (isFigure) 'imageLayout': imageLayout,
      if (caption.trim().isNotEmpty) 'caption': caption,
      if (textAlign.trim().isNotEmpty) 'textAlign': textAlign,
      if (listDepth > 0) 'listDepth': listDepth,
      if (spans.isNotEmpty)
        'spans': spans.map((span) => span.toMap()).toList(growable: false),
    };
  }
}

@immutable
class ArticleWrapNodeGroup {
  const ArticleWrapNodeGroup({
    required this.figureIndex,
    required this.figure,
    this.narrowParagraph,
    this.belowParagraph,
  });

  final int figureIndex;
  final ArticleDocumentNode figure;
  final ArticleDocumentNode? narrowParagraph;
  final ArticleDocumentNode? belowParagraph;

  String get assetId =>
      figure.assetId.trim().isNotEmpty ? figure.assetId : figure.id;
  String get narrowText => narrowParagraph?.text ?? '';
  String get belowText => belowParagraph?.text ?? '';
  String get combinedText => '$narrowText$belowText';
  bool get hasBothParagraphs =>
      narrowParagraph != null && belowParagraph != null;
  Set<String> get paragraphNodeIds => <String>{
    if (narrowParagraph != null && narrowParagraph!.id.trim().isNotEmpty)
      narrowParagraph!.id,
    if (belowParagraph != null && belowParagraph!.id.trim().isNotEmpty)
      belowParagraph!.id,
  };
}

List<ArticleWrapNodeGroup> resolveArticleWrapNodeGroups(
  List<ArticleDocumentNode> nodes,
) {
  final groups = <ArticleWrapNodeGroup>[];
  for (var index = 0; index < nodes.length; index += 1) {
    final node = nodes[index];
    if (!node.isFigure || !node.usesWrappedLayout) {
      continue;
    }
    ArticleDocumentNode? narrowParagraph;
    ArticleDocumentNode? belowParagraph;
    if (index + 1 < nodes.length &&
        _isWrapParagraphCandidate(nodes[index + 1])) {
      narrowParagraph = nodes[index + 1];
      if (index + 2 < nodes.length &&
          _isWrapParagraphCandidate(nodes[index + 2])) {
        belowParagraph = nodes[index + 2];
      }
    }
    groups.add(
      ArticleWrapNodeGroup(
        figureIndex: index,
        figure: node,
        narrowParagraph: narrowParagraph,
        belowParagraph: belowParagraph,
      ),
    );
  }
  return groups;
}

ArticleWrapNodeGroup? resolveArticleWrapNodeGroupByFigureId(
  List<ArticleDocumentNode> nodes,
  String figureNodeId,
) {
  final targetId = figureNodeId.trim();
  if (targetId.isEmpty) {
    return null;
  }
  for (final group in resolveArticleWrapNodeGroups(nodes)) {
    if (group.figure.id == targetId) {
      return group;
    }
  }
  return null;
}

Map<String, ArticleWrapNodeGroup> buildArticleWrapNodeGroupsByAssetId(
  List<ArticleDocumentNode> nodes,
) {
  return <String, ArticleWrapNodeGroup>{
    for (final group in resolveArticleWrapNodeGroups(nodes))
      group.assetId: group,
  };
}

bool _isWrapParagraphCandidate(ArticleDocumentNode node) {
  return node.type == ArticleDocumentNodeType.paragraph;
}

/// 行内样式 span（与 contracts/metadata/content/post/article_document_schema.yaml 对齐）
@immutable
class ArticleInlineSpan {
  const ArticleInlineSpan({
    required this.start,
    required this.end,
    this.bold = false,
    this.italic = false,
    this.underline = false,
    this.strikethrough = false,
    this.kind = 'text',
    this.targetType,
    this.targetId,
    this.displayText,
  });

  factory ArticleInlineSpan.fromMap(Map<String, dynamic> map) {
    return ArticleInlineSpan(
      start: (map['start'] as num?)?.toInt() ?? 0,
      end: (map['end'] as num?)?.toInt() ?? 0,
      bold: map['bold'] == true,
      italic: map['italic'] == true,
      underline: map['underline'] == true,
      strikethrough: map['strikethrough'] == true,
      kind: (map['kind'] ?? 'text').toString(),
      targetType: map['targetType']?.toString(),
      targetId: map['targetId']?.toString(),
      displayText: map['displayText']?.toString(),
    );
  }

  final int start;
  final int end;
  final bool bold;
  final bool italic;
  final bool underline;
  final bool strikethrough;
  final String kind;
  final String? targetType;
  final String? targetId;
  final String? displayText;

  bool get isEntity =>
      kind == 'entity' &&
      (targetType ?? '').trim().isNotEmpty &&
      (targetId ?? '').trim().isNotEmpty;

  bool get isTag =>
      kind == 'tag' &&
      (targetType ?? '').trim().isNotEmpty &&
      (targetId ?? '').trim().isNotEmpty;

  /// 正文内联可点击 mention（实体或标签），渲染与序列化统一以此判定。
  bool get isInlineMention => isEntity || isTag;

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      'start': start,
      'end': end,
      if (bold) 'bold': true,
      if (italic) 'italic': true,
      if (underline) 'underline': true,
      if (strikethrough) 'strikethrough': true,
      if (kind != 'text') 'kind': kind,
      if (targetType != null) 'targetType': targetType,
      if (targetId != null) 'targetId': targetId,
      if (displayText != null) 'displayText': displayText,
    };
  }
}

@immutable
class ArticleDocumentBlock {
  const ArticleDocumentBlock({
    required this.id,
    required this.type,
    this.offset = 0,
    this.text = '',
    this.imageUrl = '',
    this.imageLayout = 'fullWidth',
    this.caption = '',
    this.orderedIndex,
    this.textAlign = '',
    this.listDepth = 0,
    this.spans = const <ArticleInlineSpan>[],
  });

  final String id;
  final ArticleDocumentBlockType type;
  final int offset;
  final String text;
  final String imageUrl;
  final String imageLayout;
  final String caption;
  final int? orderedIndex;

  /// start | center | end | justify（空表示默认）
  final String textAlign;

  /// 有序/无序嵌套深度 1–3（0 表示非列表块或未设置）
  final int listDepth;
  final List<ArticleInlineSpan> spans;

  bool get isTextLike => type != ArticleDocumentBlockType.image;
  bool get hasText => text.trim().isNotEmpty;
  bool get hasImage => imageUrl.trim().isNotEmpty;
  bool get usesWrappedLayout =>
      imageLayout == 'wrapLeft' || imageLayout == 'wrapRight';
}

@immutable
class ArticleDocumentAsset {
  const ArticleDocumentAsset({
    required this.id,
    required this.offset,
    this.imageUrl = '',
    this.imageLayout = 'fullWidth',
    this.caption = '',
  });

  final String id;
  final int offset;
  final String imageUrl;
  final String imageLayout;
  final String caption;

  bool get hasImage => imageUrl.trim().isNotEmpty;
  bool get usesWrappedLayout =>
      imageLayout == 'wrapLeft' || imageLayout == 'wrapRight';
}

@immutable
class ArticleDocumentData {
  /// 文章文档数据。
  ///
  /// [nodes] 是唯一编辑真相源；[title]、[body]、[assets]、[blocks] 均为只读投影。
  ArticleDocumentData({
    List<ArticleDocumentNode> nodes = const <ArticleDocumentNode>[],
    this.template = 'gentle',
    this.fontPreset = 'clean',
    this.coverImageUrl = '',
    this.titleStyle = ArticleDocumentTitleStyle.major,
  }) : nodes = _normalizeDocumentNodes(nodes);

  /// 从 canonical nodes JSON 构造。
  factory ArticleDocumentData.fromMap(Map<String, dynamic> map) {
    final nodeEntries = ((map['nodes'] as List?) ?? const <Object?>[])
        .whereType<Map>()
        .map(
          (entry) =>
              ArticleDocumentNode.fromMap(Map<String, dynamic>.from(entry)),
        )
        .where(
          (node) =>
              node.id.trim().isNotEmpty &&
              (node.hasText ||
                  node.hasImage ||
                  node.isDocumentTitle ||
                  node.type == ArticleDocumentNodeType.paragraph),
        )
        .toList(growable: false);
    final template = (map['template'] ?? 'gentle').toString();
    final fontPreset = (map['fontPreset'] ?? 'clean').toString();
    final coverImageUrl = (map['coverImageUrl'] ?? '').toString().trim();
    final titleStyle = ArticleDocumentTitleStyle.values.firstWhere(
      (s) => s.name == (map['titleStyle'] ?? '').toString(),
      orElse: () => ArticleDocumentTitleStyle.major,
    );

    return ArticleDocumentData(
      nodes: nodeEntries,
      template: template,
      fontPreset: fontPreset,
      coverImageUrl: coverImageUrl,
      titleStyle: titleStyle,
    );
  }

  final List<ArticleDocumentNode> nodes;
  final String template;
  final String fontPreset;
  final String coverImageUrl;
  final ArticleDocumentTitleStyle titleStyle;

  /// 从 [nodes] 自动投影的只读属性。不要用这些值反向驱动编辑。
  late final _ArticleDocumentProjection _projection = _projectArticleDocument(
    nodes,
  );

  /// 只读投影：文档标题（从 nodes 中 documentTitle 节点派生）。
  String get title => _projection.title;

  /// 只读投影：正文纯文本（从 nodes 中正文类节点按行拼接，不含图片语义）。
  String get body => _projection.body;

  /// 只读投影：图片资产列表（从 nodes 中 figure 节点派生）。
  List<ArticleDocumentAsset> get assets => _projection.assets;

  /// 只读投影：仅含 heading/sectionTitle/image 类型（供外部结构查询）。
  List<ArticleDocumentBlock> get blocks => _projection.blocks;

  /// 含所有类型（包括 paragraph），供内容块投射使用。
  List<ArticleDocumentBlock> get contentBlocks => _projection.allBlocks;
  ArticleDocumentNode? get titleNode => _projection.titleNode;

  bool get hasTitle => title.trim().isNotEmpty;
  bool get hasBody =>
      body.trim().isNotEmpty ||
      nodes.any((node) => node.isBodyText && node.hasText);
  bool get hasAssets => assets.any((asset) => asset.hasImage);
  bool get hasBlocks => nodes.any((node) => node.isHeading || node.isFigure);
  bool get hasStructuredTextBlocks => nodes.any((node) => node.isHeading);
  bool get isEmpty => nodes.isEmpty && coverImageUrl.trim().isEmpty;

  /// 复制并修改文档。
  ///
  /// 内容变更只能显式传入 [nodes]；投影字段不能反向改写文档。
  ArticleDocumentData copyWith({
    List<ArticleDocumentNode>? nodes,
    String? template,
    String? fontPreset,
    String? coverImageUrl,
    ArticleDocumentTitleStyle? titleStyle,
  }) {
    return ArticleDocumentData(
      nodes: nodes ?? this.nodes,
      template: template ?? this.template,
      fontPreset: fontPreset ?? this.fontPreset,
      coverImageUrl: coverImageUrl ?? this.coverImageUrl,
      titleStyle: titleStyle ?? this.titleStyle,
    );
  }

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      'nodes': nodes.map((node) => node.toMap()).toList(growable: false),
      'template': template,
      'fontPreset': fontPreset,
      'coverImageUrl': coverImageUrl,
      'titleStyle': titleStyle.name,
    };
  }
}

@immutable
class ArticleTextRange {
  const ArticleTextRange({required this.start, required this.end});

  final int start;
  final int end;

  bool get isCollapsed => start >= end;

  ArticleTextRange copyWith({int? start, int? end}) {
    return ArticleTextRange(start: start ?? this.start, end: end ?? this.end);
  }
}

@immutable
class ArticlePageBinding {
  const ArticlePageBinding({
    this.titleRange,
    this.bodyRange,
    this.assetId,
    this.assetOffset,
    this.pageAssetIds,
    required this.insertOffset,
  });

  final ArticleTextRange? titleRange;
  final ArticleTextRange? bodyRange;
  final String? assetId;
  final int? assetOffset;

  /// 同一分页卡片内多张通栏图时，与 [assetId]（首张）一并列出；单图时为 null。
  final List<String>? pageAssetIds;
  final int insertOffset;

  bool get hasTitleSlice => titleRange != null && !titleRange!.isCollapsed;
  bool get hasBodySlice => bodyRange != null && !bodyRange!.isCollapsed;

  List<String> get resolvedAssetIds {
    if (pageAssetIds != null && pageAssetIds!.isNotEmpty) {
      return pageAssetIds!;
    }
    if (assetId != null && assetId!.trim().isNotEmpty) {
      return <String>[assetId!];
    }
    return const <String>[];
  }

  bool get hasAsset => resolvedAssetIds.isNotEmpty;
}

List<ArticleDocumentNode> _normalizeDocumentNodes(
  List<ArticleDocumentNode> nodes,
) {
  return nodes
      .where(
        (node) =>
            node.id.trim().isNotEmpty &&
            (node.hasText ||
                node.hasImage ||
                node.isDocumentTitle ||
                node.type == ArticleDocumentNodeType.paragraph),
      )
      .map(
        (node) => node.copyWith(
          text: _normalizeArticleText(node.text),
          imageUrl: node.imageUrl.trim(),
          caption: node.caption.trim(),
        ),
      )
      .toList(growable: false);
}

class _ArticleDocumentProjection {
  const _ArticleDocumentProjection({
    required this.title,
    required this.titleNode,
    required this.body,
    required this.assets,
    required this.blocks,
    required this.allBlocks,
  });

  final String title;
  final ArticleDocumentNode? titleNode;
  final String body;
  final List<ArticleDocumentAsset> assets;

  /// 仅含 heading/sectionTitle/image 类型，供外部 `document.blocks` 使用。
  final List<ArticleDocumentBlock> blocks;

  /// 含所有类型（包括 paragraph），供内容块投射使用。
  final List<ArticleDocumentBlock> allBlocks;
}

_ArticleDocumentProjection _projectArticleDocument(
  List<ArticleDocumentNode> nodes,
) {
  final titleNode = nodes.firstWhere(
    (node) => node.isDocumentTitle,
    orElse: () => const ArticleDocumentNode(
      id: '',
      type: ArticleDocumentNodeType.documentTitle,
    ),
  );
  final bodyBuffer = StringBuffer();
  final assets = <ArticleDocumentAsset>[];
  final blocks = <ArticleDocumentBlock>[];
  final allBlocks = <ArticleDocumentBlock>[];
  var orderedIndex = 0;
  final joinedWrapBelowParagraphIds = resolveArticleWrapNodeGroups(
    nodes,
  ).map((group) => group.belowParagraph?.id).whereType<String>().toSet();

  void appendBodyText(String line, {bool separateLine = true}) {
    final normalized = line.trim();
    if (normalized.isEmpty) {
      return;
    }
    if (separateLine && bodyBuffer.isNotEmpty) {
      bodyBuffer.write('\n');
    }
    bodyBuffer.write(normalized);
  }

  for (final node in nodes) {
    if (node.isDocumentTitle) {
      continue;
    }
    switch (node.type) {
      case ArticleDocumentNodeType.documentTitle:
        break;
      case ArticleDocumentNodeType.headingMajor:
        orderedIndex = 0;
        {
          final b = ArticleDocumentBlock(
            id: node.id,
            type: ArticleDocumentBlockType.heading2,
            offset: bodyBuffer.length,
            text: node.text,
            textAlign: node.textAlign,
            listDepth: node.listDepth,
            spans: node.spans,
          );
          blocks.add(b);
          allBlocks.add(b);
        }
        break;
      case ArticleDocumentNodeType.headingMinor:
        orderedIndex = 0;
        {
          final b = ArticleDocumentBlock(
            id: node.id,
            type: ArticleDocumentBlockType.heading3,
            offset: bodyBuffer.length,
            text: node.text,
            textAlign: node.textAlign,
            listDepth: node.listDepth,
            spans: node.spans,
          );
          blocks.add(b);
          allBlocks.add(b);
        }
        break;
      case ArticleDocumentNodeType.paragraph:
        orderedIndex = 0;
        if (node.text.trim().isNotEmpty) {
          final b = ArticleDocumentBlock(
            id: node.id,
            type: ArticleDocumentBlockType.paragraph,
            offset: bodyBuffer.length,
            text: node.text,
            textAlign: node.textAlign,
            spans: node.spans,
          );
          if (node.spans.any((span) => span.isInlineMention)) {
            blocks.add(b);
          }
          allBlocks.add(b);
        }
        appendBodyText(
          node.text,
          separateLine: !joinedWrapBelowParagraphIds.contains(node.id),
        );
        break;
      case ArticleDocumentNodeType.orderedItem:
        orderedIndex += 1;
        appendBodyText('$orderedIndex. ${node.text.trim()}');
        break;
      case ArticleDocumentNodeType.bulletItem:
        orderedIndex = 0;
        appendBodyText(node.text.trim().isEmpty ? '' : '• ${node.text.trim()}');
        break;
      case ArticleDocumentNodeType.figure:
        orderedIndex = 0;
        assets.add(
          ArticleDocumentAsset(
            id: node.assetId.trim().isNotEmpty ? node.assetId : node.id,
            offset: bodyBuffer.length,
            imageUrl: node.imageUrl,
            imageLayout: node.imageLayout,
            caption: node.caption,
          ),
        );
        {
          final b = ArticleDocumentBlock(
            id: node.id,
            type: ArticleDocumentBlockType.image,
            offset: bodyBuffer.length,
            imageUrl: node.imageUrl,
            imageLayout: node.imageLayout,
            caption: node.caption,
          );
          blocks.add(b);
          allBlocks.add(b);
        }
        break;
    }
  }

  final resolvedTitle = titleNode.id.isEmpty ? '' : titleNode.text.trim();
  return _ArticleDocumentProjection(
    title: resolvedTitle,
    titleNode: titleNode.id.isEmpty ? null : titleNode,
    body: bodyBuffer.toString(),
    assets: assets,
    blocks: blocks,
    allBlocks: allBlocks,
  );
}
