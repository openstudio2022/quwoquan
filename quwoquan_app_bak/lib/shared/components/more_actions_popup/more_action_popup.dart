import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/shared/components/more_actions_popup/configs/media_post_config.dart';

/// 更多操作弹窗组件
class MoreActionPopup extends StatelessWidget {
  final dynamic config;
  
  const MoreActionPopup({
    super.key,
    required this.config,
  });
  
  /// 显示更多操作弹窗
  static Future<void> show({
    required BuildContext context,
    required dynamic config,
    bool showDragHandle = true,
    bool isScrollControlled = true,
  }) async {
    if (config is MediaPostMoreActionConfig) {
      await showModalBottomSheet(
        context: context,
        backgroundColor: Colors.transparent,
        isScrollControlled: isScrollControlled,
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
  
  const _MediaPostMoreActionSheet({
    required this.config,
  });
  
  @override
  ConsumerState<_MediaPostMoreActionSheet> createState() => _MediaPostMoreActionSheetState();
}

class _MediaPostMoreActionSheetState extends ConsumerState<_MediaPostMoreActionSheet> {
  List<_ScrollAction> _buildScrollActions(bool isDark) {
    return [
      _ScrollAction(
        id: 'reward',
        icon: Icons.card_giftcard,
        label: AppStrings.reward,
        onTap: widget.config.onReward,
      ),
      _ScrollAction(
        id: 'save',
        icon: Icons.download, // 使用 download 而不是 bookmark_outline
        label: AppStrings.save,
        onTap: widget.config.onSave,
      ),
      _ScrollAction(
        id: 'message',
        icon: Icons.message_outlined,
        label: AppStrings.message,
        onTap: widget.config.onMessage,
      ),
      _ScrollAction(
        id: 'copyLink',
        icon: Icons.link,
        label: AppStrings.copyLink,
        onTap: widget.config.onCopyLink,
      ),
      _ScrollAction(
        id: 'viewOriginal',
        icon: Icons.image_outlined,
        label: AppStrings.viewOriginal,
        onTap: widget.config.onViewOriginal,
      ),
      _ScrollAction(
        id: 'fontSettings',
        icon: Icons.font_download,
        label: AppStrings.fontSettings,
        onTap: widget.config.onFontSettings,
      ),
      _ScrollAction(
        id: 'darkMode',
        icon: isDark ? Icons.light_mode : Icons.dark_mode,
        label: isDark ? AppStrings.lightMode : AppStrings.darkMode,
        onTap: widget.config.onThemeToggle,
      ),
      _ScrollAction(
        id: 'feedback',
        icon: Icons.edit, // 使用 edit 而不是 feedback
        label: AppStrings.feedback,
        onTap: widget.config.onFeedback,
      ),
    ];
  }
  
  List<_BottomAction> _buildBottomActions() {
    return [
      _BottomAction(
        id: 'notInterested',
        icon: Icons.visibility_off, // 使用 visibility_off 而不是 block
        label: AppStrings.notInterested,
        description: AppStrings.notInterestedDescription,
        onTap: widget.config.onNotInterested,
      ),
      _BottomAction(
        id: 'blockUser',
        icon: Icons.person_off,
        label: AppStrings.blockUser,
        description: AppStrings.blockUserDescription,
        onTap: widget.config.onBlockUser,
      ),
      _BottomAction(
        id: 'blockWords',
        icon: Icons.filter_list, // 添加屏蔽词图标
        label: AppStrings.blockWords,
        description: AppStrings.blockWordsDescription,
        onTap: null, // 暂时没有回调
      ),
      _BottomAction(
        id: 'report',
        icon: Icons.flag,
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
    
    return Container(
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
        borderRadius: BorderRadius.only(
          topLeft: Radius.circular(20.r),
          topRight: Radius.circular(20.r),
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // 拖拽指示器
          Container(
            width: 40.w,
            height: 4.h,
            margin: EdgeInsets.only(top: 12.h, bottom: 16.h),
            decoration: BoxDecoration(
              color: AppColorsFunctional.getColor(isDark, ColorType.foregroundTertiary),
              borderRadius: BorderRadius.circular(2.r),
            ),
          ),
          
          // 标题和关闭按钮
          Padding(
            padding: EdgeInsets.symmetric(horizontal: AppSpacing.md.w),
            child: Row(
              children: [
                Expanded(
                  child: Center(
                    child: Text(
                      AppStrings.moreActionsTitle,
                      style: TextStyle(
                        fontSize: 16.sp,
                        fontWeight: FontWeight.normal,
                        color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
                      ),
                    ),
                  ),
                ),
                IconButton(
                  icon: Icon(
                    Icons.close,
                    size: 20.sp,
                    color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
                  ),
                  onPressed: () => Navigator.pop(context),
                  padding: EdgeInsets.zero,
                  constraints: BoxConstraints(),
                ),
              ],
            ),
          ),
          
          SizedBox(height: 24.h),
          
          // 滚动行区域
          if (scrollActions.isNotEmpty) ...[
            SizedBox(
              height: 100.h, // 圆形按钮高度 + 文字高度 + 间距
              child: ListView.builder(
                scrollDirection: Axis.horizontal,
                padding: EdgeInsets.symmetric(horizontal: AppSpacing.md.w),
                itemCount: scrollActions.length,
                itemBuilder: (context, index) {
                  final action = scrollActions[index];
                  return Container(
                    width: 80.w,
                    margin: EdgeInsets.only(right: index < scrollActions.length - 1 ? AppSpacing.xs.w : 0),
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
                            width: 56.w, // avatar-xlarge: 56px
                            height: 56.w,
                            decoration: BoxDecoration(
                              color: AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary),
                              shape: BoxShape.circle,
                            ),
                            child: Icon(
                              action.icon,
                              size: 24.sp, // icon-pure-medium: 24px
                              color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
                            ),
                          ),
                        ),
                        SizedBox(height: 8.h),
                        // 文字标签
                        Text(
                          action.label,
                          style: TextStyle(
                            fontSize: 12.sp,
                            color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
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
            SizedBox(height: 24.h),
          ],
          
          // 分隔线
          if (scrollActions.isNotEmpty && bottomActions.isNotEmpty) ...[
            Divider(
              height: 1,
              thickness: 1,
              color: AppColorsFunctional.getColor(isDark, ColorType.foregroundTertiary).withValues(alpha: 0.3),
              indent: AppSpacing.md.w,
              endIndent: AppSpacing.md.w,
            ),
            SizedBox(height: 16.h),
          ],
          
          // 底部操作项区域
          if (bottomActions.isNotEmpty) ...[
            Container(
              margin: EdgeInsets.symmetric(horizontal: AppSpacing.md.w),
              decoration: BoxDecoration(
                color: AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary).withValues(alpha: 0.3),
                borderRadius: BorderRadius.circular(12.r),
              ),
              child: Column(
                children: bottomActions.asMap().entries.map((entry) {
                  final index = entry.key;
                  final action = entry.value;
                  return Column(
                    children: [
                      ListTile(
                        contentPadding: EdgeInsets.symmetric(
                          horizontal: AppSpacing.md.w,
                          vertical: AppSpacing.sm.h,
                        ),
                        leading: Icon(
                          action.icon,
                          size: 20.sp, // h-5 w-5: 20px
                          color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
                        ),
                        title: Text(
                          action.label,
                          style: TextStyle(
                            fontSize: 16.sp,
                            fontWeight: FontWeight.normal,
                            color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
                          ),
                        ),
                        subtitle: action.description != null
                            ? Text(
                                action.description!,
                                style: TextStyle(
                                  fontSize: 14.sp,
                                  color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
                                ),
                              )
                            : null,
                        trailing: null,
                        onTap: () {
                          Navigator.pop(context);
                          action.onTap?.call();
                        },
                      ),
                      // 分隔线 (除了最后一个选项)
                      if (index < bottomActions.length - 1)
                        Divider(
                          height: 1,
                          thickness: 1,
                          color: AppColorsFunctional.getColor(isDark, ColorType.foregroundTertiary).withValues(alpha: 0.4),
                          indent: AppSpacing.md.w,
                          endIndent: AppSpacing.md.w,
                        ),
                    ],
                  );
                }).toList(),
              ),
            ),
            SizedBox(height: 24.h),
          ],
        ],
      ),
    );
  }
}
