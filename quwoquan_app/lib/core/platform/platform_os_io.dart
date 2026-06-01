import 'dart:io' show Platform;

/// Native OS name on platforms that ship `dart:io` (mobile / desktop / ohos).
///
/// Returns values such as `android`, `ios`, `ohos`, `macos`, `windows`,
/// `linux`. Consumed only by [platform_target.dart] for assembly; business
/// code must not import this file directly.
String readNativeOperatingSystem() => Platform.operatingSystem;
