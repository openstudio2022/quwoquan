import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/user/models/creator_impact_summary.dart';

/// 创作者影响力卡片（双向可解释性·生产端 v0）。
///
/// 仅渲染 [CreatorImpactSummary] 中的真实事实；摘要为空时展示鼓励发布的空态，
/// 不展示任何占位/估算数字。
class CreatorImpactCard extends StatelessWidget {
  const CreatorImpactCard({
    super.key,
    required this.summary,
    required this.isDark,
  });

  final CreatorImpactSummary summary;
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    final fg = AppColors.iosLabel(context);
    final fgSecondary = AppColors.iosSecondaryLabel(context);

    return Container(
      key: const ValueKey<String>('creator-impact-card'),
      width: double.infinity,
      padding: EdgeInsets.all(AppSpacing.containerLg),
      decoration: BoxDecoration(
        color: AppColors.iosGroupedSurfaceElevated(context),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Icon(
                CupertinoIcons.sparkles,
                size: AppSpacing.iconSmall,
                color: AppColors.primaryColor,
              ),
              SizedBox(width: AppSpacing.intraGroupSm),
              Text(
                UITextConstants.creatorImpactTitle,
                style: TextStyle(
                  fontSize: AppTypography.iosBody,
                  fontWeight: AppTypography.bold,
                  color: fg,
                ),
              ),
            ],
          ),
          SizedBox(height: AppSpacing.intraGroupXs),
          Text(
            UITextConstants.creatorImpactSubtitle,
            style: TextStyle(
              fontSize: AppTypography.iosFootnote,
              color: fgSecondary,
            ),
          ),
          SizedBox(height: AppSpacing.interGroupMd),
          if (summary.isEmpty)
            Text(
              key: const ValueKey<String>('creator-impact-empty'),
              UITextConstants.creatorImpactEmpty,
              style: TextStyle(
                fontSize: AppTypography.iosCallout,
                height: AppSpacing.textLineHeightBody,
                color: fgSecondary,
              ),
            )
          else
            ...summary.facts.map(
              (fact) => Padding(
                padding: EdgeInsets.only(bottom: AppSpacing.sm),
                child: _ImpactRow(fact: fact, fg: fg, fgSecondary: fgSecondary),
              ),
            ),
        ],
      ),
    );
  }
}

class _ImpactRow extends StatelessWidget {
  const _ImpactRow({
    required this.fact,
    required this.fg,
    required this.fgSecondary,
  });

  final CreatorImpactFact fact;
  final Color fg;
  final Color fgSecondary;

  @override
  Widget build(BuildContext context) {
    return Row(
      key: ValueKey<String>('creator-impact-fact-${fact.category.name}'),
      crossAxisAlignment: CrossAxisAlignment.center,
      children: <Widget>[
        Text(
          '${fact.count}',
          style: TextStyle(
            fontSize: AppTypography.iosTitle3,
            fontWeight: AppTypography.bold,
            color: AppColors.primaryColor,
          ),
        ),
        SizedBox(width: AppSpacing.containerSm),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(
                fact.label,
                style: TextStyle(
                  fontSize: AppTypography.iosSubheadline,
                  fontWeight: AppTypography.semiBold,
                  color: fg,
                ),
              ),
              SizedBox(height: AppSpacing.intraGroupXs),
              Text(
                fact.narrative,
                style: TextStyle(
                  fontSize: AppTypography.iosFootnote,
                  color: fgSecondary,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
