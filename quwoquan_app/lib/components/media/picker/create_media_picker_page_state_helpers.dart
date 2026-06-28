part of 'create_media_picker_page.dart';

extension _CreateMediaPickerPageStateHelpers on _CreateMediaPickerPageState {
  Widget _buildTopBar(Color fg, Color sub) {
    final selectedAlbum = _selectedAlbum;
    final albumName = selectedAlbum == null
        ? UITextConstants.mediaPickerAlbumAll
        : _albumDisplayName(selectedAlbum);
    final title = switch (widget.entryMode) {
      MediaPickerEntryMode.image => UITextConstants.mediaPickerPhotoTitle,
      MediaPickerEntryMode.video => UITextConstants.mediaPickerVideoTitle,
      MediaPickerEntryMode.mixed => albumName,
    };
    return SizedBox(
      key: _topBarKey,
      height: AppSpacing.toolbarHeight,
      child: Row(
        children: [
          AppNavigationBarIconButton(
            icon: CupertinoIcons.xmark,
            onPressed: () => Navigator.of(context).pop(),
          ),
          Expanded(
            child: Center(
              child: GestureDetector(
                onTap: _selectAlbum,
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      title,
                      style: TextStyle(
                        color: fg,
                        fontSize: AppTypography.lg,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    Icon(
                      CupertinoIcons.chevron_down,
                      color: sub,
                      size: AppSpacing.iconMedium,
                    ),
                  ],
                ),
              ),
            ),
          ),
          SizedBox(width: AppSpacing.iconButtonMinSizeSm),
        ],
      ),
    );
  }

  Widget _buildGrid(List<AssetEntity> list, bool isDark) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final crossCount = _gridCrossAxisCount(constraints.maxWidth);
        final includesCameraTile =
            widget.entryMode != MediaPickerEntryMode.video;
        final total = list.length + (includesCameraTile ? 1 : 0);
        if (total == 0) {
          return _buildGridEmptyState(isDark);
        }
        return ColoredBox(
          color: AppColors.black,
          child: Stack(
            children: [
              GridView.builder(
                controller: _scrollController,
                padding: EdgeInsets.all(AppSpacing.intraGroupXs),
                itemCount: total,
                gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: crossCount,
                  mainAxisSpacing: AppSpacing.intraGroupXs,
                  crossAxisSpacing: AppSpacing.intraGroupXs,
                ),
                itemBuilder: (context, index) {
                  if (includesCameraTile && index == 0) {
                    return _buildCameraTile(isDark);
                  }
                  final entity = list[index - (includesCameraTile ? 1 : 0)];
                  return GestureDetector(
                    key: ValueKey<String>('media-picker-asset-${entity.id}'),
                    onTap: () => _toggleAsset(entity),
                    child: Stack(
                      fit: StackFit.expand,
                      children: [
                        Positioned.fill(
                          child: _buildAssetThumb(entity, isDark),
                        ),
                        if (entity.type == AssetType.video)
                          Positioned(
                            left: AppSpacing.intraGroupSm,
                            bottom: AppSpacing.intraGroupSm,
                            child: Container(
                              padding: EdgeInsets.symmetric(
                                horizontal: AppSpacing.intraGroupSm,
                                vertical: AppSpacing.intraGroupXs / 2,
                              ),
                              decoration: BoxDecoration(
                                color: AppColors.black.withValues(alpha: 0.54),
                                borderRadius: BorderRadius.circular(
                                  AppSpacing.smallBorderRadius,
                                ),
                              ),
                              child: Text(
                                _formatVideoDuration(entity.duration),
                                style: TextStyle(
                                  color: AppColors.white,
                                  fontSize: AppTypography.sm,
                                ),
                              ),
                            ),
                          ),
                        Positioned(
                          top: AppSpacing.intraGroupSm,
                          right: AppSpacing.intraGroupSm,
                          child: _buildSelectBadge(entity.id),
                        ),
                      ],
                    ),
                  );
                },
              ),
              if (list.isEmpty && includesCameraTile)
                Positioned.fill(
                  top: constraints.maxWidth / crossCount,
                  child: _buildGridEmptyState(isDark),
                ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildGridEmptyState(bool isDark) {
    final primary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final secondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return ColoredBox(
      color: AppColors.black,
      child: Center(
        child: Padding(
          padding: EdgeInsets.all(AppSpacing.containerLg),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                CupertinoIcons.photo_on_rectangle,
                color: secondary,
                size: AppSpacing.iconLarge + AppSpacing.iconMedium,
              ),
              SizedBox(height: AppSpacing.interGroupSm),
              Text(
                widget.entryMode == MediaPickerEntryMode.mixed
                    ? UITextConstants.mediaPickerMixedAlbumEmpty
                    : UITextConstants.mediaPickerAlbumEmpty,
                style: TextStyle(
                  color: primary,
                  fontSize: AppTypography.lg,
                  fontWeight: FontWeight.w700,
                ),
              ),
              SizedBox(height: AppSpacing.intraGroupXs),
              Text(
                widget.entryMode == MediaPickerEntryMode.mixed
                    ? UITextConstants.mediaPickerMixedCameraEntry
                    : UITextConstants.mediaPickerCameraEntry,
                style: TextStyle(color: secondary, fontSize: AppTypography.sm),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildVideoShootHero(bool isDark) {
    final background = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundSecondary,
    );
    final foreground = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final secondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return Padding(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        AppSpacing.intraGroupSm,
        AppSpacing.containerMd,
        AppSpacing.interGroupSm,
      ),
      child: GestureDetector(
        key: const ValueKey<String>('media-picker-video-camera-hero'),
        onTap: _openCamera,
        child: Container(
          height: AppSpacing.buttonHeight * 3,
          decoration: BoxDecoration(
            color: background,
            borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
            border: Border.all(
              color: AppColors.primaryColor.withValues(alpha: 0.28),
            ),
          ),
          padding: EdgeInsets.all(AppSpacing.containerMd),
          child: Row(
            children: [
              Container(
                width: AppSpacing.buttonHeight + AppSpacing.buttonHeightSm,
                height: AppSpacing.buttonHeight + AppSpacing.buttonHeightSm,
                decoration: BoxDecoration(
                  color: AppColors.primaryColor.withValues(alpha: 0.18),
                  shape: BoxShape.circle,
                ),
                child: Icon(
                  CupertinoIcons.videocam_fill,
                  color: AppColors.primaryColor,
                  size: AppSpacing.iconLarge,
                ),
              ),
              SizedBox(width: AppSpacing.containerMd),
              Expanded(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      UITextConstants.mediaPickerVideoCameraEntry,
                      style: TextStyle(
                        color: foreground,
                        fontSize: AppTypography.lg,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                    SizedBox(height: AppSpacing.intraGroupXs),
                    Text(
                      UITextConstants.cameraVideoMode,
                      style: TextStyle(
                        color: secondary,
                        fontSize: AppTypography.sm,
                      ),
                    ),
                  ],
                ),
              ),
              Icon(
                CupertinoIcons.chevron_forward,
                color: secondary,
                size: AppSpacing.iconSmall,
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _selectedItemThumb({
    required CreateMediaItem item,
    required bool isDark,
    VoidCallback? onDelete,
    bool showDelete = true,
  }) {
    final size = AppSpacing.bottomNavHeight;
    final file = File(item.path);
    return Stack(
      clipBehavior: Clip.none,
      children: [
        Container(
          key: ValueKey<String>('media-picker-selected-thumb-${item.id}'),
          width: size,
          height: size,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
            border: Border.all(
              color: AppColorsFunctional.getColor(
                isDark,
                ColorType.borderSecondary,
              ),
            ),
          ),
          clipBehavior: Clip.antiAlias,
          child: item.isVideo
              ? Container(
                  color: AppColors.black.withValues(alpha: 0.87),
                  child: Icon(
                    Icons.videocam_outlined,
                    color: AppColors.white,
                    size: AppSpacing.iconMedium,
                  ),
                )
              : Image.file(
                  file,
                  fit: BoxFit.cover,
                  errorBuilder: (context, error, stackTrace) => Container(
                    color: AppColorsFunctional.getColor(
                      isDark,
                      ColorType.backgroundSecondary,
                    ),
                  ),
                ),
        ),
        if (showDelete && onDelete != null)
          Positioned(
            right: -AppSpacing.intraGroupXs,
            top: -AppSpacing.intraGroupXs,
            child: GestureDetector(
              key: ValueKey<String>('media-picker-selected-delete-${item.id}'),
              onTap: onDelete,
              child: Container(
                width: AppSpacing.iconSmall + AppSpacing.intraGroupSm,
                height: AppSpacing.iconSmall + AppSpacing.intraGroupSm,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: AppColors.black.withValues(alpha: 0.87),
                ),
                child: Icon(
                  Icons.close,
                  color: AppColors.white,
                  size: AppSpacing.iconSmall,
                ),
              ),
            ),
          ),
      ],
    );
  }
}
