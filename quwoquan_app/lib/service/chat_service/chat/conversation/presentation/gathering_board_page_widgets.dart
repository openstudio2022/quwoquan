part of 'gathering_board_page.dart';

TextStyle _boardBodyStyle(bool isDark) => TextStyle(
  color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
  fontSize: AppTypography.iosBody,
  height: AppTypography.bodyLineHeight,
);

TextStyle _boardSecondaryStyle(bool isDark) => TextStyle(
  color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
  fontSize: AppTypography.iosFootnote,
  height: AppTypography.lineHeightCompact,
);

class _GatheringBoardActivityHeader extends StatelessWidget {
  const _GatheringBoardActivityHeader({
    required this.activity,
    required this.access,
    required this.foregroundSecondary,
    required this.isDark,
  });

  final GatheringBoardActivitySlice activity;
  final GatheringBoardChatAccessSummary access;
  final Color foregroundSecondary;
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    final foreground = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final accent = access.isReadOnly
        ? AppColors.warning
        : AppColors.primaryColor;
    return Container(
      key: const ValueKey<String>('gathering-board-activity-header'),
      padding: EdgeInsets.all(AppSpacing.containerMd),
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(isDark, ColorType.surfaceElevated),
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        border: Border.all(
          color: AppColorsFunctional.getColor(
            isDark,
            ColorType.separatorSubtle,
          ),
          width: AppSpacing.hairline,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  activity.title,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    color: foreground,
                    fontSize: AppTypography.iosTitle2,
                    fontWeight: AppTypography.semiBold,
                    height: AppTypography.lineHeightTight,
                  ),
                ),
              ),
              SizedBox(width: AppSpacing.intraGroupSm),
              Container(
                key: access.isReadOnly
                    ? const ValueKey<String>('gathering-board-read-only')
                    : const ValueKey<String>('gathering-board-active'),
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.sm,
                  vertical: AppSpacing.xs,
                ),
                decoration: BoxDecoration(
                  color: accent.withValues(alpha: isDark ? 0.2 : 0.12),
                  borderRadius: BorderRadius.circular(
                    AppSpacing.smallBorderRadius,
                  ),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      access.isReadOnly
                          ? CupertinoIcons.lock
                          : CupertinoIcons.check_mark_circled_solid,
                      color: accent,
                      size: AppSpacing.iconSmall,
                    ),
                    SizedBox(width: AppSpacing.intraGroupXs),
                    Text(
                      access.statusLabel,
                      style: TextStyle(
                        color: accent,
                        fontSize: AppTypography.iosCaption1,
                        fontWeight: AppTypography.medium,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          SizedBox(height: AppSpacing.intraGroupSm),
          _GatheringBoardMetaLine(
            icon: CupertinoIcons.time,
            label: activity.scheduleLabel,
            color: foregroundSecondary,
          ),
          SizedBox(height: AppSpacing.intraGroupXs),
          _GatheringBoardMetaLine(
            icon: CupertinoIcons.location,
            label: activity.placeLabel,
            color: foregroundSecondary,
          ),
        ],
      ),
    );
  }
}

class _GatheringBoardMetaLine extends StatelessWidget {
  const _GatheringBoardMetaLine({
    required this.icon,
    required this.label,
    required this.color,
  });

  final IconData icon;
  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) => Row(
    children: [
      Icon(icon, size: AppSpacing.iconSmall, color: color),
      SizedBox(width: AppSpacing.intraGroupSm),
      Expanded(
        child: Text(
          label,
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            color: color,
            fontSize: AppTypography.iosFootnote,
            height: AppTypography.lineHeightCompact,
          ),
        ),
      ),
    ],
  );
}

class _GatheringBoardSectionCard extends StatelessWidget {
  const _GatheringBoardSectionCard({
    required this.sectionKey,
    required this.title,
    required this.icon,
    required this.isDark,
    required this.children,
    this.onOpen,
  });

  final Key sectionKey;
  final String title;
  final IconData icon;
  final bool isDark;
  final List<Widget> children;
  final VoidCallback? onOpen;

