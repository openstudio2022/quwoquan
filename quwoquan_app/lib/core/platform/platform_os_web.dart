/// Web has no `dart:io`; the native OS name is always reported as `web`.
///
/// Consumed only by [platform_target.dart]; the real platform discrimination
/// on web happens via `kIsWeb` before this value is ever used.
String readNativeOperatingSystem() => 'web';
