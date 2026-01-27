import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import 'package:quwoquan_app/core/quwoquan_core.dart';

class SearchPage extends ConsumerWidget {
  final String? initialQuery;
  final String? sourcePage;

  const SearchPage({
    super.key,
    this.initialQuery,
    this.sourcePage,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isDark = ref.watch(isDarkProvider);
    
    return Scaffold(
      backgroundColor: isDark 
        ? AppColors.dark.backgroundPrimary
        : AppColors.light.backgroundPrimary,
      appBar: AppBar(
        title: const Text('搜索'),
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
              Icons.search,
              size: 64.sp,
              color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary),
            ),
            SizedBox(height: 16.h),
            Text(
              '搜索页面',
              style: TextStyle(
                fontSize: 24.sp,
                fontWeight: FontWeight.bold,
                color: isDark ? AppColors.dark.foregroundPrimary : AppColors.light.foregroundPrimary,
              ),
            ),
            SizedBox(height: 8.h),
            Text(
              '搜索功能开发中...',
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
