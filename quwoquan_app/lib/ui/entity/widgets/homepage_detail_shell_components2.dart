part of 'homepage_detail_shell.dart';

class _HomepagePreviewCell extends StatelessWidget {
  const _HomepagePreviewCell({
    required this.title,
    required this.subtitle,
    required this.label,
    required this.icon,
    this.coverUrl,
  });

  final String title;
  final String subtitle;
  final String label;
  final IconData icon;
  final String? coverUrl;

  @override
  Widget build(BuildContext context) {
    final leading = _HomepagePreviewCover(coverUrl: coverUrl, icon: icon);
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerMd,
        vertical: AppSpacing.containerSm,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          leading,
          SizedBox(width: AppSpacing.containerSm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                _HomepageSummaryChipWidget(label: label, accent: false),
                SizedBox(height: AppSpacing.intraGroupXs),
                Text(
                  title,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: AppTypography.iosSubheadline,
                    fontWeight: AppTypography.medium,
                    color: AppColors.iosLabel(context),
                    height: AppSpacing.textLineHeightBody,
                  ),
                ),
                if (subtitle.trim().isNotEmpty) ...<Widget>[
                  SizedBox(height: AppSpacing.intraGroupXs),
                  Text(
                    subtitle,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.iosFootnote,
                      color: AppColors.iosSecondaryLabel(context),
                      height: AppSpacing.textLineHeightBody,
                    ),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _HomepagePreviewCover extends StatelessWidget {
  const _HomepagePreviewCover({required this.coverUrl, required this.icon});

  final String? coverUrl;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    final fallback = DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.iosSecondaryFill(context),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
      ),
      child: Icon(
        icon,
        size: AppSpacing.iconMedium,
        color: AppColors.iosSecondaryLabel(context),
      ),
    );

    return ClipRRect(
      borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
      child: SizedBox(
        width: AppSpacing.oneHundred - AppSpacing.twentyEight,
        height: AppSpacing.oneHundred - AppSpacing.twentyEight,
        child: (coverUrl ?? '').trim().isEmpty
            ? fallback
            : CircleMediaImage(
                imageSource: coverUrl!,
                fit: BoxFit.cover,
                placeholder: fallback,
                errorWidget: fallback,
              ),
      ),
    );
  }
}

class _HomepageEmptyState extends StatelessWidget {
  const _HomepageEmptyState({
    required this.icon,
    required this.title,
    required this.description,
  });

  final IconData icon;
  final String title;
  final String description;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.symmetric(vertical: AppSpacing.containerLg),
      child: Column(
        children: <Widget>[
          Container(
            width: AppSpacing.buttonSize,
            height: AppSpacing.buttonSize,
            decoration: BoxDecoration(
              color: AppColors.iosSecondaryFill(context),
              borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
            ),
            child: Icon(
              icon,
              size: AppSpacing.iconLarge,
              color: AppColors.iosSecondaryLabel(context),
            ),
          ),
          SizedBox(height: AppSpacing.containerSm),
          Text(
            title,
            style: TextStyle(
              fontSize: AppTypography.iosSubheadline,
              fontWeight: AppTypography.semiBold,
              color: AppColors.iosLabel(context),
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupXs),
          Text(
            description,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: AppTypography.iosFootnote,
              color: AppColors.iosSecondaryLabel(context),
              height: AppSpacing.textLineHeightBody,
            ),
          ),
        ],
      ),
    );
  }
}

class _HomepageBottomActionBar extends StatelessWidget {
  const _HomepageBottomActionBar({
    required this.enabled,
    required this.onPressed,
  });

  final bool enabled;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        AppSpacing.containerSm,
        AppSpacing.containerMd,
        MediaQuery.paddingOf(context).bottom + AppSpacing.containerMd,
      ),
      decoration: BoxDecoration(
        color: AppColors.iosSystemBackground(context),
        border: Border(
          top: BorderSide(
            color: AppColors.iosSeparator(context).withValues(alpha: 0.14),
            width: AppSpacing.hairline,
          ),
        ),
      ),
      child: SizedBox(
        width: double.infinity,
        height: AppSpacing.buttonHeight,
        child: CupertinoButton.filled(
          key: TestKeys.homepageDetailAttachButton,
          onPressed: enabled ? onPressed : null,
          child: Text(enabled ? '关联到本次发布' : '该主页待审核，暂不可操作'),
        ),
      ),
    );
  }
}

class _HomepageSummaryChipWidget extends StatelessWidget {
  const _HomepageSummaryChipWidget({required this.label, required this.accent});

  final String label;
  final bool accent;

  @override
  Widget build(BuildContext context) {
    final accentColor = AppColors.iosAccent(context);
    final background = accent
        ? accentColor.withValues(alpha: 0.12)
        : AppColors.iosSecondaryFill(context);
    final foreground = accent
        ? accentColor
        : AppColors.iosSecondaryLabel(context);
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.intraGroupXs,
      ),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: AppTypography.iosCaption2,
          fontWeight: AppTypography.medium,
          color: foreground,
        ),
      ),
    );
  }
}

class _HomepagePrimaryTabSpec {
  const _HomepagePrimaryTabSpec({required this.id, required this.label});

  final String id;
  final String label;
}

class _HomepageSummaryStats {
  const _HomepageSummaryStats({
    required this.averageRating,
    required this.ratingCount,
    required this.contentCount,
    required this.relatedCount,
  });

  final double? averageRating;
  final int ratingCount;
  final int contentCount;
  final int relatedCount;
}

class _HomepageSummaryChip {
  const _HomepageSummaryChip({required this.label, this.accent = false});

  final String label;
  final bool accent;
}

enum _HomepageMoreAction { claim, maintain, report }

String _statusLabel(String? status) {
  switch ((status ?? '').trim()) {
    case 'candidate':
      return '待发布';
    case 'offline':
      return '已下线';
    case 'published':
      return '已发布';
    default:
      return '主页';
  }
}

String _sourceLabel(String? sourceType) {
  switch ((sourceType ?? '').trim()) {
    case 'official_seed':
      return '官方初始化';
    case 'user_suggested':
      return '用户补充';
    case 'user_created':
      return '用户创建';
    default:
      return '未知来源';
  }
}

String _claimLabel(String? claimStatus) {
  switch ((claimStatus ?? '').trim()) {
    case 'pending_review':
    case 'pending':
      return '认领审核中';
    case 'claimed':
      return '已认领';
    case 'rejected':
      return '认领被退回';
    default:
      return '待认领';
  }
}

String _contentTypeLabel(String contentType) {
  switch (contentType.trim()) {
    case 'article':
      return '长文';
    case 'video':
      return '视频';
    case 'image':
      return '图片';
    default:
      return '内容';
  }
}

IconData _contentTypeIcon(String contentType) {
  switch (contentType.trim()) {
    case 'article':
      return CupertinoIcons.doc_text;
    case 'video':
      return CupertinoIcons.play_rectangle;
    case 'image':
      return CupertinoIcons.photo;
    default:
      return CupertinoIcons.square_stack_3d_up;
  }
}

String _typeLabel(String type) {
  switch (type.trim()) {
    case 'hotel':
      return '酒店';
    case 'restaurant':
      return '餐厅';
    case 'vehicle':
      return '车型';
    case 'sight':
      return '景点';
    case 'university':
      return '大学';
    case 'travel_photo':
      return '旅行摄影';
    default:
      return '主页';
  }
}
