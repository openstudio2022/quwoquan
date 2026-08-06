import "package:quwoquan_cloud_contracts/generated/chat_contracts.dart";
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show CallType, EndReason;
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/public/call_log_summary.dart';

/// Conversation-owned rendering of an RTC-authored call-log fact.
final class RtcCallLogPresentation {
  const RtcCallLogPresentation({required this.callType, required this.summary});

  final CallType callType;
  final String summary;

  bool get isVideo => callType == CallType.video;

  factory RtcCallLogPresentation.fromCard(MessageCard? card) {
    final attributes = <String, String>{
      for (final attribute in card?.attributes ?? const [])
        attribute.name: attribute.value,
    };
    final durationMs = int.tryParse(attributes['durationMs'] ?? '') ?? 0;
    final callType = attributes['callType'];
    final endReason = attributes['endReason'];
    if (callType == null || endReason == null) {
      throw const FormatException(
        'rtc_call_log attributes require callType and endReason',
      );
    }
    final summary = resolveCallLogSummary(
      duration: Duration(milliseconds: durationMs),
      endReason: EndReason.fromWire(endReason, 'MessageCard.endReason'),
      connected: durationMs > 0,
    );
    return RtcCallLogPresentation(
      callType: CallType.fromWire(callType, 'MessageCard.callType'),
      summary: switch (summary.kind) {
        CallLogSummaryKind.duration =>
          '${CallText.callSummaryDurationPrefix}'
              '${summary.formattedDuration ?? ''}',
        CallLogSummaryKind.cancelled => CallText.callSummaryCancelled,
        CallLogSummaryKind.rejected => CallText.callSummaryRejected,
        CallLogSummaryKind.noAnswer => CallText.callSummaryNoAnswer,
        CallLogSummaryKind.missed => CallText.callSummaryMissed,
      },
    );
  }
}

class RtcCallLogBubble extends StatelessWidget {
  const RtcCallLogBubble({
    super.key,
    required this.card,
    required this.onRedial,
  });

  final MessageCard? card;
  final VoidCallback? onRedial;

  @override
  Widget build(BuildContext context) {
    final presentation = RtcCallLogPresentation.fromCard(card);
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final foreground = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final background = AppColorsFunctional.getColor(
      isDark,
      ColorType.surfaceElevated,
    );
    return Semantics(
      button: onRedial != null,
      label: presentation.isVideo ? CallText.callVideo : CallText.callVoice,
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        onPressed: onRedial,
        child: Container(
          constraints: const BoxConstraints(
            minWidth: AppSpacing.twoHundredTwenty,
          ),
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.containerSm,
            vertical: AppSpacing.intraGroupMd,
          ),
          decoration: BoxDecoration(
            color: background,
            borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
            border: Border.all(color: foreground.withValues(alpha: 0.08)),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: AppSpacing.iconButtonMinSizeSm,
                height: AppSpacing.iconButtonMinSizeSm,
                decoration: BoxDecoration(
                  color: AppColors.primaryColor.withValues(alpha: 0.14),
                  shape: BoxShape.circle,
                ),
                child: Icon(
                  presentation.isVideo
                      ? CupertinoIcons.video_camera_solid
                      : CupertinoIcons.phone_fill,
                  color: AppColors.primaryColor,
                  size: AppSpacing.iconMedium,
                ),
              ),
              SizedBox(width: AppSpacing.intraGroupMd),
              Flexible(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      presentation.isVideo
                          ? CallText.callVideo
                          : CallText.callVoice,
                      style: TextStyle(
                        color: foreground,
                        fontSize: AppTypography.iosBody,
                        fontWeight: AppTypography.semiBold,
                      ),
                    ),
                    SizedBox(height: AppSpacing.xs),
                    Text(
                      presentation.summary,
                      style: TextStyle(
                        color: foreground.withValues(alpha: 0.68),
                        fontSize: AppTypography.iosFootnote,
                      ),
                    ),
                  ],
                ),
              ),
              if (onRedial != null) ...[
                SizedBox(width: AppSpacing.intraGroupMd),
                Text(
                  CallText.callRedial,
                  style: TextStyle(
                    color: AppColors.primaryColor,
                    fontSize: AppTypography.iosFootnote,
                    fontWeight: AppTypography.medium,
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
