import 'package:flutter/cupertino.dart';

enum UiErrorAppearanceMode { inherit, light, dark }

extension UiErrorAppearanceModeX on UiErrorAppearanceMode {
  String? get routeValue {
    return switch (this) {
      UiErrorAppearanceMode.inherit => null,
      UiErrorAppearanceMode.light => 'light',
      UiErrorAppearanceMode.dark => 'dark',
    };
  }

  Brightness? get brightness {
    return switch (this) {
      UiErrorAppearanceMode.inherit => null,
      UiErrorAppearanceMode.light => Brightness.light,
      UiErrorAppearanceMode.dark => Brightness.dark,
    };
  }
}

UiErrorAppearanceMode uiErrorAppearanceModeFromBrightness(
  Brightness brightness,
) {
  return brightness == Brightness.dark
      ? UiErrorAppearanceMode.dark
      : UiErrorAppearanceMode.light;
}

UiErrorAppearanceMode uiErrorAppearanceModeFromRouteValue(String? raw) {
  return switch ((raw ?? '').trim()) {
    'light' => UiErrorAppearanceMode.light,
    'dark' => UiErrorAppearanceMode.dark,
    _ => UiErrorAppearanceMode.inherit,
  };
}

String? uiErrorAppearanceRouteValueFor(BuildContext context) {
  return uiErrorAppearanceModeFromBrightness(
    CupertinoTheme.of(context).brightness ?? Brightness.light,
  ).routeValue;
}
