import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/article_wrap_layout.dart';

enum ArticleWrapEditorSegment { narrow, below }

class ArticleWrapParagraphEditor extends StatefulWidget {
  const ArticleWrapParagraphEditor({
    super.key,
    required this.groupId,
    required this.narrowText,
    required this.belowText,
    required this.imageChild,
    required this.imageWidth,
    required this.narrowWidth,
    required this.gap,
    required this.isLeft,
    required this.floatHeight,
    required this.style,
    required this.placeholderStyle,
    required this.onChanged,
    required this.onFocused,
    required this.onSelectionChanged,
    this.placeholder,
    this.autofocusSegment,
    this.autofocusSelectionOffset,
    this.belowSpacing = 0,
    this.maxLinesBeside,
  });

  final String groupId;
  final String narrowText;
  final String belowText;
  final Widget imageChild;
  final double imageWidth;
  final double narrowWidth;
  final double gap;
  final bool isLeft;
  final double floatHeight;
  final TextStyle style;
  final TextStyle placeholderStyle;
  final void Function(String narrowText, String belowText) onChanged;
  final ValueChanged<ArticleWrapEditorSegment> onFocused;
  final void Function(ArticleWrapEditorSegment segment, int offset)
      onSelectionChanged;
  final String? placeholder;
  final ArticleWrapEditorSegment? autofocusSegment;
  final int? autofocusSelectionOffset;
  final double belowSpacing;
  final int? maxLinesBeside;

  @override
  State<ArticleWrapParagraphEditor> createState() =>
      ArticleWrapParagraphEditorState();
}

