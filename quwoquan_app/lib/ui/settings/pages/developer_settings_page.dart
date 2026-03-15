import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';

/// 开发者设置页：Mock/Remote 数据源切换
class DeveloperSettingsPage extends ConsumerWidget {
  const DeveloperSettingsPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isDark = ref.watch(isDarkProvider);
    final mode = ref.watch(appDataSourceModeProvider);
    final pageBg = SettingsSemanticConstants.pageBackground(isDark);
    final blockBg = SettingsSemanticConstants.blockBackground(isDark);
    final fgPrimary = SettingsSemanticConstants.labelColor(isDark);
    final fgSecondary = SettingsSemanticConstants.secondaryColor(isDark);

    return AppScaffold(
      backgroundColor: pageBg,
      navigationBar: AppNavigationBar(
        backgroundColor: blockBg,
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: () => context.pop(),
          child: const Icon(CupertinoIcons.back),
        ),
        middle: Text(
          '开发者',
          style: TextStyle(
            fontSize: AppTypography.xl,
            fontWeight: FontWeight.w700,
            color: fgPrimary,
          ),
        ),
      ),
      body: ListView(
        padding: EdgeInsets.symmetric(
          horizontal: SettingsSemanticConstants.blockHorizontalPadding,
          vertical: SettingsSemanticConstants.blockSpacing,
        ),
        children: [
          CupertinoListTile(
            padding: EdgeInsets.symmetric(vertical: AppSpacing.sm, horizontal: AppSpacing.md),
            leading: Icon(CupertinoIcons.cloud, color: fgSecondary, size: AppSpacing.iconMedium),
            title: Text(
              '数据源',
              style: TextStyle(
                fontSize: AppTypography.lg,
                fontWeight: FontWeight.w600,
                color: fgPrimary,
              ),
            ),
            subtitle: Text(
              mode == AppDataSourceMode.remote ? '云侧接口' : '本地 Mock',
              style: TextStyle(fontSize: AppTypography.base, color: fgSecondary),
            ),
            trailing: CupertinoSwitch(
              value: mode == AppDataSourceMode.remote,
              activeTrackColor: SettingsSemanticConstants.switchActiveTrackColor,
              inactiveTrackColor: SettingsSemanticConstants.switchInactiveTrackColor(isDark),
              onChanged: (value) {
                ref.read(appDataSourceModeProvider.notifier).setMode(
                      value ? AppDataSourceMode.remote : AppDataSourceMode.mock,
                    );
                if (context.mounted) {
                  AppToast.show(
                    context,
                    value ? '已切换至云侧接口' : '已切换至本地 Mock',
                  );
                }
              },
            ),
          ),
        ],
      ),
    );
  }
}
