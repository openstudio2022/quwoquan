import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/providers/appearance_settings_provider.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/services/user/appearance_settings_repository.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

class SettingsPage extends ConsumerWidget {
  const SettingsPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final appearanceState = ref.watch(appearanceSettingsControllerProvider);
    final contentAccessState = ref.watch(personalContentAccessProvider);
    final snapshot = appearanceState.snapshot;
    final backgroundColor = CupertinoDynamicColor.resolve(
      CupertinoColors.systemGroupedBackground,
      context,
    );

    return CupertinoPageScaffold(
      backgroundColor: backgroundColor,
      navigationBar: CupertinoNavigationBar(
        middle: Text(UITextConstants.settings),
        leading: CupertinoNavigationBarBackButton(
          onPressed: () {
            if (context.canPop()) {
              context.pop();
            } else {
              context.go(AppRoutePaths.profile);
            }
          },
        ),
      ),
      child: Material(
        type: MaterialType.transparency,
        child: SafeArea(
          bottom: false,
          child: ListView(
            padding: EdgeInsets.fromLTRB(
              AppSpacing.containerMd,
              AppSpacing.intraGroupLg,
              AppSpacing.containerMd,
              AppSpacing.xl,
            ),
            children: <Widget>[
              _SettingsGroup(
                title: '偏好',
                children: <Widget>[
                  _SettingsRow(
                    icon: CupertinoIcons.paintbrush,
                    label: '外观与字号',
                    trailingText: _appearanceSummary(snapshot, appearanceState),
                    onTap: () => showCupertinoModalPopup<void>(
                      context: context,
                      builder: (_) => const _AppearanceSettingsSheet(),
                    ),
                  ),
                  _SettingsRow(
                    icon: CupertinoIcons.bell,
                    label: '通知',
                    onTap: () => _showPendingNotice(context, '通知'),
                  ),
                  _SettingsRow(
                    icon: CupertinoIcons.lock_shield,
                    label: '${AppConceptConstants.assistantLabel}读取创作内容',
                    trailingText: _personalContentAccessSummary(
                      contentAccessState,
                    ),
                    onTap: () => _showPersonalContentAccessDialog(
                      context,
                      ref,
                      contentAccessState,
                    ),
                  ),
                ],
              ),
              SizedBox(height: AppSpacing.md),
              _SettingsGroup(
                title: '其他',
                children: <Widget>[
                  _SettingsRow(
                    icon: CupertinoIcons.sparkles,
                    label: AppConceptConstants.assistantLabel,
                    onTap: () => context.push(AppRoutePaths.assistantManagement),
                  ),
                  _SettingsRow(
                    icon: CupertinoIcons.lab_flask,
                    label: '开发者',
                    onTap: () => context.push(AppRoutePaths.settingsDeveloper),
                  ),
                  _SettingsRow(
                    icon: CupertinoIcons.info,
                    label: '关于',
                    onTap: () => _showPendingNotice(context, '关于'),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  static String _appearanceSummary(
    AppearanceSettingsSnapshot snapshot,
    AppearanceSettingsState state,
  ) {
    final base =
        '${_themeModeLabel(snapshot.themeMode)} · '
        '${_fontSizePresetLabel(snapshot.fontSizePreset)}';
    return state.hasPendingSync ? '$base · 待同步' : base;
  }

  static String _personalContentAccessSummary(
    PersonalContentAccessState state,
  ) {
    if (state.isSyncing) return '同步中';
    if (state.isHydrating) return '加载中';
    return state.summaryLabel;
  }

  static Future<void> _showPersonalContentAccessDialog(
    BuildContext context,
    WidgetRef ref,
    PersonalContentAccessState state,
  ) async {
    if (state.isHydrating || state.isSyncing) {
      return;
    }
    final enable = !state.granted;
    final confirmed = await showCupertinoDialog<bool>(
      context: context,
      builder: (ctx) => CupertinoAlertDialog(
        title: Text('${AppConceptConstants.assistantLabel}读取创作内容'),
        content: Text(
          enable
              ? '允许后，${AppConceptConstants.assistantLabel}可在授权范围内读取你的点滴与作品，用于上下文记忆和长期知识引用。'
              : '关闭后，${AppConceptConstants.assistantLabel}将停止使用你的创作内容，并回退到不含个人创作内容的旧检索链路。',
        ),
        actions: <Widget>[
          CupertinoDialogAction(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('取消'),
          ),
          CupertinoDialogAction(
            isDefaultAction: true,
            onPressed: () => Navigator.of(ctx).pop(true),
            child: Text(enable ? '允许' : '关闭'),
          ),
        ],
      ),
    );
    if (confirmed != true) {
      return;
    }
    await ref.read(personalContentAccessProvider.notifier).setGranted(enable);
  }

  static void _showPendingNotice(BuildContext context, String label) {
    showCupertinoDialog<void>(
      context: context,
      builder: (ctx) => CupertinoAlertDialog(
        title: Text(label),
        content: const Text('该功能待接入'),
        actions: <Widget>[
          CupertinoDialogAction(
            isDefaultAction: true,
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('确定'),
          ),
        ],
      ),
    );
  }
}

class _AppearanceSettingsSheet extends ConsumerStatefulWidget {
  const _AppearanceSettingsSheet();

  @override
  ConsumerState<_AppearanceSettingsSheet> createState() =>
      _AppearanceSettingsSheetState();
}

class _AppearanceSettingsSheetState
    extends ConsumerState<_AppearanceSettingsSheet> {
  bool _syncAllAccounts = true;

  @override
  Widget build(BuildContext context) {
    final controller = ref.read(appearanceSettingsControllerProvider.notifier);
    final state = ref.watch(appearanceSettingsControllerProvider);
    final snapshot = state.snapshot;
    final accessibility = ref.watch(accessibilityProvider);
    final backgroundColor = CupertinoDynamicColor.resolve(
      CupertinoColors.secondarySystemGroupedBackground,
      context,
    );

    return Align(
      alignment: Alignment.bottomCenter,
      child: SafeArea(
        top: false,
        child: CupertinoPopupSurface(
          isSurfacePainted: true,
          child: Container(
            height: MediaQuery.of(context).size.height * 0.78,
            color: backgroundColor,
            child: Column(
              children: <Widget>[
                SizedBox(height: AppSpacing.sm),
                Container(
                  width: AppSpacing.createEntrySheetHandleWidth,
                  height: AppSpacing.createEntrySheetHandleHeight,
                  decoration: BoxDecoration(
                    color: CupertinoColors.systemGrey3,
                    borderRadius: BorderRadius.circular(
                      AppSpacing.circularBorderRadius,
                    ),
                  ),
                ),
                Padding(
                  padding: EdgeInsets.fromLTRB(
                    AppSpacing.containerMd,
                    AppSpacing.md,
                    AppSpacing.containerMd,
                    AppSpacing.sm,
                  ),
                  child: Row(
                    children: <Widget>[
                      Text(
                        '外观与字号',
                        style: CupertinoTheme.of(
                          context,
                        ).textTheme.navTitleTextStyle,
                      ),
                      const Spacer(),
                      CupertinoButton(
                        padding: EdgeInsets.zero,
                        onPressed: () => Navigator.of(context).pop(),
                        child: const Text('完成'),
                      ),
                    ],
                  ),
                ),
                Expanded(
                  child: ListView(
                    padding: EdgeInsets.fromLTRB(
                      AppSpacing.containerMd,
                      AppSpacing.sm,
                      AppSpacing.containerMd,
                      AppSpacing.lg,
                    ),
                    children: <Widget>[
                      _SettingsGroup(
                        title: '主题模式',
                        children: AppearanceThemeMode.values
                            .map(
                              (mode) => _SelectionRow(
                                label: _themeModeLabel(mode),
                                selected: snapshot.themeMode == mode,
                                onTap: () => controller.updateSettings(
                                  themeMode: mode,
                                  fontSizePreset: snapshot.fontSizePreset,
                                  applyScope: _syncAllAccounts
                                      ? AppearanceApplyScope.allAccounts
                                      : AppearanceApplyScope.currentSubAccount,
                                ),
                              ),
                            )
                            .toList(),
                      ),
                      SizedBox(height: AppSpacing.md),
                      _SettingsGroup(
                        title: '字号',
                        children: AppearanceFontSizePreset.values
                            .map(
                              (preset) => _SelectionRow(
                                label: _fontSizePresetLabel(preset),
                                subtitle: _fontSizePresetDescription(preset),
                                selected: snapshot.fontSizePreset == preset,
                                onTap: () => controller.updateSettings(
                                  themeMode: snapshot.themeMode,
                                  fontSizePreset: preset,
                                  applyScope: _syncAllAccounts
                                      ? AppearanceApplyScope.allAccounts
                                      : AppearanceApplyScope.currentSubAccount,
                                ),
                              ),
                            )
                            .toList(),
                      ),
                      SizedBox(height: AppSpacing.md),
                      _SettingsGroup(
                        title: '作用范围',
                        children: <Widget>[
                          _SwitchRow(
                            label: '同步到所有账号',
                            value: _syncAllAccounts,
                            subtitle: _syncAllAccounts
                                ? '勾选后写入 Owner 默认值，并让全部子账号收敛到新的统一默认值'
                                : '关闭后仅当前子账号生效，不改写 Owner 默认值',
                            onChanged: (value) {
                              setState(() {
                                _syncAllAccounts = value;
                              });
                            },
                          ),
                          if (snapshot.hasSubAccountOverride)
                            _ActionRow(
                              label: '恢复继承 Owner 默认',
                              onTap: controller.inheritOwnerDefault,
                            ),
                        ],
                      ),
                      SizedBox(height: AppSpacing.md),
                      _SettingsGroup(
                        title: '当前状态',
                        children: <Widget>[
                          _InfoRow(
                            label: '来源',
                            value: _sourceLabel(snapshot.source),
                          ),
                          _InfoRow(
                            label: '同步状态',
                            value: state.hasPendingSync ? '待同步，将在恢复时重试' : '已同步',
                          ),
                          _InfoRow(
                            label: '版本',
                            value: snapshot.version.toString(),
                          ),
                          _InfoRow(
                            label: '更新时间',
                            value: snapshot.updatedAt
                                .toLocal()
                                .toIso8601String()
                                .substring(0, 19)
                                .replaceFirst('T', ' '),
                          ),
                          _InfoRow(
                            label: '粗体文本',
                            value: accessibility.boldText ? '跟随系统：开' : '跟随系统：关',
                          ),
                          _InfoRow(
                            label: '高对比度',
                            value: accessibility.highContrast
                                ? '跟随系统：开'
                                : '跟随系统：关',
                          ),
                        ],
                      ),
                      if (state.lastError != null) ...<Widget>[
                        SizedBox(height: AppSpacing.intraGroupLg),
                        Text(
                          '最近一次同步失败，已保留本地设置，恢复后会继续重试。',
                          style: CupertinoTheme.of(context).textTheme.textStyle
                              .copyWith(
                                color: CupertinoColors.systemRed.resolveFrom(
                                  context,
                                ),
                                fontSize: AppTypography.smPlus,
                              ),
                        ),
                      ],
                      if (state.isLoading) ...<Widget>[
                        SizedBox(height: AppSpacing.md),
                        const Center(child: CupertinoActivityIndicator()),
                      ],
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _SettingsGroup extends StatelessWidget {
  const _SettingsGroup({required this.title, required this.children});

  final String title;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final sectionColor = CupertinoDynamicColor.resolve(
      CupertinoColors.secondarySystemGroupedBackground,
      context,
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Padding(
          padding: EdgeInsets.only(left: AppSpacing.xs, bottom: AppSpacing.sm),
          child: Text(
            title,
            style: CupertinoTheme.of(context).textTheme.textStyle.copyWith(
              fontSize: AppTypography.smPlus,
              color: CupertinoColors.secondaryLabel.resolveFrom(context),
            ),
          ),
        ),
        Container(
          decoration: BoxDecoration(
            color: sectionColor,
            borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
          ),
          clipBehavior: Clip.antiAlias,
          child: Column(children: children),
        ),
      ],
    );
  }
}

class _SettingsRow extends StatelessWidget {
  const _SettingsRow({
    required this.icon,
    required this.label,
    required this.onTap,
    this.trailingText,
  });

  final IconData icon;
  final String label;
  final String? trailingText;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final titleStyle = CupertinoTheme.of(context).textTheme.textStyle.copyWith(
      fontSize: AppTypography.lg,
      fontWeight: AppTypography.semiBold,
    );

    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onTap,
      child: Container(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.fourteen,
        ),
        decoration: BoxDecoration(
          border: Border(
            bottom: BorderSide(
              color: CupertinoColors.separator,
              width: AppSpacing.one * 0,
            ),
          ),
        ),
        child: Row(
          children: <Widget>[
            Icon(
              icon,
              size: AppSpacing.iconSmall,
              color: CupertinoColors.systemGrey,
            ),
            SizedBox(width: AppSpacing.intraGroupLg),
            Expanded(
              child: Text(label, style: titleStyle, textAlign: TextAlign.left),
            ),
            if (trailingText != null) ...<Widget>[
              Flexible(
                child: Text(
                  trailingText!,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: CupertinoTheme.of(context).textTheme.textStyle
                      .copyWith(
                        fontSize: AppTypography.smPlus,
                        color: CupertinoColors.secondaryLabel.resolveFrom(
                          context,
                        ),
                      ),
                ),
              ),
              SizedBox(width: AppSpacing.sm),
            ],
            Icon(
              CupertinoIcons.chevron_forward,
              size: AppSpacing.iconSmall,
              color: CupertinoColors.systemGrey2,
            ),
          ],
        ),
      ),
    );
  }
}

class _SelectionRow extends StatelessWidget {
  const _SelectionRow({
    required this.label,
    required this.selected,
    required this.onTap,
    this.subtitle,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;
  final String? subtitle;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onTap,
      child: Padding(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.fourteen,
        ),
        child: Row(
          children: <Widget>[
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    label,
                    style: CupertinoTheme.of(context).textTheme.textStyle
                        .copyWith(
                          fontSize: AppTypography.lg,
                          fontWeight: AppTypography.semiBold,
                        ),
                    textAlign: TextAlign.left,
                  ),
                  if (subtitle != null) ...<Widget>[
                    SizedBox(height: AppSpacing.xs),
                    Text(
                      subtitle!,
                      style: CupertinoTheme.of(context).textTheme.textStyle
                          .copyWith(
                            fontSize: AppTypography.smPlus,
                            color: CupertinoColors.secondaryLabel.resolveFrom(
                              context,
                            ),
                          ),
                      textAlign: TextAlign.left,
                    ),
                  ],
                ],
              ),
            ),
            Icon(
              selected
                  ? CupertinoIcons.check_mark_circled_solid
                  : CupertinoIcons.circle,
              color: selected
                  ? CupertinoColors.activeBlue
                  : CupertinoColors.systemGrey3.resolveFrom(context),
              size: AppSpacing.iconMedium,
            ),
          ],
        ),
      ),
    );
  }
}

class _SwitchRow extends StatelessWidget {
  const _SwitchRow({
    required this.label,
    required this.value,
    required this.onChanged,
    this.subtitle,
  });

  final String label;
  final bool value;
  final ValueChanged<bool> onChanged;
  final String? subtitle;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () => onChanged(!value),
      child: Padding(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.fourteen,
        ),
        child: Row(
          children: <Widget>[
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    label,
                    style: CupertinoTheme.of(context).textTheme.textStyle
                        .copyWith(
                          fontSize: AppTypography.lg,
                          fontWeight: AppTypography.semiBold,
                        ),
                  ),
                  if (subtitle != null) ...<Widget>[
                    SizedBox(height: AppSpacing.xs),
                    Text(
                      subtitle!,
                      style: CupertinoTheme.of(context).textTheme.textStyle
                          .copyWith(
                            fontSize: AppTypography.smPlus,
                            color: CupertinoColors.secondaryLabel.resolveFrom(
                              context,
                            ),
                          ),
                    ),
                  ],
                ],
              ),
            ),
            SizedBox(width: AppSpacing.intraGroupLg),
            CupertinoSwitch(
              value: value,
              onChanged: onChanged,
              activeTrackColor: SettingsSemanticConstants.switchActiveTrackColor,
              inactiveTrackColor: SettingsSemanticConstants.switchInactiveTrackColor(isDark),
            ),
          ],
        ),
      ),
    );
  }
}

class _ActionRow extends StatelessWidget {
  const _ActionRow({required this.label, required this.onTap});

  final String label;
  final Future<void> Function() onTap;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.intraGroupLg,
      ),
      onPressed: onTap,
      alignment: Alignment.centerLeft,
      child: Text(
        label,
        style: CupertinoTheme.of(context).textTheme.actionTextStyle,
      ),
    );
  }
}

