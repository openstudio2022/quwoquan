import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import 'package:quwoquan_app/core/quwoquan_core.dart';

class ChatPage extends ConsumerWidget {
  final String initialTab;

  const ChatPage({
    super.key,
    this.initialTab = 'messages',
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isDark = ref.watch(isDarkProvider);
    
    return Scaffold(
      backgroundColor: isDark 
        ? AppColors.dark.backgroundPrimary
        : AppColors.light.backgroundPrimary,
      appBar: AppBar(
        title: const Text('聊天'),
        backgroundColor: isDark 
          ? AppColors.dark.backgroundSecondary
          : AppColors.light.backgroundSecondary,
        foregroundColor: isDark 
          ? AppColors.dark.foregroundPrimary
          : AppColors.light.foregroundPrimary,
      ),
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.chat,
              size: 64.sp,
              color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
            ),
            SizedBox(height: 16.h),
            Text(
              '聊天页面',
              style: TextStyle(
                fontSize: 24.sp,
                fontWeight: FontWeight.bold,
                color: isDark ? AppColors.dark.foregroundPrimary : AppColors.light.foregroundPrimary,
              ),
            ),
            SizedBox(height: 8.h),
            Text(
              '聊天功能开发中...',
              style: TextStyle(
                fontSize: 16.sp,
                color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
