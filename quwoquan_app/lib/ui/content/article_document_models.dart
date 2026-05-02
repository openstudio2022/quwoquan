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

final RegExp _orderedArticleLinePattern = RegExp(r'^\s*(\d+)[\.\u3001]\s+');
final RegExp _bulletArticleLinePattern = RegExp(r'^\s*[•\-]\s+');

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
      imageUrl: (map['imageUrl'] ?? map['imagePath'] ?? '').toString(),
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
  });

  factory ArticleInlineSpan.fromMap(Map<String, dynamic> map) {
    return ArticleInlineSpan(
      start: (map['start'] as num?)?.toInt() ?? 0,
      end: (map['end'] as num?)?.toInt() ?? 0,
      bold: map['bold'] == true,
      italic: map['italic'] == true,
      underline: map['underline'] == true,
      strikethrough: map['strikethrough'] == true,
    );
  }

  final int start;
  final int end;
  final bool bold;
  final bool italic;
  final bool underline;
  final bool strikethrough;

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      'start': start,
      'end': end,
      if (bold) 'bold': true,
      if (italic) 'italic': true,
      if (underline) 'underline': true,
      if (strikethrough) 'strikethrough': true,
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

  factory ArticleDocumentBlock.fromMap(Map<String, dynamic> map) {
    final typeName = (map['type'] ?? 'paragraph').toString().trim();
    final type = switch (typeName) {
      'heading2' => ArticleDocumentBlockType.heading2,
      'heading3' => ArticleDocumentBlockType.heading3,
      'sectionTitle' => ArticleDocumentBlockType.sectionTitle,
      'orderedItem' => ArticleDocumentBlockType.orderedItem,
      'bulletItem' => ArticleDocumentBlockType.bulletItem,
      'image' => ArticleDocumentBlockType.image,
      _ => ArticleDocumentBlockType.paragraph,
    };
    final spansRaw = (map['spans'] as List?) ?? const <Object?>[];
    final spans = spansRaw
        .whereType<Map>()
        .map((e) => ArticleInlineSpan.fromMap(Map<String, dynamic>.from(e)))
        .toList(growable: false);
    return ArticleDocumentBlock(
      id: (map['id'] ?? '').toString(),
      type: type,
      offset: (map['offset'] as num?)?.toInt() ?? 0,
      text: (map['text'] ?? '').toString(),
      imageUrl: (map['imageUrl'] ?? map['imagePath'] ?? '').toString(),
      imageLayout: (map['imageLayout'] ?? 'fullWidth').toString(),
      caption: (map['caption'] ?? '').toString(),
      orderedIndex: (map['orderedIndex'] as num?)?.toInt(),
      textAlign: (map['textAlign'] ?? '').toString(),
      listDepth: (map['listDepth'] as num?)?.toInt() ?? 0,
      spans: spans,
    );
  }

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

  ArticleDocumentBlock copyWith({
    String? id,
    ArticleDocumentBlockType? type,
    int? offset,
    String? text,
    String? imageUrl,
    String? imageLayout,
    String? caption,
    int? orderedIndex,
    String? textAlign,
    int? listDepth,
    List<ArticleInlineSpan>? spans,
  }) {
    return ArticleDocumentBlock(
      id: id ?? this.id,
      type: type ?? this.type,
      offset: offset ?? this.offset,
      text: text ?? this.text,
      imageUrl: imageUrl ?? this.imageUrl,
      imageLayout: imageLayout ?? this.imageLayout,
      caption: caption ?? this.caption,
      orderedIndex: orderedIndex ?? this.orderedIndex,
      textAlign: textAlign ?? this.textAlign,
      listDepth: listDepth ?? this.listDepth,
      spans: spans ?? this.spans,
    );
  }

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      'id': id,
      'type': type.name,
      'offset': offset,
      'text': text,
      'imageUrl': imageUrl,
      'imageLayout': imageLayout,
      'caption': caption,
      if (orderedIndex != null) 'orderedIndex': orderedIndex,
      if (textAlign.isNotEmpty) 'textAlign': textAlign,
      if (listDepth > 0) 'listDepth': listDepth,
      if (spans.isNotEmpty)
        'spans': spans.map((s) => s.toMap()).toList(growable: false),
    };
  }
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

  factory ArticleDocumentAsset.fromMap(Map<String, dynamic> map) {
    return ArticleDocumentAsset(
      id: (map['id'] ?? '').toString(),
      offset: (map['offset'] as num?)?.toInt() ?? 0,
      imageUrl: (map['imageUrl'] ?? map['imagePath'] ?? '').toString(),
      imageLayout: (map['imageLayout'] ?? 'fullWidth').toString(),
      caption: (map['caption'] ?? '').toString(),
    );
  }

  final String id;
  final int offset;
  final String imageUrl;
  final String imageLayout;
  final String caption;

  bool get hasImage => imageUrl.trim().isNotEmpty;
  bool get usesWrappedLayout =>
      imageLayout == 'wrapLeft' || imageLayout == 'wrapRight';

  ArticleDocumentAsset copyWith({
    String? id,
    int? offset,
    String? imageUrl,
    String? imageLayout,
    String? caption,
  }) {
    return ArticleDocumentAsset(
      id: id ?? this.id,
      offset: offset ?? this.offset,
      imageUrl: imageUrl ?? this.imageUrl,
      imageLayout: imageLayout ?? this.imageLayout,
      caption: caption ?? this.caption,
    );
  }

  Map<String, dynamic> toMap() {
    return <String, dynamic>{
      'id': id,
      'offset': offset,
      'imageUrl': imageUrl,
      'imageLayout': imageLayout,
      'caption': caption,
    };
  }
}

