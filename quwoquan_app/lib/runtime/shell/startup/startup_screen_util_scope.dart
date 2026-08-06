import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

/// 主壳启用后再包 ScreenUtilInit，欢迎首帧不触发 ScreenUtil 初始化。
class StartupScreenUtilScope extends StatelessWidget {
  const StartupScreenUtilScope({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return ScreenUtilInit(
      designSize: const Size(375, 812),
      minTextAdapt: true,
      splitScreenMode: true,
      child: child,
    );
  }
}
