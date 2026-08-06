part of 'create_media_picker_page.dart';

extension _CreateMediaPickerPageStateHelpers on _CreateMediaPickerPageState {
  Widget _buildTopBar(Color fg, Color sub) {
    final selectedAlbum = _selectedAlbum;
    final albumName = selectedAlbum == null
        ? MediaText.mediaPickerAlbumAll
        : _albumDisplayName(selectedAlbum);
    final title = switch (widget.entryMode) {
      MediaPickerEntryMode.image => MediaText.mediaPickerPhotoTitle,
      MediaPickerEntryMode.video => MediaText.mediaPickerVideoTitle,
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
          if (widget.entryMode == MediaPickerEntryMode.image)
            CupertinoButton(
              padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
              minimumSize: Size(
                AppSpacing.iconButtonMinSizeSm,
                AppSpacing.buttonHeightSm,
              ),
              onPressed: _openDrafts,
              child: Text(
                CreationText.drafts,
                style: TextStyle(
                  color: fg,
                  fontSize: AppTypography.base,
                  fontWeight: AppTypography.semiBold,
                ),
              ),
            )
          else
            SizedBox(width: AppSpacing.iconButtonMinSizeSm),
        ],
      ),
    );
  }

  void _openDrafts() {
    try {
      context.push(AppRoutePaths.localDrafts);
    } catch (_) {
      // Widget tests may mount the picker outside the app router.
    }
  }

  Widget _buildGrid(List<MediaPickerAssetRef> list, bool isDark) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final crossCount = _gridCrossAxisCount(constraints.maxWidth);
        const fixedTileCount = 1;
        final total = list.length + fixedTileCount;
        if (total == 0) {
          return _buildGridEmptyState(isDark);
        }
        final gridBackground = AppColorsFunctional.getColor(
          true,
          ColorType.backgroundPrimary,
        );
        return ColoredBox(
          color: gridBackground,
          child: Stack(
            children: [
              GridView.builder(
                controller: _scrollController,
                padding: EdgeInsets.all(AppSpacing.containerXs),
                itemCount: total,
                gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: crossCount,
                  mainAxisSpacing: AppSpacing.containerXs,
                  crossAxisSpacing: AppSpacing.containerXs,
                ),
                itemBuilder: (context, index) {
                  if (index == 0) {
                    return _buildCameraTile(isDark);
                  }
                  final entity = list[index - fixedTileCount];
                  final selected = _selectedItems.any(
                    (item) => item.id == entity.id,
                  );
                  return GestureDetector(
                    key: ValueKey<String>('media-picker-asset-${entity.id}'),
                    onTap: () => _toggleAsset(entity),
                    child: DecoratedBox(
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(
                          AppSpacing.smallBorderRadius,
                        ),
                        border: Border.all(
                          color: selected
                              ? AppColors.primaryColor
                              : AppColors.white.withValues(alpha: 0.08),
                          width: selected
                              ? AppSpacing.hairline * 2
                              : AppSpacing.hairline,
                        ),
                      ),
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(
                          AppSpacing.smallBorderRadius,
                        ),
                        child: Stack(
                          fit: StackFit.expand,
                          children: [
                            Positioned.fill(
                              child: _buildAssetThumb(entity, isDark),
                            ),
                            if (!selected)
                              Positioned.fill(
                                child: DecoratedBox(
                                  decoration: BoxDecoration(
                                    color: AppColors.black.withValues(
                                      alpha: 0.05,
                                    ),
                                  ),
                                ),
                              ),
                            if (entity.type == MediaPickerAssetType.video)
                              Positioned(
                                left: AppSpacing.intraGroupSm,
                                bottom: AppSpacing.intraGroupSm,
                                child: Container(
                                  padding: EdgeInsets.symmetric(
                                    horizontal: AppSpacing.intraGroupSm,
                                    vertical: AppSpacing.intraGroupXs / 2,
                                  ),
                                  decoration: BoxDecoration(
                                    color: AppColors.black.withValues(
                                      alpha: 0.58,
                                    ),
                                    borderRadius: BorderRadius.circular(
                                      AppSpacing.smallBorderRadius,
                                    ),
                                  ),
                                  child: Text(
                                    _formatVideoDuration(
                                      entity.durationMs ~/ 1000,
                                    ),
                                    style: TextStyle(
                                      color: AppColors.white,
                                      fontSize: AppTypography.sm,
                                      fontWeight: AppTypography.medium,
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
                      ),
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
      color: AppColorsFunctional.getColor(true, ColorType.backgroundPrimary),
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
                  MediaPickerEntryMode.video => MediaText.videoNoVideo,
                  MediaPickerEntryMode.mixed =>
                    MediaText.mediaPickerMixedAlbumEmpty,
                  MediaPickerEntryMode.image => MediaText.mediaPickerAlbumEmpty,
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
                    MediaText.mediaPickerVideoCameraEntry,
                  MediaPickerEntryMode.mixed =>
                    MediaText.mediaPickerMixedCameraEntry,
                  MediaPickerEntryMode.image =>
                    MediaText.mediaPickerCameraEntry,
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
              : Image(
                  image: localFileImageProvider(item.path),
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
