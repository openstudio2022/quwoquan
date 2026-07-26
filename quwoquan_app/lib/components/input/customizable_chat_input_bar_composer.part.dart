part of 'customizable_chat_input_bar.dart';

extension _CustomizableChatInputBarComposer on _CustomizableChatInputBarState {
  void _insertXiaoquMention() {
    if (widget.disabled) {
      return;
    }
    final controller = _controller;
    if (controller is ChatMentionTextEditingController) {
      controller.insertMentionAtSelection(
        const ChatInputMentionCandidate(
          id: 'assistant',
          displayName: '小趣',
          kind: ChatInputMentionKind.assistant,
        ),
      );
      _focusNode.requestFocus();
      _updateState(() => _panelMode = ChatInputPanelMode.none);
      return;
    }
    const mention = '${ChatText.commentAtXiaoqu} ';
    final text = controller.text;
    final selection = controller.selection;
    final insertionOffset = selection.isValid
        ? selection.baseOffset.clamp(0, text.length)
        : text.length;
    controller
      ..text =
          text.substring(0, insertionOffset) +
          mention +
          text.substring(insertionOffset)
      ..selection = TextSelection.collapsed(
        offset: insertionOffset + mention.length,
      );
    _pendingMentions.add('assistant');
    _focusNode.requestFocus();
    _updateState(() => _panelMode = ChatInputPanelMode.none);
  }

  void _toggleEmojiPanel() {
    if (widget.disabled) return;
    if (!widget.showEmojiButton) return;
    _updateState(() {
      _panelMode = _showEmojiPanel
          ? ChatInputPanelMode.none
          : ChatInputPanelMode.emoji;
      if (_panelMode == ChatInputPanelMode.emoji) {
        _focusNode.unfocus();
      } else if (!_isVoiceMode) {
        _focusNode.requestFocus();
      }
    });
  }

  Future<void> _send() async {
    if (!_canSend) return;
    final mentionIds = <String>{..._pendingMentions};
    final controller = _controller;
    if (controller is ChatMentionTextEditingController) {
      mentionIds.addAll(controller.activeMentionIds);
    }
    final payload = ChatInputSubmitPayload(
      text: controller.text.trim(),
      attachments: List<ChatInputAttachment>.from(_attachments),
      mentions: List<String>.unmodifiable(mentionIds),
    );
    final hadAttachments = _attachments.isNotEmpty;
    _updateState(() {
      _controller.clear();
      _attachments.clear();
      _pendingMentions.clear();
      _panelMode = ChatInputPanelMode.none;
    });
    if (hadAttachments) {
      widget.onAttachmentChanged?.call(const <ChatInputAttachment>[]);
    }
    await widget.onSend(payload);
  }

