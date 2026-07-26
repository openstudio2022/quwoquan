part of 'content_share_sheet.dart';

/// 分享面板的无业务状态展示组件。
///
/// 登录续接、接收方加载、外部分发和忙碌状态仍由父文件中的两个 State
/// 唯一持有，本文件只消费已投影的模板与回调。
class _ShareHeader extends StatelessWidget {
  const _ShareHeader({required this.primaryText});

  final Color primaryText;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: AppSpacing.modalHeaderHeight,
      child: Stack(
        alignment: Alignment.center,
        children: <Widget>[
          Text(
            ChatText.shareTo,
            style: TextStyle(
              fontSize: AppTypography.iosTitle3,
              fontWeight: AppTypography.semiBold,
              color: primaryText,
            ),
          ),
          PositionedDirectional(
            end: 0,
            child: CupertinoButton(
              key: const ValueKey<String>('content-share-close-button'),
              padding: EdgeInsets.zero,
              minimumSize: const Size(
                AppSpacing.minInteractiveSize,
                AppSpacing.minInteractiveSize,
              ),
              onPressed: () => Navigator.of(context).maybePop(),
              child: Icon(
                CupertinoIcons.xmark,
                size: AppSpacing.iconMedium,
                color: primaryText,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _SharePreviewCard extends StatelessWidget {
  const _SharePreviewCard({
    required this.template,
    required this.primaryText,
    required this.secondaryText,
  });

  final ContentShareTemplate template;
  final Color primaryText;
  final Color secondaryText;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.iosGroupedSurface(context),
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
      ),
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerSm),
        child: Row(
          children: <Widget>[
            ClipRRect(
              borderRadius: BorderRadius.circular(
                AppSpacing.contentPreviewCornerRadius,
              ),
              child: SizedBox(
                width: AppSpacing.largeButtonSize,
                height: AppSpacing.largeButtonSize,
                child: template.coverUrl.trim().isEmpty
                    ? ColoredBox(
                        color: AppColors.iosTintedFill(context),
                        child: Icon(
                          CupertinoIcons.doc_richtext,
                          color: AppColors.iosAccent(context),
                        ),
                      )
                    : AppCachedNetworkImage(
                        imageUrl: template.coverUrl,
                        fit: BoxFit.cover,
                        width: AppSpacing.largeButtonSize,
                        height: AppSpacing.largeButtonSize,
                        cdnPreset: CdnImagePreset.thumbnail,
                        errorWidget: ColoredBox(
                          color: AppColors.iosTintedFill(context),
                          child: Icon(
                            CupertinoIcons.doc_richtext,
                            color: AppColors.iosAccent(context),
                          ),
                        ),
                      ),
              ),
            ),
            SizedBox(width: AppSpacing.containerSm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    template.title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.iosCaption1,
                      color: AppColors.iosAccent(context),
                    ),
                  ),
                  SizedBox(height: AppSpacing.intraGroupXs),
                  Text(
                    template.shareTitle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.iosSubheadline,
                      fontWeight: AppTypography.semiBold,
                      color: primaryText,
                    ),
                  ),
                  if (template.shareSummary.trim().isNotEmpty)
                    Text(
                      template.shareSummary,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: AppTypography.iosCaption1,
                        color: secondaryText,
                      ),
                    ),
                  Text(
                    template.subtitle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.iosCaption2,
                      color: secondaryText,
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
}

class _ShareSectionTitle extends StatelessWidget {
  const _ShareSectionTitle({required this.title, required this.color});

  final String title;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Text(
      title,
      style: TextStyle(
        fontSize: AppTypography.iosSubheadline,
        fontWeight: AppTypography.semiBold,
        color: color,
      ),
    );
  }
}

class _ShareTargetAction extends StatelessWidget {
  const _ShareTargetAction({
    required this.icon,
    required this.label,
    required this.color,
    required this.onPressed,
    this.busy = false,
  });

  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback? onPressed;
  final bool busy;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: AppSpacing.largeButtonSize + AppSpacing.containerMd,
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        onPressed: onPressed,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Container(
              width: AppSpacing.largeButtonSize,
              height: AppSpacing.largeButtonSize,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: color.withValues(alpha: 0.12),
                shape: BoxShape.circle,
              ),
              child: busy
                  ? const CupertinoActivityIndicator()
                  : Icon(icon, size: AppSpacing.iconLarge, color: color),
            ),
            SizedBox(height: AppSpacing.intraGroupXs),
            Text(
              label,
              textAlign: TextAlign.center,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: AppTypography.iosCaption2,
                color: AppColors.iosSecondaryLabel(context),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _BlockedShareNotice extends StatelessWidget {
  const _BlockedShareNotice({required this.primaryText});

  final Color primaryText;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.iosSecondaryFill(context),
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
      ),
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerMd),
        child: Row(
          children: <Widget>[
            Icon(
              CupertinoIcons.lock_fill,
              color: AppColors.iosSecondaryLabel(context),
            ),
            SizedBox(width: AppSpacing.containerSm),
            Expanded(
              child: Text(
                ChatText.sharePrivateBlocked,
                style: TextStyle(
                  fontSize: AppTypography.iosSubheadline,
                  color: primaryText,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
