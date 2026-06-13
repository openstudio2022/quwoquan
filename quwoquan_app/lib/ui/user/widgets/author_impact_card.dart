import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_summary.g.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 影响力摘要模块（他人主页 / 我的主页双视角，可解释）。
///
/// 只读直出 [AuthorImpactSummary] 的前 [maxItems] 条云侧 displayText 结论句
/// （如「23人加入相关圈子」），端不本地拼装文案（G2）；
/// other 模式无数据不占位，mine 模式空态展示鼓励发布文案。
class AuthorImpactCard extends StatelessWidget {
  const AuthorImpactCard({
    super.key,
    required this.summary,
    required this.isDark,
    required this.isMine,
    this.maxItems = 3,
  });

  static const Key cardKey = ValueKey<String>('author-impact-card');
  static const Key emptyKey = ValueKey<String>('author-impact-empty');

  final AuthorImpactSummary summary;
  final bool isDark;

  /// true = 我的主页；false = 他人主页。
  final bool isMine;
  final int maxItems;

  bool get _isEmpty =>
      summary.total <= 0 ||
      summary.items.every((item) => item.displayText.trim().isEmpty);

  @override
  Widget build(BuildContext context) {
    if (_isEmpty && !isMine) {
      // 用户主页无影响事实不占位（不造假、不放占位数字）。
      return const SizedBox.shrink();
    }
    final fg = AppColors.iosLabel(context);
    final fgSecondary = AppColors.iosSecondaryLabel(context);
    final visible = summary.items
        .where((item) => item.displayText.trim().isNotEmpty)
        .take(maxItems)
        .toList(growable: false);

    return Container(
      key: AuthorImpactCard.cardKey,
      width: double.infinity,
      padding: EdgeInsets.all(AppSpacing.containerSm),
      decoration: BoxDecoration(
        color: AppColors.iosProfileSurface(context),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
        border: Border.all(
          color: AppColors.iosSeparator(
            context,
          ).withValues(alpha: isDark ? 0.24 : 0.08),
          width: AppSpacing.hairline,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Container(
                width: AppSpacing.buttonHeightSm,
                height: AppSpacing.buttonHeightSm,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: AppColors.primaryColor.withValues(alpha: 0.12),
                  shape: BoxShape.circle,
                ),
                child: Icon(
                  CupertinoIcons.waveform_path_ecg,
                  size: AppSpacing.iconSmall,
                  color: AppColors.primaryColor,
                ),
              ),
              SizedBox(width: AppSpacing.intraGroupSm),
              Expanded(
                child: Text(
                  isMine
                      ? UITextConstants.profileImpactTitleMine
                      : UITextConstants.profileImpactTitleOther,
                  style: TextStyle(
                    fontSize: AppTypography.iosSubheadline,
                    fontWeight: AppTypography.semiBold,
                    color: fg,
                  ),
                ),
              ),
            ],
          ),
          SizedBox(height: AppSpacing.intraGroupXs),
          Text(
            isMine
                ? UITextConstants.profileImpactSubtitleMine
                : UITextConstants.profileImpactSubtitleOther,
            style: TextStyle(
              fontSize: AppTypography.iosFootnote,
              color: fgSecondary,
            ),
          ),
          SizedBox(height: AppSpacing.containerSm),
          if (_isEmpty)
            Text(
              key: AuthorImpactCard.emptyKey,
              UITextConstants.profileImpactEmptyMine,
              style: TextStyle(
                fontSize: AppTypography.iosCallout,
                height: AppSpacing.textLineHeightBody,
                color: fgSecondary,
              ),
            )
          else
            for (var i = 0; i < visible.length; i++) ...<Widget>[
              if (i > 0) _ImpactDivider(isDark: isDark),
              _ImpactRow(
                count: visible[i].count,
                displayText: visible[i].displayText.trim(),
                helpType: visible[i].helpType,
                source: visible[i].source,
                fg: fg,
                isMine: isMine,
              ),
            ],
        ],
      ),
    );
  }
}

class _ImpactRow extends StatelessWidget {
  const _ImpactRow({
    required this.count,
    required this.displayText,
    required this.helpType,
    required this.source,
    required this.fg,
    required this.isMine,
  });

  final int count;
  final String displayText;
  final String helpType;
  final String source;
  final Color fg;
  final bool isMine;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      key: ValueKey<String>('author-impact-fact-$helpType'),
      padding: EdgeInsets.zero,
      minimumSize: const Size(
        AppSpacing.minInteractiveSize,
        AppSpacing.minInteractiveSize,
      ),
      onPressed: () => _showEvidence(context),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: <Widget>[
          Container(
            width: AppSpacing.buttonHeightMd,
            height: AppSpacing.buttonHeightMd,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: AppColors.primaryColor.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
            ),
            child: Icon(
              _icon,
              size: AppSpacing.iconSmall,
              color: AppColors.primaryColor,
            ),
          ),
          SizedBox(width: AppSpacing.containerSm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  displayText,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: AppTypography.iosSubheadline,
                    color: fg,
                  ),
                ),
                if (count > 0)
                  Text(
                    isMine
                        ? UITextConstants.impactEnumerableHintMine
                        : UITextConstants.impactEnumerableHintOther,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.iosCaption1,
                      color: AppColors.iosSecondaryLabel(context),
                    ),
                  ),
              ],
            ),
          ),
          Icon(
            CupertinoIcons.chevron_forward,
            size: AppSpacing.iconXSmall,
            color: AppColors.iosTertiaryLabel(context),
          ),
        ],
      ),
    );
  }

  Future<void> _showEvidence(BuildContext context) {
    final sourceLabel = source.trim().isEmpty
        ? (isMine
              ? UITextConstants.profileImpactTitleMine
              : UITextConstants.profileImpactTitleOther)
        : source.trim();
    final hint = isMine
        ? UITextConstants.impactEnumerableHintMine
        : UITextConstants.impactEnumerableHintOther;
    final message = count > 0
        ? '$hint\n$sourceLabel · $count'
        : '$hint\n$sourceLabel';
    return showAppActionSheet<void>(
      context,
      title: displayText,
      message: message,
      sections: const <AppActionSheetSection<void>>[],
      cancelLabel: UITextConstants.confirm,
    );
  }

  IconData get _icon {
    switch (helpType) {
      case 'circle':
      case 'join_circle':
        return CupertinoIcons.person_2_fill;
      case 'friend':
      case 'connection':
        return CupertinoIcons.person_add_solid;
      default:
        return CupertinoIcons.link;
    }
  }
}

class _ImpactDivider extends StatelessWidget {
  const _ImpactDivider({required this.isDark});

  final bool isDark;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.symmetric(vertical: AppSpacing.intraGroupSm),
      child: Container(
        height: AppSpacing.hairline,
        color: AppColors.iosSeparator(
          context,
        ).withValues(alpha: isDark ? 0.18 : 0.12),
      ),
    );
  }
}