  Future<void> _openExpandedEditor() async {
    if (widget.disabled || !widget.enableExpandedEditor || _isVoiceMode) {
      return;
    }
    final shouldRefocus = _focusNode.hasFocus;
    final draft = await Navigator.of(context).push<_ExpandedInputDraft>(
      CupertinoPageRoute<_ExpandedInputDraft>(
        settings: const RouteSettings(
          name: PageAccessInternalRoutes.chatInputExpandedDraft,
        ),
        fullscreenDialog: true,
        builder: (context) => _ExpandedChatInputPage(
          initialText: _controller.text,
          hintText: widget.hintText ?? ChatText.inputHint,
          showEmojiButton: widget.showEmojiButton,
        ),
      ),
    );
    if (!mounted || draft == null) {
      return;
    }
    _controller.value = TextEditingValue(
      text: draft.text,
      selection: TextSelection.collapsed(offset: draft.text.length),
    );
    _updateState(() {
      _panelMode = draft.openEmojiPanel && widget.showEmojiButton
          ? ChatInputPanelMode.emoji
          : ChatInputPanelMode.none;
    });
    if (shouldRefocus && !_showEmojiPanel) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) {
          _focusNode.requestFocus();
        }
      });
    }
  }

  List<Widget> _buildTrailingButtons(
    BuildContext context, {
    required bool compact,
  }) {
    final buttons = <Widget>[];
    if (widget.showXiaoquMentionButton && !_isVoiceMode && !compact) {
      buttons.add(
        Semantics(
          button: true,
          label: ChatText.commentAtXiaoqu,
          child: CupertinoButton(
            key: TestKeys.chatInputAtXiaoquButton,
            padding: EdgeInsets.symmetric(horizontal: AppSpacing.xs),
            minimumSize: Size(
              AppSpacing.chatInputIconButtonSize,
              AppSpacing.chatInputIconButtonSize,
            ),
            onPressed: widget.disabled ? null : _insertXiaoquMention,
            child: Text(
              ChatText.commentAtXiaoqu,
              style: TextStyle(
                fontSize: AppTypography.xs,
                fontWeight: AppTypography.semiBold,
                color: AppColors.primaryColor,
              ),
            ),
          ),
        ),
      );
      if (widget.showEmojiButton || _canSend || widget.showAddPanel) {
        buttons.add(SizedBox(width: AppSpacing.xs));
      }
    }
    if (widget.showEmojiButton) {
      buttons.add(
        _buildToolbarPlainIconButton(
          context: context,
          key: TestKeys.chatInputEmojiToggleButton,
          icon: _showEmojiPanel
              ? _kChatInputKeyboardCompactIcon
              : _kChatInputEmojiPanelIcon,
          onTap: widget.disabled ? null : _toggleEmojiPanel,
          semanticLabel: _showEmojiPanel ? ChatText.keyboard : ChatText.emoji,
        ),
      );
    }
    if (widget.showEmojiButton && (_canSend || widget.showAddPanel)) {
      buttons.add(SizedBox(width: AppSpacing.xs));
    }
    if (_canSend) {
      buttons.add(_buildSendButton(context));
      return buttons;
    }
    if (widget.showAddPanel) {
      buttons.add(
        _buildToolbarPlainIconButton(
          context: context,
          key: TestKeys.chatInputMoreButton,
          icon: CupertinoIcons.add,
          onTap: widget.disabled ? null : _toggleAddPanel,
          semanticLabel: ChatText.more,
        ),
      );
    }
    return buttons;
  }

  /// 与工具栏底同色语义：无圆框、透明热区，图标即按钮。
  Widget _buildToolbarPlainIconButton({
    required BuildContext context,
    Key? key,
    required IconData icon,
    required VoidCallback? onTap,
    required String semanticLabel,
    double iconSize = _kChatInputToolbarGlyphSize,
  }) {
    final fg = _foregroundPrimary(
      context,
    ).withValues(alpha: onTap == null ? 0.32 : 0.82);
    return Semantics(
      button: true,
      label: semanticLabel,
      child: CupertinoButton(
        key: key,
        padding: EdgeInsets.zero,
        minimumSize: Size.square(AppSpacing.chatInputIconButtonSize),
        onPressed: onTap,
        child: Icon(icon, size: iconSize, color: fg),
      ),
    );
  }

  Widget _buildSendButton(BuildContext context) {
    return Semantics(
      button: true,
      label: ChatText.send,
      onTap: widget.disabled ? null : _send,
      child: GestureDetector(
        key: widget.sendButtonKey,
        onTap: widget.disabled ? null : _send,
        child: Container(
          width: AppSpacing.chatInputSendButtonSize,
          height: AppSpacing.chatInputSendButtonSize,
          decoration: BoxDecoration(
            color: widget.disabled
                ? AppColors.primaryColor.withValues(alpha: 0.35)
                : AppColors.primaryColor,
            borderRadius: BorderRadius.circular(
              AppSpacing.chatInputSendButtonSize,
            ),
          ),
          alignment: Alignment.center,
          child: Icon(
            Icons.arrow_upward_rounded,
            size: _kChatInputSendGlyphSize,
            color: _fieldBackground(context),
          ),
        ),
      ),
    );
  }

  int _estimateLineCount({
    required String text,
    required TextStyle style,
    required double maxWidth,
  }) {
    if (text.trim().isEmpty || maxWidth <= 0) {
      return 1;
    }
    final painter = TextPainter(
      text: TextSpan(text: text, style: style),
      textDirection: TextDirection.ltr,
    )..layout(maxWidth: maxWidth);
    return math.max(1, painter.computeLineMetrics().length);
  }

  Widget _buildTextComposerCenter() {
    final textStyle = _composerTextStyle(context);
    final secondary = _foregroundSecondary(context);
    final hPad = AppSpacing.md;
    return LayoutBuilder(
      builder: (context, constraints) {
        final estimatedWidth = constraints.maxWidth - hPad * 2;
        final lineCount = _estimateLineCount(
          text: _controller.text,
          style: textStyle,
          maxWidth: estimatedWidth,
        );
        final canExpandInline =
            widget.enableExpandedEditor && lineCount > widget.maxVisibleLines;
        final alignVertical = lineCount <= 1
            ? TextAlignVertical.center
            : TextAlignVertical.top;
        final fontSize = textStyle.fontSize ?? AppSpacing.md;
        final lineHeight = textStyle.height ?? AppTypography.bodyLineHeight;
        final lineBoxHeight = fontSize * lineHeight;
        final vPad = lineCount <= 1
            ? ((_CustomizableChatInputBarState._composerCenterMinHeight -
                          lineBoxHeight) /
                      2)
                  .clamp(AppSpacing.xs, AppSpacing.lg)
            : AppSpacing.sm;
        return ClipRRect(
          borderRadius: BorderRadius.circular(
            _CustomizableChatInputBarState._fieldCornerRadius,
          ),
          child: ColoredBox(
            color: _composerInputFill(context),
            child: ConstrainedBox(
              constraints: const BoxConstraints(
                minHeight:
                    _CustomizableChatInputBarState._composerCenterMinHeight,
              ),
              child: Stack(
                children: [
                  TextField(
                    key: widget.textFieldKey,
                    controller: _controller,
                    focusNode: _focusNode,
                    scrollController: _textScrollController,
                    enabled: !widget.disabled && !_isVoiceMode,
                    maxLength: widget.maxTextLength,
                    maxLines: widget.maxVisibleLines,
                    minLines: 1,
                    textAlignVertical: alignVertical,
                    cursorColor: AppColors.primaryColor,
                    style: textStyle,
                    strutStyle: StrutStyle(
                      fontSize: fontSize,
                      height: lineHeight,
                      leadingDistribution: TextLeadingDistribution.even,
                      forceStrutHeight: true,
                    ),
                    onTap: () {
                      if (widget.disabled) {
                        return;
                      }
                      if (_panelMode != ChatInputPanelMode.none) {
                        _updateState(
                          () => _panelMode = ChatInputPanelMode.none,
                        );
                      }
                    },
                    decoration: InputDecoration(
                      hintText: widget.disabled
                          ? ChatText.chatBlockedConversationInputHint
                          : widget.hintText ?? ChatText.inputHint,
                      hintStyle: TextStyle(
                        color: secondary,
                        fontSize: fontSize,
                        height: lineHeight,
                      ),
                      border: InputBorder.none,
                      isDense: true,
                      counterText: '',
                      contentPadding: EdgeInsets.fromLTRB(
                        hPad,
                        vPad,
                        hPad,
                        vPad,
                      ),
                    ),
                  ),
                  if (canExpandInline)
                    Positioned(
                      left: AppSpacing.sm,
                      top: AppSpacing.xs,
                      child: CupertinoButton(
                        key: TestKeys.chatInputExpandButton,
                        padding: EdgeInsets.zero,
                        minimumSize: Size.square(
                          AppSpacing.iconButtonMinSizeSm,
                        ),
                        onPressed: widget.disabled ? null : _openExpandedEditor,
                        child: Align(
                          alignment: Alignment.centerLeft,
                          child: Icon(
                            CupertinoIcons.arrow_up_left_arrow_down_right,
                            size: AppSpacing.iconSmall,
                            color: secondary,
                          ),
                        ),
                      ),
                    ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _buildEmojiPanel() {
    if (!_showEmojiPanel) return const SizedBox.shrink();
    return Container(
      margin: EdgeInsets.only(top: AppSpacing.sm),
      child: UnifiedEmojiPicker(
        showCloseButton: true,
        onClose: () => _updateState(() => _panelMode = ChatInputPanelMode.none),
        onEmojiSelected: (char) {
          final next = '${_controller.text}$char';
          _controller.value = TextEditingValue(
            text: next,
            selection: TextSelection.collapsed(offset: next.length),
          );
        },
      ),
    );
  }
}

class _ExpandedInputDraft {
  const _ExpandedInputDraft({required this.text, required this.openEmojiPanel});

  final String text;
  final bool openEmojiPanel;
}

class _ExpandedChatInputPage extends StatefulWidget {
  const _ExpandedChatInputPage({
    required this.initialText,
    required this.hintText,
    required this.showEmojiButton,
  });

  final String initialText;
  final String hintText;
  final bool showEmojiButton;

  @override
  State<_ExpandedChatInputPage> createState() => _ExpandedChatInputPageState();
}

class _ExpandedChatInputPageState extends State<_ExpandedChatInputPage> {
  late final TextEditingController _controller;
  final FocusNode _focusNode = FocusNode();
  bool _showEmojiPanel = false;

  Color _cupertinoColor(BuildContext context, CupertinoDynamicColor color) {
    return CupertinoDynamicColor.resolve(color, context);
  }

  Color _foregroundPrimary(BuildContext context) =>
      _cupertinoColor(context, CupertinoColors.label);

  Color _foregroundSecondary(BuildContext context) =>
      _cupertinoColor(context, CupertinoColors.secondaryLabel);

  Color _surfaceBackground(BuildContext context) => _cupertinoColor(
    context,
    CupertinoColors.secondarySystemGroupedBackground,
  );

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: widget.initialText);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        _focusNode.requestFocus();
      }
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  void _closeEditor() {
    Navigator.of(context).pop(
      _ExpandedInputDraft(
        text: _controller.text,
        openEmojiPanel: _showEmojiPanel,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final composerFontSize = AppTypography.base;
    final composerStyle = TextStyle(
      fontSize: composerFontSize,
      height: AppTypography.bodyLineHeight,
      color: _foregroundPrimary(context),
    );
    return CupertinoPageScaffold(
      backgroundColor: _surfaceBackground(context),
      child: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: EdgeInsets.fromLTRB(
                AppSpacing.sm,
                AppSpacing.xs,
                AppSpacing.sm,
                AppSpacing.sm,
              ),
              child: Row(
                children: [
                  CupertinoButton(
                    key: TestKeys.chatInputCollapseButton,
                    padding: EdgeInsets.zero,
                    minimumSize: Size.square(AppSpacing.iconButtonMinSizeSm),
                    onPressed: _closeEditor,
                    child: Icon(
                      CupertinoIcons.chevron_down,
                      color: _foregroundPrimary(context),
                    ),
                  ),
                ],
              ),
            ),
            Expanded(
              child: Container(
                key: TestKeys.fullscreenModalSurface,
                width: double.infinity,
                margin: EdgeInsets.symmetric(horizontal: AppSpacing.md),
                padding: EdgeInsets.all(AppSpacing.md),
                decoration: BoxDecoration(
                  color: CupertinoColors.systemBackground.resolveFrom(context),
                  borderRadius: BorderRadius.circular(
                    AppSpacing.largeBorderRadius,
                  ),
                ),
                child: TextField(
                  controller: _controller,
                  focusNode: _focusNode,
                  maxLines: null,
                  expands: true,
                  textAlignVertical: TextAlignVertical.top,
                  cursorColor: AppColors.primaryColor,
                  style: composerStyle,
                  decoration: InputDecoration(
                    hintText: widget.hintText,
                    hintStyle: composerStyle.copyWith(
                      color: _foregroundSecondary(context),
                    ),
                    border: InputBorder.none,
                  ),
                ),
              ),
            ),
            Padding(
              padding: EdgeInsets.fromLTRB(
                AppSpacing.md,
                AppSpacing.sm,
                AppSpacing.md,
                AppSpacing.sm,
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  if (widget.showEmojiButton)
                    CupertinoButton(
                      key: TestKeys.chatInputExpandedEmojiToggleButton,
                      padding: EdgeInsets.zero,
                      minimumSize: Size.square(AppSpacing.iconButtonMinSizeSm),
                      onPressed: () {
                        setState(() => _showEmojiPanel = !_showEmojiPanel);
                        if (_showEmojiPanel) {
                          _focusNode.unfocus();
                        } else {
                          _focusNode.requestFocus();
                        }
                      },
                      child: Icon(
                        _showEmojiPanel
                            ? _kChatInputKeyboardCompactIcon
                            : _kChatInputEmojiPanelIcon,
                        size: _kChatInputToolbarGlyphSize,
                        color: _foregroundPrimary(
                          context,
                        ).withValues(alpha: 0.82),
                      ),
                    ),
                ],
              ),
            ),
            if (_showEmojiPanel)
              UnifiedEmojiPicker(
                showCloseButton: false,
                onEmojiSelected: (char) {
                  final next = '${_controller.text}$char';
                  _controller.value = TextEditingValue(
                    text: next,
                    selection: TextSelection.collapsed(offset: next.length),
                  );
                },
              ),
          ],
        ),
      ),
    );
  }
}