class ArticleWrapParagraphEditorState
    extends State<ArticleWrapParagraphEditor> {
  late TextEditingController _narrowController;
  late TextEditingController _belowController;
  late FocusNode _narrowFocusNode;
  late FocusNode _belowFocusNode;
  ArticleWrapEditorSegment? _pendingFocusSegment;
  bool _syncingControllers = false;

  void unfocus() {
    if (_narrowFocusNode.hasFocus) {
      _narrowFocusNode.unfocus();
    }
    if (_belowFocusNode.hasFocus) {
      _belowFocusNode.unfocus();
    }
  }

  @override
  void initState() {
    super.initState();
    _narrowController = TextEditingController(text: widget.narrowText);
    _belowController = TextEditingController(text: widget.belowText);
    _narrowFocusNode = FocusNode(debugLabel: 'wrap_narrow_${widget.groupId}');
    _belowFocusNode = FocusNode(debugLabel: 'wrap_below_${widget.groupId}');
    _narrowController.addListener(_handleNarrowChanged);
    _belowController.addListener(_handleBelowChanged);
    _narrowFocusNode.addListener(
      () => _handleFocusChanged(ArticleWrapEditorSegment.narrow),
    );
    _belowFocusNode.addListener(
      () => _handleFocusChanged(ArticleWrapEditorSegment.below),
    );
    _scheduleAutofocusIfNeeded();
  }

  @override
  void didUpdateWidget(covariant ArticleWrapParagraphEditor oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.narrowText != oldWidget.narrowText) {
      _replaceControllerText(
        _narrowController,
        widget.narrowText,
        preserveFocus: _narrowFocusNode.hasFocus,
      );
    }
    if (widget.belowText != oldWidget.belowText) {
      _replaceControllerText(
        _belowController,
        widget.belowText,
        preserveFocus: _belowFocusNode.hasFocus,
      );
    }
    if (widget.autofocusSegment != oldWidget.autofocusSegment ||
        widget.autofocusSelectionOffset != oldWidget.autofocusSelectionOffset) {
      _scheduleAutofocusIfNeeded();
    }
    if (widget.narrowWidth != oldWidget.narrowWidth ||
        widget.floatHeight != oldWidget.floatHeight ||
        widget.maxLinesBeside != oldWidget.maxLinesBeside) {
      _spillOverflowToBelow();
    }
  }

  void _scheduleAutofocusIfNeeded() {
    if (widget.autofocusSegment == null) {
      return;
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || widget.autofocusSegment == null) {
        return;
      }
      _requestFocus(
        widget.autofocusSegment!,
        widget.autofocusSelectionOffset ?? 0,
      );
    });
  }

  void _replaceControllerText(
    TextEditingController controller,
    String nextText, {
    required bool preserveFocus,
  }) {
    final nextSelection = preserveFocus && controller.selection.isValid
        ? TextSelection.collapsed(
            offset: controller.selection.extentOffset.clamp(0, nextText.length),
          )
        : TextSelection.collapsed(offset: nextText.length);
    _syncingControllers = true;
    controller.value = TextEditingValue(text: nextText, selection: nextSelection);
    _syncingControllers = false;
  }

  int _narrowMaxLines() {
    if (widget.maxLinesBeside != null) {
      return widget.maxLinesBeside!.clamp(1, 24);
    }
    final lineHeight =
        (widget.style.fontSize ?? AppTypography.base) *
        (widget.style.height ?? 1.0);
    return (widget.floatHeight / lineHeight).floor().clamp(1, 24);
  }

  TextEditingController _controller(ArticleWrapEditorSegment segment) =>
      segment == ArticleWrapEditorSegment.narrow
          ? _narrowController
          : _belowController;

  FocusNode _focusNode(ArticleWrapEditorSegment segment) =>
      segment == ArticleWrapEditorSegment.narrow
          ? _narrowFocusNode
          : _belowFocusNode;

  ArticleWrapEditorSegment? _currentFocusedSegment() {
    if (_belowFocusNode.hasFocus) {
      return ArticleWrapEditorSegment.below;
    }
    if (_narrowFocusNode.hasFocus) {
      return ArticleWrapEditorSegment.narrow;
    }
    return null;
  }

  void _handleFocusChanged(ArticleWrapEditorSegment segment) {
    final focusNode = _focusNode(segment);
    if (!focusNode.hasFocus) {
      if (mounted) {
        setState(() {});
      }
      return;
    }
    _pendingFocusSegment = null;
    final otherSegment = segment == ArticleWrapEditorSegment.narrow
        ? ArticleWrapEditorSegment.below
        : ArticleWrapEditorSegment.narrow;
    final otherFocusNode = _focusNode(otherSegment);
    if (otherFocusNode.hasFocus) {
      otherFocusNode.unfocus();
    }
    widget.onFocused(segment);
    widget.onSelectionChanged(
      segment,
      _controller(segment).selection.extentOffset.clamp(
            0,
            _controller(segment).text.length,
          ),
    );
    if (mounted) {
      setState(() {});
    }
  }

  void _handleNarrowChanged() {
    if (_syncingControllers) {
      return;
    }
    final overflowOffset = _spillOverflowToBelow();
    if (_narrowFocusNode.hasFocus) {
      widget.onSelectionChanged(
        ArticleWrapEditorSegment.narrow,
        _narrowController.selection.extentOffset.clamp(
          0,
          _narrowController.text.length,
        ),
      );
    }
    widget.onChanged(_narrowController.text, _belowController.text);
    if (overflowOffset != null) {
      _requestFocus(ArticleWrapEditorSegment.below, overflowOffset);
    }
  }

  void _handleBelowChanged() {
    if (_syncingControllers) {
      return;
    }
    if (_belowFocusNode.hasFocus) {
      widget.onSelectionChanged(
        ArticleWrapEditorSegment.below,
        _belowController.selection.extentOffset.clamp(
          0,
          _belowController.text.length,
        ),
      );
    }
    widget.onChanged(_narrowController.text, _belowController.text);
  }

  int? _spillOverflowToBelow() {
    final currentText = _narrowController.text;
    if (currentText.isEmpty || widget.narrowWidth <= 0 || widget.floatHeight <= 0) {
      return null;
    }
    final splitOffset = resolveWrappedSplitIndex(
      text: currentText,
      sideWidth: widget.narrowWidth,
      style: widget.style,
      maxLines: _narrowMaxLines(),
    );
    if (splitOffset >= currentText.length) {
      return null;
    }
    final selectionOffset = _narrowController.selection.extentOffset.clamp(
      0,
      currentText.length,
    );
    final overflowText = currentText.substring(splitOffset);
    final nextNarrow = currentText.substring(0, splitOffset);
    final nextBelow = '$overflowText${_belowController.text}';
    final shouldMoveFocus =
        _narrowFocusNode.hasFocus && selectionOffset > splitOffset;
    final nextBelowOffset = shouldMoveFocus
        ? (selectionOffset - splitOffset).clamp(0, nextBelow.length)
        : _belowController.selection.extentOffset.clamp(0, nextBelow.length);
    _syncingControllers = true;
    _narrowController.value = TextEditingValue(
      text: nextNarrow,
      selection: TextSelection.collapsed(
        offset: selectionOffset.clamp(0, nextNarrow.length),
      ),
    );
    _belowController.value = TextEditingValue(
      text: nextBelow,
      selection: TextSelection.collapsed(offset: nextBelowOffset),
    );
    _syncingControllers = false;
    return shouldMoveFocus ? nextBelowOffset : null;
  }

  void _requestFocus(ArticleWrapEditorSegment segment, int localOffset) {
    final focusNode = _focusNode(segment);
    final controller = _controller(segment);
    final otherFocusNode = _focusNode(
      segment == ArticleWrapEditorSegment.narrow
          ? ArticleWrapEditorSegment.below
          : ArticleWrapEditorSegment.narrow,
    );
    if (otherFocusNode.hasFocus) {
      otherFocusNode.unfocus();
    }
    if (focusNode.hasFocus) {
      _pendingFocusSegment = null;
      controller.selection = TextSelection.collapsed(
        offset: localOffset.clamp(0, controller.text.length),
      );
      widget.onSelectionChanged(
        segment,
        localOffset.clamp(0, controller.text.length),
      );
      return;
    }
    _pendingFocusSegment = segment;
    if (mounted) {
      setState(() {});
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      final targetFocusNode = _focusNode(segment);
      final targetController = _controller(segment);
      targetFocusNode.requestFocus();
      targetController.selection = TextSelection.collapsed(
        offset: localOffset.clamp(0, targetController.text.length),
      );
      widget.onSelectionChanged(
        segment,
        localOffset.clamp(0, targetController.text.length),
      );
    });
  }

  Widget _buildInactiveBelow(double lineHeight) {
    if (_belowController.text.isNotEmpty) {
      return Text(
        _belowController.text,
        style: widget.style,
      );
    }
    return SizedBox(
      height: lineHeight,
      child: const SizedBox.shrink(),
    );
  }

  @override
  void dispose() {
    _narrowController.dispose();
    _belowController.dispose();
    _narrowFocusNode.dispose();
    _belowFocusNode.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final lineHeight =
        (widget.style.fontSize ?? AppTypography.base) *
        (widget.style.height ?? 1.0);
    final narrowStyle = widget.style.copyWith(
      leadingDistribution: TextLeadingDistribution.even,
    );
    final narrowStrut = StrutStyle.fromTextStyle(
      narrowStyle,
      forceStrutHeight: true,
    );
    final activeSegment =
        _pendingFocusSegment ?? (_currentFocusedSegment() ?? ArticleWrapEditorSegment.narrow);

    final Widget narrowField = activeSegment != ArticleWrapEditorSegment.below
        ? EditableText(
            key: ValueKey<String>('wrap_narrow_${widget.groupId}'),
            controller: _narrowController,
            focusNode: _narrowFocusNode,
            style: narrowStyle,
            strutStyle: narrowStrut,
            cursorColor: CupertinoColors.activeBlue,
            backgroundCursorColor: CupertinoColors.inactiveGray,
            keyboardType: TextInputType.multiline,
            textInputAction: TextInputAction.newline,
            maxLines: _narrowMaxLines(),
            minLines: 1,
          )
        : GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: () => _requestFocus(
              ArticleWrapEditorSegment.narrow,
              _narrowController.text.length,
            ),
            child: Text(
              _narrowController.text,
              key: ValueKey<String>('wrap_narrow_${widget.groupId}'),
              style: narrowStyle,
              strutStyle: narrowStrut,
              maxLines: _narrowMaxLines(),
            ),
          );

    final showPlaceholder =
        _narrowController.text.isEmpty && widget.placeholder != null;
    Widget narrowContent = narrowField;
    if (showPlaceholder) {
      narrowContent = Stack(
        children: <Widget>[
          narrowField,
          IgnorePointer(
            child: Text(
              widget.placeholder!,
              style: widget.placeholderStyle,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      );
    }

    final sideChild = GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () => _requestFocus(
        ArticleWrapEditorSegment.narrow,
        _narrowController.text.length,
      ),
      child: Align(
        alignment: Alignment.topLeft,
        child: narrowContent,
      ),
    );

    final Widget belowField = activeSegment == ArticleWrapEditorSegment.below
        ? EditableText(
            controller: _belowController,
            focusNode: _belowFocusNode,
            style: widget.style,
            cursorColor: CupertinoColors.activeBlue,
            backgroundCursorColor: CupertinoColors.inactiveGray,
            keyboardType: TextInputType.multiline,
            textInputAction: TextInputAction.newline,
            maxLines: null,
            minLines: 1,
          )
        : _buildInactiveBelow(lineHeight);

    final belowChild = GestureDetector(
      key: ValueKey<String>('wrap_below_${widget.groupId}'),
      behavior: HitTestBehavior.opaque,
      onTap: () => _requestFocus(
        ArticleWrapEditorSegment.below,
        _belowController.text.length,
      ),
      child: belowField,
    );

    return ArticleWrapLayout(
      imageWidth: widget.imageWidth,
      gap: widget.gap,
      isLeft: widget.isLeft,
      imageChild: widget.imageChild,
      sideChild: sideChild,
      sideMinHeight: 0,
      belowChild: belowChild,
      belowSpacing: widget.belowSpacing,
    );
  }
}
