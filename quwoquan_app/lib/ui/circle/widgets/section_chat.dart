import 'package:flutter/cupertino.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 圈子群聊板块：显示群聊入口卡片；会话缺失时显示未开启空态。
///
/// 会话 id 由 [CircleStateNotifier.loadCircle] 随圈子详情同步解析，
/// 本组件为纯展示投影，无独立加载态。
class SectionChat extends StatelessWidget {
  const SectionChat({
    super.key,
    required this.circleId,
    required this.conversationId,
    required this.isDark,
  });

  final String circleId;
  final String? conversationId;
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    if (conversationId == null) {
      return _buildEmpty();
    }
    return _buildChatEntry(context);
  }

  Widget _buildChatEntry(BuildContext context) {
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return CupertinoButton(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerMd,
        vertical: AppSpacing.containerSm,
      ),
      minimumSize: Size.zero,
      onPressed: () =>
          context.push(AppRoutePaths.chatDetail(id: conversationId!)),
      child: Row(
        children: [
          Container(
            width: AppSpacing.largeButtonSize,
            height: AppSpacing.largeButtonSize,
            decoration: BoxDecoration(
              color: AppColors.primaryColor.withValues(alpha: 0.15),
              shape: BoxShape.circle,
            ),
            child: Icon(
              CupertinoIcons.chat_bubble_2_fill,
              color: AppColors.primaryColor,
              size: AppSpacing.iconMedium,
            ),
          ),
          SizedBox(width: AppSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  UITextConstants.circleChatEntryTitle,
                  style: TextStyle(
                    fontSize: AppTypography.lg,
                    fontWeight: AppTypography.semiBold,
                    color: fgPrimary,
                  ),
                ),
                SizedBox(height: AppSpacing.xs),
                Text(
                  UITextConstants.circleChatEntrySubtitle,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: AppTypography.sm,
                    color: fgSecondary,
                  ),
                ),
              ],
            ),
          ),
          Icon(
            CupertinoIcons.chevron_forward,
            color: fgSecondary,
            size: AppSpacing.iconSmall,
          ),
        ],
      ),
    );
  }

  Widget _buildEmpty() {
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerMd,
        vertical: AppSpacing.containerLg,
      ),
      child: Center(
        child: Text(
          UITextConstants.circleNoChatEnabled,
          style: TextStyle(fontSize: AppTypography.base, color: fgSecondary),
        ),
      ),
    );
  }
}
