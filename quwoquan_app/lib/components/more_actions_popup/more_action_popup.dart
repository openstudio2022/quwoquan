import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/components/more_actions_popup/configs/media_post_config.dart';

/// 更多操作弹窗组件
class MoreActionPopup extends StatelessWidget {
  final dynamic config;

  const MoreActionPopup({super.key, required this.config});

  /// 显示更多操作弹窗
  static Future<void> show({
    required BuildContext context,
    required dynamic config,
    bool showDragHandle = true,
    bool isScrollControlled = true,
  }) async {
    if (config is MediaPostMoreActionConfig) {
      await showCupertinoModalPopup(
        context: context,
        builder: (context) => _MediaPostMoreActionSheet(config: config),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(); // Stub
  }
}

/// 滚动行操作项
class _ScrollAction {
  final String id;
  final IconData icon;
  final String label;
  final VoidCallback? onTap;

  const _ScrollAction({
    required this.id,
    required this.icon,
    required this.label,
    this.onTap,
  });
}

/// 底部操作项
class _BottomAction {
  final String id;
  final IconData icon;
  final String label;
  final String? description;
  final VoidCallback? onTap;

  const _BottomAction({
    required this.id,
    required this.icon,
    required this.label,
    this.description,
    this.onTap,
  });
}

/// 媒体帖子更多操作底部弹窗
class _MediaPostMoreActionSheet extends ConsumerStatefulWidget {
  final MediaPostMoreActionConfig config;

  const _MediaPostMoreActionSheet({required this.config});

  @override
  ConsumerState<_MediaPostMoreActionSheet> createState() =>
      _MediaPostMoreActionSheetState();
}

class _MediaPostMoreActionSheetState
    extends ConsumerState<_MediaPostMoreActionSheet> {
  List<_ScrollAction> _buildScrollActions(bool isDark) {
    return [
      _ScrollAction(
        id: 'reward',
        icon: CupertinoIcons.gift,
        label: AppStrings.reward,
        onTap: widget.config.onReward,
      ),
      _ScrollAction(
        id: 'save',
        icon: CupertinoIcons.arrow_down_to_line,
        label: AppStrings.save,
        onTap: widget.config.onSave,
      ),
      _ScrollAction(
        id: 'message',
        icon: CupertinoIcons.chat_bubble,
        label: AppStrings.message,
        onTap: widget.config.onMessage,
      ),
      _ScrollAction(
        id: 'copyLink',
        icon: CupertinoIcons.link,
        label: AppStrings.copyLink,
        onTap: widget.config.onCopyLink,
      ),
      _ScrollAction(
        id: 'share',
        icon: CupertinoIcons.share,
        label: UITextConstants.share,
        onTap: widget.config.onShare,
      ),
      _ScrollAction(
        id: 'viewOriginal',
        icon: CupertinoIcons.photo,
        label: AppStrings.viewOriginal,
        onTap: widget.config.onViewOriginal,
      ),
      _ScrollAction(
        id: 'fontSettings',
        icon: CupertinoIcons.textformat,
        label: AppStrings.fontSettings,
        onTap: widget.config.onFontSettings,
      ),
      _ScrollAction(
        id: 'darkMode',
        icon: isDark ? CupertinoIcons.sun_max : CupertinoIcons.moon,
        label: isDark ? AppStrings.lightMode : AppStrings.darkMode,
        onTap: widget.config.onThemeToggle,
      ),
      _ScrollAction(
        id: 'feedback',
        icon: CupertinoIcons.pencil,
        label: AppStrings.feedback,
        onTap: widget.config.onFeedback,
      ),
    ];
  }

  List<_BottomAction> _buildBottomActions() {
    return [
      _BottomAction(
        id: 'notInterested',
        icon: CupertinoIcons.eye_slash,
        label: AppStrings.notInterested,
        description: AppStrings.notInterestedDescription,
        onTap: widget.config.onNotInterested,
      ),
      _BottomAction(
        id: 'blockUser',
        icon: CupertinoIcons.person_badge_minus,
        label: AppStrings.blockUser,
        description: AppStrings.blockUserDescription,
        onTap: widget.config.onBlockUser,
      ),
      _BottomAction(
        id: 'blockWords',
        icon: CupertinoIcons.slider_horizontal_3,
        label: AppStrings.blockWords,
        description: AppStrings.blockWordsDescription,
        onTap: widget.config.onBlockWords,
      ),
      _BottomAction(
        id: 'report',
        icon: CupertinoIcons.flag,
        label: AppStrings.report,
        description: AppStrings.reportDescription,
        onTap: widget.config.onReport,
      ),
    ];
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final scrollActions = _buildScrollActions(isDark);
    final bottomActions = _buildBottomActions();

    return Material(
      type: MaterialType.transparency,
      child: Container(
        decoration: BoxDecoration(
          color: AppColorsFunctional.getColor(
            isDark,
            ColorType.backgroundPrimary,
          ),
          borderRadius: BorderRadius.only(
            topLeft: Radius.circular(20.r),
            topRight: Radius.circular(20.r),
          ),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // 标题和关闭按钮
            Padding(
              padding: EdgeInsets.only(
                left: AppSpacing.md.w,
                right: AppSpacing.md.w,
                top: AppSpacing.md.h,
              ),
              child: Row(
                children: [
                  Expanded(
                    child: Center(
                      child: Text(
                        AppStrings.moreActionsTitle,
                        style: TextStyle(
                          fontSize: AppTypography.lg.sp,
                          fontWeight: FontWeight.normal,
                          color: AppColorsFunctional.getColor(
                            isDark,
                            ColorType.foregroundPrimary,
                          ),
                        ),
                      ),
                    ),
                  ),
                  CupertinoButton(
                    padding: EdgeInsets.zero,
                    onPressed: () => Navigator.pop(context), minimumSize: Size(AppSpacing.minInteractiveSize, AppSpacing.minInteractiveSize),
                    child: Icon(
                      CupertinoIcons.xmark,
                      size: AppSpacing.twenty.sp,
                      color: AppColorsFunctional.getColor(
                        isDark,
                        ColorType.foregroundPrimary,
                      ),
                    ),
                  ),
                ],
              ),
            ),
            SizedBox(
              height: AppSpacing.lg.h,
            ),

            // 滚动行区域
            if (scrollActions.isNotEmpty) ...[
              SizedBox(
                height: AppSpacing.oneHundred.h,
                child: ListView.builder(
                  scrollDirection: Axis.horizontal,
                  padding: EdgeInsets.symmetric(horizontal: AppSpacing.md.w),
                  itemCount: scrollActions.length,
                  itemBuilder: (context, index) {
                    final action = scrollActions[index];
                    return Container(
                      width: AppSpacing.storyHeight.w,
                      margin: EdgeInsets.only(
                        right: index < scrollActions.length - 1
                            ? AppSpacing.xs.w
                            : 0,
                      ),
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          // 圆形按钮
                          GestureDetector(
                            onTap: () {
                              Navigator.pop(context);
                              action.onTap?.call();
                            },
                            child: Container(
                              width: AppSpacing.avatarUserLg.w,
                              height: AppSpacing.avatarUserLg.w,
                              decoration: BoxDecoration(
                                color: AppColorsFunctional.getColor(
                                  isDark,
                                  ColorType.backgroundSecondary,
                                ),
                                shape: BoxShape.circle,
                              ),
                              child: Icon(
                                action.icon,
                                size: AppSpacing.iconMedium.sp,
                                color: AppColorsFunctional.getColor(
                                  isDark,
                                  ColorType.foregroundSecondary,
                                ),
                              ),
                            ),
                          ),
                          SizedBox(height: AppSpacing.sm.h),
                          // 文字标签
                          Text(
                            action.label,
                            style: TextStyle(
                              fontSize: AppTypography.sm.sp,
                              color: AppColorsFunctional.getColor(
                                isDark,
                                ColorType.foregroundPrimary,
                              ),
                            ),
                            textAlign: TextAlign.center,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ],
                      ),
                    );
                  },
                ),
              ),
              SizedBox(height: AppSpacing.lg.h),
            ],

            // 分隔线
            if (scrollActions.isNotEmpty && bottomActions.isNotEmpty) ...[
              Container(
                height: AppSpacing.hairline,
                color: AppColorsFunctional.getColor(
                  isDark,
                  ColorType.foregroundTertiary,
                ).withValues(alpha: 0.3),
                margin: EdgeInsets.symmetric(horizontal: AppSpacing.md.w),
              ),
              SizedBox(height: AppSpacing.md.h),
            ],

            // 底部操作项区域
            if (bottomActions.isNotEmpty) ...[
              Container(
                margin: EdgeInsets.symmetric(horizontal: AppSpacing.md.w),
                decoration: BoxDecoration(
                  color: AppColorsFunctional.getColor(
                    isDark,
                    ColorType.backgroundSecondary,
                  ).withValues(alpha: 0.3),
                  borderRadius: BorderRadius.circular(
                    AppSpacing.largeBorderRadius.r,
                  ),
                ),
                child: Column(
                  children: bottomActions.asMap().entries.map((entry) {
                    final index = entry.key;
                    final action = entry.value;
                    return Column(
                      children: [
                        GestureDetector(
                          onTap: () {
                            Navigator.pop(context);
                            action.onTap?.call();
                          },
                          child: Padding(
                            padding: EdgeInsets.symmetric(
                              horizontal: AppSpacing.md.w,
                              vertical: AppSpacing.md.h,
                            ),
                            child: Row(
                              children: [
                                Icon(
                                  action.icon,
                                  size: AppSpacing.twenty.sp,
                                  color: AppColorsFunctional.getColor(
                                    isDark,
                                    ColorType.foregroundPrimary,
                                  ),
                                ),
                                SizedBox(width: AppSpacing.sm.w),
                                Expanded(
                                  child: Text(
                                    action.label,
                                    style: TextStyle(
                                      fontSize: AppTypography.lg.sp,
                                      fontWeight: FontWeight.normal,
                                      color: AppColorsFunctional.getColor(
                                        isDark,
                                        ColorType.foregroundPrimary,
                                      ),
                                    ),
                                  ),
                                ),
                                if (action.description != null)
                                  Text(
                                    action.description!,
                                    style: TextStyle(
                                      fontSize: AppTypography.base.sp,
                                      color: AppColorsFunctional.getColor(
                                        isDark,
                                        ColorType.foregroundSecondary,
                                      ),
                                    ),
                                    textAlign: TextAlign.right,
                                  ),
                              ],
                            ),
                          ),
                        ),
                        // 分隔线 (除了最后一个选项)
                        if (index < bottomActions.length - 1)
                          Container(
                            height: AppSpacing.hairline,
                            color: AppColorsFunctional.getColor(
                              isDark,
                              ColorType.foregroundTertiary,
                            ).withValues(alpha: 0.2),
                            margin: EdgeInsets.symmetric(
                              horizontal: AppSpacing.md.w,
                            ),
                          ),
                      ],
                    );
                  }).toList(),
                ),
              ),
              SizedBox(height: AppSpacing.lg.h),
            ],
          ],
        ),
      ),
    );
  }
}
