import 'package:flutter/foundation.dart';

import 'package:quwoquan_app/runtime/platform/platform_target.dart';

/// 字体栈需要区分的平台族。
enum AppFontPlatform { apple, web, bundled }

/// 解析字体栈平台族。
///
/// [AppPlatform] 把 macOS 折进 `desktop`，无法单独表达「Apple 系统字体可用」，
/// 因此显式平台缺省时仍需读 [defaultTargetPlatform]；平台判断只允许留在
/// `lib/core/platform/**`，排版层只消费本枚举。
AppFontPlatform resolveAppFontPlatform([AppPlatform? platform]) {
  if (platform != null) {
    return switch (platform) {
      AppPlatform.ios => AppFontPlatform.apple,
      AppPlatform.web => AppFontPlatform.web,
      AppPlatform.android ||
      AppPlatform.ohos ||
      AppPlatform.desktop => AppFontPlatform.bundled,
    };
  }
  if (!kIsWeb &&
      (defaultTargetPlatform == TargetPlatform.iOS ||
          defaultTargetPlatform == TargetPlatform.macOS)) {
    return AppFontPlatform.apple;
  }
  return currentAppPlatform == AppPlatform.web
      ? AppFontPlatform.web
      : AppFontPlatform.bundled;
}
