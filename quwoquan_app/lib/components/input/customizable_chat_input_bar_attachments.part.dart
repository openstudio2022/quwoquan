part of 'customizable_chat_input_bar.dart';

extension _CustomizableChatInputBarAttachments
    on _CustomizableChatInputBarState {
  bool _acceptAttachmentType(ChatInputAttachmentType type) {
    if (_attachments.isEmpty) return true;
    final existingType = _attachments.first.type;
    if (existingType == type) return true;
    _emitToast(ChatText.chatAttachmentTypeConflict);
    return false;
  }

  int get _remainingAttachmentCount =>
      math.max(0, widget.maxAttachmentCount - _attachments.length);

  Future<void> _addAttachments(List<ChatInputAttachment> attachments) async {
    if (widget.disabled) return;
    if (attachments.isEmpty) return;
    if (_attachments.length >= widget.maxAttachmentCount) {
      _emitToast(
        ChatText.chatAttachmentMaxCount.replaceFirst(
          '%s',
          widget.maxAttachmentCount.toString(),
        ),
      );
      return;
    }
    final type = attachments.first.type;
    if (!_acceptAttachmentType(type)) return;
    final canAdd = _remainingAttachmentCount;
    final toAdd = attachments.take(canAdd).toList(growable: false);
    if (toAdd.isEmpty) return;
    _updateState(() {
      _attachments.addAll(toAdd);
    });
    widget.onAttachmentChanged?.call(
      List<ChatInputAttachment>.from(_attachments),
    );
    if (attachments.length > canAdd) {
      _emitToast(
        ChatText.chatAttachmentMaxCount.replaceFirst(
          '%s',
          widget.maxAttachmentCount.toString(),
        ),
      );
    }
  }

  Future<void> _pickImages() async {
    if (widget.disabled) return;
    if (widget.onPickImages == null) return;
    if (!_acceptAttachmentType(ChatInputAttachmentType.image)) return;
    final list = await widget.onPickImages!(_remainingAttachmentCount);
    if (!mounted) return;
    await _addAttachments(list);
  }

  Future<void> _pickFiles() async {
    if (widget.disabled) return;
    if (widget.onPickFiles == null) return;
    if (!_acceptAttachmentType(ChatInputAttachmentType.file)) return;
    final list = await widget.onPickFiles!(_remainingAttachmentCount);
    if (!mounted) return;
    await _addAttachments(list);
  }

  Future<void> _capturePhoto() async {
    if (widget.disabled) return;
    if (widget.onCapturePhoto == null) return;
    if (!_acceptAttachmentType(ChatInputAttachmentType.image)) return;
    final item = await widget.onCapturePhoto!();
    if (!mounted || item == null) return;
    await _addAttachments(<ChatInputAttachment>[item]);
  }

  void _removeAttachment(String id) {
    if (widget.disabled) return;
    _updateState(() {
      _attachments.removeWhere((item) => item.id == id);
    });
    widget.onAttachmentChanged?.call(
      List<ChatInputAttachment>.from(_attachments),
    );
  }

  void _toggleAddPanel() {
    if (widget.disabled) return;
    if (!widget.showAddPanel) return;
    _updateState(() {
      _panelMode = _showAddPanel
          ? ChatInputPanelMode.none
          : ChatInputPanelMode.more;
      if (_panelMode == ChatInputPanelMode.more) {
        _focusNode.unfocus();
      }
    });
  }

  Widget _buildAttachmentPreview() {
    if (_attachments.isEmpty) return const SizedBox.shrink();
    final secondaryText = _foregroundSecondary(context);
    return SizedBox(
      height: AppSpacing.buttonSize + AppSpacing.sm,
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        physics: const BouncingScrollPhysics(),
        child: Row(
          children: _attachments
              .map((item) {
                final bg = item.type == ChatInputAttachmentType.image
                    ? _sheetBackground(context)
                    : _sheetBackground(context).withValues(alpha: 0.82);
                return Container(
                  width: AppSpacing.twoHundredTwenty,
                  margin: EdgeInsets.only(right: AppSpacing.sm),
                  padding: EdgeInsets.all(AppSpacing.sm),
                  decoration: BoxDecoration(
                    color: bg,
                    borderRadius: BorderRadius.circular(
                      AppSpacing.borderRadius,
                    ),
                  ),
                  child: Row(
                    children: [
                      _buildAttachmentLeading(item),
                      SizedBox(width: AppSpacing.sm),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Text(
                              item.name,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                fontSize: AppTypography.base,
                                color: _foregroundPrimary(
                                  context,
                                ).withValues(alpha: 0.88),
                              ),
                            ),
                            if ((item.subtitle ?? '').trim().isNotEmpty)
                              Text(
                                item.subtitle!,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  fontSize: AppTypography.sm,
                                  color: secondaryText,
                                ),
                              ),
                          ],
                        ),
                      ),
                      SizedBox(width: AppSpacing.xs),
                      GestureDetector(
                        onTap: widget.disabled
                            ? null
                            : () => _removeAttachment(item.id),
                        child: Container(
                          width: AppSpacing.iconButtonMinSizeSm,
                          height: AppSpacing.iconButtonMinSizeSm,
                          alignment: Alignment.center,
                          child: Icon(
                            Icons.close,
                            size: AppSpacing.iconSmall,
                            color: secondaryText,
                          ),
                        ),
                      ),
                    ],
                  ),
                );
              })
              .toList(growable: false),
        ),
      ),
    );
  }

  Widget _buildAttachmentLeading(ChatInputAttachment item) {
    final radius = BorderRadius.circular(AppSpacing.smallBorderRadius);
    if (item.thumbnailProvider != null) {
      return ClipRRect(
        borderRadius: radius,
        child: Image(
          image: item.thumbnailProvider!,
          width: AppSpacing.buttonSize,
          height: AppSpacing.buttonSize,
          fit: BoxFit.cover,
        ),
      );
    }
    return Container(
      width: AppSpacing.buttonSize,
      height: AppSpacing.buttonSize,
      decoration: BoxDecoration(
        color: _fieldBackground(context),
        borderRadius: radius,
      ),
      alignment: Alignment.center,
      child: Icon(
        item.type == ChatInputAttachmentType.image
            ? Icons.image_outlined
            : Icons.insert_drive_file_outlined,
        size: AppSpacing.iconMedium,
        color: _foregroundSecondary(context),
      ),
    );
  }

  Widget _buildAddPanel() {
    if (!_showAddPanel) return const SizedBox.shrink();
    final disableImage =
        _attachments.isNotEmpty &&
        _attachments.first.type == ChatInputAttachmentType.file;
    final disableFile =
        _attachments.isNotEmpty &&
        _attachments.first.type == ChatInputAttachmentType.image;
    final panelItems = <_PanelActionItem>[
      _PanelActionItem(
        icon: Icons.photo_library_outlined,
        text: ChatText.chatMorePhoto,
        disabled: widget.disabled || disableImage,
        onTap: _pickImages,
      ),
      _PanelActionItem(
        icon: Icons.camera_alt_outlined,
        text: ChatText.chatMoreShoot,
        disabled: widget.disabled || disableImage,
        onTap: _capturePhoto,
      ),
      _PanelActionItem(
        icon: Icons.insert_drive_file_outlined,
        text: ChatText.chatMoreFile,
        disabled: widget.disabled || disableFile,
        onTap: _pickFiles,
      ),
      ...widget.extraPanelItems.map(
        (item) => _PanelActionItem(
          icon: item.icon,
          text: item.text,
          disabled: widget.disabled || item.disabled,
          onTap: item.onTap,
        ),
      ),
    ];
    return Container(
      margin: EdgeInsets.only(top: AppSpacing.sm),
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.md,
      ),
      decoration: BoxDecoration(
        color: _sheetBackground(context),
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        border: Border.all(
          color: _separatorColor(context).withValues(alpha: 0.35),
        ),
      ),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final columns = panelItems.length < 4 ? panelItems.length : 4;
          final itemWidth =
              (constraints.maxWidth - AppSpacing.sm * (columns - 1)) / columns;
          return Wrap(
            spacing: AppSpacing.sm,
            runSpacing: AppSpacing.md,
            children: panelItems
                .map(
                  (item) => SizedBox(
                    width: itemWidth,
                    child: _buildPanelItem(
                      icon: item.icon,
                      text: item.text,
                      disabled: item.disabled,
                      onTap: item.onTap,
                    ),
                  ),
                )
                .toList(growable: false),
          );
        },
      ),
    );
  }

  Widget _buildPanelItem({
    required IconData icon,
    required String text,
    required bool disabled,
    required Future<void> Function() onTap,
  }) {
    final fg = disabled
        ? _foregroundPrimary(context).withValues(alpha: 0.25)
        : _foregroundPrimary(context).withValues(alpha: 0.78);
    return Semantics(
      button: true,
      enabled: !disabled,
      label: text,
      child: GestureDetector(
        onTap: disabled ? null : onTap,
        child: Container(
          padding: EdgeInsets.symmetric(
            vertical: AppSpacing.md,
            horizontal: AppSpacing.xs,
          ),
          decoration: BoxDecoration(
            color: _fieldBackground(
              context,
            ).withValues(alpha: disabled ? 0.55 : 1),
            borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: AppSpacing.buttonSize + AppSpacing.md,
                height: AppSpacing.buttonSize + AppSpacing.md,
                decoration: BoxDecoration(
                  color: _sheetBackground(context),
                  borderRadius: BorderRadius.circular(
                    AppSpacing.largeBorderRadius,
                  ),
                ),
                alignment: Alignment.center,
                child: Icon(icon, size: AppSpacing.iconLarge, color: fg),
              ),
              SizedBox(height: AppSpacing.sm),
              Text(
                text,
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: AppTypography.sm, color: fg),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _PanelActionItem {
  const _PanelActionItem({
    required this.icon,
    required this.text,
    required this.disabled,
    required this.onTap,
  });

  final IconData icon;
  final String text;
  final bool disabled;
  final Future<void> Function() onTap;
}
