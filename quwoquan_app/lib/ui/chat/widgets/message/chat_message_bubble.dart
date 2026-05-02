import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:quwoquan_app/components/avatar/rounded_square_avatar.dart';
import 'package:quwoquan_app/components/conversation/message_bubble_frame.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/chat/widgets/message/voice_message_bubble.dart';

/// 聊天气泡最大宽度（语义尺寸，多屏适配由布局约束决定）
const double chatBubbleMaxWidth = 280.0;
const double chatBubbleWidthFactor = 0.84;

/// 聊天气泡内图片展示尺寸（语义尺寸）
const double chatBubbleImageSize = 200.0;

class ChatMessageBubble extends StatelessWidget {
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
  });

  final Map<String, dynamic> message;
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

  @override
  Widget build(BuildContext context) {
    final viewportWidth = MediaQuery.of(context).size.width;
    const horizontalPadding = 24.0;
    final effectiveMaxWidth = useFullWidth
        ? viewportWidth - 2 * horizontalPadding
        : math.max(chatBubbleMaxWidth, viewportWidth * chatBubbleWidthFactor);
    final type = message['type'] as String? ?? 'text';
    final content = message['content'] as String? ?? '';
    final senderName = message['senderName'] as String? ?? '';
    final avatar = (message['senderAvatar'] as String?)?.trim();
    assert(() {
      if (!hideAvatarAndName && (avatar == null || avatar.isEmpty)) {
        debugPrint('消息头像契约：senderAvatar 为空 senderName=$senderName');
      }
      return true;
    }());
    final isRead = message['isRead'] == true;
    final renderPlainSelfText =
        renderSelfTextWithoutBubble && isRight && type == 'text';
    final isDark = Theme.of(context).brightness == Brightness.dark;

    Widget contentWidget;
    if (type == 'task_card') {
      final tasks = message['tasks'] as List<dynamic>? ?? [];
      contentWidget = Container(
        constraints: BoxConstraints(maxWidth: effectiveMaxWidth),
        decoration: BoxDecoration(
          color: bubbleColor.withValues(alpha: 0.2),
          borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
          border: Border.all(color: bubbleColor.withValues(alpha: 0.3)),
        ),
        padding: EdgeInsets.all(AppSpacing.sm),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '今日待办提醒',
              style: TextStyle(
                fontSize: AppTypography.sm,
                fontWeight: FontWeight.w600,
                color: textColor,
              ),
            ),
            SizedBox(height: AppSpacing.sm),
            ...tasks.map<Widget>((t) {
              final map = t is Map
                  ? t as Map<String, dynamic>
                  : <String, dynamic>{};
              final title = map['title'] as String? ?? '';
              final time = map['time'] as String? ?? '';
              final status = map['status'] as String? ?? 'pending';
              return Padding(
                padding: EdgeInsets.only(bottom: AppSpacing.xs),
                child: Row(
                  children: [
                    Icon(
                      status == 'completed'
                          ? Icons.check_circle
                          : Icons.radio_button_unchecked,
                      size: AppSpacing.iconSmall,
                      color: textColor,
                    ),
                    SizedBox(width: AppSpacing.intraGroupSm),
                    Expanded(
                      child: Text(
                        '$title · $time',
                        style: TextStyle(
                          fontSize: AppTypography.sm,
                          color: textColor,
                        ),
                      ),
                    ),
                  ],
                ),
              );
            }),
          ],
        ),
      );
    } else if (type == 'image') {
      final imageUrl =
          message['imageUrl'] as String? ??
          message['thumbnailUrl'] as String? ??
          '';
      contentWidget = ClipRRect(
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        child: Image.network(
          imageUrl,
          width: chatBubbleImageSize,
          height: chatBubbleImageSize,
          fit: BoxFit.cover,
          errorBuilder: (context, error, stackTrace) => Container(
            width: chatBubbleImageSize,
            height: chatBubbleImageSize,
            color: bubbleColor,
            child: Icon(Icons.broken_image, color: textColor),
          ),
        ),
      );
    } else if (type == 'audio') {
      final media = message['media'] is Map
          ? (message['media'] as Map).cast<String, dynamic>()
          : <String, dynamic>{};
      final mediaUrl =
          (media['url'] as String?) ?? (message['mediaUrl'] as String?) ?? '';
      final durationMs = (media['durationMs'] as num?)?.toInt() ?? 0;
      final waveformRaw = media['waveform'];
      final waveform = waveformRaw is List
          ? waveformRaw.map((e) => (e as num).toDouble()).toList()
          : <double>[];
      final msgId = (message['_id'] ?? message['id'] ?? '') as String;
      final msgStatus =
          (message['messageStatus'] ?? message['status'] ?? 'sent') as String;
      contentWidget = VoiceMessageBubble(
        messageId: msgId,
        mediaUrl: mediaUrl,
        durationMs: durationMs,
        waveform: waveform,
        isOutgoing: isRight,
        isRead: isRead,
        messageStatus: msgStatus,
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
          child: SelectableText(
            content,
            textAlign: TextAlign.left,
            style: TextStyle(
              fontSize: AppTypography.lg,
              color: AppColorsFunctional.getColor(
                isDark,
                ColorType.foregroundInverse,
              ),
              height: AppTypography.bodyLineHeight,
            ),
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
          child: SelectableText(
            content,
            style: TextStyle(fontSize: AppTypography.lg, color: textColor),
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
                messageStatus: messageStatus,
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

  static const double _radius = 12;
  static const double _tailExtent = 8;
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
    final sizedForTail = Padding(
      padding: EdgeInsets.only(
        left: isRight ? 0 : _tailExtent,
        right: isRight ? _tailExtent : 0,
      ),
      child: content,
    );
    return Stack(
      clipBehavior: Clip.none,
      alignment: Alignment.center,
      children: [
        Opacity(opacity: 0, child: sizedForTail),
        Positioned.fill(
          child: CustomPaint(
            painter: _BubbleTailPainter(
              color: color,
              isRight: isRight,
              tailExtent: _tailExtent,
              shadowColor: tailShadowColor,
            ),
          ),
        ),
        Positioned(
          left: isRight ? 0 : _tailExtent,
          top: 0,
          right: isRight ? _tailExtent : 0,
          bottom: 0,
          child: content,
        ),
      ],
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
      icon = Icons.error_outline;
      color = AppColors.error;
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