class _InfoRow extends StatelessWidget {
  const _InfoRow({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final secondaryColor = CupertinoColors.secondaryLabel.resolveFrom(context);
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.intraGroupLg,
      ),
      child: Row(
        children: <Widget>[
          Expanded(
            child: Text(
              label,
              style: CupertinoTheme.of(context).textTheme.textStyle.copyWith(
                fontSize: AppTypography.lg,
                color: secondaryColor,
              ),
            ),
          ),
          SizedBox(width: AppSpacing.intraGroupLg),
          Flexible(
            child: Text(
              value,
              textAlign: TextAlign.right,
              style: CupertinoTheme.of(context).textTheme.textStyle.copyWith(
                fontSize: AppTypography.lg,
                fontWeight: AppTypography.semiBold,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

String _themeModeLabel(AppearanceThemeMode mode) {
  return switch (mode) {
    AppearanceThemeMode.system => '跟随系统',
    AppearanceThemeMode.light => '浅色',
    AppearanceThemeMode.dark => '深色',
  };
}

String _fontSizePresetLabel(AppearanceFontSizePreset preset) {
  return switch (preset) {
    AppearanceFontSizePreset.xs => '特小',
    AppearanceFontSizePreset.sm => '偏小',
    AppearanceFontSizePreset.md => '标准',
    AppearanceFontSizePreset.lg => '偏大',
    AppearanceFontSizePreset.xl => '特大',
  };
}

String _fontSizePresetDescription(AppearanceFontSizePreset preset) {
  return switch (preset) {
    AppearanceFontSizePreset.xs => '适合高信息密度浏览',
    AppearanceFontSizePreset.sm => '比默认更紧凑',
    AppearanceFontSizePreset.md => '推荐默认设置',
    AppearanceFontSizePreset.lg => '更适合长时间阅读',
    AppearanceFontSizePreset.xl => '最大字号，适合远距或弱视场景',
  };
}

String _sourceLabel(AppearanceSettingsSource source) {
  return switch (source) {
    AppearanceSettingsSource.ownerDefault => 'Owner 默认',
    AppearanceSettingsSource.subOverride => '当前子账号覆盖',
    AppearanceSettingsSource.systemDefault => '系统默认',
  };
}
