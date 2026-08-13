import 'package:flutter/cupertino.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';

/// 圈子群聊板块：显示群聊入口卡片。
///
/// 会话 id 由 [CircleStateNotifier.loadCircle] 随圈子详情同步解析，
/// 本组件为纯展示投影，无独立加载态。三态语义：
/// - 会话已绑定：群聊入口卡；
/// - 有默认公共群但会话未绑定：诚实「开通中」等待态 + 刷新（绑定是
///   Circle→Chat 的异步 durable 投影，不降级成普通群冒充成功）；
/// - 圈子未配置默认公共群：「讨论尚未开启」空态。
class SectionChat extends StatelessWidget {
  const SectionChat({
    super.key,
    required this.circleId,
    required this.conversationId,
    required this.isDark,
    this.hasDefaultGroup = false,
    this.onRefresh,
  });

  final String circleId;
  final String? conversationId;
  final bool isDark;
  final bool hasDefaultGroup;
  final VoidCallback? onRefresh;

  @override
  Widget build(BuildContext context) {
    final boundConversationId = (conversationId ?? '').trim();
    if (boundConversationId.isEmpty) {
      return hasDefaultGroup ? _buildBindingPending(context) : _buildEmpty();
    }
    return _buildChatEntry(context, boundConversationId);
  }

  Widget _buildChatEntry(BuildContext context, String boundConversationId) {
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
          context.push(AppRoutePaths.chatDetail(id: boundConversationId)),
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
                  CommunityText.circleChatEntryTitle,
                  style: TextStyle(
                    fontSize: AppTypography.lg,
                    fontWeight: AppTypography.semiBold,
                    color: fgPrimary,
                  ),
                ),
                SizedBox(height: AppSpacing.xs),
                Text(
                  CommunityText.circleChatEntrySubtitle,
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

  /// 绑定未就绪：诚实等待 + 刷新重试，不提供假聊天入口。
  Widget _buildBindingPending(BuildContext context) {
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return Padding(
      key: const ValueKey<String>('circle-chat-binding-pending'),
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerMd,
        vertical: AppSpacing.containerLg,
      ),
      child: Column(
        children: [
          Icon(
            CupertinoIcons.chat_bubble_2,
            color: fgSecondary,
            size: AppSpacing.iconLarge,
          ),
          SizedBox(height: AppSpacing.sm),
          Text(
            CommunityText.circleChatBindingPendingTitle,
            style: TextStyle(
              fontSize: AppTypography.base,
              fontWeight: AppTypography.semiBold,
              color: fgPrimary,
            ),
          ),
          SizedBox(height: AppSpacing.xs),
          Text(
            CommunityText.circleChatBindingPendingHint,
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: AppTypography.sm, color: fgSecondary),
          ),
          if (onRefresh != null) ...[
            SizedBox(height: AppSpacing.containerSm),
            CupertinoButton(
              key: const ValueKey<String>('circle-chat-binding-retry'),
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.containerMd,
                vertical: AppSpacing.sm,
              ),
              minimumSize: Size.zero,
              onPressed: onRefresh,
              child: Text(
                FoundationText.retry,
                style: TextStyle(
                  fontSize: AppTypography.sm,
                  fontWeight: AppTypography.semiBold,
                  color: AppColors.primaryColor,
                ),
              ),
            ),
          ],
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
          CommunityText.circleNoChatEnabled,
          style: TextStyle(fontSize: AppTypography.base, color: fgSecondary),
        ),
      ),
    );
  }
}
