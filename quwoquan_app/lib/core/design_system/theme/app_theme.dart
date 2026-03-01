import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// Source Han Serif CN 等效字体（思源宋体简体）
const String _kDefaultFontFamily = 'Noto Serif SC';

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
      textTheme: GoogleFonts.notoSerifScTextTheme(),
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
      textTheme: GoogleFonts.notoSerifScTextTheme(
        ThemeData.dark().textTheme,
      ),
    );
  }
}