  @override
  Widget build(BuildContext context) {
    final foreground = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    return Container(
      key: sectionKey,
      padding: EdgeInsets.all(AppSpacing.containerMd),
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(isDark, ColorType.surfaceElevated),
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        border: Border.all(
          color: AppColorsFunctional.getColor(
            isDark,
            ColorType.separatorSubtle,
          ),
          width: AppSpacing.hairline,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, color: AppColors.primaryColor),
              SizedBox(width: AppSpacing.intraGroupSm),
              Expanded(
                child: Text(
                  title,
                  style: TextStyle(
                    color: foreground,
                    fontSize: AppTypography.iosTitle3,
                    fontWeight: AppTypography.semiBold,
                  ),
                ),
              ),
              if (onOpen != null)
                CupertinoButton(
                  padding: EdgeInsets.zero,
                  minimumSize: const Size(
                    AppSpacing.minInteractiveSize,
                    AppSpacing.minInteractiveSize,
                  ),
                  onPressed: onOpen,
                  child: const Icon(CupertinoIcons.chevron_forward),
                ),
            ],
          ),
          SizedBox(height: AppSpacing.intraGroupSm),
          ...children,
        ],
      ),
    );
  }
}

class _GatheringBoardCapabilityRow extends StatelessWidget {
  const _GatheringBoardCapabilityRow({
    required this.capability,
    required this.icon,
    required this.isDark,
    this.onOpen,
  });

  final GatheringBoardCapabilitySummary capability;
  final IconData icon;
  final bool isDark;
  final VoidCallback? onOpen;

  @override
  Widget build(BuildContext context) {
    final color = capability.isAvailable
        ? AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary)
        : AppColors.warning;
    final unavailableLabel = capability.unavailableLabel.trim();
    final label = capability.isAvailable
        ? capability.summaryLabel
        : (unavailableLabel.isEmpty
              ? capability.summaryLabel
              : unavailableLabel);
    return CupertinoButton(
      padding: EdgeInsets.symmetric(vertical: AppSpacing.sm),
      minimumSize: const Size(
        AppSpacing.minInteractiveSize,
        AppSpacing.minInteractiveSize,
      ),
      onPressed: onOpen,
      child: Row(
        children: [
          Icon(
            // 能力暂不可用是信息态而非错误警示：统一低打扰视觉，
            // 圆形感叹号仅保留给共享 inline error 原语。
            capability.isAvailable ? icon : CupertinoIcons.info_circle,
            color: color,
            size: AppSpacing.iconMedium,
          ),
          SizedBox(width: AppSpacing.intraGroupSm),
          Expanded(
            child: Text(
              label,
              style: TextStyle(
                color: color,
                fontSize: AppTypography.iosSubheadline,
                height: AppTypography.lineHeightCompact,
              ),
            ),
          ),
          if (onOpen != null)
            Icon(
              CupertinoIcons.chevron_forward,
              color: color,
              size: AppSpacing.iconSmall,
            ),
        ],
      ),
    );
  }
}

class _GatheringBoardPlanItemRow extends StatelessWidget {
  const _GatheringBoardPlanItemRow({required this.item, required this.isDark});

  final GatheringBoardPlanItem item;
  final bool isDark;

  @override
  Widget build(BuildContext context) => Padding(
    padding: EdgeInsets.symmetric(vertical: AppSpacing.sm),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(
          item.completed
              ? CupertinoIcons.check_mark_circled_solid
              : CupertinoIcons.circle,
          size: AppSpacing.iconMedium,
          color: item.completed
              ? AppColors.success
              : AppColorsFunctional.getColor(
                  isDark,
                  ColorType.foregroundSecondary,
                ),
        ),
        SizedBox(width: AppSpacing.intraGroupSm),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(item.title, style: _boardBodyStyle(isDark)),
              if (item.detail.trim().isNotEmpty) ...[
                SizedBox(height: AppSpacing.intraGroupXs),
                Text(item.detail, style: _boardSecondaryStyle(isDark)),
              ],
            ],
          ),
        ),
      ],
    ),
  );
}

