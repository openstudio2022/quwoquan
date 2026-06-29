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
        final fixedTileCount = widget.entryMode == MediaPickerEntryMode.video
            ? 2
            : 1;
        final total = list.length + fixedTileCount;
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
                  if (index == 0) {
                    return _buildCameraTile(isDark);
                  }
                  if (widget.entryMode == MediaPickerEntryMode.video &&
                      index == 1) {
                    return _buildOneTapMovieTile(isDark);
                  }
                  final entity = list[index - fixedTileCount];
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
              if (list.isEmpty)
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
                switch (widget.entryMode) {
                  MediaPickerEntryMode.video => UITextConstants.videoNoVideo,
                  MediaPickerEntryMode.mixed =>
                    UITextConstants.mediaPickerMixedAlbumEmpty,
                  MediaPickerEntryMode.image =>
                    UITextConstants.mediaPickerAlbumEmpty,
                },
                style: TextStyle(
                  color: primary,
                  fontSize: AppTypography.lg,
                  fontWeight: FontWeight.w700,
                ),
              ),
              SizedBox(height: AppSpacing.intraGroupXs),
              Text(
                switch (widget.entryMode) {
                  MediaPickerEntryMode.video =>
                    UITextConstants.mediaPickerVideoCameraEntry,
                  MediaPickerEntryMode.mixed =>
                    UITextConstants.mediaPickerMixedCameraEntry,
                  MediaPickerEntryMode.image =>
                    UITextConstants.mediaPickerCameraEntry,
                },
                style: TextStyle(color: secondary, fontSize: AppTypography.sm),
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
