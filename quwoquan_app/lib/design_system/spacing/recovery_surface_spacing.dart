/// 不可恢复异常页的稳定布局与状态切换时序 token。
///
/// 固定内容槽可避免版本检查、容器重建和失败终态切换时发生纵向跳动。
abstract final class RecoverySurfaceSpacing {
  static const double contentMaxWidth = 280.0;
  static const double horizontalInset = 24.0;
  static const double titleSlotHeight = 44.0;
  static const double subtitleSlotHeight = 52.0;
  static const double actionSlotHeight = 108.0;
  static const double titleSubtitleGap = 16.0;
  static const double subtitleActionGap = 28.0;
  static const double buttonGap = 12.0;
  static const double visualCenterAlignment = 0.1;
  static const Duration oldContentFadeDuration = Duration(milliseconds: 80);
  static const Duration newContentFadeDuration = Duration(milliseconds: 120);
}
