import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/ui/content/article_document_models.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';

/// 编辑态文档开头锚点。
///
/// 当插入位置位于第一条正文/图片之前时，editor 会把此值作为“前一个 node”
/// 传给 provider，provider 再把它解释为索引 0。
const String kArticleEditorStartAnchorId = '__article_editor_start__';

enum ArticleEditorProjectionEntryKind { slot, node, wrapGroup }
enum ArticleEditorSlotRole { start, between, tail }

@immutable
abstract class ArticleEditorProjectionEntry {
  const ArticleEditorProjectionEntry(this.kind, this.id);

  final ArticleEditorProjectionEntryKind kind;
  final String id;
}

@immutable
abstract class ArticleEditorProjectionContentEntry
    extends ArticleEditorProjectionEntry {
  const ArticleEditorProjectionContentEntry(
    super.kind,
    super.id, {
    required this.leadingSemantic,
    required this.trailingSemantic,
    required this.leadingNodeId,
    required this.trailingNodeId,
  });

  final ArticleSpacingSemantic leadingSemantic;
  final ArticleSpacingSemantic trailingSemantic;
  final String leadingNodeId;
  final String trailingNodeId;
}

@immutable
class ArticleEditorSlotProjection extends ArticleEditorProjectionEntry {
  const ArticleEditorSlotProjection({
    required String id,
    required this.anchorNodeId,
    required this.role,
    required this.collapsedHeight,
    required this.hasFigureAbove,
    required this.hasFigureBelow,
    this.previousSemantic,
    this.nextSemantic,
  }) : super(ArticleEditorProjectionEntryKind.slot, id);

  final String anchorNodeId;
  final ArticleEditorSlotRole role;
  final double collapsedHeight;
  final bool hasFigureAbove;
  final bool hasFigureBelow;
  final ArticleSpacingSemantic? previousSemantic;
  final ArticleSpacingSemantic? nextSemantic;

  bool get isStartSlot => role == ArticleEditorSlotRole.start;
  bool get isTailSlot => role == ArticleEditorSlotRole.tail;
  bool get isFigureFigureSlot => hasFigureAbove && hasFigureBelow;
}

@immutable
class ArticleEditorNodeProjection extends ArticleEditorProjectionContentEntry {
  ArticleEditorNodeProjection({
    required this.node,
  }) : super(
         ArticleEditorProjectionEntryKind.node,
         node.id,
         leadingSemantic: _semanticForNode(node),
         trailingSemantic: _semanticForNode(node),
         leadingNodeId: node.id,
         trailingNodeId: node.id,
       );

  final ArticleDocumentNode node;
}

@immutable
class ArticleEditorWrapGroupProjection extends ArticleEditorProjectionContentEntry {
  ArticleEditorWrapGroupProjection({
    required this.figure,
    required this.narrowParagraphNode,
    required this.belowParagraphNode,
  }) : super(
         ArticleEditorProjectionEntryKind.wrapGroup,
         'wrap_${figure.id}',
         leadingSemantic: ArticleSpacingSemantic.figure,
         trailingSemantic: belowParagraphNode != null
             ? _semanticForNode(belowParagraphNode)
             : narrowParagraphNode != null
                 ? _semanticForNode(narrowParagraphNode)
                 : ArticleSpacingSemantic.figure,
         leadingNodeId: figure.id,
         trailingNodeId: belowParagraphNode != null
             ? belowParagraphNode.id
             : narrowParagraphNode != null
                 ? narrowParagraphNode.id
                 : figure.id,
       );

  final ArticleDocumentNode figure;
  final ArticleDocumentNode? narrowParagraphNode;
  final ArticleDocumentNode? belowParagraphNode;

  bool get hasNarrowParagraph => narrowParagraphNode != null;
  bool get hasBelowParagraph => belowParagraphNode != null;
  String get narrowText => narrowParagraphNode?.text ?? '';
  String get belowText => belowParagraphNode?.text ?? '';
  String get combinedText => '$narrowText$belowText';
  Set<String> get paragraphNodeIds => <String>{
    if (narrowParagraphNode != null &&
        narrowParagraphNode!.id.trim().isNotEmpty)
      narrowParagraphNode!.id,
    if (belowParagraphNode != null &&
        belowParagraphNode!.id.trim().isNotEmpty)
      belowParagraphNode!.id,
  };
}

@immutable
class ArticleEditorProjection {
  const ArticleEditorProjection(this.entries);

  final List<ArticleEditorProjectionEntry> entries;

  bool get hasContent => entries.any(
    (entry) => entry is ArticleEditorProjectionContentEntry,
  );
}

