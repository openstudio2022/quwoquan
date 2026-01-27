import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import 'package:quwoquan_app/core/quwoquan_core.dart';

class SettingsPage extends ConsumerWidget {
  const SettingsPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isDark = ref.watch(isDarkProvider);
    
    return Scaffold(
      backgroundColor: isDark 
        ? AppColors.dark.backgroundPrimary
        : AppColors.light.backgroundPrimary,
      appBar: AppBar(
        title: const Text('设置'),
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
              Icons.settings,
              size: 64.sp,
              color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
            ),
            SizedBox(height: 16.h),
            Text(
              '设置页面',
              style: TextStyle(
                fontSize: 24.sp,
                fontWeight: FontWeight.bold,
                color: AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary),
              ),
            ),
            SizedBox(height: 8.h),
            Text(
              '设置功能开发中...',
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
