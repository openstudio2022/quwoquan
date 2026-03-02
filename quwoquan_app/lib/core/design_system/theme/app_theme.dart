import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// 全局无衬线黑体（思源黑体简体）
const String _kDefaultFontFamily = 'Noto Sans SC';

class AppTheme {
  static ThemeData get lightTheme {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.light,
      colorScheme: ColorScheme.fromSeed(
        seedColor: Colors.blue,
        brightness: Brightness.light,
      ),
      fontFamily: _kDefaultFontFamily,
      textTheme: GoogleFonts.notoSansScTextTheme(),
    );
  }

  static ThemeData get darkTheme {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      colorScheme: ColorScheme.fromSeed(
        seedColor: Colors.blue,
        brightness: Brightness.dark,
      ),
      fontFamily: _kDefaultFontFamily,
      textTheme: GoogleFonts.notoSansScTextTheme(
        ThemeData.dark().textTheme,
      ),
    );
  }
}

