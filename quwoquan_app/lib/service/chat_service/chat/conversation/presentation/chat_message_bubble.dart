import 'dart:math' as math;

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/chat_message_display_item.dart';
import 'package:quwoquan_app/design_system/avatar/rounded_square_avatar.dart';
import 'package:quwoquan_app/design_system/chat/message_bubble_frame.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/design_system/typography/app_font_families.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/chat_mention_text.dart';
import 'package:quwoquan_app/runtime/di/chat_presentation_slots.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/rtc_call_log_bubble.dart';

/// 聊天气泡最大宽度（语义尺寸，多屏适配由布局约束决定）
const double chatBubbleMaxWidth = AppSpacing.chatBubbleMaxWidth;
const double chatBubbleWidthFactor = 0.84;

/// 聊天气泡内图片展示尺寸（语义尺寸）
const double chatBubbleImageSize = AppSpacing.chatBubbleImageSize;

class ChatMessageBubble extends ConsumerWidget {
  const ChatMessageBubble({
    super.key,
    required this.message,
    required this.isRight,
    required this.bubbleColor,
    required this.textColor,
    required this.isSelectionMode,
    required this.isSelected,
    required this.onLongPressStart,
    this.onTap,
    this.onAvatarTap,
    this.hideAvatarAndName = false,
    this.useFullWidth = false,
    this.renderSelfTextWithoutBubble = false,
    this.receiptEnabled = false,
    this.memberCount = 2,
    this.messageStatus,
    this.mentionDisplayNames = const <String, String>{},
    this.onMentionTap,
  });

  final ChatMessageDisplayItem message;
  final bool isRight;
  final Color bubbleColor;
  final Color textColor;
  final bool isSelectionMode;
  final bool isSelected;
  final void Function(LongPressStartDetails details) onLongPressStart;
  final VoidCallback? onTap;
  final VoidCallback? onAvatarTap;

  /// 为 true 时不展示头像与昵称（新会话交互布局）
  final bool hideAvatarAndName;

  /// 为 true 时气泡内容占满可用宽度（新会话交互布局）
  final bool useFullWidth;

  /// 为 true 时，自己的文本消息改为右对齐纯文本，不再使用气泡。
  final bool renderSelfTextWithoutBubble;

  /// 会话是否开启已读回执
  final bool receiptEnabled;

  /// 会话成员数（群聊 >2 时不展示逐条回执）
  final int memberCount;

  /// 消息发送状态（sending / sent / failed / recalled）
  final String? messageStatus;
  final Map<String, String> mentionDisplayNames;
  final ValueChanged<String>? onMentionTap;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final viewportWidth = MediaQuery.of(context).size.width;
    const horizontalPadding = AppSpacing.chatBubbleHorizontalPadding;
    final effectiveMaxWidth = useFullWidth
        ? viewportWidth - 2 * horizontalPadding
        : math.max(chatBubbleMaxWidth, viewportWidth * chatBubbleWidthFactor);
    final type = message.type;
    final content = message.content;
    final senderName = message.senderName;
    final avatar = message.senderAvatar.trim().isEmpty
        ? null
        : message.senderAvatar.trim();
    assert(() {
      if (!hideAvatarAndName && (avatar == null || avatar.isEmpty)) {
        debugPrint('消息头像契约：senderAvatar 为空 senderName=$senderName');
      }
      return true;
    }());
    final isRead = message.isRead;
    final renderPlainSelfText =
        renderSelfTextWithoutBubble && isRight && type == 'text';
    final isDark = Theme.of(context).brightness == Brightness.dark;

