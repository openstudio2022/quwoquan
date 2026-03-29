import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 圈子群聊板块：显示群聊入口卡片（含独立 loading/error 状态）
class SectionChat extends ConsumerStatefulWidget {
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
  ConsumerState<SectionChat> createState() => _SectionChatState();
}

class _SectionChatState extends ConsumerState<SectionChat> {
  bool _isLoading = false;
  String? _error;

  Future<void> _retry() async {
    setState(() {
      _error = null;
      _isLoading = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoading) {
      return const Center(child: CupertinoActivityIndicator());
    }
    if (_error != null) {
      return _buildErrorCard();
    }
    if (widget.conversationId == null) {
      return _buildEmpty();
    }
    return _buildChatEntry(context);
  }

  Widget _buildChatEntry(BuildContext context) {
    final fgPrimary = AppColorsFunctional.getColor(widget.isDark, ColorType.foregroundPrimary);
    final fgSecondary = AppColorsFunctional.getColor(widget.isDark, ColorType.foregroundSecondary);
    final bgSecondary = AppColorsFunctional.getColor(widget.isDark, ColorType.backgroundSecondary);

    return Container(
      margin: EdgeInsets.symmetric(horizontal: AppSpacing.md),
      decoration: BoxDecoration(
        color: bgSecondary,
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
      ),
      child: CupertinoButton(
        padding: EdgeInsets.all(AppSpacing.md),
        minimumSize: Size.zero,
        onPressed: () => context.push(
          AppRoutePaths.chatDetail(id: widget.conversationId!),
        ),
        child: Row(
          children: [
            Container(
              width: AppSpacing.largeButtonSize,
              height: AppSpacing.largeButtonSize,
              decoration: BoxDecoration(
                color: AppColors.primaryColor.withValues(alpha: 0.15),
                borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
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
                    '圈聊入口',
                    style: TextStyle(
                      fontSize: AppTypography.lg,
                      fontWeight: AppTypography.semiBold,
                      color: fgPrimary,
                    ),
                  ),
                  SizedBox(height: AppSpacing.xs),
                  Text(
                    '最近消息与未读会话统一在趣信中查看',
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
            Container(
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.sm,
                vertical: AppSpacing.xs,
              ),
              decoration: BoxDecoration(
                color: AppColors.error,
                borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
              ),
              child: Text(
                '3',
                style: TextStyle(
                  fontSize: AppTypography.xs,
                  fontWeight: AppTypography.bold,
                  color: AppColors.white,
                ),
              ),
            ),
            SizedBox(width: AppSpacing.sm),
            Icon(
              CupertinoIcons.chevron_forward,
              color: fgSecondary,
              size: AppSpacing.iconSmall,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildEmpty() {
    final fgSecondary = AppColorsFunctional.getColor(widget.isDark, ColorType.foregroundSecondary);
    return Container(
      margin: EdgeInsets.symmetric(horizontal: AppSpacing.md),
      padding: EdgeInsets.all(AppSpacing.lg),
      child: Center(
        child: Text(
          UITextConstants.circleNoChatEnabled,
          style: TextStyle(
            fontSize: AppTypography.base,
            color: fgSecondary,
          ),
        ),
      ),
    );
  }

  Widget _buildErrorCard() {
    final fgSecondary = AppColorsFunctional.getColor(widget.isDark, ColorType.foregroundSecondary);
    return Container(
      padding: EdgeInsets.all(AppSpacing.lg),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.error_outline, color: AppColors.error, size: AppSpacing.iconLarge),
          SizedBox(height: AppSpacing.sm),
          Text(
            UITextConstants.loadFailed,
            style: TextStyle(color: fgSecondary, fontSize: AppTypography.base),
          ),
          SizedBox(height: AppSpacing.sm),
          CupertinoButton(
            onPressed: _retry,
            child: Text(
              UITextConstants.retry,
              style: TextStyle(
                color: AppColors.primaryColor,
                fontSize: AppTypography.base,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
