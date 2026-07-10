part of 'create_editor_provider.dart';

extension CreateEditorNotifierArticleHelpers on CreateEditorNotifier {
  /// 两图之间插文槽草稿与 [syncParagraphDraftBeforeAsset] 同理。
  void syncParagraphDraftBetweenAssets(String anchorAssetId, String draft) {
    final id = anchorAssetId.trim();
    if (id.isEmpty) {
      return;
    }
    final document = _currentState.articleDocument;
    final sorted = _documentSortedImageAssets(document);
    final index = sorted.indexWhere((a) => a.id == id);
    if (index < 0 || index + 1 >= sorted.length) {
      return;
    }
    final cur = sorted[index];
    final nxt = sorted[index + 1];
    final a = cur.offset.clamp(0, document.body.length);
    final b = nxt.offset.clamp(a, document.body.length);
    final newMid = _normalizeArticleBody(draft.replaceAll('\r\n', '\n'));
    final oldMid = document.body.substring(a, b);
    if (oldMid == newMid) {
      return;
    }
    final recordUndo =
        (oldMid.trim().isEmpty && newMid.trim().isNotEmpty) ||
        (oldMid.trim().isNotEmpty && newMid.trim().isEmpty);
    final nextBody = _normalizeArticleBody(
      document.body.substring(0, a) + newMid + document.body.substring(b),
    );
    final delta = newMid.length - (b - a);
    final nextAssets = document.assets
        .map(
          (asset) => asset.offset >= b
              ? asset.copyWith(offset: asset.offset + delta)
              : asset,
        )
        .toList(growable: false);
    _applyArticleDocument(
      document.copyWith(
        body: nextBody,
        assets: _normalizeAssets(nextAssets, nextBody.length),
      ),
      recordUndoPoint: recordUndo,
    );
  }

  /// 在指定文本 node 的光标位置为插图腾出空间。
  ///
  /// 返回后续图片应插入到哪个锚点之后。
  String prepareTextNodeForImageInsertion(String nodeId, int selectionOffset) {
    final id = nodeId.trim();
    if (id.isEmpty) {
      return kArticleEditorStartAnchorId;
    }
    final doc = _currentState.articleDocument;
    final index = doc.nodes.indexWhere((node) => node.id == id);
    if (index < 0) {
      return kArticleEditorStartAnchorId;
    }
    final node = doc.nodes[index];
    if (node.isFigure || node.isDocumentTitle) {
      return index > 0 ? doc.nodes[index - 1].id : kArticleEditorStartAnchorId;
    }

    final text = node.text;
    final offset = selectionOffset.clamp(0, text.length);
    if (offset <= 0) {
      return index > 0 ? doc.nodes[index - 1].id : kArticleEditorStartAnchorId;
    }
    if (offset >= text.length) {
      return node.id;
    }

    final leftText = text.substring(0, offset);
    final rightText = text.substring(offset);
    final keepLeft = leftText.trim().isNotEmpty;
    final keepRight = rightText.trim().isNotEmpty;
    final leftSpans = _sliceInlineSpans(node.spans, 0, offset);
    final rightSpans = _sliceInlineSpans(node.spans, offset, text.length);
    final nextNodes = List<ArticleDocumentNode>.from(doc.nodes)
      ..removeAt(index);

    var insertIndex = index;
    var anchorId = index > 0
        ? doc.nodes[index - 1].id
        : kArticleEditorStartAnchorId;

    if (keepLeft) {
      nextNodes.insert(
        insertIndex,
        _cloneTextNode(node, id: node.id, text: leftText, spans: leftSpans),
      );
      anchorId = node.id;
      insertIndex += 1;
    }

    if (keepRight) {
      final rightNodeId = keepLeft
          ? _nextArticleTextNodeId(node.type)
          : node.id;
      nextNodes.insert(
        insertIndex,
        _cloneTextNode(
          node,
          id: rightNodeId,
          text: rightText,
          spans: rightSpans,
        ),
      );
    }

    _applyArticleDocument(doc.copyWith(nodes: nextNodes));
    return anchorId;
  }
}
