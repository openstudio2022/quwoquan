import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/ui/travel/timeline/trip_timeline_board.dart';
import 'package:quwoquan_app/ui/travel/travel_text_constants.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 当前 Persona 尚未进入共享时间线的个人 Moment。这里展示 canonical
/// TripMoment slice，不从相册、本地草稿或 Timeline 缺口反推记录。
final class TripMomentInboxPanel extends StatelessWidget {
  const TripMomentInboxPanel({
    super.key,
    required this.moments,
    required this.onManage,
  });

  final List<TripMomentSlice> moments;
  final ValueChanged<String> onManage;

  @override
  Widget build(BuildContext context) {
    if (moments.isEmpty) {
      return const SizedBox.shrink();
    }
    final colors = Theme.of(context).colorScheme;
    return Semantics(
      container: true,
      label: TravelText.personalMoments,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: colors.tertiaryContainer,
          borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        ),
        child: Padding(
          padding: EdgeInsets.all(AppSpacing.containerMd),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              Text(
                TravelText.personalMoments,
                style: TextStyle(
                  color: colors.onTertiaryContainer,
                  fontSize: AppTypography.sectionTitle,
                  fontWeight: AppTypography.semiBold,
                ),
              ),
              SizedBox(height: AppSpacing.intraGroupXs),
              Text(
                TravelText.personalMomentsMessage,
                style: TextStyle(
                  color: colors.onTertiaryContainer,
                  fontSize: AppTypography.secondary,
                ),
              ),
              SizedBox(height: AppSpacing.containerSm),
              for (final moment in moments)
                _MomentInboxRow(moment: moment, onManage: onManage),
            ],
          ),
        ),
      ),
    );
  }
}

final class _MomentInboxRow extends StatelessWidget {
  const _MomentInboxRow({required this.moment, required this.onManage});

  final TripMomentSlice moment;
  final ValueChanged<String> onManage;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final text = (moment.inlineText ?? '').trim();
    return Padding(
      padding: EdgeInsets.only(top: AppSpacing.intraGroupXs),
      child: Row(
        children: <Widget>[
          Icon(
            tripMomentKindIcon(moment.kind),
            color: colors.onTertiaryContainer,
            size: AppSpacing.iconSmall,
          ),
          SizedBox(width: AppSpacing.intraGroupSm),
          Expanded(
            child: Text(
              text.isEmpty ? tripMomentKindLabel(moment.kind) : text,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: colors.onTertiaryContainer,
                fontSize: AppTypography.body,
              ),
            ),
          ),
          CupertinoButton(
            padding: EdgeInsets.symmetric(
              horizontal: AppSpacing.containerSm,
              vertical: AppSpacing.intraGroupXs,
            ),
            onPressed: () => onManage(moment.momentId),
            child: const Text(TravelText.organizeMoment),
          ),
        ],
      ),
    );
  }
}