    Widget contentWidget;
    if (message.status == 'recalled') {
      contentWidget = _BubbleWithTail(
        isRight: isRight,
        color: bubbleColor.withValues(alpha: 0.72),
        tailShadowColor: AppColorsFunctional.getColor(
          isDark,
          ColorType.dropShadow,
        ),
        child: Container(
          constraints: BoxConstraints(maxWidth: effectiveMaxWidth),
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.containerSm,
            vertical: AppSpacing.intraGroupLg,
          ),
          child: Text(
            ChatText.chatPreviewRecalled,
            style: TextStyle(
              fontSize: AppTypography.base,
              color: textColor.withValues(alpha: 0.72),
            ),
          ),
        ),
      );
    } else if (type == 'system_call_log') {
      contentWidget = RtcCallLogBubble(card: message.card, onRedial: onTap);
    } else if (type == 'image') {
      final imageUrl = message.imageUrl.isNotEmpty
          ? message.imageUrl
          : message.thumbnailUrl;
      contentWidget = ClipRRect(
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        child: AppCachedNetworkImage(
          imageUrl: imageUrl,
          width: chatBubbleImageSize,
          height: chatBubbleImageSize,
          fit: BoxFit.cover,
          cdnPreset: CdnImagePreset.inline,
          errorWidget: Container(
            width: chatBubbleImageSize,
            height: chatBubbleImageSize,
            color: bubbleColor,
            child: Icon(Icons.broken_image, color: textColor),
          ),
        ),
      );
    } else if (type == 'audio') {
      contentWidget = ref.watch(voiceMessageBubbleBuilderProvider)(
        messageId: message.id,
        mediaUrl: message.mediaUrl,
        durationMs: message.audioDurationMs,
        waveform: message.audioWaveform,
        isOutgoing: isRight,
        isRead: isRead,
        messageStatus: message.status,
      );
    } else if (type == 'file') {
      final title = content.isNotEmpty ? content : ChatText.chatPreviewFile;
      contentWidget = _BubbleWithTail(
        isRight: isRight,
        color: bubbleColor.withValues(alpha: 0.92),
        tailShadowColor: AppColorsFunctional.getColor(
          isDark,
          ColorType.dropShadow,
        ),
        child: Container(
          constraints: BoxConstraints(
            maxWidth: effectiveMaxWidth * 0.82,
            minWidth: 180,
          ),
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.containerSm,
            vertical: AppSpacing.intraGroupMd,
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              Icon(
                Icons.insert_drive_file_rounded,
                color: textColor.withValues(alpha: 0.92),
                size: AppSpacing.iconMedium,
              ),
              SizedBox(width: AppSpacing.intraGroupSm),
              Flexible(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: AppTypography.iosBody,
                        color: textColor,
                        height: AppTypography.lineHeightCompact,
                      ),
                    ),
                    SizedBox(height: AppSpacing.xs),
                    Text(
                      ChatText.chatPreviewFile,
                      style: TextStyle(
                        fontSize: AppTypography.iosFootnote,
                        color: textColor.withValues(alpha: 0.72),
                        height: AppTypography.lineHeightCompact,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      );
    } else if (type == 'video') {
      final previewUrl = message.thumbnailUrl.isNotEmpty
          ? message.thumbnailUrl
          : message.imageUrl;
      final title = content.isNotEmpty ? content : ChatText.chatPreviewVideo;
      contentWidget = _BubbleWithTail(
        isRight: isRight,
        color: bubbleColor.withValues(alpha: 0.92),
        tailShadowColor: AppColorsFunctional.getColor(
          isDark,
          ColorType.dropShadow,
        ),
        child: ConstrainedBox(
          constraints: BoxConstraints(
            maxWidth: effectiveMaxWidth * 0.86,
            minWidth: AppSpacing.twoHundredTwenty,
          ),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
            child: Stack(
              alignment: Alignment.center,
              children: [
                if (previewUrl.isNotEmpty)
                  AppCachedNetworkImage(
                    imageUrl: previewUrl,
                    width: effectiveMaxWidth * 0.86,
                    height: AppSpacing.twoHundredTwenty,
                    fit: BoxFit.cover,
                    cdnPreset: CdnImagePreset.cover,
                    errorWidget: Container(
                      width: effectiveMaxWidth * 0.86,
                      height: AppSpacing.twoHundredTwenty,
                      color: bubbleColor.withValues(alpha: 0.24),
                      child: Icon(
                        Icons.video_file_rounded,
                        color: textColor.withValues(alpha: 0.92),
                        size: AppSpacing.iconLarge,
                      ),
                    ),
                  )
                else
                  Container(
                    width: effectiveMaxWidth * 0.86,
                    height: AppSpacing.twoHundredTwenty,
                    color: bubbleColor.withValues(alpha: 0.24),
                    child: Icon(
                      Icons.video_file_rounded,
                      color: textColor.withValues(alpha: 0.92),
                      size: AppSpacing.iconLarge,
                    ),
                  ),
                Positioned.fill(
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.topCenter,
                        end: Alignment.bottomCenter,
                        colors: [
                          AppColors.transparent,
                          AppColors.black.withValues(alpha: 0.06),
                          AppColors.black.withValues(alpha: 0.44),
                        ],
                        stops: const [0, 0.58, 1],
                      ),
                    ),
                  ),
                ),
                Positioned(
                  right: AppSpacing.containerSm,
                  top: AppSpacing.containerSm,
                  child: Icon(
                    Icons.play_circle_fill_rounded,
                    color: AppColors.white.withValues(alpha: 0.94),
                    size: AppSpacing.iconLarge,
                  ),
                ),
                Positioned(
                  left: AppSpacing.containerSm,
                  right: AppSpacing.containerSm,
                  bottom: AppSpacing.containerSm,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        title,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: AppTypography.iosBody,
                          color: AppColors.white,
                          height: AppTypography.lineHeightCompact,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      SizedBox(height: AppSpacing.xs),
                      Text(
                        ChatText.chatPreviewVideo,
                        style: TextStyle(
                          fontSize: AppTypography.iosFootnote,
                          color: AppColors.white.withValues(alpha: 0.84),
                          height: AppTypography.lineHeightCompact,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      );
    } else if (type == 'card' && message.card != null) {
      final card = message.card!;
      final title = card.title.trim().isEmpty
          ? ChatText.chatPreviewCard
          : card.title.trim();
      final subtitle = card.subtitle?.trim() ?? '';
      final thumbnailUrl = card.thumbnailUrl?.trim() ?? '';
      contentWidget = _BubbleWithTail(
        isRight: isRight,
        color: bubbleColor.withValues(alpha: 0.94),
        tailShadowColor: AppColorsFunctional.getColor(
          isDark,
          ColorType.dropShadow,
        ),
        child: ConstrainedBox(
          constraints: BoxConstraints(
            maxWidth: effectiveMaxWidth * 0.92,
            minWidth: AppSpacing.twoHundredTwenty,
          ),
          child: Padding(
            padding: EdgeInsets.all(AppSpacing.containerSm),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                if (thumbnailUrl.isNotEmpty) ...[
                  ClipRRect(
                    borderRadius: BorderRadius.circular(
                      AppSpacing.largeBorderRadius,
                    ),
                    child: AppCachedNetworkImage(
                      imageUrl: thumbnailUrl,
                      width: AppSpacing.avatarUserXl,
                      height: AppSpacing.avatarUserXl,
                      fit: BoxFit.cover,
                      cdnPreset: CdnImagePreset.thumbnail,
                      errorWidget: Container(
                        width: AppSpacing.avatarUserXl,
                        height: AppSpacing.avatarUserXl,
                        color: bubbleColor.withValues(alpha: 0.3),
                        child: Icon(
                          Icons.link_rounded,
                          color: textColor.withValues(alpha: 0.8),
                        ),
                      ),
                    ),
                  ),
                  SizedBox(width: AppSpacing.intraGroupSm),
                ],
                Expanded(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: AppTypography.iosBody,
                          color: textColor,
                          height: AppTypography.lineHeightCompact,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      if (subtitle.isNotEmpty) ...[
                        SizedBox(height: AppSpacing.xs),
                        Text(
                          subtitle,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: AppTypography.iosFootnote,
                            color: textColor.withValues(alpha: 0.72),
                            height: AppTypography.lineHeightCompact,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
                SizedBox(width: AppSpacing.intraGroupXs),
                Icon(
                  CupertinoIcons.chevron_forward,
                  color: textColor.withValues(alpha: 0.64),
                  size: AppSpacing.iconMedium,
                ),
              ],
            ),
          ),
        ),
      );
    } else if (renderPlainSelfText) {
      contentWidget = Align(
        alignment: Alignment.centerRight,
        child: Container(
          constraints: BoxConstraints(maxWidth: effectiveMaxWidth * 0.8),
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.containerSm,
            vertical: AppSpacing.intraGroupLg,
          ),
          decoration: BoxDecoration(
            color: bubbleColor,
            borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
          ),
          child: ChatMentionText(
            content: content,
            mentions: message.mentions,
            displayNames: mentionDisplayNames,
            textAlign: TextAlign.left,
            style: TextStyle(
              fontSize: AppTypography.lg,
              color: AppColorsFunctional.getColor(
                isDark,
                ColorType.foregroundInverse,
              ),
              height: AppTypography.bodyLineHeight,
              fontFamily: resolveAppThemeFontFamily(),
              fontFamilyFallback: resolveAppThemeFontFallbacks(),
            ),
            mentionStyle: TextStyle(
              fontSize: AppTypography.lg,
              color: AppColorsFunctional.getColor(
                isDark,
                ColorType.foregroundInverse,
              ),
              height: AppTypography.bodyLineHeight,
              fontWeight: FontWeight.w700,
              decoration: TextDecoration.underline,
              fontFamily: resolveAppThemeFontFamily(),
              fontFamilyFallback: resolveAppThemeFontFallbacks(),
            ),
            onMentionTap: onMentionTap,
          ),
        ),
      );
    } else {
      contentWidget = _BubbleWithTail(
        isRight: isRight,
        color: bubbleColor,
        tailShadowColor: AppColorsFunctional.getColor(
          isDark,
          ColorType.dropShadow,
        ),
        child: Container(
          constraints: BoxConstraints(maxWidth: effectiveMaxWidth),
          padding: EdgeInsets.fromLTRB(
            AppSpacing.containerSm,
            AppSpacing.intraGroupLg,
            AppSpacing.containerSm + 2,
            AppSpacing.intraGroupLg,
          ),
          child: ChatMentionText(
            content: content,
            mentions: message.mentions,
            displayNames: mentionDisplayNames,
            style: TextStyle(
              fontSize: AppTypography.lg,
              color: textColor,
              fontFamily: resolveAppThemeFontFamily(),
              fontFamilyFallback: resolveAppThemeFontFallbacks(),
            ),
            mentionStyle: TextStyle(
              fontSize: AppTypography.lg,
              color: isRight ? textColor : AppColors.primaryColor,
              fontWeight: FontWeight.w700,
              decoration: isRight ? TextDecoration.underline : null,
              fontFamily: resolveAppThemeFontFamily(),
              fontFamilyFallback: resolveAppThemeFontFallbacks(),
            ),
            onMentionTap: onMentionTap,
          ),
        ),
      );
    }

    Widget? avatarWidget;
    if (!hideAvatarAndName) {
      final chatAvatarSize = AppSpacing.avatarUserMd;
      if (avatar != null && avatar.isNotEmpty) {
        avatarWidget = GestureDetector(
          onTap: onAvatarTap,
          child: RoundedSquareAvatar(
            size: chatAvatarSize,
            imageUrl: avatar,
            name: senderName,
          ),
        );
      } else if (onAvatarTap != null) {
        avatarWidget = GestureDetector(
          onTap: onAvatarTap,
          child: RoundedSquareAvatar(
            size: chatAvatarSize,
            imageUrl: null,
            name: senderName,
          ),
        );
      }
    }

    return GestureDetector(
      onTap: onTap,
      onLongPressStart: onLongPressStart,
      child: MessageBubbleFrame(
        isRight: isRight,
        hideAvatarAndName: hideAvatarAndName,
        senderName: senderName,
        textColor: textColor,
        avatar: avatarWidget,
        content: Row(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            if (isSelectionMode)
              Padding(
                padding: EdgeInsets.only(right: AppSpacing.intraGroupSm),
                child: Icon(
                  isSelected
                      ? Icons.check_circle
                      : Icons.radio_button_unchecked,
                  size: AppSpacing.iconMedium,
                  color: AppColors.primaryColor,
                ),
              ),
            if (isRight && (type == 'text' || type == 'image'))
              _ReceiptStatusIndicator(
                isRead: isRead,
                receiptEnabled: receiptEnabled,
                memberCount: memberCount,
                messageStatus: message.status,
                textColor: textColor,
              ),
            Flexible(fit: FlexFit.loose, child: contentWidget),
          ],
        ),
      ),
    );
  }
}

/// 带侧边自然尾巴与 3D 阴影的气泡（原型图一：尾巴在气泡侧边略靠上、上下斜线不同）
class _BubbleWithTail extends StatelessWidget {
  const _BubbleWithTail({
    required this.isRight,
    required this.color,
    required this.tailShadowColor,
    required this.child,
  });

  final bool isRight;
  final Color color;
  final Color tailShadowColor;
  final Widget child;

  static const double _radius = AppSpacing.chatBubbleRadius;
  static const double _tailExtent = AppSpacing.chatBubbleTailExtent;
  static const double _tailTopRatio = 0.35;
  static const double _tailBottomRatio = 0.65;

  static Path _path(double w, double h, bool isRight) {
    final r = _radius;
    final path = Path();
    final ty0 = h * _tailTopRatio;
    final ty1 = h * 0.5;
    final ty2 = h * _tailBottomRatio;
    if (isRight) {
      path.moveTo(r, 0);
      path.lineTo(w - r, 0);
      path.arcTo(
        Rect.fromLTWH(w - r, 0, r, r),
        -math.pi / 2,
        math.pi / 2,
        false,
      );
      path.lineTo(w, ty0 - 1);
      path.lineTo(w + _tailExtent, ty1);
      path.lineTo(w, ty2 + 1);
      path.lineTo(w, h - r);
      path.arcTo(Rect.fromLTWH(w - r, h - r, r, r), 0, math.pi / 2, false);
      path.lineTo(r, h);
      path.arcTo(
        Rect.fromLTWH(0, h - r, r, r),
        math.pi / 2,
        math.pi / 2,
        false,
      );
      path.lineTo(0, r);
      path.arcTo(Rect.fromLTWH(0, 0, r, r), math.pi, math.pi / 2, false);
    } else {
      path.moveTo(r, 0);
      path.lineTo(w - r, 0);
      path.arcTo(
        Rect.fromLTWH(w - r, 0, r, r),
        -math.pi / 2,
        math.pi / 2,
        false,
      );
      path.lineTo(w, h - r);
      path.arcTo(Rect.fromLTWH(w - r, h - r, r, r), 0, math.pi / 2, false);
      path.lineTo(r, h);
      path.arcTo(
        Rect.fromLTWH(0, h - r, r, r),
        math.pi / 2,
        math.pi / 2,
        false,
      );
      path.lineTo(0, ty2 + 1);
      path.lineTo(-_tailExtent, ty1);
      path.lineTo(0, ty0 - 1);
      path.lineTo(0, r);
      path.arcTo(Rect.fromLTWH(0, 0, r, r), math.pi, math.pi / 2, false);
    }
    path.close();
    return path;
  }

  @override
  Widget build(BuildContext context) {
    final content = ClipRRect(
      borderRadius: BorderRadius.circular(_radius),
      child: child,
    );
    return CustomPaint(
      painter: _BubbleTailPainter(
        color: color,
        isRight: isRight,
        tailExtent: _tailExtent,
        shadowColor: tailShadowColor,
      ),
      child: Padding(
        padding: EdgeInsets.only(
          left: isRight ? 0 : _tailExtent,
          right: isRight ? _tailExtent : 0,
        ),
        child: content,
      ),
    );
  }
}

class _BubbleTailPainter extends CustomPainter {
  _BubbleTailPainter({
    required this.color,
    required this.isRight,
    required this.tailExtent,
    required this.shadowColor,
  });

  final Color color;
  final bool isRight;
  final double tailExtent;
  final Color shadowColor;

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width - tailExtent;
    final h = size.height;
    final path = _BubbleWithTail._path(w, h, isRight);
    if (!isRight) canvas.translate(tailExtent, 0);
    final shadowPaint = Paint()
      ..color = shadowColor
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 4);
    canvas.save();
    canvas.translate(0, 2);
    canvas.drawPath(path, shadowPaint);
    canvas.restore();
    canvas.drawPath(path, Paint()..color = color);
    if (!isRight) canvas.translate(-tailExtent, 0);
  }

  @override
  bool shouldRepaint(covariant _BubbleTailPainter oldDelegate) =>
      oldDelegate.color != color ||
      oldDelegate.shadowColor != shadowColor ||
      oldDelegate.isRight != isRight ||
      oldDelegate.tailExtent != tailExtent;
}

