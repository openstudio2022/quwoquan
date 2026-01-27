import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/shared/components/more_actions_popup/more_action_types.dart';
import 'more_action_style.dart';

/// 更多功能弹窗配置基类
abstract class MoreActionConfig {
  String get title;
  List<MoreActionItem> get horizontalItems;
  List<MoreActionItem> get bottomActions;
  MoreActionPermissionChecker? get permissionChecker;
  MoreActionStyle get style;
}

/// 更多功能项目
class MoreActionItem {
  final String title;
  final String? subtitle;
  final IconData icon;
  final MoreActionType type;
  final VoidCallback onTap;
  final bool enabled;
  final String? permission;

  const MoreActionItem({
    required this.title,
    this.subtitle,
    required this.icon,
    required this.type,
    required this.onTap,
    this.enabled = true,
    this.permission,
  });

  factory MoreActionItem.simple({
    required String title,
    String? subtitle,
    required IconData icon,
    required MoreActionType type,
    required VoidCallback onTap,
    bool enabled = true,
    String? permission,
  }) {
    return MoreActionItem(
      title: title,
      subtitle: subtitle,
      icon: icon,
      type: type,
      onTap: onTap,
      enabled: enabled,
      permission: permission,
    );
  }

  factory MoreActionItem.custom({
    required String title,
    String? subtitle,
    required IconData icon,
    required MoreActionType type,
    required VoidCallback onTap,
    bool enabled = true,
    String? permission,
  }) {
    return MoreActionItem(
      title: title,
      subtitle: subtitle,
      icon: icon,
      type: type,
      onTap: onTap,
      enabled: enabled,
      permission: permission,
    );
  }
}

/// 权限检查器类型
typedef MoreActionPermissionChecker = bool Function(String permission);