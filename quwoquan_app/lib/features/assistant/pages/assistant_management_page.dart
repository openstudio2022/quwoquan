import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 私人助理管理页
///
/// 性格选择（温柔/严厉/极简）、隐私权限、记忆管理、技能生效时间
class AssistantManagementPage extends ConsumerStatefulWidget {
  const AssistantManagementPage({
    super.key,
    required this.onBack,
  });

  final VoidCallback onBack;

  @override
  ConsumerState<AssistantManagementPage> createState() =>
      _AssistantManagementPageState();
}

class _AssistantManagementPageState extends ConsumerState<AssistantManagementPage> {
  String _personality = 'gentle'; // gentle | strict | minimal
  bool _permChat = true;
  bool _permDynamic = true;
  bool _permLocation = false;
  bool _permNotifications = true;

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final bgColor =
        AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary);
    final fgPrimary =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final borderColor =
        AppColorsFunctional.getColor(isDark, ColorType.borderPrimary);

    return Scaffold(
      backgroundColor: bgColor,
      appBar: AppBar(
        backgroundColor: bgColor,
        leading: IconButton(
          onPressed: widget.onBack,
          icon: Icon(Icons.arrow_back, color: fgPrimary),
        ),
        title: Text(
          AppConceptConstants.assistantManagementTitle,
          style: TextStyle(
            fontSize: 20,
            fontWeight: FontWeight.w700,
            color: fgPrimary,
          ),
        ),
        centerTitle: false,
      ),
      body: SingleChildScrollView(
        padding: EdgeInsets.symmetric(horizontal: 24, vertical: 24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _buildSectionTitle(Icons.person_outline, '性格选择', fgSecondary),
            SizedBox(height: 16),
            Row(
              children: [
                _buildPersonalityChip('gentle', '温柔', '情感关怀', Icons.face),
                SizedBox(width: 12),
                _buildPersonalityChip('strict', '严厉', '强力催促', Icons.face_3),
                SizedBox(width: 12),
                _buildPersonalityChip('minimal', '极简', '言简意赅', Icons.flash_on),
              ],
            ),
            SizedBox(height: 32),
            _buildSectionTitle(Icons.shield_outlined, '隐私权限', fgSecondary),
            SizedBox(height: 16),
            Container(
              decoration: BoxDecoration(
                color: isDark
                    ? Colors.white.withValues(alpha: 0.05)
                    : Colors.black.withValues(alpha: 0.03),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: borderColor.withValues(alpha: 0.5)),
              ),
              child: Column(
                children: [
                  _buildPermissionRow('允许读取聊天', _permChat, (v) => setState(() => _permChat = v), Icons.lock_outline),
                  Divider(height: 1),
                  _buildPermissionRow('允许读取动态', _permDynamic, (v) => setState(() => _permDynamic = v), Icons.memory),
                  Divider(height: 1),
                  _buildPermissionRow('允许访问位置', _permLocation, (v) => setState(() => _permLocation = v), Icons.location_on_outlined),
                  Divider(height: 1),
                  _buildPermissionRow('系统通知', _permNotifications, (v) => setState(() => _permNotifications = v), Icons.notifications_outlined),
                ],
              ),
            ),
            SizedBox(height: 32),
            _buildSectionTitle(Icons.delete_outline, '记忆管理', fgSecondary),
            SizedBox(height: 16),
            Material(
              color: AppColors.error.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(16),
              child: InkWell(
                onTap: () {
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: Text('一键清除记忆（确认逻辑待接入）'),
                      behavior: SnackBarBehavior.floating,
                    ),
                  );
                },
                borderRadius: BorderRadius.circular(16),
                child: Container(
                  padding: EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(
                      color: AppColors.error.withValues(alpha: 0.3),
                    ),
                  ),
                  child: Row(
                    children: [
                      Icon(Icons.delete_outline, color: AppColors.error, size: 20),
                      SizedBox(width: 12),
                      Text(
                        '一键清除记忆',
                        style: TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w700,
                          color: AppColors.error,
                        ),
                      ),
                      Spacer(),
                      Icon(Icons.chevron_right, color: AppColors.error.withValues(alpha: 0.7)),
                    ],
                  ),
                ),
              ),
            ),
            SizedBox(height: 12),
            Text(
              AppConceptConstants.assistantClearMemoryWarning,
              style: TextStyle(
                fontSize: 11,
                color: fgSecondary,
                height: 1.4,
              ),
            ),
            SizedBox(height: 32),
            _buildSectionTitle(Icons.schedule, '技能生效时间', fgSecondary),
            SizedBox(height: 16),
            Container(
              padding: EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: isDark
                    ? Colors.white.withValues(alpha: 0.05)
                    : Colors.black.withValues(alpha: 0.03),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: borderColor.withValues(alpha: 0.5)),
              ),
              child: Column(
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        '日报生成时间',
                        style: TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w700,
                          color: fgPrimary,
                        ),
                      ),
                      Text(
                        '22:00',
                        style: TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w500,
                          color: AppColors.primaryColor,
                        ),
                      ),
                    ],
                  ),
                  SizedBox(height: 16),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(8),
                    child: LinearProgressIndicator(
                      value: 0.85,
                      backgroundColor: fgSecondary.withValues(alpha: 0.2),
                      valueColor: AlwaysStoppedAnimation<Color>(AppColors.primaryColor),
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
        Icon(icon, size: 16, color: fgSecondary),
        SizedBox(width: 8),
        Text(
          label,
          style: TextStyle(
            fontSize: 14,
            fontWeight: FontWeight.w700,
            color: fgSecondary,
          ),
        ),
      ],
    );
  }

  Widget _buildPersonalityChip(
      String id, String label, String desc, IconData icon) {
    final isDark = ref.watch(isDarkProvider);
    final fgPrimary =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final active = _personality == id;
    return Expanded(
      child: Material(
        color: active
            ? AppColors.primaryColor.withValues(alpha: 0.1)
            : (isDark
                ? Colors.white.withValues(alpha: 0.05)
                : Colors.black.withValues(alpha: 0.03)),
        borderRadius: BorderRadius.circular(16),
        child: InkWell(
          onTap: () => setState(() => _personality = id),
          borderRadius: BorderRadius.circular(16),
          child: Container(
            padding: EdgeInsets.symmetric(vertical: 16),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(16),
              border: Border.all(
                color: active
                    ? AppColors.primaryColor
                    : Colors.transparent,
                width: 2,
              ),
            ),
            child: Column(
              children: [
                Icon(
                  icon,
                  size: 24,
                  color: active ? AppColors.primaryColor : fgSecondary,
                ),
                SizedBox(height: 8),
                Text(
                  label,
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                    color: active ? AppColors.primaryColor : fgPrimary,
                  ),
                ),
                Text(
                  desc,
                  style: TextStyle(
                    fontSize: 10,
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
      String label, bool value, ValueChanged<bool> onChanged, IconData icon) {
    final isDark = ref.watch(isDarkProvider);
    final fgPrimary =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    return Padding(
      padding: EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      child: Row(
        children: [
          Icon(icon, size: 16, color: fgSecondary),
          SizedBox(width: 12),
          Text(
            label,
            style: TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.w700,
              color: fgPrimary,
            ),
          ),
          Spacer(),
          Switch(
            value: value,
            onChanged: onChanged,
            activeTrackColor: AppColors.primaryColor.withValues(alpha: 0.5),
            activeThumbColor: AppColors.primaryColor,
          ),
        ],
      ),
    );
  }
}