ArticleEditorProjection buildArticleEditorProjection(
  List<ArticleDocumentNode> nodes,
) {
  final spacing = articleSpacingResolver();
  final titleNode = nodes.firstWhere(
    (node) => node.isDocumentTitle && node.id.trim().isNotEmpty,
    orElse: () => const ArticleDocumentNode(
      id: kArticleEditorStartAnchorId,
      type: ArticleDocumentNodeType.documentTitle,
    ),
  );
  final titleNodeId = titleNode.id;
  final rootSemantic = titleNodeId == kArticleEditorStartAnchorId
      ? null
      : ArticleSpacingSemantic.documentTitle;
  final bodyNodes = nodes
      .where((node) => !node.isDocumentTitle)
      .toList(growable: false);
  final contentEntries = <ArticleEditorProjectionContentEntry>[];

  for (var index = 0; index < bodyNodes.length; index += 1) {
    final node = bodyNodes[index];
    if (node.isFigure && node.usesWrappedLayout) {
      // 图后最多连续吞入两个 paragraph：
      // 第一个是窄文，第二个是图下独立自然段。
      // 图上方 paragraph 始终保持独立，确保全图↔环绕切换时位置不变。
      ArticleDocumentNode? narrowParagraphNode;
      ArticleDocumentNode? belowParagraphNode;
      if (index + 1 < bodyNodes.length) {
        final next = bodyNodes[index + 1];
        if (next.type == ArticleDocumentNodeType.paragraph) {
          narrowParagraphNode = next;
          index += 1;
          if (index + 1 < bodyNodes.length) {
            final below = bodyNodes[index + 1];
            if (below.type == ArticleDocumentNodeType.paragraph) {
              belowParagraphNode = below;
              index += 1;
            }
          }
        }
      }
      contentEntries.add(
        ArticleEditorWrapGroupProjection(
          figure: node,
          narrowParagraphNode: narrowParagraphNode,
          belowParagraphNode: belowParagraphNode,
        ),
      );
      continue;
    }
    contentEntries.add(ArticleEditorNodeProjection(node: node));
  }

  if (contentEntries.isEmpty) {
    return ArticleEditorProjection(<ArticleEditorProjectionEntry>[
      ArticleEditorSlotProjection(
        id: 'slot_${titleNodeId}_empty',
        anchorNodeId: titleNodeId,
        role: ArticleEditorSlotRole.start,
        collapsedHeight: 0,
        hasFigureAbove: false,
        hasFigureBelow: false,
        previousSemantic: rootSemantic,
      ),
    ]);
  }

  final entries = <ArticleEditorProjectionEntry>[];
  ArticleEditorProjectionContentEntry? previous;

  for (final current in contentEntries) {
    final previousSemantic = previous?.trailingSemantic ?? rootSemantic;
    final nextSemantic = current.leadingSemantic;
    final collapsedHeight =
        previousSemantic == ArticleSpacingSemantic.figure &&
            nextSemantic == ArticleSpacingSemantic.figure
        ? spacing.betweenConsecutiveFigures()
        : spacing.between(previousSemantic, nextSemantic);

    entries.add(
      ArticleEditorSlotProjection(
        id:
            'slot_${previous?.trailingNodeId ?? kArticleEditorStartAnchorId}_${current.leadingNodeId}',
        anchorNodeId: previous?.trailingNodeId ?? titleNodeId,
        role: previous == null
            ? ArticleEditorSlotRole.start
            : ArticleEditorSlotRole.between,
        collapsedHeight: collapsedHeight,
        hasFigureAbove: previousSemantic == ArticleSpacingSemantic.figure,
        hasFigureBelow: nextSemantic == ArticleSpacingSemantic.figure,
        previousSemantic: previousSemantic,
        nextSemantic: nextSemantic,
      ),
    );
    entries.add(current);
    previous = current;
  }

  if (previous != null) {
    entries.add(
      ArticleEditorSlotProjection(
        id: 'slot_${previous.trailingNodeId}_end',
        anchorNodeId: previous.trailingNodeId,
        role: ArticleEditorSlotRole.tail,
        collapsedHeight: spacing.after(previous.trailingSemantic),
        hasFigureAbove: previous.trailingSemantic == ArticleSpacingSemantic.figure,
        hasFigureBelow: false,
        previousSemantic: previous.trailingSemantic,
      ),
    );
  }

  return ArticleEditorProjection(entries);
}

ArticleEditorSlotProjection? projectionSlotById(
  ArticleEditorProjection projection,
  String? slotId,
) {
  if (slotId == null || slotId.trim().isEmpty) {
    return null;
  }
  for (final entry in projection.entries) {
    if (entry is ArticleEditorSlotProjection && entry.id == slotId) {
      return entry;
    }
  }
  return null;
}

ArticleSpacingSemantic _semanticForNode(ArticleDocumentNode node) {
  if (node.isFigure) {
    return ArticleSpacingSemantic.figure;
  }
  if (node.type == ArticleDocumentNodeType.headingMajor) {
    return ArticleSpacingSemantic.headingMajor;
  }
  if (node.type == ArticleDocumentNodeType.headingMinor) {
    return ArticleSpacingSemantic.headingMinor;
  }
  return ArticleSpacingSemantic.paragraph;
}