/// 消息回执状态指示器：根据 receiptEnabled / memberCount / messageStatus 显示不同状态。
/// - sending -> 时钟图标
/// - failed -> 红色感叹号
/// - 1:1 会话 + receiptEnabled -> 双勾（已读）/ 单勾（已送达）
/// - 群聊（memberCount > 2）或 receiptEnabled=false -> 单勾
class _ReceiptStatusIndicator extends StatelessWidget {
  const _ReceiptStatusIndicator({
    required this.isRead,
    required this.receiptEnabled,
    required this.memberCount,
    required this.textColor,
    this.messageStatus,
  });

  final bool isRead;
  final bool receiptEnabled;
  final int memberCount;
  final String? messageStatus;
  final Color textColor;

  @override
  Widget build(BuildContext context) {
    final IconData icon;
    final Color color;

    if (messageStatus == 'sending') {
      icon = Icons.access_time;
      color = textColor.withValues(alpha: 0.5);
    } else if (messageStatus == 'failed') {
      icon = Icons.info_outline;
      color = textColor.withValues(alpha: 0.58);
    } else if (receiptEnabled && memberCount <= 2 && isRead) {
      icon = Icons.done_all;
      color = AppColors.primaryColor;
    } else {
      icon = Icons.done;
      color = textColor.withValues(alpha: 0.6);
    }

    return Padding(
      padding: EdgeInsets.only(right: AppSpacing.xs),
      child: Icon(icon, size: AppSpacing.iconSmall, color: color),
    );
  }
}
