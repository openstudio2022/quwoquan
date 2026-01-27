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
      height: 105.h,
      padding: EdgeInsets.symmetric(vertical: 8.h),
      child: ListView.builder(
        scrollDirection: Axis.horizontal,
        padding: EdgeInsets.symmetric(horizontal: 16.w),
        itemCount: 8, // 模拟8个故事
        itemBuilder: (context, index) {
          return _buildStoryItem(context, index, isDark);
        },
      ),
    );
  }

  Widget _buildStoryItem(BuildContext context, int index, bool isDark) {
    final isAddButton = index == 0;
    final avatarSize = 60.r;
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
        width: 80.w,
        margin: EdgeInsets.only(right: 8.w),
        child: Column(
          mainAxisSize: MainAxisSize.min,
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
                            AppColors.functionalSuccess,
                            AppColors.functionalWarning,
                          ],
                          begin: Alignment.topLeft,
                          end: Alignment.bottomRight,
                        ),
                ),
                child: Container(
                  margin: EdgeInsets.all(borderWidth),
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: isDark ? AppColors.dark.backgroundPrimary : AppColors.light.backgroundPrimary,
                  ),
                  child: Center(
                    child: isAddButton
                        ? Icon(
                            Icons.add,
                            color: isDark ? AppColors.dark.foregroundSecondary : AppColors.light.foregroundSecondary,
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
                      color: AppColors.functionalSuccess,
                      border: Border.all(
                        color: isDark ? AppColors.dark.backgroundPrimary : AppColors.light.backgroundPrimary,
                        width: 2,
                      ),
                    ),
                  ),
                ),
            ],
          ),
          
          SizedBox(height: 4.h),
          
          // 用户名
          Text(
            isAddButton ? '我的' : '用户$index',
            style: TextStyle(
              fontSize: 12.sp,
              color: isDark ? AppColors.dark.foregroundPrimary : AppColors.light.foregroundPrimary,
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
