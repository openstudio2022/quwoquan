import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

class AppTheme {
  // 颜色定义
  static const Color primaryColor = Color(0xFF6366F1);
  static const Color secondaryColor = Color(0xFF8B5CF6);
  static const Color accentColor = Color(0xFF06B6D4);
  static const Color errorColor = Color(0xFFEF4444);
  static const Color warningColor = Color(0xFFF59E0B);
  static const Color successColor = Color(0xFF10B981);
  
  // 中性色
  static const Color backgroundColor = Color(0xFFF8FAFC);
  static const Color surfaceColor = Color(0xFFFFFFFF);
  static const Color cardColor = Color(0xFFFFFFFF);
  
  // 文本颜色
  static const Color textPrimary = Color(0xFF1E293B);
  static const Color textSecondary = Color(0xFF64748B);
  static const Color textTertiary = Color(0xFF94A3B8);
  
  // 边框颜色
  static const Color borderColor = Color(0xFFE2E8F0);
  static const Color dividerColor = Color(0xFFF1F5F9);
  
  // 阴影
  static const List<BoxShadow> cardShadow = [
    BoxShadow(
      color: Color(0x0A000000),
      blurRadius: 8,
      offset: Offset(0, 2),
    ),
  ];
  
  static const List<BoxShadow> elevatedShadow = [
    BoxShadow(
      color: Color(0x14000000),
      blurRadius: 12,
      offset: Offset(0, 4),
    ),
  ];