@immutable
class ArticleDocumentData {
  /// 文章文档数据。
  ///
  /// [nodes] 是唯一编辑真相源。当 [nodes] 非空时，[title]、[body]、[assets]、
  /// [blocks] 均从 [nodes] 自动投影派生，外部传入的同名参数会被忽略。
  ///
  /// 当 [nodes] 为空时（兼容旧格式反序列化），会从 [title]、[body]、[assets]、
  /// [blocks] 反向构建 [nodes]。新代码应始终传入 [nodes]。
  ArticleDocumentData({
    List<ArticleDocumentNode> nodes = const <ArticleDocumentNode>[],
    this.template = 'gentle',
    this.fontPreset = 'clean',
    this.coverImageUrl = '',
    this.titleStyle = ArticleDocumentTitleStyle.major,
    String title = '',
    String body = '',
    List<ArticleDocumentAsset> assets = const <ArticleDocumentAsset>[],
    List<ArticleDocumentBlock> blocks = const <ArticleDocumentBlock>[],
  }) : nodes = nodes.isNotEmpty
           ? _normalizeDocumentNodes(nodes)
           : _buildDocumentNodesFromCurrent(
               title: title,
               body: body,
               assets: assets,
               blocks: blocks,
               useFullBlockSequence: false,
             );

  /// 从 wire JSON 构造，支持新格式（blocks 含 image/paragraph 完整序列）。
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
    final assets = ((map['assets'] as List?) ?? const <Object?>[])
        .whereType<Map>()
        .map(
          (entry) =>
              ArticleDocumentAsset.fromMap(Map<String, dynamic>.from(entry)),
        )
        .where((asset) => asset.id.trim().isNotEmpty && asset.hasImage)
        .toList(growable: false);
    final blocks = ((map['blocks'] as List?) ?? const <Object?>[])
        .whereType<Map>()
        .map(
          (entry) =>
              ArticleDocumentBlock.fromMap(Map<String, dynamic>.from(entry)),
        )
        .where((block) => block.id.trim().isNotEmpty)
        .toList(growable: false);
    final title = _normalizeArticleText((map['title'] ?? '').toString()).trim();
    final body = _normalizeArticleText((map['body'] ?? '').toString());
    final template = (map['template'] ?? 'gentle').toString();
    final fontPreset = (map['fontPreset'] ?? 'clean').toString();
    final coverImageUrl = (map['coverImageUrl'] ?? '').toString().trim();
    final titleStyle = ArticleDocumentTitleStyle.values.firstWhere(
      (s) => s.name == (map['titleStyle'] ?? '').toString(),
      orElse: () => ArticleDocumentTitleStyle.major,
    );

