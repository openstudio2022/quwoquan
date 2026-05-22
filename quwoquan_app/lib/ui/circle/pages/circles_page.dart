import 'package:quwoquan_app/ui/circle/pages/home_circles_hub_page.dart';

/// 圈子主入口。
///
/// 统一走更完整的 hub 版布局，避免目录页与 hub 页并存导致的双体验分叉。
class CirclesPage extends CirclesHubPage {
  const CirclesPage({super.key, super.onPrimaryOverflowSwipe});
}
