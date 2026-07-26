part of 'circle_edit_settings_page.dart';

extension _CircleEditSettingsPageControls on _CircleEditSettingsPageState {
  Widget _buildSegmentedControl<T extends Object>({
    required T groupValue,
    required Map<T, Widget> children,
    required ValueChanged<T?> onValueChanged,
    required Color cardBg,
  }) {
    return Container(
      padding: EdgeInsets.all(AppSpacing.xs),
      decoration: BoxDecoration(
        color: cardBg,
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
      ),
      child: CupertinoSlidingSegmentedControl<T>(
        groupValue: groupValue,
        backgroundColor: cardBg,
        thumbColor: AppColors.primaryColor.withValues(alpha: 0.12),
        children: children,
        onValueChanged: onValueChanged,
      ),
    );
  }
}
