import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_message_card_dto.g.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/ui/rtc/models/call_state.dart';

final class RtcCallLogPresentation {
  const RtcCallLogPresentation({required this.callType, required this.summary});

  final String callType;
  final String summary;

  bool get isVideo => callType == 'video';

  factory RtcCallLogPresentation.fromCard(ChatMessageCardDto? card) {
    final attributes = <String, String>{
      for (final attribute in card?.attributes ?? const [])
        attribute.name: attribute.value,
    };
    final durationMs = int.tryParse(attributes['durationMs'] ?? '') ?? 0;
    return RtcCallLogPresentation(
      callType: attributes['callType'] == 'video' ? 'video' : 'audio',
      summary: CallSummary.describe(
        duration: Duration(milliseconds: durationMs),
        endReason: EndReason.fromString(attributes['endReason']),
        connected: durationMs > 0,
      ),
    );
  }
}

class RtcCallLogBubble extends StatelessWidget {
  const RtcCallLogBubble({
    super.key,
    required this.card,
    required this.onRedial,
  });

  final ChatMessageCardDto? card;
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
      label: presentation.isVideo
          ? UITextConstants.callVideo
          : UITextConstants.callVoice,
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
                          ? UITextConstants.callVideo
                          : UITextConstants.callVoice,
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
                  UITextConstants.callRedial,
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
