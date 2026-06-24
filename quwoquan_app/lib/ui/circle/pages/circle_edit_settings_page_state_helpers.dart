part of 'circle_edit_settings_page.dart';

extension _CircleEditSettingsPageStateHelpers on _CircleEditSettingsPageState {
  Widget _buildHeroCard(Color cardBg, Color fg, Color fgSecondary) {
    final coverUrl = _resolvedCoverSource;
    final avatarUrl = _resolvedAvatarSource;
    return Container(
      decoration: BoxDecoration(
        color: cardBg,
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        boxShadow: [
          BoxShadow(
            color: AppColors.black.withValues(alpha: 0.08),
            blurRadius: AppSpacing.lg,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        child: Stack(
          children: [
            SizedBox(
              height:
                  AppSpacing.oneHundred +
                  AppSpacing.avatarCircleXl +
                  AppSpacing.md,
              width: double.infinity,
              child: coverUrl.isNotEmpty
                  ? AppMediaImage(
                      imageSource: coverUrl,
                      fit: BoxFit.cover,
                      placeholder: ColoredBox(color: cardBg),
                      errorWidget: ColoredBox(color: cardBg),
                    )
                  : ColoredBox(
                      color: AppColors.primaryColor.withValues(alpha: 0.1),
                    ),
            ),
            Positioned.fill(
              child: DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [
                      AppColors.black.withValues(alpha: 0.12),
                      AppColors.black.withValues(alpha: 0.04),
                      AppColors.black.withValues(alpha: 0.42),
                    ],
                  ),
                ),
              ),
            ),
            Positioned(
              left: AppSpacing.containerMd,
              right: AppSpacing.containerMd,
              bottom: AppSpacing.containerMd,
              child: Row(
                children: [
                  Container(
                    width: AppSpacing.avatarCircleLg,
                    height: AppSpacing.avatarCircleLg,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: AppColors.white.withValues(alpha: 0.22),
                      border: Border.all(
                        color: AppColors.white,
                        width: AppSpacing.two,
                      ),
                    ),
                    child: avatarUrl.isNotEmpty
                        ? ClipOval(
                            child: AppMediaImage(
                              imageSource: avatarUrl,
                              fit: BoxFit.cover,
                              errorWidget: const ColoredBox(
                                color: AppColors.transparent,
                                child: Center(
                                  child: Icon(
                                    CupertinoIcons.person_3_fill,
                                    color: AppColors.white,
                                  ),
                                ),
                              ),
                            ),
                          )
                        : const Icon(
                            CupertinoIcons.person_3_fill,
                            color: AppColors.white,
                          ),
                  ),
                  SizedBox(width: AppSpacing.sm),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          _nameController.text.trim().isEmpty
                              ? (_isCreateMode
                                    ? UITextConstants.createCircle
                                    : _seedCircle.name)
                              : _nameController.text.trim(),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            color: AppColors.white,
                            fontSize: AppTypography.xl,
                            fontWeight: AppTypography.bold,
                          ),
                        ),
                        SizedBox(height: AppSpacing.intraGroupXs),
                        Text(
                          _isCreateMode
                              ? (_activeTab == CircleEditSettingsTab.info
                                    ? UITextConstants.createCircle
                                    : UITextConstants.circleEditSettings)
                              : (_activeTab == CircleEditSettingsTab.info
                                    ? UITextConstants.editCircle
                                    : UITextConstants.manageCenter),
                          style: TextStyle(
                            color: AppColors.white.withValues(alpha: 0.86),
                            fontSize: AppTypography.sm,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildCoverPickerTile({
    required Color fill,
    required Color fg,
    required Color fgSecondary,
    required Color border,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildSegmentTitle(UITextConstants.circleCoverLabel, fgSecondary),
        SizedBox(height: AppSpacing.sm),
        Container(
          decoration: BoxDecoration(
            color: fill,
            borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
            border: Border.all(color: border.withValues(alpha: 0.2)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              ClipRRect(
                borderRadius: BorderRadius.vertical(
                  top: Radius.circular(AppSpacing.largeBorderRadius),
                ),
                child: AspectRatio(
                  aspectRatio: 16 / 9,
                  child: _hasCoverSource
                      ? AppMediaImage(
                          imageSource: _resolvedCoverSource,
                          fit: BoxFit.cover,
                          placeholder: ColoredBox(color: fill),
                          errorWidget: ColoredBox(color: fill),
                        )
                      : DecoratedBox(
                          decoration: BoxDecoration(
                            gradient: LinearGradient(
                              begin: Alignment.topLeft,
                              end: Alignment.bottomRight,
                              colors: [
                                AppColors.primaryColor.withValues(alpha: 0.18),
                                fill,
                              ],
                            ),
                          ),
                          child: Center(
                            child: Icon(
                              CupertinoIcons.photo_on_rectangle,
                              color: fgSecondary,
                              size: AppSpacing.iconLarge,
                            ),
                          ),
                        ),
                ),
              ),
              Padding(
                padding: EdgeInsets.all(AppSpacing.containerSm),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        UITextConstants.circleCoverHint,
                        style: TextStyle(
                          fontSize: AppTypography.sm,
                          color: fgSecondary,
                        ),
                      ),
                    ),
                    SizedBox(width: AppSpacing.containerSm),
                    CupertinoButton(
                      padding: EdgeInsets.symmetric(
                        horizontal: AppSpacing.containerSm,
                        vertical: AppSpacing.intraGroupSm,
                      ),
                      minimumSize: Size.zero,
                      color: AppColors.primaryColor.withValues(alpha: 0.12),
                      borderRadius: BorderRadius.circular(
                        AppSpacing.circularBorderRadius,
                      ),
                      onPressed: () =>
                          _showMediaActionSheet(_CircleMediaSlot.cover),
                      child: Text(
                        _hasCoverSource
                            ? UITextConstants.videoChangeCover
                            : UITextConstants.addCover,
                        style: TextStyle(
                          fontSize: AppTypography.sm,
                          fontWeight: AppTypography.semiBold,
                          color: AppColors.primaryColor,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildAvatarPickerTile({
    required Color fill,
    required Color fg,
    required Color fgSecondary,
    required Color border,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _buildSegmentTitle(UITextConstants.circleAvatarLabel, fgSecondary),
        SizedBox(height: AppSpacing.sm),
        Container(
          padding: EdgeInsets.all(AppSpacing.containerSm),
          decoration: BoxDecoration(
            color: fill,
            borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
            border: Border.all(color: border.withValues(alpha: 0.2)),
          ),
          child: Row(
            children: [
              Container(
                width: AppSpacing.avatarCircleLg,
                height: AppSpacing.avatarCircleLg,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: fgSecondary.withValues(alpha: 0.14),
                  border: Border.all(
                    color: AppColors.white,
                    width: AppSpacing.two,
                  ),
                ),
                child: ClipOval(
                  child: _hasAvatarSource
                      ? AppMediaImage(
                          imageSource: _resolvedAvatarSource,
                          fit: BoxFit.cover,
                          placeholder: ColoredBox(
                            color: fgSecondary.withValues(alpha: 0.12),
                          ),
                          errorWidget: ColoredBox(
                            color: fgSecondary.withValues(alpha: 0.12),
                            child: Icon(
                              CupertinoIcons.person_3_fill,
                              color: fgSecondary,
                            ),
                          ),
                        )
                      : Icon(CupertinoIcons.person_3_fill, color: fgSecondary),
                ),
              ),
              SizedBox(width: AppSpacing.containerSm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      UITextConstants.circleAvatarTitle,
                      style: TextStyle(
                        fontSize: AppTypography.base,
                        fontWeight: AppTypography.semiBold,
                        color: fg,
                      ),
                    ),
                    SizedBox(height: AppSpacing.intraGroupXs),
                    Text(
                      UITextConstants.circleAvatarHint,
                      style: TextStyle(
                        fontSize: AppTypography.sm,
                        color: fgSecondary,
                      ),
                    ),
                  ],
                ),
              ),
              SizedBox(width: AppSpacing.containerSm),
              CupertinoButton(
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.containerSm,
                  vertical: AppSpacing.intraGroupSm,
                ),
                minimumSize: Size.zero,
                color: AppColors.primaryColor.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(
                  AppSpacing.circularBorderRadius,
                ),
                onPressed: () => _showMediaActionSheet(_CircleMediaSlot.avatar),
                child: Text(
                  _hasAvatarSource
                      ? UITextConstants.circleChangeAvatar
                      : UITextConstants.circleAddAvatar,
                  style: TextStyle(
                    fontSize: AppTypography.sm,
                    fontWeight: AppTypography.semiBold,
                    color: AppColors.primaryColor,
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