  // 主题数据
  static ThemeData get lightTheme {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.light,
      primarySwatch: Colors.indigo,
      primaryColor: primaryColor,
      scaffoldBackgroundColor: backgroundColor,
      
      // 颜色方案
      colorScheme: const ColorScheme.light(
        primary: primaryColor,
        secondary: secondaryColor,
        tertiary: accentColor,
        error: errorColor,
        background: backgroundColor,
        surface: surfaceColor,
        onPrimary: Colors.white,
        onSecondary: Colors.white,
        onTertiary: Colors.white,
        onError: Colors.white,
        onBackground: textPrimary,
        onSurface: textPrimary,
      ),
      
      // 应用栏主题
      appBarTheme: AppBarTheme(
        backgroundColor: surfaceColor,
        foregroundColor: textPrimary,
        elevation: 0,
        centerTitle: true,
        titleTextStyle: TextStyle(
          color: textPrimary,
          fontSize: 18.sp,
          fontWeight: FontWeight.w600,
          fontFamily: 'PingFang',
        ),
      ),
      
      // 卡片主题
      cardTheme: CardTheme(
        color: cardColor,
        elevation: 0,
        shadowColor: Colors.transparent,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12.r),
          side: const BorderSide(color: borderColor),
        ),
      ),
      
      // 按钮主题
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: primaryColor,
          foregroundColor: Colors.white,
          elevation: 0,
          shadowColor: Colors.transparent,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(8.r),
          ),
          padding: EdgeInsets.symmetric(
            horizontal: 24.w,
            vertical: 12.h,
          ),
          textStyle: TextStyle(
            fontSize: 16.sp,
            fontWeight: FontWeight.w500,
            fontFamily: 'PingFang',
          ),
        ),
      ),
      
      // 文本按钮主题
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: primaryColor,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(8.r),
          ),
          padding: EdgeInsets.symmetric(
            horizontal: 16.w,
            vertical: 8.h,
          ),
          textStyle: TextStyle(
            fontSize: 16.sp,
            fontWeight: FontWeight.w500,
            fontFamily: 'PingFang',
          ),
        ),
      ),
      
      // 输入框主题
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: surfaceColor,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8.r),
          borderSide: const BorderSide(color: borderColor),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8.r),
          borderSide: const BorderSide(color: borderColor),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8.r),
          borderSide: const BorderSide(color: primaryColor, width: 2),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8.r),
          borderSide: const BorderSide(color: errorColor),
        ),
        contentPadding: EdgeInsets.symmetric(
          horizontal: 16.w,
          vertical: 12.h,
        ),
        hintStyle: TextStyle(
          color: textTertiary,
          fontSize: 16.sp,
          fontFamily: 'PingFang',
        ),
        labelStyle: TextStyle(
          color: textSecondary,
          fontSize: 16.sp,
          fontFamily: 'PingFang',
        ),
      ),
      
      // 文本主题
      textTheme: TextTheme(
        displayLarge: TextStyle(
          color: textPrimary,
          fontSize: 32.sp,
          fontWeight: FontWeight.bold,
          fontFamily: 'PingFang',
        ),
        displayMedium: TextStyle(
          color: textPrimary,
          fontSize: 28.sp,
          fontWeight: FontWeight.bold,
          fontFamily: 'PingFang',
        ),
        displaySmall: TextStyle(
          color: textPrimary,
          fontSize: 24.sp,
          fontWeight: FontWeight.w600,
          fontFamily: 'PingFang',
        ),
        headlineLarge: TextStyle(
          color: textPrimary,
          fontSize: 22.sp,
          fontWeight: FontWeight.w600,
          fontFamily: 'PingFang',
        ),
        headlineMedium: TextStyle(
          color: textPrimary,
          fontSize: 20.sp,
          fontWeight: FontWeight.w600,
          fontFamily: 'PingFang',
        ),
        headlineSmall: TextStyle(
          color: textPrimary,
          fontSize: 18.sp,
          fontWeight: FontWeight.w600,
          fontFamily: 'PingFang',
        ),
        titleLarge: TextStyle(
          color: textPrimary,
          fontSize: 16.sp,
          fontWeight: FontWeight.w600,
          fontFamily: 'PingFang',
        ),
        titleMedium: TextStyle(
          color: textPrimary,
          fontSize: 14.sp,
          fontWeight: FontWeight.w500,
          fontFamily: 'PingFang',
        ),
        titleSmall: TextStyle(
          color: textPrimary,
          fontSize: 12.sp,
          fontWeight: FontWeight.w500,
          fontFamily: 'PingFang',
        ),
        bodyLarge: TextStyle(
          color: textPrimary,
          fontSize: 16.sp,
          fontWeight: FontWeight.normal,
          fontFamily: 'PingFang',
        ),
        bodyMedium: TextStyle(
          color: textPrimary,
          fontSize: 14.sp,
          fontWeight: FontWeight.normal,
          fontFamily: 'PingFang',
        ),
        bodySmall: TextStyle(
          color: textSecondary,
          fontSize: 12.sp,
          fontWeight: FontWeight.normal,
          fontFamily: 'PingFang',
        ),
        labelLarge: TextStyle(
          color: textPrimary,
          fontSize: 14.sp,
          fontWeight: FontWeight.w500,
          fontFamily: 'PingFang',
        ),
        labelMedium: TextStyle(
          color: textSecondary,
          fontSize: 12.sp,
          fontWeight: FontWeight.w500,
          fontFamily: 'PingFang',
        ),
        labelSmall: TextStyle(
          color: textTertiary,
          fontSize: 10.sp,
          fontWeight: FontWeight.w500,
          fontFamily: 'PingFang',
        ),
      ),
      
      // 底部导航栏主题
      bottomNavigationBarTheme: BottomNavigationBarThemeData(
        backgroundColor: surfaceColor,
        selectedItemColor: primaryColor,
        unselectedItemColor: textTertiary,
        type: BottomNavigationBarType.fixed,
        elevation: 8,
        selectedLabelStyle: TextStyle(
          fontSize: 12.sp,
          fontWeight: FontWeight.w500,
          fontFamily: 'PingFang',
        ),
        unselectedLabelStyle: TextStyle(
          fontSize: 12.sp,
          fontWeight: FontWeight.normal,
          fontFamily: 'PingFang',
        ),
      ),
      
      // 分割线主题
      dividerTheme: const DividerThemeData(
        color: dividerColor,
        thickness: 1,
        space: 1,
      ),
    );
  }
  
  // 深色主题（可选）
  static ThemeData get darkTheme {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      // 深色主题配置...
    );
  }
}

