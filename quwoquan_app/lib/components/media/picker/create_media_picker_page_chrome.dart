part of 'create_media_picker_page.dart';

extension _CreateMediaPickerPageChrome on _CreateMediaPickerPageState {
  Widget _buildCameraTile(bool isDark) {
    return GestureDetector(
      key: const ValueKey<String>('media-picker-camera-tile'),
      onTap: _openCamera,
      child: Container(
        decoration: BoxDecoration(
          color: AppColorsFunctional.getColor(
            true,
            ColorType.surfaceElevated,
          ).withValues(alpha: 0.88),
          borderRadius: BorderRadius.circular(AppSpacing.smallBorderRadius),
          border: Border.all(
            color: AppColors.white.withValues(alpha: 0.10),
            width: AppSpacing.hairline,
          ),
        ),
        alignment: Alignment.center,
        child: FittedBox(
          fit: BoxFit.scaleDown,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(
                widget.entryMode == MediaPickerEntryMode.video
                    ? CupertinoIcons.videocam_fill
                    : CupertinoIcons.camera,
                size: AppSpacing.iconLarge + AppSpacing.intraGroupSm,
                color: AppColors.white.withValues(alpha: 0.92),
              ),
              SizedBox(height: AppSpacing.intraGroupSm),
              Text(
                switch (widget.entryMode) {
                  MediaPickerEntryMode.video =>
                    UITextConstants.mediaPickerVideoCameraEntry,
                  MediaPickerEntryMode.mixed =>
                    UITextConstants.mediaPickerMixedCameraEntry,
                  MediaPickerEntryMode.image =>
                    UITextConstants.mediaPickerCameraEntry,
                },
                style: TextStyle(
                  color: AppColorsFunctional.getColor(
                    isDark,
                    ColorType.foregroundPrimary,
                  ),
                  fontSize: AppTypography.base,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildSelectBadge(String id) {
    final index = _selectedItems.indexWhere((item) => item.id == id);
    final selected = index >= 0;
    return AnimatedContainer(
      duration: const Duration(milliseconds: 120),
      width: AppSpacing.buttonHeightXs,
      height: AppSpacing.buttonHeightXs,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: selected
            ? AppColors.primaryColor
            : AppColors.black.withValues(alpha: 0.26),
        border: Border.all(
          color: AppColors.white,
          width: AppSpacing.hairline * 2,
        ),
      ),
      child: selected
          ? Text(
              '${index + 1}',
              style: TextStyle(
                color: AppColors.white,
                fontWeight: FontWeight.w700,
                fontSize: AppTypography.iosCaption1,
                height: AppTypography.lineHeightTight,
              ),
            )
          : const SizedBox.shrink(),
    );
  }

  Widget _buildSelectedStrip(Color sub, bool isDark) {
    final background = AppColorsFunctional.getColor(
      true,
      ColorType.backgroundPrimary,
    );
    final thumbSize = AppSpacing.bottomNavHeight;
    return Container(
      height: AppSpacing.bottomNavHeight + AppSpacing.containerMd,
      color: background,
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.containerXs,
      ),
      // 统一拖拽重排：长按起拖 + 兄弟实时让位 + 松手提交，复用 MediaReorderableView。
      // 替换旧的 LongPressDraggable + DragTarget「跳变」方案，与其余两处共用同一交互真相源。
      child: MediaReorderableView(
        layout: MediaReorderableLayout.strip,
        itemCount: _selectedItems.length,
        spacing: AppSpacing.intraGroupSm,
        itemSize: Size(thumbSize, thumbSize),
        onReorder: (oldIndex, newIndex) {
          // 组件用 Flutter 标准插入位，_reorderSelected 用最终下标，需转换。
          final to = oldIndex < newIndex ? newIndex - 1 : newIndex;
          _reorderSelected(oldIndex, to);
        },
        itemBuilder: (context, index, isDragging) {
          final item = _selectedItems[index];
          return GestureDetector(
            onTap: item.isImage
                ? () => unawaited(_editSelectedImageAt(index))
                : null,
            child: _selectedItemThumb(
              item: item,
              isDark: isDark,
              onDelete: () => _removeSelectedAt(index),
            ),
          );
        },
      ),
    );
  }

  Widget _buildBottomActions(bool isDark) {
    final selectionCount = _selectedItems.length;
    final actions = mediaPickerBottomActionsForEntryMode(
      mode: widget.entryMode,
      selectionCount: selectionCount,
      flowIntent: widget.flowIntent,
    );
    final background = AppColorsFunctional.getColor(
      true,
      ColorType.backgroundPrimary,
    );
    final border = AppColorsFunctional.getColor(
      isDark,
      ColorType.borderSecondary,
    );
    final bottomInset = MediaQuery.paddingOf(context).bottom;
    final bottomPadding =
        (bottomInset > 0 ? bottomInset : AppSpacing.containerMd) +
        AppSpacing.intraGroupSm;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: background,
        border: Border(
          top: BorderSide(color: border, width: AppSpacing.hairline),
        ),
      ),
      child: Padding(
        padding: EdgeInsets.fromLTRB(
          AppSpacing.containerMd,
          AppSpacing.intraGroupSm,
          AppSpacing.containerMd,
          bottomPadding,
        ),
        child: Row(
          children: [
            for (var i = 0; i < actions.length; i++) ...[
              if (i > 0) SizedBox(width: AppSpacing.interGroupSm),
              Expanded(child: _buildBottomActionButton(actions[i])),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildBottomActionButton(CreateMediaPickerBottomActionSpec spec) {
    final onPressed = spec.enabled
        ? () {
            switch (spec.action) {
              case CreateMediaPickerBottomAction.editImage:
                unawaited(_openOneTapMovie());
                return;
              case CreateMediaPickerBottomAction.completeImage:
                unawaited(_openImageEditorForNextStep());
                return;
              case CreateMediaPickerBottomAction.nextStep:
                _finishSelection();
                return;
            }
          }
        : null;
    final variant = spec.isPrimary
        ? MediaCreationBottomButtonVariant.partialPrimary
        : MediaCreationBottomButtonVariant.secondaryNeutral;
    return MediaCreationBottomButton(
      key: ValueKey<String>('media-picker-bottom-action-${spec.action.name}'),
      label: spec.label,
      variant: variant,
      height: AppSpacing.minInteractiveSize,
      onPressed: onPressed,
    );
  }

  String _formatVideoDuration(int seconds) {
    final s = seconds % 60;
    final m = (seconds ~/ 60) % 60;
    final h = seconds ~/ 3600;
    if (h > 0) {
      return '${h.toString().padLeft(2, '0')}:${m.toString().padLeft(2, '0')}:${s.toString().padLeft(2, '0')}';
    }
    return '${m.toString().padLeft(2, '0')}:${s.toString().padLeft(2, '0')}';
  }

  Future<Uint8List?> _cachedThumbnailFuture(AssetEntity entity) {
    return _thumbnailFutures.putIfAbsent(
      entity.id,
      () => widget.mediaPickerService.loadThumbnail(entity),
    );
  }

  Widget _buildAssetThumb(AssetEntity entity, bool isDark) {
    return FutureBuilder<Uint8List?>(
      future: _cachedThumbnailFuture(entity),
      builder: (context, snapshot) {
        final bytes = snapshot.data;
        if (bytes != null && bytes.isNotEmpty) {
          return Image.memory(bytes, fit: BoxFit.cover);
        }
        return Container(
          color: AppColorsFunctional.getColor(
            isDark,
            ColorType.backgroundSecondary,
          ),
        );
      },
    );
  }
}
