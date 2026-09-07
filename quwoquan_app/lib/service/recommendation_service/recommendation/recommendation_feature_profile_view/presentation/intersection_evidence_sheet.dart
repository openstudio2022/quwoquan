import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_surface.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/application/public/intersection_reason_selection.dart';

/// 首页、视频书、对象页与交集收件箱共用的渐进证据半屏。
///
/// 紧凑面只展示 [IntersectionDisplayResolution.reason] 的主句；用户主动打开本
/// 半屏后，才展示云侧下发的 `evidenceRows`（IntersectionEvidenceRow 契约闭集，
/// 顺序、去重与上限均在云侧水合出口决定）与 resolver 选出的唯一 canonical 行动。
/// 本组件只按序渲染，不合并异构字段、不推断证据、不拼行动文案，也不自行分发 action。
class IntersectionEvidenceSheet extends StatelessWidget {
  const IntersectionEvidenceSheet({
    super.key,
    required this.resolution,
    required this.onDismiss,
    required this.panelKey,
    this.primaryActionKey = const ValueKey<String>(
      'intersection-evidence-primary-action',
    ),
    this.onPrimaryAction,
  });

  final IntersectionDisplayResolution resolution;
  final VoidCallback onDismiss;
  final Key panelKey;
  final Key primaryActionKey;
  final VoidCallback? onPrimaryAction;

  @override
  Widget build(BuildContext context) {
    final reason = resolution.reason;
    final evidenceRows = reason.evidenceRows;
    return AppBottomModalSurface(
      onDismiss: onDismiss,
      panelKey: panelKey,
      contentPadding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        0,
        AppSpacing.containerMd,
        AppSpacing.containerMd,
      ),
      child: SingleChildScrollView(
        physics: const BouncingScrollPhysics(),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Padding(
              padding: EdgeInsets.symmetric(vertical: AppSpacing.containerSm),
              child: Text(
                DiscoveryFeedText.intersectionDetailTitle,
                style: TextStyle(
                  fontSize: AppTypography.lg,
                  fontWeight: AppTypography.semiBold,
                ),
              ),
            ),
            Text(
              reason.primaryText.trim(),
              style: TextStyle(
                fontSize: AppTypography.base,
                fontWeight: AppTypography.medium,
                color: AppColors.iosLabel(context),
              ),
            ),
            for (
              var index = 0;
              index < evidenceRows.length;
              index += 1
            ) ...<Widget>[
              SizedBox(height: AppSpacing.intraGroupSm),
              Row(
                key: ValueKey<String>('intersection-evidence-item-$index'),
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Icon(
                    CupertinoIcons.checkmark_circle_fill,
                    size: AppSpacing.iconSmall,
                    color: AppColors.iosAccent(context),
                  ),
                  SizedBox(width: AppSpacing.intraGroupSm),
                  Expanded(
                    child: Text(
                      evidenceRows[index].text.trim(),
                      style: TextStyle(
                        fontSize: AppTypography.iosFootnote,
                        color: AppColors.iosSecondaryLabel(context),
                      ),
                    ),
                  ),
                ],
              ),
            ],
            if (resolution.primaryHint != null &&
                onPrimaryAction != null) ...<Widget>[
              SizedBox(height: AppSpacing.interGroupSm),
              SizedBox(
                width: double.infinity,
                child: CupertinoButton.filled(
                  key: primaryActionKey,
                  onPressed: onPrimaryAction,
                  child: Text(resolution.primaryHint!.label.trim()),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
