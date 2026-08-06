part of 'article_editor.dart';

/// 文章正文节点、环绕图片与图片工具栏的视图构建。
///
/// 编辑状态、控制器、选区和环绕几何仍唯一归属 [_ArticleEditorState]；
/// 本文件只扩展同一 state，不建立第二套编辑或布局状态。
extension _ArticleEditorContentBuilders on _ArticleEditorState {
  Widget _buildTextNode(
    BuildContext context,
    ArticleDocumentNode node,
    ArticleTypographySpec typography, {
    bool isPrimaryBodyNode = false,
  }) {
    final c = _controllerFor(node.id, node.text);
    final f = _focusNodeFor(node.id);

    // 自动聚焦：由 _InsertSlot 创建新 node 后触发
    if (_pendingFocusNodeId == node.id) {
      _pendingFocusNodeId = null;
      final pendingSelection = _pendingFocusSelectionOffset;
      _pendingFocusSelectionOffset = null;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && !f.hasFocus) {
          f.requestFocus();
          final offset = (pendingSelection ?? c.text.length).clamp(
            0,
            c.text.length,
          );
          c.selection = TextSelection.collapsed(offset: offset);
          _nodeSelections[node.id] = c.selection;
        }
      });
    }

    final style = switch (node.type) {
      ArticleDocumentNodeType.headingMajor => typography.bodyStyle.copyWith(
        fontSize: (typography.bodyStyle.fontSize ?? AppTypography.base) * 1.3,
        fontWeight: AppTypography.semiBold,
      ),
      ArticleDocumentNodeType.headingMinor => typography.bodyStyle.copyWith(
        fontSize: (typography.bodyStyle.fontSize ?? AppTypography.base) * 1.15,
        fontWeight: AppTypography.medium,
      ),
      _ => typography.bodyStyle,
    };

    return CupertinoTextField(
      key: isPrimaryBodyNode
          ? TestKeys.createMomentInput
          : ValueKey<String>('node_text_${node.id}'),
      controller: c,
      focusNode: f,
      keyboardType: TextInputType.multiline,
      textInputAction: TextInputAction.newline,
      textAlignVertical: TextAlignVertical.top,
      maxLines: null,
      minLines: 1,
      padding: EdgeInsets.symmetric(vertical: AppSpacing.intraGroupXs),
      decoration: const BoxDecoration(),
      style: style,
      placeholder: isPrimaryBodyNode
          ? CreatePageText.articleBodyPlaceholder
          : null,
      placeholderStyle: typography.placeholderStyle,
      onTap: () {
        // 延迟一帧读取 selection，确保 Flutter 已完成 hit test 和 selection 更新
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (mounted) {
            _nodeSelections[node.id] = c.selection;
          }
        });
      },
      onChanged: (value) {
        widget.onUpdateNodeText(node.id, value);
        _scheduleTextCommit();
      },
    );
  }

  Widget _buildInsertionSlot(
    BuildContext context,
    ArticleEditorSlotProjection slot,
    ArticleTypographySpec typography,
  ) {
    final isActive = _activeSlotId == slot.id;
    if (!isActive) {
      final showHint = slot.isFigureFigureSlot;
      // slot 只负责可点击区域，不承担语义间距
      final double effectiveHeight = slot.isTailSlot ? 88.0 : 44.0;
      return GestureDetector(
        key: ValueKey<String>('article_slot_${slot.id}'),
        behavior: HitTestBehavior.opaque,
        onTap: () => _activateSlot(slot),
        child: SizedBox(
          height: effectiveHeight,
          width: double.infinity,
          child: showHint
              ? Center(
                  child: Text(
                    CreatePageText.articleBodyStartPlaceholder,
                    style: typography.bodyStyle.copyWith(
                      color: typography.placeholderStyle.color,
                    ),
                  ),
                )
              : null,
        ),
      );
    }

    final controller = _ensureActiveSlotController();
    final focusNode = _ensureActiveSlotFocusNode();
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () {
        if (!focusNode.hasFocus) {
          focusNode.requestFocus();
        }
      },
      child: CupertinoTextField(
        key: ValueKey<String>('article_slot_input_${slot.id}'),
        controller: controller,
        focusNode: focusNode,
        keyboardType: TextInputType.multiline,
        textInputAction: TextInputAction.newline,
        textAlignVertical: TextAlignVertical.top,
        maxLines: null,
        minLines: 1,
        padding: EdgeInsets.symmetric(vertical: AppSpacing.intraGroupXs),
        decoration: const BoxDecoration(),
        style: typography.bodyStyle,
        placeholderStyle: typography.placeholderStyle,
        onChanged: (value) {
          if (value.trim().isEmpty) {
            return;
          }
          final newNodeId = widget.onInsertTextNodeAfter(
            slot.anchorNodeId,
            initialText: value,
          );
          if (newNodeId.trim().isEmpty) {
            return;
          }
          final selectionOffset = value.length;
          _nodeSelections[newNodeId] = TextSelection.collapsed(
            offset: selectionOffset,
          );
          _setEditorState(() {
            _pendingFocusNodeId = newNodeId;
            _pendingFocusSelectionOffset = selectionOffset;
            _focusedNodeId = newNodeId;
            _activeSlotId = null;
            controller.clear();
          });
        },
      ),
    );
  }

  _TextSelectionInsertionTarget? _currentSelectionInsertionTarget() {
    final nodeId = _focusedNodeId;
    if (nodeId == null ||
        nodeId == 'title' ||
        nodeId == _kEmptyDocumentBodyFocusId ||
        _activeSlotId != null ||
        _selectedImageNodeId != null) {
      return null;
    }
    ArticleDocumentNode? node;
    for (final entry in widget.state.articleDocument.nodes) {
      if (entry.id == nodeId) {
        node = entry;
        break;
      }
    }
    if (node == null || node.isFigure) {
      return null;
    }
    final controller = _nodeControllers[nodeId];
    final selection =
        _nodeSelections[nodeId] ??
        controller?.selection ??
        const TextSelection.collapsed(offset: 0);
    final rawOffset = selection.isValid
        ? selection.extentOffset
        : node.text.length;
    final selectionOffset = rawOffset.clamp(0, node.text.length);
    return _TextSelectionInsertionTarget(
      nodeId: nodeId,
      selectionOffset: selectionOffset,
    );
  }

  void _scheduleWrapGroupNormalization(
    String figureNodeId, {
    int? splitOffset,
  }) {
    if (_pendingWrapNormalizations.contains(figureNodeId)) {
      return;
    }
    _pendingWrapNormalizations.add(figureNodeId);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _pendingWrapNormalizations.remove(figureNodeId);
      if (!mounted) {
        return;
      }
      widget.onEnsureWrapNodeGroup(figureNodeId, splitOffset: splitOffset);
    });
  }

  String? _ensureWrapSegmentNodeId(
    ArticleEditorWrapGroupProjection group,
    ArticleWrapEditorSegment segment, {
    int? splitOffset,
    int selectionOffset = 0,
  }) {
    final existingNode = segment == ArticleWrapEditorSegment.narrow
        ? group.narrowParagraphNode
        : group.belowParagraphNode;
    if (existingNode != null) {
      return existingNode.id;
    }
    final ensured = widget.onEnsureWrapNodeGroup(
      group.figure.id,
      splitOffset: splitOffset,
    );
    final targetNode = segment == ArticleWrapEditorSegment.narrow
        ? ensured?.narrowParagraph
        : ensured?.belowParagraph;
    if (targetNode != null) {
      _pendingFocusNodeId = targetNode.id;
      _pendingFocusSelectionOffset = selectionOffset;
      return targetNode.id;
    }
    return null;
  }

  Widget _buildWrapGroup(
    BuildContext context,
    ArticleEditorWrapGroupProjection group,
    ArticleTypographySpec typography,
  ) {
    final node = group.figure;
    final isSelected = _selectedImageNodeId == node.id;
    final isLeft = node.imageLayout == 'wrapLeft';
    final narrowNode = group.narrowParagraphNode;
    final belowNode = group.belowParagraphNode;

    return LayoutBuilder(
      builder: (context, constraints) {
        // ── 共享几何：复用阅读态的 resolveArticleWrapLayout() ──
        final contentWidth = constraints.maxWidth;
        final captionStyle = TextStyle(
          color: CupertinoColors.secondaryLabel.resolveFrom(context),
          fontSize: AppTypography.sm,
          height: articleCaptionLineHeight(),
        );
        final wrapResult = resolveArticleWrapLayout(
          ArticleWrapLayoutInput(
            body: group.combinedText,
            leadingText: group.hasBelowParagraph ? group.narrowText : null,
            trailingText: group.hasBelowParagraph ? group.belowText : null,
            rowContentWidth: contentWidth,
            bodyStyle: typography.bodyStyle,
            captionText: node.caption,
            captionStyle: captionStyle,
            captionPlaceholderWhenEmpty: isSelected,
            imageLayout: node.imageLayout,
          ),
        );
        final wrapData = wrapResult.layout;
        final imageWidth = wrapData.imageWidth;
        final gap = wrapData.sideGap;
        final narrowWidth = wrapData.besideWidth;
        final floatHeight = wrapData.besideHeight;
        final resolvedNarrowText = group.hasBelowParagraph
            ? group.narrowText
            : wrapResult.leadingText;
        final resolvedBelowText = group.hasBelowParagraph
            ? group.belowText
            : wrapResult.trailingText;

        if (!group.hasNarrowParagraph || !group.hasBelowParagraph) {
          _scheduleWrapGroupNormalization(
            node.id,
            splitOffset: group.hasNarrowParagraph ? wrapData.splitOffset : null,
          );
        }

        // 图片列加 Padding(top: halfLeading)，让图片视觉顶部
        // 与文字视觉顶部对齐。
        final imageColumn = Padding(
          padding: EdgeInsets.only(top: wrapData.textHalfLeading),
          child: SizedBox(
            width: imageWidth,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                _buildImageWidget(
                  context,
                  node,
                  isSelected,
                  width: imageWidth,
                  height: wrapData.imageHeight,
                ),
                if (node.caption.trim().isNotEmpty || isSelected)
                  _buildCaptionField(context, node, typography),
                // 工具栏紧跟配文，在 imageColumn 内部，
                // 不在全宽文字之后。
                if (isSelected)
                  _buildImageToolbar(
                    context,
                    node,
                    imageWidth: imageWidth,
                    alignment: Alignment.centerLeft,
                  ),
              ],
            ),
          ),
        );
        ArticleWrapEditorSegment? autofocusSegment;
        int? autofocusSelectionOffset;
        if (_pendingFocusNodeId != null) {
          if (narrowNode != null && _pendingFocusNodeId == narrowNode.id) {
            autofocusSegment = ArticleWrapEditorSegment.narrow;
            autofocusSelectionOffset = _pendingFocusSelectionOffset;
            _pendingFocusNodeId = null;
            _pendingFocusSelectionOffset = null;
          } else if (belowNode != null && _pendingFocusNodeId == belowNode.id) {
            autofocusSegment = ArticleWrapEditorSegment.below;
            autofocusSelectionOffset = _pendingFocusSelectionOffset;
            _pendingFocusNodeId = null;
            _pendingFocusSelectionOffset = null;
          }
        }
        final wrapKey = _wrapEditorKeys.putIfAbsent(
          group.id,
          () => GlobalKey<ArticleWrapParagraphEditorState>(
            debugLabel: 'wrap_${group.id}',
          ),
        );
        _wrapEditorGroupNodeIds[group.id] = group.paragraphNodeIds;
        final wrapContent = ArticleWrapParagraphEditor(
          key: wrapKey,
          groupId: node.id,
          narrowText: resolvedNarrowText,
          belowText: resolvedBelowText,
          imageChild: imageColumn,
          imageWidth: imageWidth,
          narrowWidth: narrowWidth,
          gap: gap,
          isLeft: isLeft,
          floatHeight: floatHeight,
          style: typography.bodyStyle,
          placeholderStyle: typography.placeholderStyle,
          placeholder: CreatePageText.articleBodyStartPlaceholder,
          autofocusSegment: autofocusSegment,
          autofocusSelectionOffset: autofocusSelectionOffset,
          belowSpacing: wrapData.sameParagraphSpacing,
          maxLinesBeside: wrapData.maxLinesBeside,
          onChanged: (narrowText, belowText) {
            widget.onUpdateWrapParagraphTexts(node.id, narrowText, belowText);
            _scheduleTextCommit();
          },
          onFocused: (segment) {
            final targetNodeId =
                _ensureWrapSegmentNodeId(
                  group,
                  segment,
                  splitOffset: wrapData.splitOffset,
                  selectionOffset: segment == ArticleWrapEditorSegment.narrow
                      ? resolvedNarrowText.length
                      : resolvedBelowText.length,
                ) ??
                (segment == ArticleWrapEditorSegment.narrow
                    ? narrowNode?.id
                    : belowNode?.id);
            _unfocusAllExcept(targetNodeId);
            if (targetNodeId != null) {
              widget.onActiveBlockChanged(targetNodeId);
            }
            if (mounted) {
              _setEditorState(() {
                _focusedNodeId = targetNodeId;
                _activeSlotId = null;
                _activeSlotController?.clear();
                _selectedImageNodeId = null;
              });
            }
          },
          onSelectionChanged: (segment, offset) {
            final targetNodeId = segment == ArticleWrapEditorSegment.narrow
                ? (narrowNode?.id ?? _pendingFocusNodeId)
                : (belowNode?.id ?? _pendingFocusNodeId);
            if (targetNodeId != null) {
              _nodeSelections[targetNodeId] = TextSelection.collapsed(
                offset: offset,
              );
            }
          },
        );

        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[wrapContent],
        );
      },
    );
  }

  Widget _buildFigureNode(
    BuildContext context,
    ArticleDocumentNode node,
    List<ArticleDocumentNode> allNodes,
    int nodeIndex,
    ArticleTypographySpec typography,
  ) {
    final isSelected = _selectedImageNodeId == node.id;
    // wrapLeft/wrapRight 的 figure 已由 projection 层的 WrapGroup 处理，
    // 这里只处理 fullWidth figure（或作为 fallback）。
    return _buildFullWidthFigureNode(context, node, typography, isSelected);
  }

  Widget _buildFullWidthFigureNode(
    BuildContext context,
    ArticleDocumentNode node,
    ArticleTypographySpec typography,
    bool isSelected,
  ) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        _buildImageWidget(context, node, isSelected),
        if (node.caption.trim().isNotEmpty || isSelected)
          _buildCaptionField(context, node, typography),
        if (isSelected) _buildImageToolbar(context, node),
      ],
    );
  }

  Widget _buildImageWidget(
    BuildContext context,
    ArticleDocumentNode node,
    bool isSelected, {
    double? width,
    double? height,
  }) {
    final url = node.imageUrl.trim();
    if (url.isEmpty) return const SizedBox.shrink();

    final aspect = ArticleImageIntrinsicRegistry.aspectRatioFor(url) ?? (4 / 3);

    Widget image;
    if (url.startsWith('http://') || url.startsWith('https://')) {
      image = AppCachedNetworkImage(
        imageUrl: url,
        fit: BoxFit.cover,
        cdnPreset: CdnImagePreset.inline,
      );
    } else {
      image = Image(image: localFileImageProvider(url), fit: BoxFit.cover);
    }

    return GestureDetector(
      onTap: () => _setEditorState(() {
        _selectedImageNodeId = _selectedImageNodeId == node.id ? null : node.id;
        _activeSlotId = null;
        _activeSlotController?.clear();
        // 选中图片时收起键盘，确保工具栏可见
        FocusManager.instance.primaryFocus?.unfocus();
      }),
      // 选中边框用 foregroundDecoration 叠加在内容之上，
      // 不增加容器尺寸，确保图片高度精确等于 wrapData.imageHeight。
      child: Container(
        foregroundDecoration: isSelected
            ? BoxDecoration(
                border: Border.all(
                  color: AppColors.iosAccent(context),
                  width: AppSpacing.two,
                ),
              )
            : null,
        // 环绕模式传入明确 height，用 SizedBox 固定尺寸；
        // 全宽模式用 AspectRatio 自然撑高。
        child: height != null
            ? SizedBox(
                width: width,
                height: height,
                child: ClipRect(
                  child: FittedBox(fit: BoxFit.cover, child: image),
                ),
              )
            : AspectRatio(aspectRatio: aspect, child: image),
      ),
    );
  }

  Widget _buildCaptionField(
    BuildContext context,
    ArticleDocumentNode node,
    ArticleTypographySpec typography,
  ) {
    final c = _captionControllerFor(node.id, node.caption);
    final fn = _captionFocusNodeFor(node.id);
    return Padding(
      padding: EdgeInsets.only(top: articleCaptionSpacing()),
      child: CupertinoTextField(
        key: ValueKey<String>('node_caption_${node.id}'),
        controller: c,
        focusNode: fn,
        keyboardType: TextInputType.text,
        textInputAction: TextInputAction.done,
        maxLines: 1,
        padding: EdgeInsets.zero,
        decoration: const BoxDecoration(),
        textAlign: TextAlign.center,
        style: typography.captionStyle,
        placeholder: CreatePageText.imageCaptionPlaceholder,
        placeholderStyle: typography.placeholderStyle.copyWith(
          fontSize: typography.captionStyle.fontSize,
        ),
        onChanged: (v) => widget.onUpdateNodeCaption(node.id, v),
      ),
    );
  }

  Widget _buildImageToolbar(
    BuildContext context,
    ArticleDocumentNode node, {
    double? imageWidth,
    Alignment alignment = Alignment.center,
  }) {
    final fg = CupertinoColors.secondaryLabel.resolveFrom(context);
    final toolbar = Row(
      mainAxisAlignment: MainAxisAlignment.center,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        _ToolBtn(
          icon: CupertinoIcons.rectangle,
          label: CreatePageText.imageLayoutFullWidth,
          active: node.imageLayout == 'fullWidth',
          color: fg,
          onTap: () => widget.onUpdateNodeImageLayout(node.id, 'fullWidth'),
        ),
        SizedBox(width: AppSpacing.md),
        _ToolBtn(
          icon: CupertinoIcons.rectangle_split_3x1,
          label: CreatePageText.imageLayoutLeft,
          active: node.imageLayout == 'wrapLeft',
          color: fg,
          onTap: () => widget.onUpdateNodeImageLayout(node.id, 'wrapLeft'),
        ),
        SizedBox(width: AppSpacing.md),
        _ToolBtn(
          icon: CupertinoIcons.rectangle_split_3x1,
          label: CreatePageText.imageLayoutRight,
          active: node.imageLayout == 'wrapRight',
          color: fg,
          onTap: () => widget.onUpdateNodeImageLayout(node.id, 'wrapRight'),
        ),
        SizedBox(width: AppSpacing.md),
        _ToolBtn(
          icon: CupertinoIcons.pencil,
          label: CreatePageText.edit,
          active: false,
          color: fg,
          onTap: () => widget.onEditNodeImage(node.id),
        ),
        SizedBox(width: AppSpacing.md),
        _ToolBtn(
          icon: CupertinoIcons.trash,
          label: CreatePageText.delete,
          active: false,
          color: fg, // 低调灰色，不用红色吸引眼球
          onTap: () {
            widget.onRemoveNodeImage(node.id);
            _setEditorState(() => _selectedImageNodeId = null);
          },
        ),
      ],
    );

    // 环绕布局时工具栏跟随图片对齐
    if (imageWidth != null) {
      return Padding(
        padding: EdgeInsets.only(top: AppSpacing.intraGroupSm),
        child: SizedBox(
          width: imageWidth,
          child: FittedBox(
            fit: BoxFit.scaleDown,
            alignment: alignment,
            child: toolbar,
          ),
        ),
      );
    }

    return Padding(
      padding: EdgeInsets.only(top: AppSpacing.intraGroupSm),
      child: toolbar,
    );
  }
}

class _ToolBtn extends StatelessWidget {
  const _ToolBtn({
    required this.icon,
    required this.label,
    required this.active,
    required this.color,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final bool active;
  final Color color;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final c = active ? AppColors.iosAccent(context) : color;
    return GestureDetector(
      onTap: onTap,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Icon(icon, size: AppSpacing.iconMedium, color: c),
          SizedBox(height: AppSpacing.two),
          Text(
            label,
            style: TextStyle(fontSize: AppTypography.xs, color: c),
          ),
        ],
      ),
    );
  }
}

class _TextSelectionInsertionTarget {
  const _TextSelectionInsertionTarget({
    required this.nodeId,
    required this.selectionOffset,
  });

  final String nodeId;
  final int selectionOffset;
}