    // 新格式检测：wire 中 blocks 含有带有效 imageUrl 的 image 类型，
    // 说明 blocks 是完整节点序列，直接从 blocks 构建 nodes。
    final useFullBlockSequence = blocks.any(
      (b) => b.type == ArticleDocumentBlockType.image && b.hasImage,
    );

    return ArticleDocumentData._wire(
      nodes: nodeEntries,
      template: template,
      fontPreset: fontPreset,
      coverImageUrl: coverImageUrl,
      titleStyle: titleStyle,
      title: title,
      body: body,
      assets: assets,
      blocks: blocks,
      useFullBlockSequence: useFullBlockSequence,
    );
  }

  ArticleDocumentData._wire({
    List<ArticleDocumentNode> nodes = const <ArticleDocumentNode>[],
    this.template = 'gentle',
    this.fontPreset = 'clean',
    this.coverImageUrl = '',
    this.titleStyle = ArticleDocumentTitleStyle.major,
    String title = '',
    String body = '',
    List<ArticleDocumentAsset> assets = const <ArticleDocumentAsset>[],
    List<ArticleDocumentBlock> blocks = const <ArticleDocumentBlock>[],
    bool useFullBlockSequence = false,
  }) : nodes = nodes.isNotEmpty
           ? _normalizeDocumentNodes(nodes)
           : _buildDocumentNodesFromCurrent(
               title: title,
               body: body,
               assets: assets,
               blocks: blocks,
               useFullBlockSequence: useFullBlockSequence,
             );

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
  /// 当显式传入 [nodes] 时，[title]、[body]、[assets]、[blocks] 参数会被忽略，
  /// 因为它们会从 [nodes] 自动投影。
  ///
  /// 当未传入 [nodes] 但传入了 [body]/[assets]/[blocks] 时，会从这些参数反向
  /// 构建 nodes（兼容旧路径，已标记 @Deprecated 的方法仍依赖此行为）。
  ArticleDocumentData copyWith({
    List<ArticleDocumentNode>? nodes,
    String? template,
    String? fontPreset,
    String? coverImageUrl,
    ArticleDocumentTitleStyle? titleStyle,
    String? title,
    String? body,
    List<ArticleDocumentAsset>? assets,
    List<ArticleDocumentBlock>? blocks,
  }) {
    final nextNodes =
        nodes ??
        ((title != null || body != null || assets != null || blocks != null)
            ? (body != null || assets != null || blocks != null
                  ? _buildDocumentNodesFromCurrent(
                      title: title ?? this.title,
                      body: body ?? this.body,
                      assets: assets ?? this.assets,
                      blocks: blocks ?? this.blocks,
                    )
                  : _replaceDocumentTitleNode(this.nodes, title ?? this.title))
            : this.nodes);
    return ArticleDocumentData(
      nodes: nextNodes,
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

List<ArticleDocumentNode> _buildDocumentNodesFromCurrent({
  required String title,
  required String body,
  required List<ArticleDocumentAsset> assets,
  required List<ArticleDocumentBlock> blocks,
  bool useFullBlockSequence = false,
}) {
  final nodes = <ArticleDocumentNode>[];
  final normalizedTitle = _normalizeArticleText(title).trim();

  // 新格式路径：仅当 fromMap 明确检测到 wire 中含有效 image block 时才启用，
  // 避免编辑器内部构造时误触发。
  if (useFullBlockSequence) {
    if (normalizedTitle.isNotEmpty) {
      nodes.add(
        ArticleDocumentNode(
          id: 'document_title',
          type: ArticleDocumentNodeType.documentTitle,
          text: normalizedTitle,
        ),
      );
    }
    for (final block in blocks) {
      switch (block.type) {
        case ArticleDocumentBlockType.heading2:
          nodes.add(
            ArticleDocumentNode(
              id: block.id,
              type: ArticleDocumentNodeType.headingMajor,
              text: block.text,
              textAlign: block.textAlign,
              spans: block.spans,
            ),
          );
          break;
        case ArticleDocumentBlockType.heading3:
          nodes.add(
            ArticleDocumentNode(
              id: block.id,
              type: ArticleDocumentNodeType.headingMinor,
              text: block.text,
              textAlign: block.textAlign,
              spans: block.spans,
            ),
          );
          break;
        case ArticleDocumentBlockType.sectionTitle:
          nodes.add(
            ArticleDocumentNode(
              id: block.id,
              type: ArticleDocumentNodeType.headingMajor,
              text: block.text,
              textAlign: block.textAlign,
              spans: block.spans,
            ),
          );
          break;
        case ArticleDocumentBlockType.image:
          if (block.hasImage) {
            nodes.add(
              ArticleDocumentNode(
                id: block.id,
                type: ArticleDocumentNodeType.figure,
                imageUrl: block.imageUrl,
                imageLayout: block.imageLayout,
                caption: block.caption,
              ),
            );
          }
          break;
        case ArticleDocumentBlockType.paragraph:
          if (block.text.trim().isNotEmpty) {
            nodes.add(
              ArticleDocumentNode(
                id: block.id,
                type: ArticleDocumentNodeType.paragraph,
                text: block.text,
                textAlign: block.textAlign,
                spans: block.spans,
              ),
            );
          }
          break;
        case ArticleDocumentBlockType.orderedItem:
          nodes.add(
            ArticleDocumentNode(
              id: block.id,
              type: ArticleDocumentNodeType.orderedItem,
              text: block.text,
              textAlign: block.textAlign,
              spans: block.spans,
            ),
          );
          break;
        case ArticleDocumentBlockType.bulletItem:
          nodes.add(
            ArticleDocumentNode(
              id: block.id,
              type: ArticleDocumentNodeType.bulletItem,
              text: block.text,
              textAlign: block.textAlign,
              spans: block.spans,
            ),
          );
          break;
      }
    }
    return nodes;
  }

  if (normalizedTitle.isNotEmpty) {
    nodes.add(
      ArticleDocumentNode(
        id: 'document_title',
        type: ArticleDocumentNodeType.documentTitle,
        text: normalizedTitle,
      ),
    );
  }

  final normalizedBody = _normalizeArticleText(body);
  final semanticBlocks =
      blocks
          .where(
            (block) =>
                block.type == ArticleDocumentBlockType.heading2 ||
                block.type == ArticleDocumentBlockType.heading3 ||
                block.type == ArticleDocumentBlockType.sectionTitle,
          )
          .toList(growable: false)
        ..sort((left, right) {
          final offsetCompare = left.offset.compareTo(right.offset);
          if (offsetCompare != 0) {
            return offsetCompare;
          }
          return left.id.compareTo(right.id);
        });

  // image 类型的 blocks 也作为图片资产参与排版（仅新格式路径使用，此处保留供参考）
  // 旧路径直接使用传入的 assets，不从 blocks 提取图片。
  final sortedAssets =
      assets.where((asset) => asset.hasImage).toList(growable: false)
        ..sort((left, right) {
          final offsetCompare = left.offset.compareTo(right.offset);
          if (offsetCompare != 0) {
            return offsetCompare;
          }
          return left.id.compareTo(right.id);
        });

  var cursor = 0;
  var semanticIndex = 0;
  var assetIndex = 0;
  var textSeed = 0;

  while (semanticIndex < semanticBlocks.length ||
      assetIndex < sortedAssets.length) {
    final nextSemanticOffset = semanticIndex < semanticBlocks.length
        ? semanticBlocks[semanticIndex].offset.clamp(
            cursor,
            normalizedBody.length,
          )
        : normalizedBody.length;
    final nextAssetOffset = assetIndex < sortedAssets.length
        ? sortedAssets[assetIndex].offset.clamp(cursor, normalizedBody.length)
        : normalizedBody.length;
    final nextOffset = nextSemanticOffset < nextAssetOffset
        ? nextSemanticOffset
        : nextAssetOffset;
    _appendTextNodesFromBodySegment(
      nodes,
      normalizedBody.substring(cursor, nextOffset),
      seedPrefix: 'paragraph',
      seedStart: textSeed,
    );
    textSeed += _countTextNodesFromBodySegment(
      normalizedBody.substring(cursor, nextOffset),
    );
    cursor = nextOffset;

    while (semanticIndex < semanticBlocks.length &&
        semanticBlocks[semanticIndex].offset.clamp(0, normalizedBody.length) <=
            cursor) {
      final block = semanticBlocks[semanticIndex];
      nodes.add(
        ArticleDocumentNode(
          id: block.id,
          type: block.type == ArticleDocumentBlockType.heading3
              ? ArticleDocumentNodeType.headingMinor
              : ArticleDocumentNodeType.headingMajor,
          text: block.text,
          textAlign: block.textAlign,
          listDepth: block.listDepth,
          spans: block.spans,
        ),
      );
      semanticIndex += 1;
    }

    while (assetIndex < sortedAssets.length &&
        sortedAssets[assetIndex].offset.clamp(0, normalizedBody.length) <=
            cursor) {
      final asset = sortedAssets[assetIndex];
      nodes.add(
        ArticleDocumentNode(
          id: asset.id,
          type: ArticleDocumentNodeType.figure,
          assetId: asset.id,
          imageUrl: asset.imageUrl,
          imageLayout: asset.imageLayout,
          caption: asset.caption,
        ),
      );
      assetIndex += 1;
    }
  }

  _appendTextNodesFromBodySegment(
    nodes,
    normalizedBody.substring(cursor),
    seedPrefix: 'paragraph',
    seedStart: textSeed,
  );
  return _normalizeDocumentNodes(nodes);
}

int _countTextNodesFromBodySegment(String segment) {
  return _normalizeArticleText(segment)
      .split('\n')
      .map((line) => line.trim())
      .where((line) => line.isNotEmpty)
      .length;
}

void _appendTextNodesFromBodySegment(
  List<ArticleDocumentNode> nodes,
  String segment, {
  required String seedPrefix,
  required int seedStart,
}) {
  var seed = seedStart;
  final lines = _normalizeArticleText(segment)
      .split('\n')
      .map((line) => line.trim())
      .where((line) => line.isNotEmpty)
      .toList(growable: false);
  for (final line in lines) {
    final orderedMatch = _orderedArticleLinePattern.firstMatch(line);
    if (orderedMatch != null) {
      final content = line.substring(orderedMatch.end).trim();
      if (content.isEmpty) {
        continue;
      }
      nodes.add(
        ArticleDocumentNode(
          id: 'ordered_${seed++}',
          type: ArticleDocumentNodeType.orderedItem,
          text: content,
        ),
      );
      continue;
    }
    final bulletMatch = _bulletArticleLinePattern.firstMatch(line);
    if (bulletMatch != null) {
      final content = line.substring(bulletMatch.end).trim();
      if (content.isEmpty) {
        continue;
      }
      nodes.add(
        ArticleDocumentNode(
          id: 'bullet_${seed++}',
          type: ArticleDocumentNodeType.bulletItem,
          text: content,
        ),
      );
      continue;
    }
    nodes.add(
      ArticleDocumentNode(
        id: '${seedPrefix}_${seed++}',
        type: ArticleDocumentNodeType.paragraph,
        text: line,
      ),
    );
  }
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
          allBlocks.add(
            ArticleDocumentBlock(
              id: node.id,
              type: ArticleDocumentBlockType.paragraph,
              offset: bodyBuffer.length,
              text: node.text,
              textAlign: node.textAlign,
              spans: node.spans,
            ),
          );
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

List<ArticleDocumentNode> _replaceDocumentTitleNode(
  List<ArticleDocumentNode> nodes,
  String title,
) {
  final normalizedTitle = _normalizeArticleText(title).trim();
  final nextNodes = nodes
      .where((node) => !node.isDocumentTitle)
      .toList(growable: true);
  if (normalizedTitle.isEmpty) {
    return nextNodes;
  }
  nextNodes.insert(
    0,
    ArticleDocumentNode(
      id: 'document_title',
      type: ArticleDocumentNodeType.documentTitle,
      text: normalizedTitle,
    ),
  );
  return nextNodes;
}
