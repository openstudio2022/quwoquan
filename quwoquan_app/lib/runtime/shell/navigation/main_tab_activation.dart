import 'package:flutter_riverpod/flutter_riverpod.dart';

/// 视频书（featured）已退出底栏，成为壳内存态目的地；首页顶部固定入口通过
/// 递增该信号请求主壳切换到视频书。主壳消费后自行 `_selectMainTab(featured)`，
/// 页面不得直接持有壳内部状态。
final featuredImmersiveActivationProvider =
    NotifierProvider<FeaturedImmersiveActivationNotifier, int>(
      FeaturedImmersiveActivationNotifier.new,
    );

class FeaturedImmersiveActivationNotifier extends Notifier<int> {
  @override
  int build() => 0;

  void request() => state = state + 1;
}
