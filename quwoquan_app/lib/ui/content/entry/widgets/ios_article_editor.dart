import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:quwoquan_app/components/input/unified_emoji_picker.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/article_detail_view.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/widgets/article_content_block_renderer.dart';

class IosArticleEditor extends StatefulWidget {
  const IosArticleEditor({
    super.key,
    required this.state,
    required this.titleController,
    required this.titleFocusNode,
    required this.onTitleChanged,
    required this.onInsertParagraph,
    required this.onInsertOrderedItem,
    required this.onInsertImages,
    required this.onUpdateTextBlock,
    required this.onRemoveBlock,
    required this.onReplaceImage,
    required this.onUpdateImageLayout,
    required this.onActiveBlockChanged,
    this.immersive = false,
  });

  final CreateEditorStateV2 state;
  final TextEditingController titleController;
  final FocusNode titleFocusNode;
  final ValueChanged<String> onTitleChanged;
  final String Function(String? afterBlockId) onInsertParagraph;
  final String Function(String? afterBlockId) onInsertOrderedItem;
  final Future<void> Function(String? afterBlockId) onInsertImages;
  final void Function(String blockId, String text) onUpdateTextBlock;
  final void Function(String blockId) onRemoveBlock;
  final Future<void> Function(String blockId) onReplaceImage;
  final void Function(String blockId, CreateTextImageLayout layout)
  onUpdateImageLayout;
  final ValueChanged<String?> onActiveBlockChanged;
  final bool immersive;

  @override
  State<IosArticleEditor> createState() => _IosArticleEditorState();
}

class _EditorRenderItem {
  const _EditorRenderItem({
    required this.view,
    this.textBlock,
    this.imageBlock,
    this.wrappedTextBlock,
  });

  final ArticleContentBlockView view;
  final CreateTextBlock? textBlock;
  final CreateTextBlock? imageBlock;
  final CreateTextBlock? wrappedTextBlock;

  bool containsBlock(String? blockId) {
    if (blockId == null) {
      return false;
    }
    return textBlock?.id == blockId ||
        imageBlock?.id == blockId ||
        wrappedTextBlock?.id == blockId;
  }

  String? get primaryTextBlockId => wrappedTextBlock?.id ?? textBlock?.id;
}

class _IosArticleEditorState extends State<IosArticleEditor> {
  static const int _kMaxBlockTextLength = 5000;
  final Map<String, TextEditingController> _blockControllers =
      <String, TextEditingController>{};
  final Map<String, FocusNode> _blockFocusNodes = <String, FocusNode>{};
  final Set<String> _boundFocusNodeIds = <String>{};
  bool _showEmojiPanel = false;
  String? _pendingFocusBlockId;

  @override
  void initState() {
    super.initState();
    _syncBlockEditors();
  }

