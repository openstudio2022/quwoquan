part of 'profile_interaction_tab.dart';

// 互动 Tab 的自包含展示组件：方向切换段控、访客关注按钮、行尾动作小药丸、
// 预览缩略图磁贴，以及预览类型归一化。与 profile_interaction_tab.dart 同库（part），
// 拆出仅为收敛主文件行数（R03/R24），公共 API 与 TestKeys 不变。

class ProfileInteractionDirectionSwitch extends StatelessWidget {
  const ProfileInteractionDirectionSwitch({
    super.key,
    required this.isDark,
    required this.current,
    required this.onSelected,
  });

  final bool isDark;
  final InteractionDirection current;
  final ValueChanged<InteractionDirection> onSelected;

  @override
  Widget build(BuildContext context) {
    final selectedForeground = AppColorsFunctional.getColor(
      isDark,
      ColorType.selectionForeground,
    );
    final unselectedForeground = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final selectedFill = AppColorsFunctional.getColor(
      isDark,
      ColorType.selectionBackground,
    );
    final border = AppColors.iosSeparator(
      context,
    ).withValues(alpha: isDark ? 0.34 : 0.26);
    final labelSize = AppTypography.secondaryTabLabelResponsive(context);

    Widget segment(InteractionDirection direction, String label) {
      final selected = current == direction;
      return GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: selected ? null : () => onSelected(direction),
        child: ConstrainedBox(
          constraints: const BoxConstraints(
            minWidth: AppSpacing.profileShareDirectionSegmentMinWidth,
            minHeight: AppSpacing.minInteractiveSize,
          ),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 180),
            curve: Curves.easeOutCubic,
            alignment: Alignment.center,
            padding: EdgeInsets.symmetric(horizontal: AppSpacing.xs),
            decoration: BoxDecoration(
              color: selected ? selectedFill : AppColors.transparent,
              borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
            ),
            child: Text(
              label,
              maxLines: 1,
              style: TextStyle(
                fontSize: labelSize,
                fontWeight: selected
                    ? AppTypography.secondaryTabSelectedWeight
                    : AppTypography.secondaryTabUnselectedWeight,
                color: selected ? selectedForeground : unselectedForeground,
                letterSpacing: -0.08,
              ),
            ),
          ),
        ),
      );
    }

    return Container(
      key: const ValueKey<String>('profile-interaction-direction-switch'),
      padding: EdgeInsets.all(AppSpacing.one),
      decoration: BoxDecoration(
        color: AppColors.transparent,
        borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
        border: Border.all(color: border, width: AppSpacing.one),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          segment(
            InteractionDirection.received,
            UITextConstants.profileInteractionDirectionReceived,
          ),
          segment(
            InteractionDirection.sent,
            UITextConstants.profileInteractionDirectionSent,
          ),
        ],
      ),
    );
  }
}

enum _ProfilePreviewKind { image, video, article, text, unavailable }

_ProfilePreviewKind _normalizedPreviewKind(
  ProfileInteractionActivityViewData item,
) {
  if (item.previewUnavailable) {
    return _ProfilePreviewKind.unavailable;
  }
  final previewKind = item.previewMediaKind.trim().toLowerCase();
  final targetType = item.targetContentType.trim().toLowerCase();
  if (previewKind == 'video' || targetType == 'video') {
    return _ProfilePreviewKind.video;
  }
  if (previewKind == 'image' ||
      previewKind == 'photo' ||
      targetType == 'image' ||
      targetType == 'photo') {
    return _ProfilePreviewKind.image;
  }
  if (previewKind == 'article' ||
      targetType == 'article' ||
      targetType == 'text' ||
      targetType == 'longform') {
    return _ProfilePreviewKind.article;
  }
  if (previewKind == 'text') {
    return _ProfilePreviewKind.text;
  }
  return item.previewText.trim().isNotEmpty
      ? _ProfilePreviewKind.text
      : _ProfilePreviewKind.unavailable;
}

