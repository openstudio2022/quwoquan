import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import 'package:quwoquan_app/core/quwoquan_core.dart';

class CreatePage extends ConsumerWidget {
  final String initialTab;

  const CreatePage({
    super.key,
    this.initialTab = 'moments',
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isDark = ref.watch(isDarkProvider);
    
    return Scaffold(
      backgroundColor: isDark 
        ? AppColors.dark.backgroundPrimary
        : AppColors.light.backgroundPrimary,
      appBar: AppBar(
        title: const Text('创建'),
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
              Icons.add_circle,
              size: 64.sp,
              color: isDark ? AppColors.dark.foregroundSecondary : AppColors.light.foregroundSecondary,
            ),
            SizedBox(height: 16.h),
            Text(
              '创建页面',
              style: TextStyle(
                fontSize: 24.sp,
                fontWeight: FontWeight.bold,
                color: isDark ? AppColors.dark.foregroundPrimary : AppColors.light.foregroundPrimary,
              ),
            ),
            SizedBox(height: 8.h),
            Text(
              '创建功能开发中...',
              style: TextStyle(
                fontSize: 16.sp,
                color: isDark ? AppColors.dark.foregroundSecondary : AppColors.light.foregroundSecondary,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
