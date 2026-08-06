part of 'customizable_chat_input_bar.dart';

extension _CustomizableChatInputBarLayout on _CustomizableChatInputBarState {
  ChatInputVisualState _visualState() {
    return ChatInputVisualState(
      hasText: _hasText,
      hasAttachments: _hasAttachments,
      isVoiceMode: _isVoiceMode,
      isRecording: _isRecording,
      panelMode: _panelMode,
    );
  }

  ChatInputDefaultActions _defaultActions() {
    return ChatInputDefaultActions(
      toggleAddPanel: widget.disabled ? () {} : _toggleAddPanel,
      toggleVoiceMode: widget.disabled ? () {} : _toggleVoiceMode,
      toggleEmojiPanel: widget.disabled ? () {} : _toggleEmojiPanel,
      send: () {
        if (!widget.disabled) {
          unawaited(_send());
        }
      },
      openExpandedEditor: () {
        if (!widget.disabled) {
          unawaited(_openExpandedEditor());
        }
      },
    );
  }

  Widget _buildComposerRow() {
    final state = _visualState();
    final actions = _defaultActions();
    return LayoutBuilder(
      builder: (context, constraints) {
        final compact = constraints.maxWidth < AppSpacing.compactBreakpoint;
        final right =
            widget.rightBuilder?.call(context, state, actions) ??
            _buildTrailingButtons(context, compact: compact);
        final left =
            widget.leftBuilder?.call(context, state, actions) ??
            (widget.enableVoiceInput
                ? _buildToolbarPlainIconButton(
                    context: context,
                    key: TestKeys.chatInputVoiceToggleButton,
                    icon: _isVoiceMode
                        ? _kChatInputKeyboardCompactIcon
                        : CupertinoIcons.mic,
                    onTap: widget.disabled ? null : _toggleVoiceMode,
                    semanticLabel: _isVoiceMode
                        ? ChatText.keyboard
                        : ChatText.voiceInput,
                  )
                : const SizedBox.shrink());
        return Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            left,
            if (left is! SizedBox) SizedBox(width: AppSpacing.intraGroupXs),
            Expanded(
              child: _isVoiceMode
                  ? _buildVoicePanel()
                  : _buildTextComposerCenter(),
            ),
            if (right.isNotEmpty) SizedBox(width: AppSpacing.intraGroupXs),
            Row(mainAxisSize: MainAxisSize.min, children: right),
          ],
        );
      },
    );
  }

  Widget _buildInputBar() {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        _buildAttachmentPreview(),
        if (_attachments.isNotEmpty) SizedBox(height: AppSpacing.sm),
        _buildVoiceRecordHud(),
        _buildComposerRow(),
        _buildEmojiPanel(),
        _buildAddPanel(),
      ],
    );
  }
}
