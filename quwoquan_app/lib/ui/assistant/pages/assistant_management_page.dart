import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/core/constants/settings_semantic_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/constants/app_concept_constants.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';

/// 私人助理管理页
///
/// 性格选择（温柔/严厉/极简）、隐私权限、记忆管理、技能生效时间
class AssistantManagementPage extends ConsumerStatefulWidget {
  const AssistantManagementPage({super.key, required this.onBack});

  final VoidCallback onBack;

  @override
  ConsumerState<AssistantManagementPage> createState() =>
      _AssistantManagementPageState();
}

class _AssistantManagementPageState
    extends ConsumerState<AssistantManagementPage> {
  String _personality = 'gentle'; // gentle | strict | minimal
  bool _permChat = true;
  bool _permLocation = false;
  bool _permNotifications = true;

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final contentAccessState = ref.watch(personalContentAccessProvider);
    final pageBg = SettingsSemanticConstants.pageBackground(isDark);
    final blockBg = SettingsSemanticConstants.blockBackground(isDark);
    final fgPrimary = SettingsSemanticConstants.labelColor(isDark);
    final fgSecondary = SettingsSemanticConstants.secondaryColor(isDark);
    final dividerClr = SettingsSemanticConstants.dividerColor(isDark);
    final blockBorder = SettingsSemanticConstants.blockBorderColor(isDark);

    return AppScaffold(
      backgroundColor: pageBg,
      navigationBar: AppNavigationBar(
        backgroundColor: blockBg,
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.back,
          onPressed: widget.onBack,
        ),
        middle: Text(
          AppConceptConstants.assistantManagementTitle,
          style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
        ),
      ),
      child: SingleChildScrollView(
        padding: EdgeInsets.symmetric(
          horizontal: SettingsSemanticConstants.blockHorizontalPadding,
          vertical: SettingsSemanticConstants.blockSpacing,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _buildSectionTitle(Icons.person_outline, '性格选择', fgSecondary),
            SizedBox(height: AppSpacing.interGroupMd),
            Row(
              children: [
                _buildPersonalityChip('gentle', '温柔', '情感关怀', Icons.face),
                SizedBox(width: AppSpacing.interGroupSm),
                _buildPersonalityChip('strict', '严厉', '强力催促', Icons.face_3),
                SizedBox(width: AppSpacing.interGroupSm),
                _buildPersonalityChip('minimal', '极简', '言简意赅', Icons.flash_on),
              ],
            ),
            SizedBox(height: AppSpacing.interGroupXl),
            _buildSectionTitle(Icons.shield_outlined, '隐私权限', fgSecondary),
            SizedBox(height: AppSpacing.interGroupMd),
            Container(
              decoration: BoxDecoration(
                color: blockBg,
                borderRadius: BorderRadius.circular(
                  SettingsSemanticConstants.blockBorderRadius,
                ),
                border: Border.all(color: blockBorder),
              ),
              child: Column(
                children: [
                  _buildPermissionRow(
                    '允许读取聊天',
                    _permChat,
                    (v) => setState(() => _permChat = v),
                    Icons.lock_outline,
                  ),
                  Divider(
                    height: AppSpacing.one,
                    color: dividerClr,
                    thickness: SettingsSemanticConstants.dividerThickness,
                  ),
                  _buildPermissionRow(
                    '允许${AppConceptConstants.assistantLabel}使用我的创作内容',
                    contentAccessState.granted,
                    (v) {
                      if (contentAccessState.isHydrating ||
                          contentAccessState.isSyncing) {
                        return;
                      }
                      ref
                          .read(personalContentAccessProvider.notifier)
                          .setGranted(v);
                    },
                    Icons.memory,
                    enabled:
                        !contentAccessState.isHydrating &&
                        !contentAccessState.isSyncing,
                    detail: contentAccessState.isSyncing
                        ? '同步中'
                        : (contentAccessState.isHydrating
                              ? '加载中'
                              : contentAccessState.summaryLabel),
                  ),
                  Divider(
                    height: AppSpacing.one,
                    color: dividerClr,
                    thickness: SettingsSemanticConstants.dividerThickness,
                  ),
                  _buildPermissionRow(
                    '允许访问位置',
                    _permLocation,
                    (v) => setState(() => _permLocation = v),
                    Icons.location_on_outlined,
                  ),
                  Divider(
                    height: AppSpacing.one,
                    color: dividerClr,
                    thickness: SettingsSemanticConstants.dividerThickness,
                  ),
                  _buildPermissionRow(
                    '系统通知',
                    _permNotifications,
                    (v) => setState(() => _permNotifications = v),
                    Icons.notifications_outlined,
                  ),
                ],
              ),
            ),
            SizedBox(height: AppSpacing.interGroupXl),
            _buildSectionTitle(Icons.delete_outline, '记忆管理', fgSecondary),
            SizedBox(height: AppSpacing.interGroupMd),
            Material(
              color: AppColors.error.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(
                SettingsSemanticConstants.blockBorderRadius,
              ),
              child: InkWell(
                onTap: () {
                  AppToast.show(context, '一键清除记忆（确认逻辑待接入）');
                },
                borderRadius: BorderRadius.circular(
                  SettingsSemanticConstants.blockBorderRadius,
                ),
                child: Container(
                  padding: EdgeInsets.all(AppSpacing.md),
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(
                      SettingsSemanticConstants.blockBorderRadius,
                    ),
                    border: Border.all(
                      color: AppColors.error.withValues(alpha: 0.3),
                    ),
                  ),
                  child: Row(
                    children: [
                      Icon(
                        Icons.delete_outline,
                        color: AppColors.error,
                        size: AppSpacing.twenty,
                      ),
                      SizedBox(width: AppSpacing.interGroupSm),
                      Text(
                        '一键清除记忆',
                        style: TextStyle(
                          fontSize: AppTypography.base,
                          fontWeight: FontWeight.w700,
                          color: AppColors.error,
                        ),
                      ),
                      Spacer(),
                      Icon(
                        CupertinoIcons.chevron_forward,
                        color: AppColors.error.withValues(alpha: 0.7),
                      ),
                    ],
                  ),
                ),
              ),
            ),
            SizedBox(height: AppSpacing.interGroupSm),
            Text(
              AppConceptConstants.assistantClearMemoryWarning,
              style: TextStyle(
                fontSize: AppTypography.xsPlus,
                color: fgSecondary,
                height: AppTypography.bodyLineHeight,
              ),
            ),
            SizedBox(height: AppSpacing.interGroupXl),
            _buildSectionTitle(Icons.schedule, '技能生效时间', fgSecondary),
            SizedBox(height: AppSpacing.interGroupMd),
            Container(
              padding: EdgeInsets.all(
                SettingsSemanticConstants.blockHorizontalPadding,
              ),
              decoration: BoxDecoration(
                color: blockBg,
                borderRadius: BorderRadius.circular(
                  SettingsSemanticConstants.blockBorderRadius,
                ),
                border: Border.all(color: blockBorder),
              ),
              child: Column(
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        '日报生成时间',
                        style: TextStyle(
                          fontSize: AppTypography.base,
                          fontWeight: FontWeight.w700,
                          color: fgPrimary,
                        ),
                      ),
                      Text(
                        '22:00',
                        style: TextStyle(
                          fontSize: AppTypography.base,
                          fontWeight: FontWeight.w500,
                          color: AppColors.primaryColor,
                        ),
                      ),
                    ],
                  ),
                  SizedBox(height: AppSpacing.interGroupMd),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(
                      AppSpacing.borderRadius,
                    ),
                    child: LinearProgressIndicator(
                      value: 0.85,
                      backgroundColor: fgSecondary.withValues(alpha: 0.2),
                      valueColor: AlwaysStoppedAnimation<Color>(
                        AppColors.primaryColor,
                      ),
                      minHeight: 6,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSectionTitle(IconData icon, String label, Color fgSecondary) {
    return Row(
      children: [
        Icon(icon, size: AppSpacing.iconSmall, color: fgSecondary),
        SizedBox(width: AppSpacing.intraGroupMd),
        Text(
          label,
          style: TextStyle(
            fontSize: AppTypography.base,
            fontWeight: FontWeight.w700,
            color: fgSecondary,
          ),
        ),
      ],
    );
  }

  Widget _buildPersonalityChip(
    String id,
    String label,
    String desc,
    IconData icon,
  ) {
    final isDark = ref.watch(isDarkProvider);
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final active = _personality == id;
    return Expanded(
      child: Material(
        color: active
            ? AppColors.primaryColor.withValues(alpha: 0.1)
            : (isDark
                  ? Colors.white.withValues(alpha: 0.05)
                  : Colors.black.withValues(alpha: 0.03)),
        borderRadius: BorderRadius.circular(
          SettingsSemanticConstants.blockBorderRadius,
        ),
        child: InkWell(
          onTap: () => setState(() => _personality = id),
          borderRadius: BorderRadius.circular(
            SettingsSemanticConstants.blockBorderRadius,
          ),
          child: Container(
            padding: EdgeInsets.symmetric(vertical: AppSpacing.md),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(
                SettingsSemanticConstants.blockBorderRadius,
              ),
              border: Border.all(
                color: active ? AppColors.primaryColor : Colors.transparent,
                width: AppSpacing.toolPanelItemBorderWidthSelected,
              ),
            ),
            child: Column(
              children: [
                Icon(
                  icon,
                  size: AppSpacing.iconMedium,
                  color: active ? AppColors.primaryColor : fgSecondary,
                ),
                SizedBox(height: AppSpacing.intraGroupMd),
                Text(
                  label,
                  style: TextStyle(
                    fontSize: AppTypography.base,
                    fontWeight: FontWeight.w700,
                    color: active ? AppColors.primaryColor : fgPrimary,
                  ),
                ),
                Text(
                  desc,
                  style: TextStyle(
                    fontSize: AppTypography.xs,
                    color: fgSecondary,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildPermissionRow(
    String label,
    bool value,
    ValueChanged<bool> onChanged,
    IconData icon, {
    bool enabled = true,
    String? detail,
  }) {
    final isDark = ref.watch(isDarkProvider);
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.interGroupSm,
      ),
      child: Row(
        children: [
          Icon(icon, size: AppSpacing.iconSmall, color: fgSecondary),
          SizedBox(width: AppSpacing.interGroupSm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  label,
                  style: TextStyle(
                    fontSize: AppTypography.base,
                    fontWeight: FontWeight.w700,
                    color: fgPrimary,
                  ),
                ),
                if (detail != null && detail.trim().isNotEmpty) ...[
                  SizedBox(height: AppSpacing.xs / 2),
                  Text(
                    detail,
                    style: TextStyle(
                      fontSize: AppTypography.xsPlus,
                      color: fgSecondary,
                    ),
                  ),
                ],
              ],
            ),
          ),
          CupertinoSwitch(
            value: value,
            onChanged: enabled ? onChanged : null,
            activeTrackColor: SettingsSemanticConstants.switchActiveTrackColor,
            inactiveTrackColor: SettingsSemanticConstants.switchInactiveTrackColor(isDark),
          ),
        ],
      ),
    );
  }
}
