import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/components/settings_form/settings_inset_form_page.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';

/// 开发者设置页：Mock/Remote 数据源切换
class DeveloperSettingsPage extends ConsumerWidget {
  const DeveloperSettingsPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isDark = ref.watch(isDarkProvider);
    final fgPrimary = SettingsSemanticConstants.labelColor(isDark);
    final fgSecondary = SettingsSemanticConstants.secondaryColor(isDark);

    return SettingsInsetFormPageScaffold(
      isDark: isDark,
      title: '开发者',
      onBack: () => context.pop(),
      body: SafeArea(
        child: ListView(
          padding: EdgeInsets.only(
            left: SettingsSemanticConstants.insetFormListHorizontalPadding,
            right: SettingsSemanticConstants.insetFormListHorizontalPadding,
            top: AppSpacing.intraGroupSm,
            bottom: AppSpacing.xl,
          ),
          children: [
            if (!kReleaseMode)
              Consumer(
                builder: (context, ref, _) {
                  final mode = ref.watch(appDataSourceModeProvider);
                  return SettingsInsetGroupedSection(
                    isDark: isDark,
                    child: CupertinoListTile(
                      padding: EdgeInsets.symmetric(
                        vertical: AppSpacing.sm,
                        horizontal: AppSpacing.md,
                      ),
                      leading: Icon(
                        CupertinoIcons.cloud,
                        color: fgSecondary,
                        size: AppSpacing.iconMedium,
                      ),
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
                        style: TextStyle(
                          fontSize: AppTypography.base,
                          color: fgSecondary,
                        ),
                      ),
                      trailing: CupertinoSwitch(
                        value: mode == AppDataSourceMode.remote,
                        activeTrackColor:
                            SettingsSemanticConstants.switchActiveTrackColor,
                        inactiveTrackColor:
                            SettingsSemanticConstants.switchInactiveTrackColor(
                              isDark,
                            ),
                        onChanged: (value) {
                          ref.read(appDataSourceModeProvider.notifier).setMode(
                                value
                                    ? AppDataSourceMode.remote
                                    : AppDataSourceMode.mock,
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
                  );
                },
              )
            else
              Padding(
                padding: EdgeInsets.symmetric(
                  horizontal: SettingsSemanticConstants.insetFormListHorizontalPadding,
                  vertical: AppSpacing.lg,
                ),
                child: Text(
                  'Release 构建下不显示数据源切换；请使用 Debug 或 --dart-define=APP_DATA_SOURCE。',
                  style: TextStyle(fontSize: AppTypography.base, color: fgSecondary),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
