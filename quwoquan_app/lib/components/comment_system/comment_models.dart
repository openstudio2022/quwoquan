import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/design_system/spacing/spacing_extensions.dart';

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
  final bool enabled;
  
  const CommentConfig({
    this.maxLength = 500,
    this.enabled = true,
  });
}

extension CommentConfigExtension on CommentConfig {
  bool get canUserComment => enabled;
  bool get isUserLoggedIn => true; // Stub
}

class CommentResponsive {
  static double getCommentItemSize(BuildContext context) => 32.0;
  static double getCommentItemIconSize(BuildContext context) => 20.0;
  static double getAvatarSize(BuildContext context) => 32.0;
  static double getIntraGroupSpacing(BuildContext context, SpacingSize size) {
    switch (size) {
      case SpacingSize.xs:
        return 4.0;
      case SpacingSize.sm:
        return 8.0;
      case SpacingSize.md:
        return 16.0;
      case SpacingSize.lg:
        return 24.0;
      case SpacingSize.xl:
        return 32.0;
    }
  }
  static double getInputHeight(BuildContext context) => 44.0;
  static double getFontSize(BuildContext context, [dynamic size]) {
    if (size is double) return size;
    // Handle CommentFontSize enum if needed
    return 14.0; // Default
  }
  static double getContainerSpacing(BuildContext context, [SpacingSize? size]) {
    if (size != null) return getIntraGroupSpacing(context, size);
    return 16.0; // Default
  }
  
  static EdgeInsets getModalPadding(BuildContext context) {
    return EdgeInsets.all(16.0);
  }
}

/// 评论模态框高度枚举
enum CommentModalHeight {
  adaptive, // 自适应高度
  half,     // 半屏高度
  full,     // 全屏高度
}

enum CommentFontSize {
  small,
  body,
}

class CommentHierarchyManager {
  static String getReplyPlaceholder(CommentModel comment) => '回复 ${comment.authorId ?? "用户"}...';
}