  @override
  void didUpdateWidget(covariant IosArticleEditor oldWidget) {
    super.didUpdateWidget(oldWidget);
    _syncBlockEditors();
    if (_pendingFocusBlockId != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted || _pendingFocusBlockId == null) {
          return;
        }
        _focusBlock(_pendingFocusBlockId!);
        _pendingFocusBlockId = null;
      });
      return;
    }
    final nextActiveId = widget.state.activeArticleBlockId;
    if (nextActiveId != null &&
        nextActiveId != oldWidget.state.activeArticleBlockId &&
        _blockFocusNodes.containsKey(nextActiveId)) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) {
          return;
        }
        final focusNode = _blockFocusNodes[nextActiveId];
        if (focusNode != null && !focusNode.hasFocus) {
          focusNode.requestFocus();
        }
      });
    }
  }

  @override
  void dispose() {
    for (final controller in _blockControllers.values) {
      controller.dispose();
    }
    for (final focusNode in _blockFocusNodes.values) {
      focusNode.dispose();
    }
    super.dispose();
  }

  void _syncBlockEditors() {
    final textBlockIds = widget.state.articleBlocks
        .where((block) => block.isTextLike)
        .map((block) => block.id)
        .toSet();

    final removedIds = _blockControllers.keys
        .where((id) => !textBlockIds.contains(id))
        .toList(growable: false);
    for (final id in removedIds) {
      _blockControllers.remove(id)?.dispose();
      _blockFocusNodes.remove(id)?.dispose();
      _boundFocusNodeIds.remove(id);
    }

    for (final block in widget.state.articleBlocks.where(
      (item) => item.isTextLike,
    )) {
      final controller = _blockControllers.putIfAbsent(
        block.id,
        () => TextEditingController(text: block.text),
      );
      if (controller.text != block.text) {
        final selectionOffset = controller.selection.baseOffset;
        final safeOffset = selectionOffset < 0
            ? block.text.length
            : selectionOffset.clamp(0, block.text.length);
        controller.value = TextEditingValue(
          text: block.text,
          selection: TextSelection.collapsed(offset: safeOffset),
        );
      }
      final focusNode = _blockFocusNodes.putIfAbsent(block.id, FocusNode.new);
      if (_boundFocusNodeIds.add(block.id)) {
        focusNode.addListener(() {
          if (!focusNode.hasFocus) {
            return;
          }
          widget.onActiveBlockChanged(block.id);
          if (_showEmojiPanel && mounted) {
            setState(() => _showEmojiPanel = false);
          }
        });
      }
    }
  }

  String? _currentAnchorId() {
    final activeId = widget.state.activeArticleBlockId;
    if (activeId != null && activeId.trim().isNotEmpty) {
      return activeId;
    }
    if (widget.state.articleBlocks.isEmpty) {
      return null;
    }
    return widget.state.articleBlocks.last.id;
  }

  void _focusBlock(String blockId) {
    widget.onActiveBlockChanged(blockId);
    final focusNode = _blockFocusNodes[blockId];
    if (focusNode == null) {
      return;
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      focusNode.requestFocus();
    });
  }

  void _insertParagraph() {
    final blockId = widget.onInsertParagraph(_currentAnchorId());
    setState(() => _showEmojiPanel = false);
    _pendingFocusBlockId = blockId;
  }

  void _insertOrderedItem() {
    final blockId = widget.onInsertOrderedItem(_currentAnchorId());
    setState(() => _showEmojiPanel = false);
    _pendingFocusBlockId = blockId;
  }

  Future<void> _insertImages() async {
    setState(() => _showEmojiPanel = false);
    await widget.onInsertImages(_currentAnchorId());
  }

  void _toggleEmojiPanel() {
    if (widget.state.articleBlocks.where((block) => block.isTextLike).isEmpty) {
      _pendingFocusBlockId = widget.onInsertParagraph(_currentAnchorId());
    }
    setState(() => _showEmojiPanel = !_showEmojiPanel);
  }

  void _insertEmoji(String char) {
    var targetId = widget.state.activeArticleBlockId;
    if (targetId == null || !_blockControllers.containsKey(targetId)) {
      targetId = widget.onInsertParagraph(_currentAnchorId());
      _pendingFocusBlockId = targetId;
    }
    final controller = _blockControllers[targetId];
    if (controller == null) {
      return;
    }
    final selection = controller.selection;
    final start = selection.isValid ? selection.start : controller.text.length;
    final end = selection.isValid ? selection.end : controller.text.length;
    final safeStart = start.clamp(0, controller.text.length);
    final safeEnd = end.clamp(0, controller.text.length);
    final nextText = controller.text.replaceRange(safeStart, safeEnd, char);
    final caretOffset = safeStart + char.length;
    controller.value = TextEditingValue(
      text: nextText,
      selection: TextSelection.collapsed(offset: caretOffset),
    );
    widget.onUpdateTextBlock(targetId, nextText);
    _focusBlock(targetId);
  }

  Color _panelColor(BuildContext context) {
    return CupertinoColors.secondarySystemGroupedBackground.resolveFrom(
      context,
    );
  }

  Widget _buildSurface({required Widget child, EdgeInsets? padding}) {
    return Container(
      padding: padding ?? EdgeInsets.all(AppSpacing.containerMd),
      decoration: BoxDecoration(
        color: _panelColor(context),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
        border: Border.all(
          color: CupertinoColors.separator
              .resolveFrom(context)
              .withValues(alpha: 0.18),
          width: AppSpacing.hairline,
        ),
      ),
      child: child,
    );
  }

  Widget _buildTitleInput() {
    return _buildSurface(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: <Widget>[
          Text(
            '标题',
            style: TextStyle(
              color: CupertinoColors.secondaryLabel.resolveFrom(context),
              fontSize: AppTypography.sm,
              fontWeight: AppTypography.semiBold,
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupSm),
          CupertinoTextField(
            key: TestKeys.createTitleInput,
            controller: widget.titleController,
            focusNode: widget.titleFocusNode,
            padding: EdgeInsets.zero,
            placeholder: '添加标题（可选）',
            decoration: const BoxDecoration(),
            style: const TextStyle(
              fontSize: AppTypography.xl,
              fontWeight: AppTypography.bold,
            ),
            placeholderStyle: TextStyle(
              color: CupertinoColors.placeholderText.resolveFrom(context),
              fontSize: AppTypography.xl,
              fontWeight: AppTypography.bold,
            ),
            onChanged: widget.onTitleChanged,
          ),
        ],
      ),
    );
  }

  ArticleContentBlockView _toBlockView(
    CreateTextBlock block, {
    int? orderedIndex,
  }) {
    return switch (block.type) {
      CreateTextBlockType.image => ArticleContentBlockView(
        type: 'image',
        imageUrl: block.imagePath,
        imageLayout: block.imageLayout.name,
      ),
      CreateTextBlockType.orderedItem => ArticleContentBlockView(
        type: 'ordered_item',
        body: block.text,
        orderedIndex: orderedIndex,
      ),
      CreateTextBlockType.paragraph => ArticleContentBlockView(
        type: 'paragraph',
        body: block.text,
      ),
    };
  }

  List<_EditorRenderItem> _buildRenderItems(Map<String, int> orderedIndices) {
    final items = <_EditorRenderItem>[];
    final blocks = widget.state.articleBlocks;
    var index = 0;
    while (index < blocks.length) {
      final block = blocks[index];
      final nextBlock = index + 1 < blocks.length ? blocks[index + 1] : null;
      if (block.type == CreateTextBlockType.image &&
          block.usesWrappedLayout &&
          nextBlock != null &&
          nextBlock.type == CreateTextBlockType.paragraph) {
        items.add(
          _EditorRenderItem(
            view: ArticleContentBlockView(
              type: 'wrapped_paragraph',
              body: nextBlock.text,
              imageUrl: block.imagePath,
              imageLayout: block.imageLayout.name,
            ),
            imageBlock: block,
            wrappedTextBlock: nextBlock,
          ),
        );
        index += 2;
        continue;
      }
      items.add(
        _EditorRenderItem(
          view: _toBlockView(block, orderedIndex: orderedIndices[block.id]),
          textBlock: block.isTextLike ? block : null,
          imageBlock: block.type == CreateTextBlockType.image ? block : null,
        ),
      );
      index += 1;
    }
    return items;
  }

  Widget _buildEditableTextBlock(
    CreateTextBlock block, {
    required int? orderedIndex,
    Key? inputKey,
  }) {
    final isOrdered = block.type == CreateTextBlockType.orderedItem;
    final controller = _blockControllers[block.id]!;
    final focusNode = _blockFocusNodes[block.id]!;
    final titleColor = CupertinoColors.label.resolveFrom(context);
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () => _focusBlock(block.id),
      child: ArticleContentSurface(
        highlighted: true,
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            if (isOrdered) ...[
              Container(
                width: 28,
                height: 28,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: CupertinoColors.activeBlue
                      .resolveFrom(context)
                      .withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(
                    AppSpacing.radiusNinetyNine,
                  ),
                ),
                child: Text(
                  '${orderedIndex ?? 1}',
                  style: TextStyle(
                    color: CupertinoColors.activeBlue.resolveFrom(context),
                    fontSize: AppTypography.sm,
                    fontWeight: AppTypography.semiBold,
                  ),
                ),
              ),
              SizedBox(width: AppSpacing.containerSm),
            ],
            Expanded(
              child: CupertinoTextField(
                key: inputKey,
                controller: controller,
                focusNode: focusNode,
                inputFormatters: <TextInputFormatter>[
                  LengthLimitingTextInputFormatter(_kMaxBlockTextLength),
                ],
                minLines: isOrdered ? 1 : 3,
                maxLines: null,
                padding: EdgeInsets.zero,
                placeholder: isOrdered ? '输入这一条内容' : '继续写内容，支持 emoji、插图和序号',
                decoration: const BoxDecoration(),
                style: TextStyle(
                  color: titleColor,
                  fontSize: AppTypography.base,
                  height: isOrdered ? 1.8 : 1.9, // ignore: verify_dart_semantic
                ),
                placeholderStyle: TextStyle(
                  color: CupertinoColors.placeholderText.resolveFrom(context),
                  fontSize: AppTypography.base,
                  height: isOrdered ? 1.8 : 1.9, // ignore: verify_dart_semantic
                ),
                onTap: () => widget.onActiveBlockChanged(block.id),
                onChanged: (value) => widget.onUpdateTextBlock(block.id, value),
              ),
            ),
            SizedBox(width: AppSpacing.intraGroupSm),
            CupertinoButton(
              padding: EdgeInsets.zero,
              minimumSize: const Size.square(28),
              onPressed: () => widget.onRemoveBlock(block.id),
              child: Icon(
                CupertinoIcons.minus_circle,
                size: AppSpacing.iconMedium,
                color: CupertinoColors.tertiaryLabel.resolveFrom(context),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildImageControls(CreateTextBlock block) {
    return Row(
      children: CreateTextImageLayout.values
          .map((layout) {
            final selected = block.imageLayout == layout;
            return Expanded(
              child: Padding(
                padding: EdgeInsets.only(
                  right: layout == CreateTextImageLayout.wrapRight
                      ? 0
                      : AppSpacing.intraGroupXs,
                ),
                child: CupertinoButton(
                  padding: EdgeInsets.symmetric(
                    vertical: AppSpacing.intraGroupXs,
                  ),
                  minSize: 0,
                  color: selected
                      ? CupertinoColors.activeBlue
                            .resolveFrom(context)
                            .withValues(alpha: 0.92)
                      : CupertinoColors.systemGrey5.resolveFrom(context),
                  borderRadius: BorderRadius.circular(
                    AppSpacing.largeBorderRadius,
                  ),
                  onPressed: () {
                    widget.onActiveBlockChanged(block.id);
                    widget.onUpdateImageLayout(block.id, layout);
                  },
                  child: Text(
                    _imageLayoutLabel(layout),
                    style: TextStyle(
                      color: selected
                          ? CupertinoColors.white
                          : CupertinoColors.label.resolveFrom(context),
                      fontSize: AppTypography.xs,
                      fontWeight: AppTypography.semiBold,
                    ),
                  ),
                ),
              ),
            );
          })
          .toList(growable: false),
    );
  }

  Widget _buildActiveImageBlock(CreateTextBlock block, {bool compact = false}) {
    final aspectRatio = switch (block.imageLayout) {
      CreateTextImageLayout.fullWidth => 4 / 3,
      CreateTextImageLayout.wrapLeft => 1,
      CreateTextImageLayout.wrapRight => 1,
    }.toDouble();
    final image = GestureDetector(
      onTap: () => widget.onReplaceImage(block.id),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
        child: AspectRatio(
          aspectRatio: aspectRatio,
          child: Stack(
            fit: StackFit.expand,
            children: <Widget>[
              ArticleAdaptiveImage(imageUrl: block.imagePath),
              Positioned(
                left: AppSpacing.containerSm,
                right: AppSpacing.containerSm,
                bottom: AppSpacing.containerSm,
                child: Container(
                  padding: EdgeInsets.symmetric(
                    horizontal: AppSpacing.containerSm,
                    vertical: AppSpacing.intraGroupXs,
                  ),
                  decoration: BoxDecoration(
                    color: Colors.black.withValues(alpha: 0.45),
                    borderRadius: BorderRadius.circular(
                      AppSpacing.largeBorderRadius,
                    ),
                  ),
                  child: Text(
                    '轻点替换图片',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: CupertinoColors.white,
                      fontSize: AppTypography.sm,
                    ),
                  ),
                ),
              ),
              Positioned(
                top: AppSpacing.containerSm,
                right: AppSpacing.containerSm,
                child: CupertinoButton(
                  padding: EdgeInsets.zero,
                  minimumSize: const Size.square(28),
                  onPressed: () => widget.onRemoveBlock(block.id),
                  child: Container(
                    width: 28,
                    height: 28,
                    decoration: BoxDecoration(
                      color: Colors.black.withValues(alpha: 0.42),
                      shape: BoxShape.circle,
                    ),
                    child: const Icon(
                      CupertinoIcons.clear,
                      color: CupertinoColors.white,
                      size: 16,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
    if (compact) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          image,
          SizedBox(height: AppSpacing.intraGroupSm),
          _buildImageControls(block),
        ],
      );
    }
    return ArticleContentSurface(
      highlighted: true,
      padding: EdgeInsets.all(AppSpacing.containerSm),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          image,
          SizedBox(height: AppSpacing.intraGroupSm),
          _buildImageControls(block),
        ],
      ),
    );
  }

  Widget _buildWrappedActiveItem(
    CreateTextBlock imageBlock,
    CreateTextBlock textBlock, {
    Key? inputKey,
  }) {
    final activeId = widget.state.activeArticleBlockId;
    final isTextActive = activeId == textBlock.id;
    final isImageActive = activeId == imageBlock.id;
    final controller = _blockControllers[textBlock.id]!;
    final focusNode = _blockFocusNodes[textBlock.id]!;
    final image = SizedBox(
      width: 120,
      child: GestureDetector(
        onTap: () {
          if (isImageActive) {
            widget.onReplaceImage(imageBlock.id);
            return;
          }
          widget.onActiveBlockChanged(imageBlock.id);
        },
        child: _buildActiveImageBlock(imageBlock, compact: true),
      ),
    );
    final textChild = isTextActive
        ? CupertinoTextField(
            key: inputKey,
            controller: controller,
            focusNode: focusNode,
            inputFormatters: <TextInputFormatter>[
              LengthLimitingTextInputFormatter(_kMaxBlockTextLength),
            ],
            minLines: 6,
            maxLines: null,
            padding: EdgeInsets.zero,
            placeholder: '继续写内容，支持 emoji、插图和序号',
            decoration: const BoxDecoration(),
            style: TextStyle(
              color: CupertinoColors.label.resolveFrom(context),
              fontSize: AppTypography.base,
              height: 1.85, // ignore: verify_dart_semantic
            ),
            placeholderStyle: TextStyle(
              color: CupertinoColors.placeholderText.resolveFrom(context),
              fontSize: AppTypography.base,
              height: 1.85, // ignore: verify_dart_semantic
            ),
            onTap: () => widget.onActiveBlockChanged(textBlock.id),
            onChanged: (value) => widget.onUpdateTextBlock(textBlock.id, value),
          )
        : GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: () => _focusBlock(textBlock.id),
            child: Text(
              textBlock.text.trim().isEmpty ? '轻点开始写正文' : textBlock.text,
              style: TextStyle(
                color: textBlock.text.trim().isEmpty
                    ? CupertinoColors.placeholderText.resolveFrom(context)
                    : CupertinoColors.label.resolveFrom(context),
                fontSize: AppTypography.base,
                height: 1.85, // ignore: verify_dart_semantic
              ),
            ),
          );
    final rowChildren =
        imageBlock.imageLayout == CreateTextImageLayout.wrapRight
        ? <Widget>[
            Expanded(child: textChild),
            SizedBox(width: AppSpacing.containerSm),
            image,
          ]
        : <Widget>[
            image,
            SizedBox(width: AppSpacing.containerSm),
            Expanded(child: textChild),
          ];
    return ArticleContentSurface(
      highlighted: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: rowChildren,
          ),
          SizedBox(height: AppSpacing.intraGroupSm),
          Row(
            children: [
              CupertinoButton(
                padding: EdgeInsets.zero,
                minimumSize: const Size.square(28),
                onPressed: () => widget.onRemoveBlock(textBlock.id),
                child: Icon(
                  CupertinoIcons.minus_circle,
                  size: AppSpacing.iconMedium,
                  color: CupertinoColors.tertiaryLabel.resolveFrom(context),
                ),
              ),
              const Spacer(),
              if (isImageActive)
                Text(
                  '正在编辑图片布局',
                  style: TextStyle(
                    color: CupertinoColors.secondaryLabel.resolveFrom(context),
                    fontSize: AppTypography.xs,
                  ),
                ),
            ],
          ),
        ],
      ),
    );
  }

  String _imageLayoutLabel(CreateTextImageLayout layout) {
    return switch (layout) {
      CreateTextImageLayout.fullWidth => '通栏',
      CreateTextImageLayout.wrapLeft => '左环绕',
      CreateTextImageLayout.wrapRight => '右环绕',
    };
  }

  Widget _buildToolbarButton({
    Key? key,
    required IconData icon,
    required String label,
    required VoidCallback onTap,
    bool isSelected = false,
  }) {
    final tint = isSelected
        ? CupertinoColors.activeBlue.resolveFrom(context)
        : CupertinoColors.label.resolveFrom(context);
    return Expanded(
      child: CupertinoButton(
        key: key,
        padding: EdgeInsets.symmetric(vertical: AppSpacing.intraGroupXs),
        onPressed: onTap,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(icon, size: AppSpacing.iconMedium, color: tint),
            SizedBox(height: AppSpacing.intraGroupXs / 2),
            Text(
              label,
              style: TextStyle(
                color: tint,
                fontSize: AppTypography.xs,
                fontWeight: AppTypography.medium,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Map<String, int> _orderedIndices() {
    final result = <String, int>{};
    var current = 0;
    for (final block in widget.state.articleBlocks) {
      if (block.type == CreateTextBlockType.orderedItem) {
        current += 1;
        result[block.id] = current;
      } else {
        current = 0;
      }
    }
    return result;
  }

  @override
  Widget build(BuildContext context) {
    final orderedIndices = _orderedIndices();
    final renderItems = _buildRenderItems(orderedIndices);
    String? inputTargetBlockId;
    for (final item in renderItems) {
      if (item.primaryTextBlockId != null &&
          item.containsBlock(widget.state.activeArticleBlockId)) {
        inputTargetBlockId = item.primaryTextBlockId;
        break;
      }
    }
    if (inputTargetBlockId == null) {
      for (final item in renderItems) {
        if (item.primaryTextBlockId != null) {
          inputTargetBlockId = item.primaryTextBlockId;
          break;
        }
      }
    }
    var primaryTextKeyUsed = false;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        _buildTitleInput(),
        SizedBox(
          height: widget.immersive
              ? AppSpacing.intraGroupSm
              : AppSpacing.interGroupMd,
        ),
        Text(
          '正文',
          style: TextStyle(
            color: CupertinoColors.secondaryLabel.resolveFrom(context),
            fontSize: AppTypography.sm,
            fontWeight: AppTypography.semiBold,
          ),
        ),
        SizedBox(height: AppSpacing.intraGroupSm),
        ...renderItems.map((item) {
          Key? inputKey;
          if (!primaryTextKeyUsed &&
              item.primaryTextBlockId != null &&
              item.primaryTextBlockId == inputTargetBlockId) {
            inputKey = TestKeys.createMomentInput;
            primaryTextKeyUsed = true;
          }
          final activeId = widget.state.activeArticleBlockId;
          final isActive = item.containsBlock(activeId);
          Widget child;
          if (item.imageBlock != null &&
              item.wrappedTextBlock != null &&
              isActive) {
            child = _buildWrappedActiveItem(
              item.imageBlock!,
              item.wrappedTextBlock!,
              inputKey: inputKey,
            );
          } else if (item.imageBlock != null &&
              item.wrappedTextBlock == null &&
              activeId == item.imageBlock!.id) {
            child = _buildActiveImageBlock(item.imageBlock!);
          } else if (item.textBlock != null && activeId == item.textBlock!.id) {
            child = _buildEditableTextBlock(
              item.textBlock!,
              orderedIndex: orderedIndices[item.textBlock!.id],
              inputKey: inputKey,
            );
          } else {
            child = ArticleContentBlockRenderer(
              block: item.view,
              onTap: () {
                final targetId = item.primaryTextBlockId ?? item.imageBlock?.id;
                if (targetId == null) {
                  return;
                }
                if (item.primaryTextBlockId != null) {
                  _focusBlock(targetId);
                } else {
                  widget.onActiveBlockChanged(targetId);
                }
              },
            );
          }
          return Padding(
            padding: EdgeInsets.only(bottom: AppSpacing.intraGroupSm),
            child: child,
          );
        }),
        SizedBox(height: AppSpacing.intraGroupXs),
        _buildSurface(
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.containerSm,
            vertical: AppSpacing.intraGroupXs,
          ),
          child: Row(
            children: <Widget>[
              _buildToolbarButton(
                icon: _showEmojiPanel
                    ? CupertinoIcons.keyboard
                    : CupertinoIcons.smiley,
                label: 'Emoji',
                onTap: _toggleEmojiPanel,
                isSelected: _showEmojiPanel,
              ),
              _buildToolbarButton(
                key: TestKeys.createMediaAddButton,
                icon: CupertinoIcons.photo_on_rectangle,
                label: '图片',
                onTap: _insertImages,
              ),
              _buildToolbarButton(
                icon: CupertinoIcons.list_number,
                label: '序号',
                onTap: _insertOrderedItem,
              ),
              _buildToolbarButton(
                icon: CupertinoIcons.text_insert,
                label: '段落',
                onTap: _insertParagraph,
              ),
            ],
          ),
        ),
        if (_showEmojiPanel) ...<Widget>[
          SizedBox(height: AppSpacing.intraGroupSm),
          ClipRRect(
            borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
            child: UnifiedEmojiPicker(
              onEmojiSelected: _insertEmoji,
              showCloseButton: true,
              onClose: () => setState(() => _showEmojiPanel = false),
            ),
          ),
        ],
      ],
    );
  }
}
