import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

class StoriesSection extends ConsumerWidget {
  final Function(dynamic) onStoryTap;
  final Function(String) onUserTap;

  const StoriesSection({
    super.key,
    required this.onStoryTap,
    required this.onUserTap,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isDark = ref.watch(isDarkProvider);

    return Container(
      height: AppSpacing.storyHeight.h,
      // 移除垂直间距，与Tab和Post无缝连接
      // 使用与FeedSection一致的次要背景色
      color: AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary), // 使用次要背景色，与PostListSection保持一致
      child: ListView.builder(
        scrollDirection: Axis.horizontal,
        shrinkWrap: true, // 确保ListView可以滚动
        physics: const ClampingScrollPhysics(), // 确保滚动物理效果
        // 占据整个屏幕宽度，内容间距使用更小的语义标签
        padding:
            EdgeInsets.symmetric(horizontal: AppSpacing.contentSpacingMd.w),
        itemCount: 15, // 增加数量确保可以滚动
        itemBuilder: (context, index) {
          return _buildStoryItem(context, index, isDark);
        },
      ),
    );
  }

  Widget _buildStoryItem(BuildContext context, int index, bool isDark) {
    final isAddButton = index == 0;
    final avatarSize = (AppSpacing.avatarSize * 1.5).r;
    final borderWidth = 2.0;

    return GestureDetector(
      onTap: () {
        if (isAddButton) {
          // 处理添加story
        } else {
          onUserTap('用户$index');
        }
      },
      child: Container(
        width: (AppSpacing.avatarSize * 2).w,
        margin: EdgeInsets.only(right: AppSpacing.sm.w),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          mainAxisAlignment: MainAxisAlignment.center, // 确保内容垂直居中，上下间距对称
          children: [
            Stack(
              children: [
                // 头像边框
                Container(
                  width: avatarSize + borderWidth * 2,
                  height: avatarSize + borderWidth * 2,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    gradient: isAddButton
                        ? null
                        : LinearGradient(
                            colors: [
                              AppColors.primaryColor,
                              AppColorsFunctional.functionalSuccess,
                              AppColorsFunctional.functionalWarning,
                            ],
                            begin: Alignment.topLeft,
                            end: Alignment.bottomRight,
                          ),
                  ),
                  child: Container(
                    margin: EdgeInsets.all(borderWidth),
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: isDark
                          ? AppColors.dark.backgroundPrimary
                          : AppColors.light.backgroundPrimary,
                    ),
                    child: Center(
                      child: isAddButton
                          ? Icon(
                              Icons.add,
                              color: isDark
                                  ? AppColors.dark.foregroundSecondary
                                  : AppColors.light.foregroundSecondary,
                              size: 24.sp,
                            )
                          : CircleAvatar(
                              radius: avatarSize / 2,
                              backgroundImage: NetworkImage(
                                'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=150&h=150&fit=crop&crop=face',
                              ),
                            ),
                    ),
                  ),
                ),

                // 在线状态指示器（非添加按钮）
                if (!isAddButton)
                  Positioned(
                    bottom: 2,
                    right: 2,
                    child: Container(
                      width: 16.w,
                      height: 16.h,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: AppColorsFunctional.functionalSuccess,
                        border: Border.all(
                          color: isDark
                              ? AppColors.dark.backgroundPrimary
                              : AppColors.light.backgroundPrimary,
                          width: 2,
                        ),
                      ),
                    ),
                  ),
              ],
            ),

            SizedBox(height: 8.h), // 增加下部间距，与上部对称

            // 用户名
            Text(
              isAddButton ? '我的' : '用户$index',
              style: TextStyle(
                fontSize: 12.sp,
                color: isDark
                    ? AppColors.dark.foregroundPrimary
                    : AppColors.light.foregroundPrimary,
              ),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ],
        ),
      ),
    );
  }
}
