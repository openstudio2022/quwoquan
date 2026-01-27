import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 更多功能工具类
class MoreActionUtils {
  /// 权限检查
  /// 根据用户权限和功能类型检查是否显示该功能
  static bool checkPermission(String? permission) {
    if (permission == null) return true;
    
    // TODO: 实现实际的权限检查逻辑
    // 这里可以根据用户角色、VIP状态等进行检查
    switch (permission) {
      case 'vip':
        // 检查用户是否为VIP
        return true; // 临时返回true
      case 'premium':
        // 检查用户是否为高级用户
        return true; // 临时返回true
      case 'admin':
        // 检查用户是否为管理员
        return false; // 临时返回false
      default:
        return true;
    }
  }

  /// 显示提示信息
  static void showToast(BuildContext context, String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        duration: const Duration(seconds: 2),
        behavior: SnackBarBehavior.floating,
        margin: EdgeInsets.all(context.safeGetContainerSpacing(SpacingSize.lg)),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(8.0),
        ),
      ),
    );
  }

  /// 显示确认对话框
  static Future<bool> showConfirmDialog(
    BuildContext context,
    String title,
    String message,
  ) async {
    return await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(title),
        content: Text(message),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: Text(UITextConstants.cancel),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: Text(UITextConstants.confirm),
          ),
        ],
      ),
    ) ?? false;
  }

  /// 获取响应式弹窗高度
  static double getModalHeight(BuildContext context, int itemCount) {
    final screenHeight = MediaQuery.of(context).size.height;
    final maxHeight = screenHeight * 0.7;
    final minHeight = 200.0;
    final itemHeight = 80.0;
    final calculatedHeight = minHeight + (itemCount * itemHeight);
    
    return calculatedHeight.clamp(minHeight, maxHeight);
  }

  /// 复制到剪贴板
  static Future<void> copyToClipboard(BuildContext? context, String text) async {
    await Clipboard.setData(ClipboardData(text: text));
    if (context != null) {
      showToast(context, AppStrings.linkCopied);
    }
  }

  /// 分享内容
  static Future<void> shareContent(BuildContext? context, String content) async {
    // TODO: 实现分享功能
    if (context != null) {
      showToast(context, AppStrings.shareFeatureDeveloping);
    }
  }

  /// 检查网络连接
  static bool isNetworkAvailable() {
    // TODO: 实现网络检查
    return true;
  }

  /// 格式化文件大小
  static String formatFileSize(int bytes) {
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
    if (bytes < 1024 * 1024 * 1024) return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
    return '${(bytes / (1024 * 1024 * 1024)).toStringAsFixed(1)} GB';
  }

  /// 格式化时间
  static String formatTimeAgo(DateTime dateTime) {
    final now = DateTime.now();
    final difference = now.difference(dateTime);

    if (difference.inMinutes < 1) {
      return UITextConstants.justNow;
    } else if (difference.inMinutes < 60) {
      return '${difference.inMinutes}${UITextConstants.minutesAgo}';
    } else if (difference.inHours < 24) {
      return '${difference.inHours}${UITextConstants.hoursAgo}';
    } else if (difference.inDays < 7) {
      return '${difference.inDays}${UITextConstants.daysAgo}';
    } else {
      return '${dateTime.month}月${dateTime.day}日';
    }
  }
}
