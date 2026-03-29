import 'package:flutter/material.dart';

/// 图片查看器更多操作配置
class ImageViewModelMoreActionConfig {
  final dynamic imageData;
  final VoidCallback? onShare;
  final VoidCallback? onSave;
  final VoidCallback? onCopyLink;
  final VoidCallback? onReport;

  const ImageViewModelMoreActionConfig({
    this.imageData,
    this.onShare,
    this.onSave,
    this.onCopyLink,
    this.onReport,
  });
}