/// 小红书式行尾内联动作小药丸：图标 + 文案，支持 active（已态）/ busy（进行中）。
class _InteractionActionChip extends StatelessWidget {
  const _InteractionActionChip({
    required this.actionKey,
    required this.icon,
    required this.label,
    required this.isDark,
    required this.onPressed,
    this.active = false,
    this.busy = false,
  });

  final Key actionKey;
  final IconData icon;
  final String label;
  final bool isDark;
  final VoidCallback? onPressed;
  final bool active;
  final bool busy;

  @override
  Widget build(BuildContext context) {
    final accent = AppColors.iosAccent(context);
    final inactiveForeground = AppColors.iosSecondaryLabel(context);
    final foreground = active ? accent : inactiveForeground;
    final border = AppColors.iosSeparator(
      context,
    ).withValues(alpha: isDark ? 0.30 : 0.22);
    return CupertinoButton(
      key: actionKey,
      padding: EdgeInsets.zero,
      minimumSize: const Size(
        AppSpacing.minInteractiveSize,
        AppSpacing.minInteractiveSize,
      ),
      onPressed: onPressed,
      child: Container(
        height: AppSpacing.buttonHeightSmCompact,
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: AppColors.transparent,
          borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
          border: Border.all(color: border, width: AppSpacing.hairline),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            if (busy)
              const CupertinoActivityIndicator()
            else
              Icon(icon, size: AppSpacing.iconSmall, color: foreground),
            SizedBox(width: AppSpacing.intraGroupXs),
            Text(
              label,
              maxLines: 1,
              style: TextStyle(
                fontSize: AppTypography.iosFootnote,
                fontWeight: AppTypography.regular,
                color: foreground,
                letterSpacing: -0.08,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ProfileInteractionPreviewTile extends StatefulWidget {
  const _ProfileInteractionPreviewTile({
    required this.item,
    required this.isDark,
    required this.backgroundColor,
  });

  final ProfileInteractionActivityViewData item;
  final bool isDark;
  final Color backgroundColor;

  @override
  State<_ProfileInteractionPreviewTile> createState() =>
      _ProfileInteractionPreviewTileState();
}

class _ProfileInteractionPreviewTileState
    extends State<_ProfileInteractionPreviewTile> {
  int _retrySeed = 0;
  bool _deferMediaLoad = true;
  Timer? _deferMediaLoadTimer;

  @override
  void initState() {
    super.initState();
    _releaseDeferredMediaLoad();
  }

  @override
  void didUpdateWidget(covariant _ProfileInteractionPreviewTile oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.item.activityId != widget.item.activityId) {
      _retrySeed = 0;
      _deferMediaLoad = true;
      _releaseDeferredMediaLoad();
    }
  }

  @override
  void dispose() {
    _deferMediaLoadTimer?.cancel();
    super.dispose();
  }

  void _releaseDeferredMediaLoad() {
    _deferMediaLoadTimer?.cancel();
    _deferMediaLoadTimer = Timer(const Duration(milliseconds: 180), () {
      if (mounted && _deferMediaLoad) {
        setState(() => _deferMediaLoad = false);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final kind = _normalizedPreviewKind(widget.item);
    final imageUrl = resolveContentMediaUrl(widget.item.previewImageUrl);
    final previewText = widget.item.previewText.trim();

    if (kind == _ProfilePreviewKind.unavailable) {
      return _buildPlaceholder(
        context,
        CupertinoIcons.doc_text,
        UITextConstants.profileInteractionOriginalUnavailable,
      );
    }

    if (kind == _ProfilePreviewKind.image ||
        kind == _ProfilePreviewKind.video) {
      if (_deferMediaLoad) {
        return _buildLoading(context);
      }
      if (imageUrl.isEmpty) {
        return _buildLoadFailed(context);
      }
      return Stack(
        fit: StackFit.expand,
        children: <Widget>[
          AppCachedNetworkImage(
            key: ValueKey<String>(
              'profile-interaction-preview-image-${widget.item.activityId}-$_retrySeed',
            ),
            imageUrl: imageUrl,
            fit: BoxFit.cover,
            cdnPreset: CdnImagePreset.thumbnail,
            placeholder: _buildLoading(context),
            errorWidget: _buildLoadFailed(context),
            imageBuilder: kind == _ProfilePreviewKind.video
                ? (context, imageProvider) => Stack(
                    fit: StackFit.expand,
                    children: <Widget>[
                      Image(image: imageProvider, fit: BoxFit.cover),
                      _buildPlayBadge(context),
                    ],
                  )
                : null,
          ),
        ],
      );
    }

    if (previewText.isNotEmpty) {
      return _buildTextPreview(context, previewText, kind: kind);
    }
    return _buildLoadFailed(context);
  }

  Widget _buildTextPreview(
    BuildContext context,
    String text, {
    required _ProfilePreviewKind kind,
  }) {
    final fg = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.foregroundPrimary,
    );
    return Align(
      alignment: Alignment.centerLeft,
      child: Padding(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.intraGroupSm,
          vertical: AppSpacing.intraGroupXs,
        ),
        child: Text(
          text,
          key: kind == _ProfilePreviewKind.article
              ? const ValueKey<String>('profile-interaction-article-preview')
              : null,
          maxLines: 3,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            fontSize: AppTypography.iosCaption2,
            fontWeight: AppTypography.regular,
            color: fg,
            height: AppTypography.lineHeightTight,
          ),
        ),
      ),
    );
  }

  Widget _buildLoading(BuildContext context) {
    final fgSecondary = AppColors.iosSecondaryLabel(context);
    return ColoredBox(
      key: const ValueKey<String>('profile-interaction-preview-loading'),
      color: widget.backgroundColor,
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            const CupertinoActivityIndicator(),
            SizedBox(height: AppSpacing.intraGroupXs),
            Text(
              UITextConstants.profileInteractionPreviewLoading,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: AppTypography.iosCaption2,
                color: fgSecondary,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildLoadFailed(BuildContext context) {
    final fgSecondary = AppColors.iosSecondaryLabel(context);
    final iconColor = AppColors.iosTertiaryLabel(context);
    return ColoredBox(
      key: const ValueKey<String>('profile-interaction-preview-error'),
      color: widget.backgroundColor,
      child: Padding(
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.intraGroupXs),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Text(
              UITextConstants.profileInteractionPreviewLoadFailed,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: AppTypography.iosCaption2,
                color: fgSecondary,
                height: AppTypography.lineHeightTight,
              ),
            ),
            SizedBox(height: AppSpacing.one),
            GestureDetector(
              key: const ValueKey<String>('profile-interaction-preview-retry'),
              behavior: HitTestBehavior.opaque,
              onTap: () {
                setState(() {
                  _retrySeed += 1;
                  _deferMediaLoad = true;
                });
                _releaseDeferredMediaLoad();
              },
              child: Padding(
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.intraGroupXs,
                ),
                child: Icon(
                  CupertinoIcons.arrow_clockwise,
                  key: const ValueKey<String>(
                    'profile-interaction-preview-retry-icon',
                  ),
                  size: AppSpacing.iconSmall,
                  color: iconColor,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildPlaceholder(BuildContext context, IconData icon, String label) {
    final fgSecondary = AppColors.iosSecondaryLabel(context);
    return Padding(
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.intraGroupSm),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: <Widget>[
          Icon(icon, size: AppSpacing.iconSmall, color: fgSecondary),
          SizedBox(height: AppSpacing.intraGroupXs),
          Text(
            label,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: AppTypography.iosCaption2,
              fontWeight: AppTypography.regular,
              color: fgSecondary,
              height: AppTypography.lineHeightTight,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildPlayBadge(BuildContext context) {
    return Center(
      child: Icon(
        CupertinoIcons.play_circle_fill,
        size: AppSpacing.iconMedium,
        color: AppColors.white.withValues(alpha: 0.92),
      ),
    );
  }
}
