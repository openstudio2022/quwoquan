import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/platform/platform_providers.dart';
import 'package:quwoquan_app/core/platform/platform_target.dart';

/// 欢迎页状态
///
/// 控制是否展示欢迎页。完成欢迎后设为 false，进入主框架。
final welcomeCompletedProvider =
    NotifierProvider<WelcomeCompletedNotifier, bool>(
      WelcomeCompletedNotifier.new,
    );

class WelcomeCompletedNotifier extends Notifier<bool> {
  @override
  bool build() => ref.read(platformTargetProvider) == AppPlatform.web;

  void setCompleted(bool value) {
    state = value;
  }
}