class _GatheringBoardAssetsSection extends StatelessWidget {
  const _GatheringBoardAssetsSection({
    required this.assets,
    required this.isDark,
    required this.onOpenAsset,
  });

  final List<GatheringBoardAssetIndexItem> assets;
  final bool isDark;
  final GatheringBoardAssetNavigation? onOpenAsset;

  @override
  Widget build(BuildContext context) {
    final imageCount = assets
        .where((asset) => asset.kind == GatheringBoardAssetKind.image)
        .length;
    final videoCount = assets
        .where((asset) => asset.kind == GatheringBoardAssetKind.video)
        .length;
    final fileCount = assets
        .where((asset) => asset.kind == GatheringBoardAssetKind.file)
        .length;
    return _GatheringBoardSectionCard(
      sectionKey: const ValueKey<String>('gathering-board-assets'),
      title: ChatText.groupCapabilityAlbum,
      icon: CupertinoIcons.photo_on_rectangle,
      isDark: isDark,
      children: [
        Row(
          children: [
            Expanded(
              child: _GatheringBoardAssetCount(
                label: ChatText.chatMorePhoto,
                count: imageCount,
                isDark: isDark,
              ),
            ),
            Expanded(
              child: _GatheringBoardAssetCount(
                label: ChatText.chatMoreVideo,
                count: videoCount,
                isDark: isDark,
              ),
            ),
            Expanded(
              child: _GatheringBoardAssetCount(
                label: ChatText.chatMoreFile,
                count: fileCount,
                isDark: isDark,
              ),
            ),
          ],
        ),
        if (assets.isEmpty)
          Padding(
            padding: EdgeInsets.only(top: AppSpacing.sm),
            child: Text(
              CommunityText.noData,
              style: _boardSecondaryStyle(isDark),
            ),
          ),
        for (final asset in assets)
          CupertinoButton(
            key: ValueKey<String>(
              'gathering-board-asset-${asset.mediaAssetId}',
            ),
            padding: EdgeInsets.symmetric(vertical: AppSpacing.sm),
            minimumSize: const Size(
              AppSpacing.minInteractiveSize,
              AppSpacing.minInteractiveSize,
            ),
            onPressed: onOpenAsset == null
                ? null
                : () => unawaited(onOpenAsset!(asset)),
            child: Row(
              children: [
                Icon(
                  _assetIcon(asset.kind),
                  color: AppColors.primaryColor,
                  size: AppSpacing.iconMedium,
                ),
                SizedBox(width: AppSpacing.intraGroupSm),
                Expanded(
                  child: Text(
                    asset.displayLabel,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: _boardBodyStyle(isDark),
                  ),
                ),
                if (onOpenAsset != null)
                  Icon(
                    CupertinoIcons.chevron_forward,
                    color: AppColorsFunctional.getColor(
                      isDark,
                      ColorType.foregroundSecondary,
                    ),
                    size: AppSpacing.iconSmall,
                  ),
              ],
            ),
          ),
      ],
    );
  }

  static IconData _assetIcon(GatheringBoardAssetKind kind) => switch (kind) {
    GatheringBoardAssetKind.image => CupertinoIcons.photo,
    GatheringBoardAssetKind.video => CupertinoIcons.video_camera,
    GatheringBoardAssetKind.file => CupertinoIcons.doc,
  };
}

class _GatheringBoardAssetCount extends StatelessWidget {
  const _GatheringBoardAssetCount({
    required this.label,
    required this.count,
    required this.isDark,
  });

  final String label;
  final int count;
  final bool isDark;

  @override
  Widget build(BuildContext context) => Column(
    children: [
      Text(
        count.toString(),
        style: TextStyle(
          color: AppColorsFunctional.getColor(
            isDark,
            ColorType.foregroundPrimary,
          ),
          fontSize: AppTypography.iosTitle3,
          fontWeight: AppTypography.semiBold,
        ),
      ),
      SizedBox(height: AppSpacing.intraGroupXs),
      Text(label, style: _boardSecondaryStyle(isDark)),
    ],
  );
}
