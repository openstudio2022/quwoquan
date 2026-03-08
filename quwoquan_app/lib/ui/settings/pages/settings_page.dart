// ignore_for_file: unnecessary_underscores

import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 设置页
///
/// 1:1 复制自 趣我圈2026/src SettingsPage.tsx 结构
/// 显示设置、无障碍、通知、隐私、开发者、关于；私人助理入口→助理管理
class SettingsPage extends ConsumerWidget {
  const SettingsPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isDark = ref.watch(isDarkProvider);
    final pageBg = SettingsSemanticConstants.pageBackground(isDark);
    final blockBg = SettingsSemanticConstants.blockBackground(isDark);
    final fgPrimary = SettingsSemanticConstants.labelColor(isDark);
    final fgSecondary = SettingsSemanticConstants.secondaryColor(isDark);
    final dividerClr = SettingsSemanticConstants.dividerColor(isDark);

    final sections = [
      _SettingsSection(id: 'display', label: '显示设置', icon: Icons.light_mode),
      _SettingsSection(
        id: 'accessibility',
        label: '无障碍',
        icon: Icons.accessibility_new,
      ),
      _SettingsSection(
        id: 'notifications',
        label: '通知',
        icon: Icons.notifications_outlined,
      ),
      _SettingsSection(id: 'privacy', label: '隐私', icon: Icons.shield_outlined),
      _SettingsSection(
        id: 'assistant',
        label: AppConceptConstants.assistantLabel,
        icon: Icons.auto_awesome,
      ),
      _SettingsSection(
        id: 'developer',
        label: '开发者',
        icon: Icons.developer_mode,
      ),
      _SettingsSection(id: 'about', label: '关于', icon: Icons.favorite_border),
    ];

    return Scaffold(
      backgroundColor: pageBg,
      appBar: AppBar(
        backgroundColor: blockBg,
        leading: IconButton(
          onPressed: () {
            if (context.canPop()) {
              context.pop();
            } else {
              context.go(AppRoutePaths.profile);
            }
          },
          icon: Icon(Icons.arrow_back, color: fgPrimary),
        ),
        title: Text(
          UITextConstants.settings,
          style: TextStyle(
            fontSize: 18,
            fontWeight: FontWeight.w700,
            color: fgPrimary,
          ),
        ),
      ),
      body: ListView.separated(
        padding: EdgeInsets.symmetric(
          horizontal: SettingsSemanticConstants.blockHorizontalPadding,
          vertical: SettingsSemanticConstants.blockSpacing,
        ),
        itemCount: sections.length,
        separatorBuilder: (_, __) => Divider(
          height: 1,
          color: dividerClr,
          thickness: SettingsSemanticConstants.dividerThickness,
        ),
        itemBuilder: (context, i) {
          final s = sections[i];
          return ListTile(
            leading: Icon(s.icon, color: fgSecondary, size: 22),
            title: Text(
              s.label,
              style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w600,
                color: fgPrimary,
              ),
            ),
            trailing: Icon(
              CupertinoIcons.chevron_forward,
              color: fgSecondary,
              size: 20,
            ),
            onTap: () {
              if (s.id == 'assistant') {
                context.push(AppRoutePaths.assistantManagement);
              } else if (s.id == 'developer') {
                context.push(AppRoutePaths.settingsDeveloper);
              } else {
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(
                    content: Text('${s.label}（待接入）'),
                    behavior: SnackBarBehavior.floating,
                  ),
                );
              }
            },
          );
        },
      ),
    );
  }
}

class _SettingsSection {
  final String id;
  final String label;
  final IconData icon;
  _SettingsSection({required this.id, required this.label, required this.icon});
}
