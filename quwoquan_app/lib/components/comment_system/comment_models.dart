import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/spacing/spacing_extensions.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';

class CommentModel {
  final String id;
  final String content;
  final String? authorId;
  final String? username;
  final CommentModel? replyTo;

  const CommentModel({
    required this.id,
    required this.content,
    this.authorId,
    this.username,
    this.replyTo,
  });
}

class CommentConfig {
  final int maxLength;
  final int maxImageAttachments;
  final bool enabled;

  const CommentConfig({
    this.maxLength = 500,
    this.maxImageAttachments = 3,
    this.enabled = true,
  });
}

extension CommentConfigExtension on CommentConfig {
  bool get canUserComment => enabled;
}

class CommentResponsive {
  static double getCommentItemSize(BuildContext context) =>
      AppSpacing.smallAvatarSize;
  static double getCommentItemIconSize(BuildContext context) =>
      AppSpacing.twenty;
  static double getAvatarSize(BuildContext context) =>
      AppSpacing.smallAvatarSize;
  static double getIntraGroupSpacing(BuildContext context, SpacingSize size) {
    switch (size) {
      case SpacingSize.xs:
        return AppSpacing.xs;
      case SpacingSize.sm:
        return AppSpacing.sm;
      case SpacingSize.md:
        return AppSpacing.md;
      case SpacingSize.lg:
        return AppSpacing.lg;
      case SpacingSize.xl:
        return AppSpacing.xl;
    }
  }

  static double getInputHeight(BuildContext context) => AppSpacing.buttonSize;
  static double getFontSize(BuildContext context, [dynamic size]) {
    if (size is double) return size;
    // Handle CommentFontSize enum if needed
    return AppTypography.base;
  }

  static double getContainerSpacing(BuildContext context, [SpacingSize? size]) {
    if (size != null) return getIntraGroupSpacing(context, size);
    return AppSpacing.md;
  }

  static EdgeInsets getModalPadding(BuildContext context) {
    return EdgeInsets.all(AppSpacing.md);
  }
}

/// 评论模态框高度枚举
enum CommentModalHeight {
  adaptive, // 自适应高度
  half, // 半屏高度
  full, // 全屏高度
}

enum CommentFontSize { small, body }

class CommentHierarchyManager {
  static String getReplyPlaceholder(CommentModel comment) =>
      UITextConstants.commentReplyToTemplate.replaceFirst(
        '%s',
        comment.username ?? comment.authorId ?? UITextConstants.user,
      );
}
