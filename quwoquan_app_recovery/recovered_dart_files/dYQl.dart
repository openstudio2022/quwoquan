import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import '../more_action_config.dart';
import '../more_action_style.dart';
import '../more_action_types.dart';
import '../more_action_utils.dart';

/// 图片浏览更多功能配置
class ImageViewerMoreActionConfig extends MoreActionConfig {
  final String imageUrl;
  final String? imageTitle;
  final String? imageDescription;
  final VoidCallback? onDownload;
  final VoidCallback? onShare;
  final VoidCallback? onCopyLink;
  final VoidCallback? onViewOriginal;
  final VoidCallback? onSetWallpaper;
  final VoidCallback? onSaveToAlbum;
  final VoidCallback? onReport;
  final VoidCallback? onBlockUser;

  ImageViewerMoreActionConfig({
    required this.imageUrl,
    this.imageTitle,
    this.imageDescription,
    this.onDownload,
    this.onShare,
    this.onCopyLink,
    this.onViewOriginal,
    this.onSetWallpaper,
    this.onSaveToAlbum,
    this.onReport,
    this.onBlockUser,
  });

  @override
  String get title => imageTitle ?? AppStrings.imageOptions;

  @override
  List<MoreActionItem> get horizontalItems => [
    // 下载功能
    MoreActionItem.simple(
      title: '下载',
      icon: Icons.download,
      type: MoreActionType.download,
      onTap: () {
        onDownload?.call();
        // TODO: 实现下载功能
      },
    ),
    
    // 分享功能
    MoreActionItem.simple(
      title: '分享',
      icon: Icons.share,
      type: MoreActionType.share,
      onTap: () {
        onShare?.call();
        // TODO: 实现分享功能
      },
    ),
    
    // 复制链接功能
    MoreActionItem.simple(
      title: '复制链接',
      icon: Icons.link,
      type: MoreActionType.copyLink,
      onTap: () {
        onCopyLink?.call();
        // TODO: 实现复制链接功能
      },
    ),
    
    // 查看原图功能
    MoreActionItem.simple(
      title: '查看原图',
      icon: Icons.zoom_in,
      type: MoreActionType.viewOriginal,
      onTap: () {
        onViewOriginal?.call();
        // TODO: 实现查看原图功能
      },
    ),
    
    // 设为壁纸功能
    MoreActionItem.custom(
      title: AppStrings.setAsWallpaper,
      icon: Icons.wallpaper_outlined,
      type: MoreActionType.custom,
      onTap: () {
        onSetWallpaper?.call();
        // TODO: 实现设为壁纸功能
      },
    ),
    
    // 保存到相册功能
    MoreActionItem.custom(
      title: AppStrings.saveToAlbum,
      icon: Icons.photo_library_outlined,
      type: MoreActionType.custom,
      onTap: () {
        onSaveToAlbum?.call();
        // TODO: 实现保存到相册功能
      },
    ),
  ];

  @override
  List<MoreActionItem> get bottomActions => [
    // 举报图片
    MoreActionItem(
      type: MoreActionType.report,
      title: AppStrings.reportImage,
      subtitle: AppStrings.reportImageDesc,
      onTap: () {
        onReport?.call();
        // TODO: 实现举报图片功能
      },
    ),
    
    // 屏蔽用户
    MoreActionItem(
      type: MoreActionType.blockUser,
      title: AppStrings.blockUser,
      subtitle: AppStrings.blockUserDesc,
      onTap: () {
        onBlockUser?.call();
        // TODO: 实现屏蔽用户功能
      },
    ),
  ];

  @override
  MoreActionStyle get style => MoreActionStyle.imageViewerStyle;

  @override
  MoreActionPermissionChecker? get permissionChecker => _checkPermission;

  /// 权限检查
  static bool _checkPermission(String permission) {
    return MoreActionUtils.checkPermission(permission);
  }
}
