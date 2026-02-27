import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 开发者设置页：Mock/Remote 数据源切换
class DeveloperSettingsPage extends ConsumerWidget {
  const DeveloperSettingsPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isDark = ref.watch(isDarkProvider);
    final mode = ref.watch(appDataSourceModeProvider);
    final bgColor =
        AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary);
    final fgPrimary =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);

    return Scaffold(
      backgroundColor: bgColor,
      appBar: AppBar(
        backgroundColor: bgColor,
        leading: IconButton(
          onPressed: () => context.pop(),
          icon: Icon(Icons.arrow_back, color: fgPrimary),
        ),
        title: Text(
          '开发者',
          style: TextStyle(
            fontSize: 18,
            fontWeight: FontWeight.w700,
            color: fgPrimary,
          ),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.symmetric(vertical: 16),
        children: [
          SwitchListTile(
            secondary: Icon(Icons.cloud, color: fgSecondary, size: 22),
            title: Text(
              '数据源',
              style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w600,
                color: fgPrimary,
              ),
            ),
            subtitle: Text(
              mode == AppDataSourceMode.remote ? '云侧接口' : '本地 Mock',
              style: TextStyle(fontSize: 14, color: fgSecondary),
            ),
            value: mode == AppDataSourceMode.remote,
            onChanged: (value) {
              ref.read(appDataSourceModeProvider.notifier).setMode(
                    value ? AppDataSourceMode.remote : AppDataSourceMode.mock,
                  );
              if (context.mounted) {
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(
                    content: Text(
                      value ? '已切换至云侧接口' : '已切换至本地 Mock',
                    ),
                    behavior: SnackBarBehavior.floating,
                  ),
                );
              }
            },
          ),
        ],
      ),
    );
  }
}
