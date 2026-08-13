import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/platform/platform_providers.dart';

/// 欢迎页状态
///
/// 控制是否展示欢迎页。完成欢迎后设为 false，进入主框架。
final welcomeCompletedProvider =
    NotifierProvider<WelcomeCompletedNotifier, bool>(
      WelcomeCompletedNotifier.new,
    );

class WelcomeCompletedNotifier extends Notifier<bool> {
  /// 能力优先（R-XP1）：是否跳过首启欢迎流由 `startupWelcomeFlow` 能力位决定
  /// （Web/桌面直接进内容），业务层不问「是不是 Web」。
  @override
  bool build() =>
      !ref.read(platformCapabilitiesProvider).startupWelcomeFlow;

  void setCompleted(bool value) {
    state = value;
  }
}
